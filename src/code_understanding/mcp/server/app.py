"""
Core MCP server implementation using FastMCP.
"""

import logging
import sys
import asyncio
from pathlib import Path
import click
from typing import List, Optional

from mcp.server.fastmcp import FastMCP
from code_understanding.config import ServerConfig, load_config
from code_understanding.repository import RepositoryManager
from code_understanding.context.builder import RepoMapBuilder
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
    """Create and configure the MCP server instance."""
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
    async def get_repo_file_content(repo_path: str, resource_path: Optional[str] = None, branch: Optional[str] = None, cache_strategy: str = "shared") -> dict:
        """Retrieve file contents or list directory entries from a cached repository.

        Usage overview
        --------------
        1. Start with :func:`list_repository_branches` to discover cached entries and reuse the
           existing ``cache_strategy``/``branch`` pairing when available.
        2. Call :func:`refresh_repo` to pull the latest commits or :func:`clone_repo` if no cache
           exists yet.
        3. Invoke this tool with matching ``repo_path``/``branch``/``cache_strategy`` to fetch
           file text or a directory listing.
        4. Handle ``{"status": "error"}`` responses that indicate the repository is missing,
           cloning, or failed to refresh. See **Repository Discovery & Preparation** in the server
           instructions for prerequisite details.

        Parameters
        ----------
        repo_path:
            Exact identifier originally supplied to :func:`clone_repo`. A mismatched string returns
            ``{"status": "error", "error": "Repository not found..."}``.
        resource_path:
            Relative path inside the repository. Defaults to ``"."`` (repository root) when
            omitted.
        branch:
            Target branch when ``cache_strategy == "per-branch"``. Ignored for shared caches.
        cache_strategy:
            ``"shared"`` (default) or ``"per-branch"``; must match the strategy used during the
            initial clone.

        Responses
        ---------
        * File payload – ``{"type": "file", "path": <relative path>, "content": <text>,
          "branch": <str>, "cache_strategy": <str>}``.
        * Directory payload – ``{"type": "directory", "path": <relative path>, "contents":
          [<entries>], "branch": <str>, "cache_strategy": <str>}``.
        * Error payload – ``{"status": "error", "error": <message>}`` for cache misses,
          incomplete clones, or unexpected failures.

        Notes
        -----
        * Directory results are not recursive; call again with a child ``resource_path`` to drill
          down.
        * File contents are returned verbatim without pagination. Consider repository size when
          fetching large binaries or generated files.
        * Cross-reference the server instructions for cloning and cache-strategy expectations.
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
                per_branch=(cache_strategy == "per-branch")
            )
            str_path = str(cache_path.resolve())
            
            repo_status = await repo_manager.cache.get_repository_status(str_path)
            if not repo_status or "clone_status" not in repo_status:
                return {"status": "error", "error": "Repository not found. Please clone it first using clone_repo."}
            
            clone_status = repo_status["clone_status"]
            if not clone_status:
                return {"status": "error", "error": "Repository not cloned. Please clone it first using clone_repo."}
            elif clone_status.get("status") in ["cloning", "copying"]:
                return {"status": "error", "error": "Repository clone still in progress. Please wait for clone to complete."}
            elif clone_status.get("status") != "complete":
                return {"status": "error", "error": "Repository clone failed or incomplete. Please try cloning again."}
            
            # Clone is complete, create repository instance with correct cache path
            from code_understanding.repository.manager import Repository
            repository = Repository(
                repo_id=str_path,
                root_path=str_path,
                repo_type="git",
                is_git=True
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
    async def refresh_repo(repo_path: str, branch: Optional[str] = None, cache_strategy: str = "shared") -> dict:
        """Refresh a cached repository and restart analysis in the background.

        Workflow
        --------
        1. Ensure the repository was previously cloned with the same ``cache_strategy``.
        2. Call this tool to pull remote changes (Git) or recopy local sources into the cache.
        3. The server triggers a fresh repository-map build. Poll :func:`get_source_repo_map`
           until the returned ``status`` becomes ``"success"``.

        Parameters
        ----------
        repo_path:
            Identifier originally passed to :func:`clone_repo`.
        branch:
            Optional branch to check out after refresh. Required when working with a
            ``per-branch`` cache entry different from the active branch.
        cache_strategy:
            ``"shared"`` (default) or ``"per-branch"``; must match the initial clone. The server
            validates this before attempting an update.

        Response schema
        ---------------
        ``{"status": "pending", "path": <cache path>, "message": <str>, "cache_strategy": <str>}``
            Refresh accepted and the analysis rebuild is running asynchronously.
        ``{"status": "switched_branch", "path": <cache path>, "message": <str>, "cache_strategy": <str>, "current_branch": <str>, "previous_branch": <str>}``
            The cache switched branches before kicking off analysis.
        ``{"status": "error", "error": <message>, "cache_strategy": <str>}``
            Validation or refresh failed; no analysis rebuild is scheduled.

        Notes
        -----
        * The source repository is never mutated; only the cached copy is updated.
        * Refreshes may take time for large histories. If the client times out, re-poll
          :func:`get_source_repo_map` or :func:`list_repository_branches` to confirm completion.
        * See the server instructions section **Refresh & Analysis Lifecycle** for end-to-end
          polling guidance.
        """
        try:
            # Validate cache_strategy
            if cache_strategy not in ["shared", "per-branch"]:
                return {"status": "error", "error": "cache_strategy must be 'shared' or 'per-branch'"}
                
            return await repo_manager.refresh_repository(repo_path, branch, cache_strategy)
        except Exception as e:
            logger.error(f"Error refreshing repository: {e}", exc_info=True)
            return {"status": "error", "error": str(e)}

    @mcp_server.tool(name="list_repository_branches")
    async def list_repository_branches(repo_url: str) -> dict:
        """Enumerate cached branches and analysis statuses for a repository URL.

        Parameters
        ----------
        repo_url:
            Exact URL/path previously supplied to :func:`clone_repo`.

        Response schema
        ---------------
        ``{"status": "success", "repo_url": <str>, "cached_branches": [...], "total_cached": <int>}``
            * ``cached_branches`` entries expose:
              - ``requested_branch`` – branch passed to :func:`clone_repo`.
              - ``current_branch`` – branch currently checked out in the cache (for shared caches
                this may differ from ``requested_branch`` after refresh operations).
              - ``cache_path`` – fully qualified cache location on disk.
              - ``cache_strategy`` – ``"shared"`` or ``"per-branch"``.
              - ``last_access`` – ISO timestamp of the most recent tool interaction.
              - ``clone_status`` – ``{"status": "cloning"|"complete"|"error", "message": <str>,
                "updated_at": <iso>}``.
              - ``repo_map_status`` – ``{"status": "building"|"waiting"|"success"|"error"|"threshold_exceeded", "message": <str>, "updated_at": <iso>}``.
        ``{"status": "error", "error": <message>}``
            Provided when the repository has never been cloned or when metadata cannot be read.

        Usage notes
        -----------
        * Use this tool before switching branches so you can reuse an existing cache entry instead
          of recloning.
        * Pairs naturally with :func:`refresh_repo` and :func:`get_source_repo_map` to monitor
          long-running analysis work.
        * Refer to the server instructions section **Cache Directory Layout & Branch Handling** for
          guidance on interpreting shared vs. per-branch entries.
        """
        try:
            return await repo_manager.list_repository_branches(repo_url)
        except Exception as e:
            logger.error(f"Error listing repository branches: {e}", exc_info=True)
            return {"status": "error", "error": str(e)}

    @mcp_server.tool(name="clone_repo")
    async def clone_repo(url: str, branch: Optional[str] = None, cache_strategy: str = "shared") -> dict:
        """Clone or copy a repository into the MCP cache and kick off analysis.

        Operational sequence
        --------------------
        1. Provide a ``url`` or local path and select a cache strategy.
        2. The server clones (Git) or copies (filesystem) the repository into its cache.
        3. A repository map build begins automatically. Poll :func:`get_source_repo_map` for
           progress updates.

        Parameters
        ----------
        url:
            Remote Git URL or local path to analyze. This exact string becomes the canonical
            ``repo_path`` for all subsequent tools.
        branch:
            Branch to check out immediately after cloning. Defaults to ``"main"`` if omitted.
        cache_strategy:
            ``"shared"`` (single cache entry reused for every branch) or ``"per-branch"`` (dedicated
            cache per branch, recommended for PR/feature review workflows).

        Response schema
        ---------------
        ``{"status": "pending", "path": <cache path>, "message": <str>, "cache_strategy": <str>, "current_branch": <str>}``
            Clone/copy accepted and analysis is running in the background.
        ``{"status": "already_cloned", "path": <cache path>, "message": <str>, "cache_strategy": <str>, "current_branch": <str>}``
            Cache entry already existed; the server reused it and kept the active branch.
        ``{"status": "switched_branch", "path": <cache path>, "message": <str>, "cache_strategy": <str>, "current_branch": <str>, "previous_branch": <str>}``
            Shared cache reused after switching branches in place.
        ``{"status": "error", "error": <message>, "cache_strategy": <str>}``
            Clone failed; no analysis will start.

        Notes
        -----
        * The source repository is read-only—no pushes or commits are performed by the server.
        * Cloning can take time for large histories. If the client disconnects, re-run this tool to
          receive the current status or check :func:`list_repository_branches`.
        * See **Repository Discovery & Preparation** in the server instructions for
          recommendations on choosing between shared and per-branch caches.
        """
        try:
            # Default branch to "main" if not provided
            if branch is None:
                branch = "main"
            
            # Validate cache_strategy
            if cache_strategy not in ["shared", "per-branch"]:
                return {"status": "error", "error": "cache_strategy must be 'shared' or 'per-branch'"}
            
            # Repository clone with new dual cache strategy support
            logger.debug(f"[TRACE] clone_repo: Starting clone_repository for {url} with branch {branch} using {cache_strategy} strategy")
            result = await repo_manager.clone_repository(url, branch, cache_strategy)
            logger.debug(f"[TRACE] clone_repo: clone_repository completed for {url}")
            return result
        except Exception as e:
            logger.error(f"Error cloning repository: {e}", exc_info=True)
            return {"status": "error", "error": str(e)}

    @mcp_server.tool(name="get_source_repo_map")
    async def get_source_repo_map(
        repo_path: str,
        directories: Optional[List[str]] = None,
        files: Optional[List[str]] = None,
        max_tokens: Optional[int] = None,
        branch: Optional[str] = None,
        cache_strategy: str = "shared",
    ) -> dict:
        """Return the latest semantic repository map built for a cached project.

        What it provides
        ----------------
        * Hierarchical summaries of files, classes, functions, and relationships.
        * Metadata about excluded files, token budgets, and completion state.
        * Status updates while background analysis is still running.

        Parameters
        ----------
        repo_path:
            Exact identifier used with :func:`clone_repo`.
        directories:
            Optional list of directory prefixes to include. When paired with ``files`` the tool
            intersects both sets, returning only matching files inside the provided directories.
        files:
            Optional list of filenames (relative paths). When provided alone, any path match within
            the repository is considered.
        max_tokens:
            Soft cap on the size of the textual map. Large limits increase processing time; consult
            **Analysis Size Management** in the server instructions for recommended ranges.
        branch:
            Branch name when querying ``per-branch`` caches.
        cache_strategy:
            ``"shared"`` (default) or ``"per-branch"``; must align with the earlier clone.

        Status values
        -------------
        ``success``
            ``content`` contains the complete map and ``metadata["is_complete"]`` is ``True``.
        ``building``
            Analysis is running. ``message`` describes the stage. Call again later.
        ``waiting``
            The repository has been cloned but map construction has not started yet (e.g., queued).
        ``threshold_exceeded``
            Size or token thresholds prevented completion. ``metadata`` includes guidance for
            narrowing scope.
        ``error``
            Analysis failed. Review the ``error`` field and consider recloning or refreshing.

        Response payload
        ----------------
        ``{"status": <status>, "content": <str | None>, "metadata": {"excluded_files_by_dir": {...}, "is_complete": <bool>, "max_tokens": <int | None>, "token_budget_used": <int | None>}, "message": <str | None>, "error": <str | None>}``

        Notes
        -----
        * The initial map build launches automatically after :func:`clone_repo`. Until it finishes
          you will see ``building``/``waiting`` responses.
        * For large monorepos, combine ``directories`` and ``files`` to scope the analysis before
          raising ``max_tokens``.
        * The server instructions outline strategies for refreshing stalled analyses and
          interpreting ``threshold_exceeded`` guidance.
        """
        try:
            # DEBUG: Log the parameters received at MCP endpoint
            logger.debug(f"[MCP DEBUG] get_source_repo_map called with:")
            logger.debug(f"[MCP DEBUG]   repo_path: {repo_path}")
            logger.debug(f"[MCP DEBUG]   files: {files}")
            logger.debug(f"[MCP DEBUG]   directories: {directories}")
            logger.debug(f"[MCP DEBUG]   max_tokens: {max_tokens}")
            
            if directories is None:
                directories = []
                
            return await repo_map_builder.get_repo_map_content(
                repo_path, files=files, directories=directories, max_tokens=max_tokens,
                branch=branch, cache_strategy=cache_strategy
            )
        except Exception as e:
            logger.error(f"Error getting context: {e}", exc_info=True)
            return {
                "status": "error",
                "error": f"Unexpected error while getting repository context: {str(e)}",
            }

    @mcp_server.tool(name="get_repo_structure")
    async def get_repo_structure(
        repo_path: str, directories: Optional[List[str]] = None, include_files: bool = False,
        branch: Optional[str] = None, cache_strategy: str = "shared"
    ) -> dict:
        """Summarize directory structure and analyzable files within a cached repository.

        Parameters
        ----------
        repo_path:
            Identifier originally passed to :func:`clone_repo`.
        directories:
            Optional subset of directories to report. When omitted the entire repository is
            scanned. Providing values reduces processing time on large projects.
        include_files:
            When ``True``, each directory entry includes a non-recursive list of file paths.
        branch:
            Branch name to inspect when the cache strategy is ``per-branch``.
        cache_strategy:
            ``"shared"`` or ``"per-branch"`` (default ``"shared"``). Must match the clone.

        Response schema
        ---------------
        ``{"status": "success", "directories": [...], "total_analyzable_files": <int>, "message": <str | None>}``
            * Each directory entry contains:
              - ``path`` – relative directory path.
              - ``analyzable_files`` – count of files matching the server's analyzable extensions.
              - ``extensions`` – mapping of extension → count.
              - ``files`` – present only when ``include_files=True``.
        ``{"status": "error", "error": <message>}``
            Returned when the repository is missing, still cloning, or another failure occurs.

        Notes
        -----
        * Use this tool to decide which directories to pass to :func:`get_source_repo_map` or
          :func:`get_repo_critical_files`.
        * See **Repository Discovery & Preparation** in the server instructions for cloning
          prerequisites and branch-handling details.
        """
        try:
            # Delegate to the RepoMapBuilder service to handle all the details
            return await repo_map_builder.get_repo_structure(
                repo_path, directories=directories, include_files=include_files,
                branch=branch, cache_strategy=cache_strategy
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
        files: Optional[List[str]] = None,
        directories: Optional[List[str]] = None,
        limit: int = 50,
        include_metrics: bool = True,
        branch: Optional[str] = None,
        cache_strategy: str = "shared",
    ) -> dict:
        """Rank repository files by structural importance using complexity metrics.

        Parameters
        ----------
        repo_path:
            Identifier originally provided to :func:`clone_repo`.
        files:
            Optional collection of file paths to evaluate. When combined with ``directories`` the
            tool analyzes only files matching both filters.
        directories:
            Optional list of directory prefixes. When omitted, the entire repository is scanned.
        limit:
            Maximum number of ranked results to return (default ``50``). Use lower values to focus on
            the highest-impact files.
        include_metrics:
            When ``True`` (default) includes the raw metrics underlying the importance score.
        branch:
            Branch name for ``per-branch`` caches.
        cache_strategy:
            ``"shared"`` or ``"per-branch"`` (default ``"shared"``); must match the clone.

        Response schema
        ---------------
        ``{"status": "success", "files": [...], "total_files_analyzed": <int>, "message": <str | None>}``
            * Each ``files`` entry contains:
              - ``path`` – relative file path.
              - ``importance_score`` – weighted sum of function count, total/max cyclomatic
                complexity, and lines of code.
              - ``metrics`` – included when ``include_metrics=True`` with keys ``total_ccn``,
                ``max_ccn``, ``function_count``, and ``nloc``.
        ``{"status": "error", "error": <message>}``
            Returned when the repository is missing or when analysis fails.

        Notes
        -----
        * Use this ranking to target deeper dives with :func:`get_source_repo_map` or code review.
        * Complexity analysis can take several seconds on large repositories. If the client
          disconnects, repeat the call to check progress—the analyzer caches intermediate results.
        * Refer to **Analysis Size Management** in the server instructions for guidance on narrowing
          ``files``/``directories`` filters when thresholds are exceeded.
        """
        try:
            # Import and initialize the analyzer
            from code_understanding.analysis.complexity import CodeComplexityAnalyzer

            analyzer = CodeComplexityAnalyzer(repo_manager, repo_map_builder)

            # Delegate to the specialized CodeComplexityAnalyzer module
            return await analyzer.analyze_repo_critical_files(
                repo_path=repo_path,
                files=files,
                directories=directories,
                limit=limit,
                include_metrics=include_metrics,
                branch=branch,
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
    async def get_repo_documentation(repo_path: str, branch: Optional[str] = None, cache_strategy: str = "shared") -> dict:
        """Aggregate documentation assets discovered in a cloned repository.

        Parameters
        ----------
        repo_path:
            Identifier originally passed to :func:`clone_repo`.
        branch:
            Branch name for ``per-branch`` caches.
        cache_strategy:
            ``"shared"`` or ``"per-branch"`` (default ``"shared"``); must match the clone.

        Response schema
        ---------------
        ``{"status": "success", "documentation": {"files": [...], "directories": [...], "stats": {...}}, "message": <str | None>}``
            * ``files`` – list of documentation artifacts with ``path``, ``category`` (readme/api/
              design/etc.), and ``format`` (markdown/rst/html/plain).
            * ``directories`` – aggregate counts by directory.
            * ``stats`` – overall totals, counts by category, and counts by format.
        ``{"status": "waiting", "message": <str>}``
            Documentation scan queued or still running.
        ``{"status": "error", "message": <str>}``
            Repository missing, still cloning, or analysis failed.

        Notes
        -----
        * Documentation discovery runs as part of the repository-map workflow. Expect ``waiting``
          until the initial clone has finished building its map.
        * Use these results to surface README files, architecture docs, or onboarding guides in
          downstream conversations.
        * Consult **Documentation Discovery Workflow** in the server instructions for additional
          curation tips and category definitions.
        """
        try:
            # Call documentation backend module (thin endpoint)
            return await get_repository_documentation(repo_path, branch=branch, cache_strategy=cache_strategy)
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
