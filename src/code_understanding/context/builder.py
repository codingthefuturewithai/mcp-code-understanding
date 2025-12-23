"""
RepoMap build management and background processing.
Following test_repo_map_simple.py's core RepoMap interaction patterns.
"""

import asyncio
import logging
import os
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

import tiktoken
from aider.io import InputOutput
from aider.repomap import RepoMap

from ..repository.cache import RepositoryCache, RepositoryMetadata
from ..repository.file_filtering import RepoFilter
from ..repository.path_utils import get_cache_path
from .extended_repo_map import UntruncatedRepoMap
from .extractor import RepoMapExtractor

logger = logging.getLogger(__name__)


class MinimalModel:
    """Minimal model implementation from test_repo_map_simple.py."""

    def token_count(self, text):
        # Rough approximation of token count
        return len(text.split()) * 1.3


class TiktokenModel:
    """Model implementation using tiktoken for exact GPT-2 token counts."""

    def __init__(self):
        # Initialize the GPT-2 encoder
        self.encoder = tiktoken.get_encoding("gpt2")

    def token_count(self, text):
        """
        Get exact token count using GPT-2 tokenizer.

        Args:
            text: Text to count tokens for

        Returns:
            Exact token count
        """
        return len(self.encoder.encode(text))


class MinimalIO(InputOutput):
    """Minimal IO implementation that prevents any stdout writes."""

    def __init__(self):
        super().__init__(pretty=False)

    def tool_output(self, text, **kwargs):
        """Override to prevent tool output to stdout"""
        pass

    def tool_error(self, text, **kwargs):
        """Override to prevent error output to stdout"""
        pass

    def prompt_for_input(self, prompt, **kwargs):
        """Override to prevent input prompts"""
        pass

    def prompt_for_yesno(self, prompt, default=None, **kwargs):
        """Override to prevent yes/no prompts"""
        return True

    def get_input(self, **kwargs):
        """Override to prevent input requests"""
        return ""

    def show_tool_output_command(self, command, output, returncode, **kwargs):
        """Override to prevent command output display"""
        pass

    def show_tool_error(self, command, output, returncode, **kwargs):
        """Override to prevent error display"""
        pass

    def info_message(self, msg, **kwargs):
        """Override to prevent info messages"""
        pass

    def warning_message(self, msg, **kwargs):
        """Override to prevent warning messages"""
        pass

    def error_message(self, msg, **kwargs):
        """Override to prevent error messages"""
        pass


class SubprocessManager:
    """Cross-platform subprocess handling."""

    async def run_command(self, cmd: List[str], **kwargs) -> str:
        """
        Execute command with proper encoding and error handling.
        Cross-platform compatible.
        """
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            **kwargs,
        )
        stdout, stderr = await proc.communicate()

        if proc.returncode != 0:
            raise RuntimeError(f"Command failed: {stderr.decode()}")

        return stdout.decode()

    async def start_background_process(self, cmd: List[str]) -> asyncio.Task:
        """
        Start long-running process that is:
        - Non-blocking
        - Monitored
        - Properly cleaned up
        """

        async def _run_and_monitor():
            proc = await asyncio.create_subprocess_exec(
                *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
            )
            await proc.wait()
            if proc.returncode != 0:
                raise RuntimeError(
                    f"Background process failed with code {proc.returncode}"
                )

        return asyncio.create_task(_run_and_monitor())


class RepoMapBuilder:
    """Manages RepoMap building process."""

    def __init__(self, cache: RepositoryCache):
        self.io = MinimalIO()
        # self.model = MinimalModel()
        self.model = TiktokenModel()
        self.cache = cache

    def _get_retry_guidance(self, file_count: int) -> Dict[str, Any]:
        """
        Get retry guidance based on file count.

        Args:
            file_count: Number of matching files

        Returns:
            Dictionary containing retry guidance with suggested wait time and context
        """
        if file_count < 100:
            category = "tiny"
            seconds = 5
        elif file_count < 1000:
            category = "small"
            seconds = 15
        elif file_count < 10000:
            category = "medium"
            seconds = 30
        else:
            category = "large"
            seconds = 60

        return {
            "suggested_retry_seconds": seconds,
            "size_context": f"{category.capitalize()} repository ({file_count} matching files), initial build in progress",
        }

    async def initialize_repo_map(
        self,
        root_dir: str,
        max_tokens: Optional[int] = None,
        is_full_build: bool = False,  # New parameter to indicate if this is a full build
    ) -> RepoMap:
        """
        Initialize RepoMap following core patterns from test_repo_map_simple.py.

        Args:
            root_dir: Repository root directory
            max_tokens: Maximum tokens for repo map output. Defaults to 1000000 if None.
            is_full_build: Whether this is a full build operation (initial or post-refresh)

        Returns:
            Initialized UntruncatedRepoMap instance
        """
        logger.debug(
            f"Initializing RepoMap for {root_dir} (max_tokens={max_tokens}, refresh={'always' if is_full_build else 'files'})"
        )
        rm = UntruncatedRepoMap(
            root=root_dir,
            io=self.io,
            main_model=self.model,
            map_tokens=max_tokens if max_tokens is not None else 1000000,
            refresh=(
                "always" if is_full_build else "files"
            ),  # Set based on operation type
            max_context_window=max_tokens if max_tokens is not None else 1000000,
        )
        return rm

    async def gather_files(self, root_dir: str) -> List[str]:
        """
        Gather all source files in the repository that match our criteria.
        Uses cache path directly - no Repository instance needed.
        """
        repo_filter = RepoFilter(Path(root_dir))
        files = repo_filter.find_source_files()
        logger.debug(f"Found {len(files)} files matching criteria in {root_dir}")
        return sorted(files)

    async def gather_files_targeted(
        self,
        root_dir: str,
        files: Optional[List[str]] = None,
        directories: Optional[List[str]] = None,
    ) -> List[str]:
        """
        Optimized file gathering.
        - If only `directories` are given, find all source files within them.
        - If only `files` are given, find all source files matching those names in the repo.
        - If BOTH are given, find all source files within the given `directories` that ALSO match the names in `files` (INTERSECTION).
        """
        repo_filter = RepoFilter(Path(root_dir))
        target_files = []

        # Case 1: Both directories and files are provided (INTERSECTION)
        if directories and files:
            logger.debug(
                f"Scanning specific directories for specific files (Intersection): dirs={directories}, files={files}"
            )
            # First, get all source files from the specified directories.
            files_in_dirs = repo_filter.find_source_files(directories)

            # Now, filter this list to include only the files that match the basenames in the `files` list.
            file_basenames_to_match = {os.path.basename(f) for f in files}

            for file_path in files_in_dirs:
                if os.path.basename(file_path) in file_basenames_to_match:
                    target_files.append(file_path)

        # Case 2: Only directories are provided
        elif directories:
            logger.debug(f"Scanning specific directories: {directories}")
            target_files.extend(repo_filter.find_source_files(directories))

        # Case 3: Only files are provided
        elif files:
            logger.debug(f"Searching for specific files globally: {files}")
            # This requires a full scan to find files by name.
            all_source_files = repo_filter.find_source_files()  # Scans the whole repo
            file_basenames_to_match = {os.path.basename(f) for f in files}

            for file_path in all_source_files:
                if os.path.basename(file_path) in file_basenames_to_match:
                    target_files.append(file_path)

        # Remove duplicates and sort
        target_files = list(dict.fromkeys(target_files))
        logger.debug(
            f"Found {len(target_files)} source files in specified paths within {root_dir}"
        )
        return sorted(target_files)

    async def _do_build(self, repo_path: str):
        """
        Internal method to perform the actual build.
        """
        try:
            logger.debug(f"Starting RepoMap build for {repo_path}")
            repo_map = await self.initialize_repo_map(
                repo_path, is_full_build=True
            )  # This is a full build
            files = await self.gather_files(repo_path)

            # Run CPU-intensive RepoMap generation in a thread pool
            output = await asyncio.to_thread(repo_map.get_ranked_tags_map, [], files)

            logger.debug(f"RepoMap generation complete for {repo_path}")

            # Update metadata with success status
            with self.cache._file_lock():
                metadata_dict = self.cache._read_metadata()
                if repo_path not in metadata_dict:
                    raise ValueError(f"Repository {repo_path} not found in cache")

                metadata = metadata_dict[repo_path]
                status = {
                    "status": "complete",
                    "completed_at": datetime.now().isoformat(),
                }
                metadata.repo_map_status = status
                self.cache._write_metadata(metadata_dict)

        except Exception as e:
            logger.error(f"Build failed for {repo_path}: {str(e)}")
            with self.cache._file_lock():
                metadata_dict = self.cache._read_metadata()
                if repo_path not in metadata_dict:
                    raise ValueError(f"Repository {repo_path} not found in cache")

                metadata = metadata_dict[repo_path]
                status = {
                    "status": "failed",
                    "completed_at": datetime.now().isoformat(),
                    "error": str(e),
                }
                metadata.repo_map_status = status
                self.cache._write_metadata(metadata_dict)
            raise

    async def start_build(self, repo_path: str) -> None:
        """Start building RepoMap for a repository."""
        logger.debug(f"Starting RepoMap build for {repo_path}")

        # Get repository metadata
        with self.cache._file_lock():
            metadata_dict = self.cache._read_metadata()
            if repo_path not in metadata_dict:
                raise ValueError(f"Repository {repo_path} not found in cache")

            metadata = metadata_dict[repo_path]

            # Get matching files count for retry guidance
            matching_files = len(await self.gather_files(repo_path))

            # Update build status
            metadata.repo_map_status = {
                "status": "building",
                "matching_files": matching_files,
                "message": "Building repository map for AI analysis",
            }
            self.cache._write_metadata(metadata_dict)

        # Start build process in background
        asyncio.create_task(self._do_build(repo_path))

    async def get_build_status(self, repo_path: str) -> dict:
        """Get current build status for a repository."""
        with self.cache._file_lock():
            metadata_dict = self.cache._read_metadata()
            if repo_path not in metadata_dict:
                raise ValueError(f"Repository {repo_path} not found in cache")

            metadata = metadata_dict[repo_path]
            if not metadata.repo_map_status:
                return {"status": "not_started"}

            return metadata.repo_map_status

    async def get_repo_map_content(
        self,
        repo_path: str,
        files: List[str] = None,
        directories: List[str] = None,
        max_tokens: int = None,
        max_files_threshold: int = None,
        branch: Optional[str] = None,
        cache_strategy: str = "shared",
    ) -> Dict[str, Any]:
        """
        Get repository map content if build is complete.
        Returns appropriate status/error messages otherwise.
        Token limiting is handled by Aider's RepoMap based on max_tokens parameter.
        Files exceeding max_files_threshold will return early with guidance.
        """
        DEFAULT_FILES_THRESHOLD = 5000

        cache_path = str(
            get_cache_path(
                self.cache.cache_dir,
                repo_path,
                branch if cache_strategy == "per-branch" else None,
                per_branch=(cache_strategy == "per-branch"),
            ).resolve()
        )
        logger.debug(
            f"Getting repo map content for {repo_path} (max_tokens={max_tokens})"
        )

        # Check status first without content generation
        with self.cache._file_lock():
            metadata_dict = self.cache._read_metadata()
            if cache_path not in metadata_dict:
                return {"status": "error", "error": "Repository not found in cache"}

            metadata = metadata_dict[cache_path]

            # Check clone status first
            clone_status = metadata.clone_status
            if not clone_status or clone_status["status"] != "complete":
                if clone_status and clone_status["status"] in ["cloning", "copying"]:
                    return {
                        "status": "waiting",
                        "message": f"Repository clone is in progress. Please try again later.",
                        "retry_guidance": {
                            "suggested_retry_seconds": 30,  # Conservative default during clone
                            "size_context": "Repository clone in progress, size unknown",
                        },
                    }
                else:
                    return {
                        "status": "error",
                        "error": f"Repository has not been cloned. Please clone it first using clone_repo with URL: {repo_path}",
                    }

            # Then check repo map status
            if not metadata.repo_map_status:
                return {
                    "status": "error",
                    "error": "Repository map build has not been started",
                }

            if metadata.repo_map_status["status"] == "building":
                matching_files = metadata.repo_map_status.get("matching_files", 0)
                return {
                    "status": "building",
                    "message": "Repository map is being built",
                    "retry_guidance": self._get_retry_guidance(matching_files),
                }
            elif metadata.repo_map_status["status"] != "complete":
                return {
                    "status": "error",
                    "error": f"Repository map build failed or unknown status: {metadata.repo_map_status['status']}",
                }

        # Only proceed with content generation if both clone and build are complete
        try:
            repo_map = await self.initialize_repo_map(cache_path, max_tokens)

            # DEBUG: Log the actual parameters received
            logger.debug(f"[FILTERING DEBUG] files parameter: {files}")
            logger.debug(f"[FILTERING DEBUG] directories parameter: {directories}")
            logger.debug(
                f"[FILTERING DEBUG] files and directories after filtering empty: files={files if files else None}, directories={directories if directories else None}"
            )

            # Filter out empty arrays - treat them as None
            effective_files = files if files else None
            effective_directories = directories if directories else None
            logger.debug(
                f"[FILTERING DEBUG] effective filtering condition: {bool(effective_files or effective_directories)}"
            )

            # Use optimized gathering if specific files/directories are provided
            if effective_files or effective_directories:
                target_files = await self.gather_files_targeted(
                    cache_path, files=files, directories=directories
                )
            else:
                # Fall back to full repository scan if no specific paths provided
                target_files = await self.gather_files(cache_path)

            logger.debug(f"Processing {len(target_files)} files")

            # SAFETY GUARD: If there are no target files after filtering/intersection,
            # return a benign success payload rather than attempting to build a map.
            # Some upstream implementations divide by the number of files when
            # computing weights, which can raise a ZeroDivisionError for empty sets.
            if not target_files:
                logger.info(
                    "No matching source files after applying filters; returning empty map content"
                )
                # Try to include current branch if available
                current_branch = None
                try:
                    repo_status = await self.cache.get_repository_status(cache_path)
                    if repo_status:
                        current_branch = repo_status.get("current_branch")
                except Exception:
                    pass

                return {
                    "status": "success",
                    "content": "",
                    "metadata": {
                        "excluded_files_by_dir": {},
                        "is_complete": True,
                        "max_tokens": max_tokens,
                        "output_tokens": 0,
                        "branch": current_branch,
                        "cache_strategy": cache_strategy,
                        "message": "No matching files for provided filters",
                    },
                }

            # Check against threshold before proceeding
            file_count = len(target_files)
            effective_threshold = max_files_threshold or DEFAULT_FILES_THRESHOLD
            if file_count > effective_threshold:
                return {
                    "status": "threshold_exceeded",
                    "message": "Number of matching files exceeds processing threshold",
                    "metadata": {
                        "matching_files": file_count,
                        "threshold": effective_threshold,
                        "size_context": f"Large repository ({file_count} matching files)",
                        "override_guidance": "You have several options: 1) Use 'files' or 'directories' parameters to analyze a smaller subset of the codebase, 2) Increase max_files_threshold AND ensure your client timeout is sufficient",
                    },
                }

            # Save complete list before filtering
            all_target_files = target_files.copy()

            # Generate map and process results
            content = repo_map.get_ranked_tags_map([], target_files)

            # Debug output - commented out to avoid file system issues
            # with open("raw_repomap_output.txt", "w", encoding="utf-8") as f:
            #     f.write(str(repo_map))

            output_tokens = self.model.token_count(content)
            logger.debug(f"Generated map size: {output_tokens} tokens")

            # Process excluded files
            extractor = RepoMapExtractor()
            included_files = await extractor.extract_files(content)
            normalized_included_files = {os.path.normpath(f) for f in included_files}

            # Convert and normalize ALL original files for comparison
            all_relative_target_files = {
                os.path.normpath(str(Path(f).relative_to(cache_path)))
                for f in all_target_files
            }

            # Compare against ALL files, not just filtered ones
            excluded_files = all_relative_target_files - normalized_included_files

            if excluded_files:
                logger.debug(f"Excluded {len(excluded_files)} files")

            # Group excluded files by directory
            excluded_by_dir = {}
            for rel_file in excluded_files:
                abs_file = os.path.join(cache_path, rel_file)
                dir_path = str(Path(abs_file).parent)
                excluded_by_dir[dir_path] = excluded_by_dir.get(dir_path, 0) + 1

            # Get current branch information
            current_branch = None
            try:
                repo_status = await self.cache.get_repository_status(cache_path)
                if repo_status:
                    current_branch = repo_status.get("current_branch")
            except Exception:
                pass  # Continue without branch info if we can't get it

            return {
                "status": "success",
                "content": content,
                "metadata": {
                    "excluded_files_by_dir": excluded_by_dir,
                    "is_complete": len(excluded_files) == 0,
                    "max_tokens": max_tokens,
                    "output_tokens": output_tokens,
                    "branch": current_branch,
                    "cache_strategy": cache_strategy,
                },
            }
        except Exception as e:
            return {
                "status": "error",
                "error": f"Failed to generate repository map: {str(e)}",
            }

    async def get_repo_structure(
        self,
        repo_path: str,
        directories: List[str] = None,
        include_files: bool = False,
        branch: Optional[str] = None,
        cache_strategy: str = "shared",
    ) -> Dict[str, Any]:
        """
        Get repository structure information with optional file listings.

        Args:
            repo_path: Path/URL matching what was provided to clone_repo
            directories: Optional list of directories to limit results to
            include_files: Whether to include list of files in response

        Returns:
            dict: Repository structure information with format:
                {
                    "status": str,
                    "message": str, # (for error/waiting only)
                    "directories": [{
                        "path": str,
                        "analyzable_files": int,
                        "extensions": {
                            "py": 10,
                            "java": 5,
                            "ts": 3
                        },
                        "files": [str]  # Only present if include_files=True
                    }],
                    "total_analyzable_files": int
                }
        """
        # Convert repo_path to absolute cache path
        cache_path = str(
            get_cache_path(
                self.cache.cache_dir,
                repo_path,
                branch if cache_strategy == "per-branch" else None,
                per_branch=(cache_strategy == "per-branch"),
            ).resolve()
        )
        logger.debug(f"Getting repo structure for {repo_path}")

        # Check repository status, similar to get_repo_map_content but only checking clone status
        with self.cache._file_lock():
            metadata_dict = self.cache._read_metadata()
            if cache_path not in metadata_dict:
                return {"status": "error", "error": "Repository not found in cache"}

            metadata = metadata_dict[cache_path]

            # Check clone status only - unlike get_repo_map_content, we don't need to wait
            # for repo map build to complete
            clone_status = metadata.clone_status
            if not clone_status or clone_status["status"] != "complete":
                if clone_status and clone_status["status"] in ["cloning", "copying"]:
                    return {
                        "status": "waiting",
                        "message": f"Repository clone is in progress. Please try again later.",
                    }
                else:
                    return {
                        "status": "error",
                        "error": f"Repository has not been cloned. Please clone it first using clone_repo with URL: {repo_path}",
                    }

        # Directory Scanning Setup
        try:
            # Use exactly the same file filtering logic as get_repo_map_content
            if directories:
                # Targeted directory scanning with the same filters
                target_files = await self.gather_files_targeted(
                    cache_path, files=None, directories=directories
                )
            else:
                # Full repository scan with the same filters
                target_files = await self.gather_files(cache_path)

            logger.debug(
                f"Found {len(target_files)} analyzable files for structure analysis"
            )

            # File Analysis
            # Initialize structures to track directory data
            directory_data = {}
            total_analyzable_files = 0

            # Process each file
            for file_path in target_files:
                # Convert to path relative to repository root
                rel_path = os.path.normpath(
                    str(Path(file_path).relative_to(cache_path))
                )

                # Extract directory and filename
                dir_path = os.path.dirname(rel_path)
                if dir_path == "":
                    dir_path = "."  # Root directory

                # Extract extension without dot
                _, ext = os.path.splitext(rel_path)
                ext = ext[1:] if ext.startswith(".") else ext

                # Initialize directory data if not exists
                if dir_path not in directory_data:
                    directory_data[dir_path] = {
                        "path": dir_path,
                        "analyzable_files": 0,
                        "extensions": {},
                        "files": [] if include_files else None,
                    }

                # Update counters
                directory_data[dir_path]["analyzable_files"] += 1
                if ext:
                    directory_data[dir_path]["extensions"][ext] = (
                        directory_data[dir_path]["extensions"].get(ext, 0) + 1
                    )

                # Optional File Listing
                # Store full relative path (not just basename) if include_files is True
                if include_files and directory_data[dir_path]["files"] is not None:
                    # Store the full relative path, ensuring format matches get_source_repo_map
                    directory_data[dir_path]["files"].append(rel_path)

                # Update total count
                total_analyzable_files += 1

            logger.debug(
                f"Analyzed {total_analyzable_files} files across {len(directory_data)} directories"
            )

            # Response Building
            # Transform directory_data into response format
            directories_list = []
            for dir_path, dir_info in sorted(directory_data.items()):
                directory_entry = {
                    "path": dir_info["path"],
                    "analyzable_files": dir_info["analyzable_files"],
                    "extensions": dir_info["extensions"],
                }

                # Add files list only if include_files was True and files were collected
                if include_files and dir_info["files"] is not None:
                    directory_entry["files"] = sorted(dir_info["files"])

                directories_list.append(directory_entry)

            # Build final response
            return {
                "status": "success",
                "directories": directories_list,
                "total_analyzable_files": total_analyzable_files,
            }

        except Exception as e:
            logger.error(
                f"Error during repository structure analysis: {e}", exc_info=True
            )
            return {
                "status": "error",
                "error": f"Failed to analyze repository structure: {str(e)}",
            }
