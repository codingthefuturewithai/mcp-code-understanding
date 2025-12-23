import asyncio
import concurrent.futures
import logging
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

import lizard

logger = logging.getLogger("code_understanding.analysis.complexity")


def _run_lizard_analysis(
    valid_files: List[str], num_threads: int
) -> List[lizard.FileInformation]:
    """
    Helper function to run lizard analysis in a separate process.
    This prevents the synchronous, multi-threaded CPU-bound task from
    blocking the main asyncio event loop of the server.
    """
    logger.debug(
        f"Running lizard analysis on {len(valid_files)} files with {num_threads} threads in a separate process."
    )
    # lizard.analyze_files returns an iterator, so we convert it to a list
    # to ensure the analysis is complete before returning from the process.
    return list(lizard.analyze_files(valid_files, threads=num_threads))


class CodeComplexityAnalyzer:
    def __init__(self, repo_manager, repo_map_builder):
        self.repo_manager = repo_manager
        self.repo_map_builder = repo_map_builder

    async def analyze_repo_critical_files(
        self,
        repo_path: str,
        files: Optional[List[str]] = None,
        directories: Optional[List[str]] = None,
        limit: int = 50,
        include_metrics: bool = True,
        branch: Optional[str] = None,
        cache_strategy: str = "shared",
    ) -> Dict[str, Any]:
        """
        Analyze repository to identify critical files based on complexity metrics.

        Args:
            repo_path: Path/URL matching what was provided to clone_repo
            files: Optional list of specific files to analyze
            directories: Optional list of specific directories to analyze
            limit: Maximum number of files to return (default: 50)
            include_metrics: Include detailed metrics in response (default: True)
            branch: Optional branch to analyze (defaults to current branch)
            cache_strategy: Cache strategy to use ("shared" or "per-branch")

        Returns:
            dict: Response with analysis results or error information
        """
        logger.info(f"Starting analysis of critical files for repo: {repo_path}")

        # Repository Status Validation - MODIFIED TO AVOID get_repository CALL
        try:
            # Calculate cache path directly instead of using get_repository
            from ..repository.path_utils import get_cache_path

            # Resolve cache path consistent with server conventions.
            # Only include branch in the cache path if the strategy is per-branch.
            cache_path = get_cache_path(
                self.repo_manager.cache_dir,
                repo_path,
                branch if cache_strategy == "per-branch" else None,
                per_branch=(cache_strategy == "per-branch"),
            )

            # Check if repository exists in the filesystem
            if not cache_path.exists():
                logger.error(f"Repository not found in cache: {repo_path}")
                return {
                    "status": "error",
                    "error": f"Repository not found in cache. Please clone it first using clone_repo with URL: {repo_path}",
                }

            # Get the absolute path as string (what we previously got from repo.root_path.resolve())
            cache_path_str = str(cache_path.resolve())

            # Check if repository is in metadata and validate clone status
            with self.repo_manager.cache._file_lock():
                metadata_dict = self.repo_manager.cache._read_metadata()
                if cache_path_str not in metadata_dict:
                    logger.error(f"Repository not found in cache metadata: {repo_path}")
                    return {
                        "status": "error",
                        "error": f"Repository not found in cache. Please clone it first using clone_repo with URL: {repo_path}",
                    }

                metadata = metadata_dict[cache_path_str]
                clone_status = metadata.clone_status
                if not clone_status or clone_status["status"] != "complete":
                    status_label = (
                        clone_status["status"] if clone_status else "not_started"
                    )
                    logger.info(
                        f"Repository clone is not complete: {repo_path}, status: {status_label}"
                    )
                    if clone_status and clone_status["status"] in (
                        "cloning",
                        "copying",
                    ):
                        return {
                            "status": "waiting",
                            "message": "Repository clone is in progress. Please try again later.",
                        }
                    return {
                        "status": "error",
                        "error": f"Repository has not been cloned. Please clone it first using clone_repo with URL: {repo_path}",
                    }

            # Log success
            logger.debug(f"Repository validation successful for {repo_path}")

        except KeyError:
            # Repository not found in cache
            logger.error(f"Repository not found in cache: {repo_path}")
            return {
                "status": "error",
                "error": f"Repository not found. Please clone it first using clone_repo with URL: {repo_path}",
            }
        except ValueError as e:
            # Repository path is invalid
            logger.error(f"Invalid repository path: {repo_path}. Error: {str(e)}")
            return {"status": "error", "error": f"Invalid repository path: {str(e)}"}
        except Exception as e:
            # Other repository-related errors
            logger.error(
                f"Error accessing repository {repo_path}: {str(e)}", exc_info=True
            )

            # Check if this is a "clone in progress" situation
            if "clone in progress" in str(e).lower():
                return {
                    "status": "waiting",
                    "message": f"Repository clone is in progress. Please try again later.",
                }

            return {"status": "error", "error": f"Repository error: {str(e)}"}

        # File Selection Strategy - MODIFIED TO USE cache_path DIRECTLY
        try:
            # Use existing RepoMapBuilder methods with the cache path
            if files or directories:
                # Use targeted file selection when specific paths are provided
                target_files = await self.repo_map_builder.gather_files_targeted(
                    str(cache_path),  # Use cache_path directly
                    files=files,
                    directories=directories,
                )
            else:
                # Fall back to full repository scan if no specific paths provided
                target_files = await self.repo_map_builder.gather_files(
                    str(cache_path)
                )  # Use cache_path directly

            # Check if we have files to analyze
            if not target_files:
                logger.info(
                    f"No matching source files found in {repo_path} with specified criteria"
                )
                return {
                    "status": "success",
                    "files": [],
                    "total_files_analyzed": 0,
                    "files_with_analysis": 0,
                    "files_without_analysis": 0,
                    "results_truncated": False,
                }

            logger.info(f"Selected {len(target_files)} files for complexity analysis")

        except Exception as e:
            logger.error(f"Error during file selection: {str(e)}", exc_info=True)
            return {
                "status": "error",
                "error": f"Failed to gather target files: {str(e)}",
            }

        # Complexity Analysis Integration - MODIFIED TO USE cache_path DIRECTLY
        try:
            # Prepare result structures
            original_results = []
            files_with_analysis = 0

            # Use our cache path directly
            repo_root = Path(cache_path)  # No need for str(repo.root_path)

            # Create a list of valid file paths (string paths, not Path objects)
            valid_files = []
            for file_path in target_files:
                file_path_obj = Path(file_path)
                if file_path_obj.is_file():
                    valid_files.append(str(file_path_obj))

            # Use lizard's batch analyze_files method with an appropriate thread count
            # Number of threads can be adjusted based on system resources and file count
            num_threads = min(
                os.cpu_count() or 4, 8
            )  # Use at most 8 threads, or fewer if CPU count is lower
            logger.debug(
                f"Analyzing {len(valid_files)} files using {num_threads} threads via ProcessPoolExecutor"
            )

            # Get the current asyncio event loop
            loop = asyncio.get_running_loop()

            # Run the synchronous, multi-threaded lizard analysis in a separate process
            # to avoid blocking the asyncio event loop.
            with concurrent.futures.ProcessPoolExecutor() as pool:
                file_analyses = await loop.run_in_executor(
                    pool, _run_lizard_analysis, valid_files, num_threads
                )

            # NOTE: Lizard will silently skip files that it cannot process (no parser available)
            # or files that don't contain any functions. These will not appear in the returned
            # file_analyses, and there's no direct way to determine which files were skipped.

            # Process each file analysis
            for file_analysis in file_analyses:
                try:
                    file_path = file_analysis.filename

                    # Skip files with no functions
                    if not file_analysis.function_list:
                        continue

                    # Calculate metrics
                    total_ccn = sum(
                        f.cyclomatic_complexity for f in file_analysis.function_list
                    )
                    max_ccn = max(
                        (f.cyclomatic_complexity for f in file_analysis.function_list),
                        default=0,
                    )
                    function_count = len(file_analysis.function_list)
                    nloc = file_analysis.nloc

                    # Calculate importance score
                    score = self.calculate_importance_score(
                        function_count, total_ccn, max_ccn, nloc
                    )

                    # Convert absolute path to repository-relative path in OS-agnostic way
                    # Using os.path.relpath for cross-platform compatibility
                    relative_path = os.path.relpath(file_path, str(repo_root))

                    # Create result entry
                    result_entry = {
                        "path": relative_path,
                        "importance_score": round(score, 2),
                    }

                    # Add metrics if requested
                    if include_metrics:
                        result_entry["metrics"] = {
                            "total_ccn": total_ccn,
                            "max_ccn": max_ccn,
                            "function_count": function_count,
                            "nloc": nloc,
                        }

                    original_results.append(result_entry)
                    files_with_analysis += 1

                except Exception as e:
                    logger.warning(
                        f"Error processing analysis for file {file_path}: {str(e)}"
                    )
                    continue

            # Calculate files without analysis
            files_without_analysis = len(valid_files) - files_with_analysis

            # Sort results by importance score in descending order
            original_results.sort(key=lambda x: x["importance_score"], reverse=True)

            # Determine if results were truncated and apply limit
            results_truncated = limit > 0 and len(original_results) > limit
            limited_results = (
                original_results[:limit] if limit > 0 else original_results
            )

            # Return formatted response with new fields
            return {
                "status": "success",
                "files": limited_results,
                "total_files_analyzed": len(valid_files),
                "files_with_analysis": files_with_analysis,
                "files_without_analysis": files_without_analysis,
                "results_truncated": results_truncated,
            }

        except Exception as e:
            logger.error(f"Error during complexity analysis: {str(e)}", exc_info=True)
            return {
                "status": "error",
                "error": f"Failed to analyze file complexity: {str(e)}",
            }

    def calculate_importance_score(self, function_count, total_ccn, max_ccn, nloc):
        """Calculate importance score using the weighted formula."""
        return (
            (2.0 * function_count) + (1.5 * total_ccn) + (1.2 * max_ccn) + (0.05 * nloc)
        )
