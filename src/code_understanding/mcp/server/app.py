"""
Core MCP server implementation using FastMCP.
"""

import asyncio
import json
import logging
import sys
from pathlib import Path
from typing import List, Optional

import click
from mcp.server.fastmcp import FastMCP

from code_understanding.config import ServerConfig, load_config
from code_understanding.context.builder import RepoMapBuilder
from code_understanding.repository import RepositoryManager
from code_understanding.repository.documentation import get_repository_documentation

# Configure logging
logging.basicConfig(
    stream=sys.stderr,
    level=logging.DEBUG,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger("code_understanding.mcp")


_INSTRUCTIONS_PATH = Path(__file__).parent / "server_instructions.txt"
_SERVER_INSTRUCTIONS = (
    _INSTRUCTIONS_PATH.read_text(encoding="utf-8")
    if _INSTRUCTIONS_PATH.exists()
    else None
)


def create_mcp_server(config: ServerConfig = None) -> FastMCP:
    """Create and configure the MCP server instance"""
    if config is None:
        config = load_config()

    server = FastMCP(name=config.name, instructions=_SERVER_INSTRUCTIONS)

    # Initialize core components
    repo_manager = RepositoryManager(config.repository)
    repo_map_builder = RepoMapBuilder(cache=repo_manager.cache)

    # Register tools
    register_tools(server, repo_manager, repo_map_builder)

    return server


def register_tools(
    mcp_server: FastMCP,
    repo_manager: RepositoryManager,
    repo_map_builder: RepoMapBuilder,
) -> None:
    """Register all MCP tools with the server."""

    @mcp_server.tool(name="get_repo_file_content")
    async def get_repo_file_content(
        repo_path: str,
        resource_path: Optional[str] = None,
        branch: Optional[str] = None,
        cache_strategy: str = "shared",
    ) -> dict:
        """
        Retrieve file contents or directory listings from a repository.

        Args:
            repo_path (str): Path or URL to the repository
            resource_path (str, optional): Path to the target file or directory within the repository. Defaults to the repository root if not provided.
            branch (str, optional): Specific branch to read from (only used with per-branch cache strategy)
            cache_strategy (str, optional): Cache strategy - "shared" (default) or "per-branch"

        Returns:
            dict: For files:
                {
                    "type": "file",
                    "path": str,  # Relative path within repository
                    "content": str,  # Complete file contents
                    "branch": str,  # Current branch name
                    "cache_strategy": str  # Cache strategy used
                }
                For directories:
                {
                    "type": "directory",
                    "path": str,  # Relative path within repository
                    "contents": List[str],  # List of immediate files and subdirectories
                    "branch": str,  # Current branch name
                    "cache_strategy": str  # Cache strategy used
                }

        Note:
            Directory listings are not recursive - they only show immediate contents.
            To explore subdirectories, make additional calls with the subdirectory path.
        """
        try:
            if resource_path is None:
                resource_path = "."

            # Check metadata.json to ensure repository is cloned and ready
            from code_understanding.repository.path_utils import get_cache_path

            cache_path = get_cache_path(
                repo_manager.cache_dir,
                repo_path,
                branch if cache_strategy == "per-branch" else None,
                per_branch=(cache_strategy == "per-branch"),
            )
            str_path = str(cache_path.resolve())

            repo_status = await repo_manager.cache.get_repository_status(str_path)
            if not repo_status or "clone_status" not in repo_status:
                return {
                    "status": "error",
                    "error": "Repository not found. Please clone it first using clone_repo.",
                }

            clone_status = repo_status["clone_status"]
            if not clone_status:
                return {
                    "status": "error",
                    "error": "Repository not cloned. Please clone it first using clone_repo.",
                }
            elif clone_status.get("status") in ["cloning", "copying"]:
                return {
                    "status": "error",
                    "error": "Repository clone still in progress. Please wait for clone to complete.",
                }
            elif clone_status.get("status") != "complete":
                return {
                    "status": "error",
                    "error": "Repository clone failed or incomplete. Please try cloning again.",
                }

            # Clone is complete, create repository instance with correct cache path
            from code_understanding.repository.manager import Repository

            repository = Repository(
                repo_id=str_path, root_path=str_path, repo_type="git", is_git=True
            )
            result = await repository.get_resource(resource_path)

            # Add branch and cache strategy information to response
            if isinstance(result, dict) and "type" in result:
                result["branch"] = repo_status.get("current_branch")
                result["cache_strategy"] = cache_strategy

            return result
        except Exception as e:
            logger.error(f"Error getting resource: {e}", exc_info=True)
            return {"status": "error", "error": str(e)}

    @mcp_server.tool(name="refresh_repo")
    async def refresh_repo(
        repo_path: str, branch: Optional[str] = None, cache_strategy: str = "shared"
    ) -> dict:
        """
        Update a previously cloned repository in MCP's cache and refresh its analysis.

        CRITICAL: Cached repositories become stale over time. ALWAYS refresh before analysis
        to ensure you're working with the latest code. Failure to refresh means your analysis
        may be based on outdated code that could be days, weeks, or months old.

        For Git repositories, performs a git pull to get latest changes.
        For local directories, copies the latest content from the source.
        Then triggers a new repository map build to ensure all analysis is based on
        the updated code.

        RECOMMENDED WORKFLOW:
            1. Check if repository is cached: list_cached_repository_branches(url)
            2. If cached, ALWAYS refresh first: refresh_repo(url)
            3. Wait a moment for refresh to complete
            4. Then perform analysis: get_source_repo_map(url, ...)

            This ensures your analysis reflects current code, not stale cached data.

        Args:
            repo_path (str): Path or URL matching what was originally provided to clone_repo
            branch (str, optional): Specific branch to switch to during refresh
            cache_strategy (str, optional): Cache strategy - must match original clone strategy

        Returns:
            dict: Response with format:
                {
                    "status": str,  # "pending", "switched_branch", "error"
                    "path": str,    # (On pending) Cache location being refreshed
                    "message": str, # (On pending) Status message
                    "error": str    # (On error) Error message
                    "cache_strategy": str  # Strategy used for caching
                }

        Note:
            - Repository must be previously cloned and have completed initial analysis
            - Updates MCP's cached copy, does not modify the source repository
            - Automatically triggers rebuild of repository map with updated files
            - If branch is specified, switches to that branch after pulling latest changes
            - cache_strategy should match the strategy used during original clone
            - Operation runs in background, check get_repo_map_content for status
        """
        try:
            # Validate cache_strategy
            if cache_strategy not in ["shared", "per-branch"]:
                return {
                    "status": "error",
                    "error": "cache_strategy must be 'shared' or 'per-branch'",
                }

            return await repo_manager.refresh_repository(
                repo_path, branch, cache_strategy
            )
        except Exception as e:
            logger.error(f"Error refreshing repository: {e}", exc_info=True)
            return {"status": "error", "error": str(e)}

    @mcp_server.tool(name="list_cached_repository_branches")
    async def list_cached_repository_branches(repo_url: str) -> dict:
        """
        Check if a repository is already cached and list all cached branch versions.

        USE THIS FIRST before calling clone_repo to avoid redundant clone attempts.
        If the repository is already cached, you can proceed directly to refresh_repo
        and analysis instead of cloning again.

        This tool scans the MCP cache to find all entries for a given repository URL,
        showing both shared and per-branch cache entries. Useful for understanding
        what branches are available and their current status.

        Args:
            repo_url (str): Repository URL to search for (must match exact URL used in clone_repo)

        Returns:
            dict: Response with format:
                {
                    "status": "success" | "error",
                    "repo_url": str,  # Repository URL searched
                    "cached_branches": [  # List of cached branch entries (empty if not cached)
                        {
                            "requested_branch": str,  # Branch that was requested during clone
                            "current_branch": str,    # Current active branch in the cache
                            "cache_path": str,        # File system path to cached repository
                            "cache_strategy": str,    # "shared" or "per-branch"
                            "last_access": str,       # ISO timestamp of last access
                            "clone_status": dict,     # Clone operation status
                            "repo_map_status": dict   # Repository map build status
                        }
                    ],
                    "total_cached": int  # Total number of cached entries (0 if not cached)
                }

        Typical Workflow:
            1. Check cache first: result = list_cached_repository_branches(url)
            2. If result["total_cached"] > 0:
               - Repository is cached, skip clone
               - Use refresh_repo(url) to update cached code
            3. If result["total_cached"] == 0:
               - Repository not cached yet
               - Use list_remote_branches(url) to discover branch names
               - Use clone_repo(url, branch=correct_branch)

        Note:
            - Only returns repositories that have been cloned via clone_repo
            - Empty cached_branches list means repository is NOT cached
            - Useful for PR review workflows to see all available branch versions
            - Shows both active and completed cache entries
            - Helps identify which cache strategy was used for each entry
        """
        try:
            return await repo_manager.list_repository_branches(repo_url)
        except Exception as e:
            logger.error(
                f"Error listing cached repository branches: {e}", exc_info=True
            )
            return {"status": "error", "error": str(e)}

    # Backward-compat alias (deprecated)
    @mcp_server.tool(name="list_repository_branches")
    async def list_repository_branches(repo_url: str) -> dict:  # noqa: F811
        try:
            return await repo_manager.list_repository_branches(repo_url)
        except Exception as e:
            logger.error(
                f"Error listing cached repository branches: {e}", exc_info=True
            )
            return {"status": "error", "error": str(e)}

    @mcp_server.tool(name="list_remote_branches")
    async def list_remote_branches(repo_url: str) -> dict:
        """
        Discover all available branches in a remote repository without cloning.

        CRITICAL USE CASE: Many repositories use "master", "develop", or other names instead
        of "main" as their default branch. Use this tool BEFORE clone_repo to discover the
        actual default branch name and avoid clone failures.

        This tool uses git ls-remote --heads to query the remote repository, which is fast
        and does not require cloning the entire repository.

        Args:
            repo_url (str): Remote repository URL (e.g., https://github.com/user/repo)

        Returns:
            dict: Response with format:
                {
                    "status": "success" | "error",
                    "repo_url": str,  # Repository URL queried
                    "remote_branches": [str],  # List of branch names (e.g., ["main", "develop", "feature-x"])
                    "total_remote": int,  # Total number of branches found
                    "error": str  # (Only on error) Error message
                }

        Common Default Branch Names to Look For:
            - "main" (modern GitHub default)
            - "master" (traditional Git default)
            - "develop" or "development" (common for dev workflows)
            - Check repository documentation if unclear

        Typical Workflow:
            1. Discover branches: branches = list_remote_branches(url)
            2. Identify default branch from branches["remote_branches"]
               - Look for "main", "master", or "develop"
               - If unsure, check the repository's web page
            3. Clone with correct branch: clone_repo(url, branch=identified_branch)

        Note:
            - Fast operation, does not clone the repository
            - Requires network access to the remote repository
            - Works with any Git repository (GitHub, GitLab, Bitbucket, etc.)
        """
        try:
            return await repo_manager.list_remote_branches(repo_url)
        except Exception as e:
            logger.error(f"Error listing remote branches: {e}", exc_info=True)
            return {"status": "error", "error": str(e)}

    @mcp_server.tool(name="clone_repo")
    async def clone_repo(
        url: str, branch: Optional[str] = None, cache_strategy: str = "shared"
    ) -> dict:
        """
        Clone a repository into MCP server's cache and prepare it for analysis.

        This tool must be called before using analysis endpoints like get_source_repo_map
        or get_repo_documentation. It copies the repository into MCP's cache and
        automatically starts building a repository map in the background.

        IMPORTANT - BEFORE CLONING:
            1. CHECK IF ALREADY CACHED: Use list_cached_repository_branches(url) first to avoid
               redundant clone attempts. Returns empty list if not cached, or existing branches if cached.

            2. VERIFY DEFAULT BRANCH NAME: Many repositories use "master", "develop", or other names
               instead of "main". If branch is not specified and clone fails:
               - Use list_remote_branches(url) to discover available branches
               - Look for "main", "master", "develop", or check repo documentation
               - Explicitly specify the correct branch parameter

            3. AFTER CLONING: The cached repository can become stale over time. Before analysis,
               consider using refresh_repo() to ensure you're working with the latest code.

        Args:
            url (str): URL of remote repository or path to local repository to analyze
            branch (str, optional): Specific branch to clone for analysis. Defaults to "main" if not
                specified, but many repositories use "master" or other names - verify first!
            cache_strategy (str, optional): Cache strategy - "shared" (default) or "per-branch"
                - "shared": One cache entry per repo, switch branches in place
                - "per-branch": Separate cache entries for each branch (useful for PR reviews)

        Returns:
            dict: Response with format:
                {
                    "status": "pending" | "already_cloned" | "switched_branch" | "error",
                    "path": str,  # Cache location where repo is being cloned
                    "message": str,  # Status message about clone and analysis
                    "cache_strategy": str,  # Strategy used for caching
                    "current_branch": str,  # (if applicable) Current active branch
                    "previous_branch": str,  # (if switched) Previous branch name
                }

        Recommended Workflow:
            1. Check cache: cached = list_cached_repository_branches(url)
            2. If not cached, discover branches: branches = list_remote_branches(url)
            3. Clone with correct branch: clone_repo(url, branch=discovered_branch)
            4. Before analysis, refresh if needed: refresh_repo(url)
            5. Perform analysis: get_source_repo_map(url, ...)

        Note:
            - This is a setup operation for MCP analysis only
            - Does not modify the source repository
            - Repository map building starts automatically after clone completes
            - Use get_source_repo_map to check analysis status and retrieve results
            - Per-branch strategy allows simultaneous access to different branches
        """
        try:
            # Default branch to "main" if not provided
            if branch is None:
                branch = "main"

            # Validate cache_strategy
            if cache_strategy not in ["shared", "per-branch"]:
                return {
                    "status": "error",
                    "error": "cache_strategy must be 'shared' or 'per-branch'",
                }

            # Repository clone with new dual cache strategy support
            logger.debug(
                f"[TRACE] clone_repo: Starting clone_repository for {url} with branch {branch} using {cache_strategy} strategy"
            )
            result = await repo_manager.clone_repository(url, branch, cache_strategy)
            logger.debug(f"[TRACE] clone_repo: clone_repository completed for {url}")
            return result
        except Exception as e:
            logger.error(f"Error cloning repository: {e}", exc_info=True)
            return {"status": "error", "error": str(e)}

    @mcp_server.tool(name="get_source_repo_map")
    async def get_source_repo_map(
        repo_path: str,
        directories: List[str] = [],
        files: List[str] = [],
        max_tokens: int = 20000,
        branch: str = "",
        cache_strategy: str = "shared",
    ) -> dict:
        """
        Retrieve a semantic analysis map of the repository's code structure.

        Returns a detailed map of the repository's structure, including file hierarchy,
        code elements (functions, classes, methods), and their relationships. Can analyze
        specific files/directories or the entire repository.

        Args:
            repo_path (str): Path or URL matching what was originally provided to clone_repo
            files (List[str], optional): Specific files to analyze. If None, analyzes all files
            directories (List[str], optional): Specific directories to analyze. If None, analyzes all directories
            max_tokens (int, optional): Limit total tokens in analysis. Useful for large repositories
            branch (str, optional): Specific branch to analyze (only used with per-branch cache strategy)
            cache_strategy (str, optional): Cache strategy - "shared" (default) or "per-branch"

        Returns:
            dict: Response with format:
                {
                    "status": str,  # "success", "building", "waiting", or "error"
                    "content": str,  # Hierarchical representation of code structure
                    "metadata": {    # Analysis metadata
                        "excluded_files_by_dir": dict,
                        "is_complete": bool,
                        "max_tokens": int
                    },
                    "message": str,  # Present for "building"/"waiting" status
                    "error": str     # Present for "error" status
                }

        Note:
            - Repository must be previously cloned using clone_repo
            - Initial analysis happens in background after clone
            - Returns "building" status while analysis is in progress
            - Content includes file structure, code elements, and their relationships
            - For large repos, consider using max_tokens or targeting specific directories
        """
        try:
            # Convert empty lists to None for backend compatibility
            directories_list = directories if directories else None
            files_list = files if files else None
            branch_opt = branch or None

            return await repo_map_builder.get_repo_map_content(
                repo_path,
                files=files_list,
                directories=directories_list,
                max_tokens=max_tokens,
                branch=branch_opt,
                cache_strategy=cache_strategy,
            )
        except Exception as e:
            logger.error(f"Error getting context: {e}", exc_info=True)
            return {
                "status": "error",
                "error": f"Unexpected error while getting repository context: {str(e)}",
            }

    @mcp_server.tool(name="get_repo_structure")
    async def get_repo_structure(
        repo_path: str,
        directories: List[str] = [],
        include_files: bool = False,
        branch: str = "",
        cache_strategy: str = "shared",
    ) -> dict:
        """
        Get repository structure information with optional file listings.

        Args:
            repo_path: Path/URL matching what was provided to clone_repo
            directories: Optional list of directories to limit results to
            include_files: Whether to include list of files in response

        Returns:
            dict: {
                "status": str,
                "message": str,
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
        try:
            # Convert empty lists to None for backend compatibility
            directories_list = directories if directories else None
            branch_opt = branch or None

            return await repo_map_builder.get_repo_structure(
                repo_path,
                directories=directories_list,
                include_files=include_files,
                branch=branch_opt,
                cache_strategy=cache_strategy,
            )
        except Exception as e:
            logger.error(f"Error getting repository structure: {e}", exc_info=True)
            return {
                "status": "error",
                "error": f"Failed to get repository structure: {str(e)}",
            }

    @mcp_server.tool(name="get_repo_critical_files")
    async def get_repo_critical_files(
        repo_path: str,
        files: List[str] = [],
        directories: List[str] = [],
        limit: int = 50,
        include_metrics: bool = True,
        branch: str = "",
        cache_strategy: str = "shared",
    ) -> dict:
        """
        Analyze and identify the most structurally significant files in a codebase.

        Uses code complexity metrics to calculate importance scores, helping identify
        files that are most critical for understanding the system's structure.

        Args:
            repo_path: Path/URL matching what was provided to clone_repo
            files: Optional list of specific files to analyze
            directories: Optional list of specific directories to analyze
            limit: Maximum number of files to return (default: 50)
            include_metrics: Include detailed metrics in response (default: True)

        Returns:
            dict: {
                "status": str,  # "success", "error"
                "files": [{
                    "path": str,
                    "importance_score": float,
                    "metrics": {  # Only if include_metrics=True
                        "total_ccn": int,
                        "max_ccn": int,
                        "function_count": int,
                        "nloc": int
                    }
                }],
                "total_files_analyzed": int
            }
        """
        try:
            # Import and initialize the analyzer
            from code_understanding.analysis.complexity import CodeComplexityAnalyzer

            analyzer = CodeComplexityAnalyzer(repo_manager, repo_map_builder)

            # Convert empty lists to None for backend compatibility
            files_list = files if files else None
            directories_list = directories if directories else None
            branch_opt = branch or None

            # Delegate to the specialized CodeComplexityAnalyzer module
            return await analyzer.analyze_repo_critical_files(
                repo_path=repo_path,
                files=files_list,
                directories=directories_list,
                limit=limit,
                include_metrics=include_metrics,
                branch=branch_opt,
                cache_strategy=cache_strategy,
            )
        except Exception as e:
            logger.error(
                f"Unexpected error in get_repo_critical_files: {str(e)}", exc_info=True
            )
            return {
                "status": "error",
                "error": f"An unexpected error occurred: {str(e)}",
            }

    @mcp_server.tool(name="get_repo_documentation")
    async def get_repo_documentation(
        repo_path: str, branch: Optional[str] = None, cache_strategy: str = "shared"
    ) -> dict:
        """
        Retrieve and analyze repository documentation files.

        Searches for and analyzes documentation within the repository, including:
        - README files
        - API documentation
        - Design documents
        - User guides
        - Installation instructions
        - Other documentation files

        Args:
            repo_path (str): Path or URL matching what was originally provided to clone_repo

        Returns:
            dict: Documentation analysis results with format:
                {
                    "status": str,  # "success", "error", or "waiting"
                    "message": str,  # Only for error/waiting status
                    "documentation": {  # Only for success status
                        "files": [
                            {
                                "path": str,      # Relative path in repo
                                "category": str,  # readme, api, docs, etc.
                                "format": str     # markdown, rst, etc.
                            }
                        ],
                        "directories": [
                            {
                                "path": str,
                                "doc_count": int
                            }
                        ],
                        "stats": {
                            "total_files": int,
                            "by_category": dict,
                            "by_format": dict
                        }
                    }
                }
        """
        try:
            # Call documentation backend module (thin endpoint)
            return await get_repository_documentation(
                repo_path, branch=branch, cache_strategy=cache_strategy
            )
        except Exception as e:
            logger.error(
                f"Error retrieving repository documentation: {e}", exc_info=True
            )
            return {
                "status": "error",
                "message": f"Failed to retrieve repository documentation: {str(e)}",
            }


# Create server instance that can be imported by MCP CLI
server = create_mcp_server()


@click.command()
@click.version_option(package_name="code-understanding-mcp-server")
@click.option("--port", default=3001, help="Port to listen on for SSE")
@click.option(
    "--transport",
    type=click.Choice(["stdio", "sse"]),
    default="stdio",
    help="Transport type (stdio or sse)",
)
@click.option(
    "--cache-dir",
    help="Directory to store repository cache",
)
@click.option(
    "--max-cached-repos",
    type=int,
    help="Maximum number of cached repositories",
)
def main(
    port: int, transport: str, cache_dir: str = None, max_cached_repos: int = None
) -> int:
    """Run the server with specified transport."""
    try:
        # Create overrides dict from command line args
        overrides = {}
        if cache_dir or max_cached_repos:
            overrides["repository"] = {}
            if cache_dir:
                overrides["repository"]["cache_dir"] = cache_dir
            if max_cached_repos:
                overrides["repository"]["max_cached_repos"] = max_cached_repos

        # Create server with command line overrides
        config = load_config(overrides=overrides)

        global server
        server = create_mcp_server(config)

        if transport == "stdio":
            asyncio.run(server.run_stdio_async())
        else:
            server.settings.port = port
            asyncio.run(server.run_sse_async())
        return 0
    except KeyboardInterrupt:
        logger.info("Server stopped by user")
        return 0
    except Exception as e:
        logger.error(f"Failed to start server: {e}", exc_info=True)
        return 1


if __name__ == "__main__":
    sys.exit(main())
