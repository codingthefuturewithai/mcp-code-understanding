"""
Repository documentation discovery functionality.
"""

import json
import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from identify import identify

from ..config import load_config
from ..repository.file_filtering import RepoFilter
from .manager import RepositoryManager
from .path_utils import get_cache_path

logger = logging.getLogger(__name__)


def is_likely_doc_file(filepath: str, config) -> bool:
    """
    Determine if a file is likely a documentation file.
    Uses configuration to check extensions and identify tags.
    Also verifies file is text.

    Args:
        filepath: Path to the file to check
        config: Server configuration object

    Returns:
        bool: True if the file is likely a documentation file
    """
    # Check if it's a text file
    try:
        tags = identify.tags_from_path(filepath)
        if "text" not in tags:
            return False
    except Exception:
        return False

    # Get configured doc tags and extensions
    doc_config = config.documentation
    include_tags = set(doc_config.include_tags)
    include_exts = set(doc_config.include_extensions)

    # Check for doc tags
    if include_tags.intersection(tags):
        return True

    # Check file extension
    ext = os.path.splitext(filepath)[1].lower()
    return ext in include_exts


def get_doc_format(filepath: str, config) -> str:
    """
    Get document format based on configured mappings.

    Args:
        filepath: Path to the file
        config: Server configuration object

    Returns:
        str: Format name (markdown, restructuredtext, etc.)
    """
    format_mapping = config.documentation.format_mapping

    # Check tag-based formats
    try:
        tags = identify.tags_from_path(filepath)
        for tag in tags:
            mapping_key = f"tag:{tag}"
            if mapping_key in format_mapping:
                return format_mapping[mapping_key]
    except Exception:
        pass

    # Check extension-based formats
    ext = os.path.splitext(filepath)[1].lower()
    mapping_key = f"ext:{ext}"
    if mapping_key in format_mapping:
        return format_mapping[mapping_key]

    return "unknown"


def categorize_doc_file(rel_path: str, config) -> str:
    """
    Categorize document based on configured patterns.

    Args:
        rel_path: Relative path from repository root
        config: Server configuration object

    Returns:
        str: Category name (readme, api, documentation, etc.)
    """
    category_patterns = config.documentation.category_patterns
    path_parts = rel_path.lower().split(os.path.sep)
    filename = os.path.basename(rel_path).lower()

    # Check each category's patterns against path and filename
    for category, patterns in category_patterns.items():
        for pattern in patterns:
            if pattern in filename or any(pattern in part for part in path_parts):
                return category

    return "other"


def calculate_stats(doc_files) -> Dict[str, Any]:
    """
    Calculate documentation statistics.

    Args:
        doc_files: List of documentation file dictionaries

    Returns:
        dict: Statistics dictionary with counts by category and format
    """
    total_files = len(doc_files)
    by_category = {}
    by_format = {}

    for doc in doc_files:
        category = doc["category"]
        doc_format = doc["format"]

        by_category[category] = by_category.get(category, 0) + 1
        by_format[doc_format] = by_format.get(doc_format, 0) + 1

    return {
        "total_files": total_files,
        "by_category": by_category,
        "by_format": by_format,
    }


async def get_repository_documentation(
    repo_path: str, branch: Optional[str] = None, cache_strategy: str = "shared"
) -> Dict[str, Any]:
    """
    Discover documentation files in a repository.

    Args:
        repo_path: Path or URL provided by the user (could be GitHub URL or local path)
        branch: Optional branch to analyze (defaults to current branch)
        cache_strategy: Cache strategy to use ("shared" or "per-branch")

    Returns:
        Dictionary with documentation files, categories, and stats
    """
    # Load configuration and resolve cache path consistently with server logic
    config = load_config()
    cache_dir = config.repository.get_cache_dir_path()
    cache_path = str(
        get_cache_path(
            cache_dir,
            repo_path,
            branch if cache_strategy == "per-branch" else None,
            per_branch=(cache_strategy == "per-branch"),
        ).resolve()
    )

    # Use RepositoryManager/metadata for readiness instead of failing early on filesystem
    repo_manager = RepositoryManager(config.repository)

    # Check repository status in metadata using the cache's methods
    with repo_manager.cache._file_lock():
        metadata_dict = repo_manager.cache._read_metadata()
        if cache_path not in metadata_dict:
            # If the folder exists but metadata not yet written, surface waiting
            if os.path.isdir(cache_path):
                return {
                    "status": "waiting",
                    "message": "Repository cache exists but metadata not initialized. Please try again shortly.",
                }
            return {
                "status": "error",
                "message": f"No repository found at '{repo_path}' in metadata",
            }

        metadata = metadata_dict[cache_path]
        clone_status = metadata.clone_status
        if not clone_status or clone_status.get("status") != "complete":
            if clone_status and clone_status.get("status") in ("cloning", "copying"):
                return {
                    "status": "waiting",
                    "message": "Repository clone is in progress. Please try again later.",
                }
            return {
                "status": "error",
                "message": "Repository has not been cloned properly.",
            }

    # Find documentation files
    try:
        doc_files = []
        doc_dirs = {}

        # Get all non-ignored files using RepoFilter
        repo_filter = RepoFilter(Path(cache_path))
        all_files = repo_filter.find_all_files()

        # Process files for documentation
        for filepath in all_files:
            # Apply checks to identify doc files
            if is_likely_doc_file(filepath, config):
                rel_path = os.path.relpath(filepath, start=cache_path)
                dir_path = os.path.dirname(rel_path)

                # Get format and category
                doc_format = get_doc_format(filepath, config)
                category = categorize_doc_file(rel_path, config)

                doc_files.append(
                    {"path": rel_path, "category": category, "format": doc_format}
                )

                # Update directory counts
                doc_dirs[dir_path] = doc_dirs.get(dir_path, 0) + 1

        # Calculate statistics
        stats = calculate_stats(doc_files)

        # Return structured response
        return {
            "status": "success",
            "documentation": {
                "files": doc_files,
                "directories": [
                    {"path": d, "doc_count": c} for d, c in doc_dirs.items()
                ],
                "stats": stats,
            },
        }

    except Exception as e:
        logger.error(f"Error analyzing repository documentation: {e}", exc_info=True)
        return {
            "status": "error",
            "message": f"Failed to analyze repository documentation: {str(e)}",
        }
