"""
Configuration management for the Code Understanding server.
"""

import importlib.resources
import logging
import os
import platform
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional

import yaml
from platformdirs import user_cache_dir, user_config_dir

# Global storage for active configuration overrides
_active_config_overrides: Optional[Dict] = None

@dataclass
class DocumentationConfig:
    include_tags: List[str] = None
    include_extensions: List[str] = None
    format_mapping: Dict[str, str] = None
    category_patterns: Dict[str, List[str]] = None

    def __post_init__(self):
        # Set default values if not provided
        if self.include_tags is None:
            self.include_tags = ["markdown", "rst", "adoc"]
        if self.include_extensions is None:
            self.include_extensions = [
                ".md",
                ".markdown",
                ".rst",
                ".txt",
                ".adoc",
                ".ipynb",
            ]
        if self.format_mapping is None:
            self.format_mapping = {
                # Tag-based format mapping
                "tag:markdown": "markdown",
                "tag:rst": "restructuredtext",
                "tag:adoc": "asciidoc",
                # Extension-based format mapping
                "ext:.md": "markdown",
                "ext:.markdown": "markdown",
                "ext:.rst": "restructuredtext",
                "ext:.txt": "plaintext",
                "ext:.adoc": "asciidoc",
                "ext:.ipynb": "jupyter",
            }
        if self.category_patterns is None:
            self.category_patterns = {
                "readme": ["readme"],
                "api": ["api"],
                "documentation": ["docs", "documentation"],
                "examples": ["examples", "sample"],
            }


@dataclass
class RepositoryConfig:
    cache_dir: Optional[str] = (
        None  # Path string from config or None for platform default
    )
    max_cached_repos: int = 50

    def get_cache_dir_path(self) -> Path:
        app_name = "mcp-code-understanding"
        if self.cache_dir:
            # User-defined path from config/override
            p = Path(self.cache_dir).expanduser().resolve()
        else:
            # Default to platform-specific dir
            p = Path(user_cache_dir(app_name))
        p.mkdir(parents=True, exist_ok=True)  # Ensure it exists
        return p


@dataclass
class ServerConfig:
    name: str = "Code Understanding Server"
    log_level: str = "info"
    host: str = "localhost"
    port: int = 8080
    repository: RepositoryConfig = None
    documentation: DocumentationConfig = None

    def __post_init__(self):
        if self.repository is None:
            self.repository = RepositoryConfig()
        elif isinstance(self.repository, dict):  # Handle initialization from YAML
            self.repository = RepositoryConfig(**self.repository)
        if self.documentation is None:
            self.documentation = DocumentationConfig()
        elif isinstance(self.documentation, dict):  # Handle initialization from YAML
            self.documentation = DocumentationConfig(**self.documentation)


def ensure_default_config() -> None:
    """Ensure default config exists in the standard platform-specific directory."""
    logger = logging.getLogger(__name__)
    app_name = "mcp-code-understanding"

    # New platform-specific config directory
    new_config_dir = Path(user_config_dir(app_name))
    new_config_path = new_config_dir / "config.yaml"

    # Old hardcoded config directory (Linux/macOS style)
    old_config_dir_linux_mac = Path.home() / ".config" / app_name
    old_config_path_linux_mac = old_config_dir_linux_mac / "config.yaml"

    # Migration logic
    if old_config_path_linux_mac.exists() and not new_config_path.exists():
        try:
            logger.info(
                f"Migrating configuration from {old_config_path_linux_mac} to {new_config_path}"
            )
            new_config_dir.mkdir(parents=True, exist_ok=True)
            shutil.copy2(old_config_path_linux_mac, new_config_path)
            logger.info(f"Successfully migrated configuration to {new_config_path}")
            # Optionally, remove the old config file/directory after successful migration
            # old_config_path_linux_mac.unlink()
            # try:
            #     old_config_dir_linux_mac.rmdir() # Only removes if empty
            # except OSError:
            #     logger.debug(f"Old config directory {old_config_dir_linux_mac} not empty, not removed.")
        except Exception as e:
            logger.error(
                f"Failed to migrate configuration from {old_config_path_linux_mac} to {new_config_path}: {e}"
            )
            # Proceed to create default if migration failed

    if not new_config_path.exists():
        new_config_dir.mkdir(parents=True, exist_ok=True)
        try:
            # Try to find the config file relative to this file (package data)
            # This assumes the default config.yaml is in a 'config' subdirectory relative to this file
            # For installed packages, importlib.resources is more robust.
            package_name = __name__.split(".")[0]  # Should be 'code_understanding'
            default_config_resource = importlib.resources.files(package_name).joinpath(
                "config/config.yaml"
            )

            if default_config_resource.is_file():
                with importlib.resources.as_file(
                    default_config_resource
                ) as default_config_file_path:
                    with open(default_config_file_path, "r") as src:
                        default_config_content = src.read()
                        with open(new_config_path, "w") as dst:
                            dst.write(default_config_content)
                logger.info(f"Created default configuration at {new_config_path}")
            else:
                # Fallback for development environments if importlib.resources doesn't find it easily
                # This part might need adjustment based on your exact project structure for development
                current_script_dir = Path(__file__).resolve().parent
                fallback_default_config_path = (
                    current_script_dir / "config" / "config.yaml"
                )
                if fallback_default_config_path.exists():
                    with open(fallback_default_config_path, "r") as src:
                        default_config_content = src.read()
                        with open(new_config_path, "w") as dst:
                            dst.write(default_config_content)
                    logger.info(
                        f"Created default configuration at {new_config_path} using fallback path."
                    )
                else:
                    logger.error(
                        f"Could not find default config using importlib.resources or fallback path: {fallback_default_config_path}"
                    )
                    raise FileNotFoundError(
                        f"Default config not found (tried importlib.resources and {fallback_default_config_path})"
                    )
        except Exception as e:
            logger.error(f"Failed to create default config at {new_config_path}: {e}")
            raise


def get_config_search_paths() -> List[Path]:
    """Get list of paths to search for config file, prioritizing platform-specific."""
    paths: List[Path] = []
    app_name = "mcp-code-understanding"

    # 1. Platform-specific configuration directory
    platform_config_path = Path(user_config_dir(app_name)) / "config.yaml"
    paths.append(platform_config_path)

    # 2. Current working directory (for development override or local config)
    paths.append(Path("./config.yaml").resolve())

    # 3. Old hardcoded path (for backward compatibility during transition, lower priority)
    # This helps if migration hasn't run or if user explicitly placed it there.
    old_config_path_linux_mac = Path.home() / ".config" / app_name / "config.yaml"
    paths.append(old_config_path_linux_mac)

    return paths


def _load_base_config(config_path_override: Optional[str] = None) -> ServerConfig:
    """Internal function to load the base configuration from YAML file."""
    logger = logging.getLogger(__name__)

    # Always ensure default config exists first
    ensure_default_config()

    # If config_path_override is explicitly provided, only try that one
    if config_path_override:
        search_paths = [Path(config_path_override).resolve()]
    else:
        search_paths = get_config_search_paths()

    # Try each path in order
    for path_obj in search_paths:
        # Convert Path object to string for os.path.exists if needed, or use path_obj.exists()
        # Standardizing to path_obj.exists() and path_obj.is_file()
        if path_obj.exists() and path_obj.is_file():
            logger.info(f"Loading configuration from {path_obj}")
            try:
                with open(path_obj, "r") as f:
                    config_data = yaml.safe_load(f)

                if not config_data:  # Handles empty YAML
                    logger.warning(
                        f"Config file {path_obj} is empty, trying next location."
                    )
                    continue

                logger.debug(f"Loaded configuration data: {config_data}")

                # Convert nested dictionaries to appropriate config objects
                repo_conf_data = config_data.get("repository")
                if repo_conf_data and isinstance(repo_conf_data, dict):
                    config_data["repository"] = RepositoryConfig(**repo_conf_data)
                elif (
                    repo_conf_data is None
                ):  # Ensure RepositoryConfig is always present
                    config_data["repository"] = RepositoryConfig()

                doc_conf_data = config_data.get("documentation")
                if doc_conf_data and isinstance(doc_conf_data, dict):
                    config_data["documentation"] = DocumentationConfig(**doc_conf_data)
                elif (
                    doc_conf_data is None
                ):  # Ensure DocumentationConfig is always present
                    config_data["documentation"] = DocumentationConfig()

                # Ensure ServerConfig always has repository and documentation objects
                # even if they were not in the yaml file at all
                final_config = ServerConfig(**config_data)
                if final_config.repository is None:
                    final_config.repository = RepositoryConfig()
                if final_config.documentation is None:
                    final_config.documentation = DocumentationConfig()

                logger.debug("Base configuration loaded:")
                logger.debug(f"  Server Name: {final_config.name}")
                logger.debug(f"  Log Level: {final_config.log_level}")
                if final_config.repository:
                    logger.debug(
                        f"  Repository Config Object: {final_config.repository}"
                    )
                    # Use the method to get the actual cache dir path
                    cache_dir_to_log = final_config.repository.get_cache_dir_path()
                    logger.debug(f"    Cache Directory: {cache_dir_to_log}")
                    logger.debug(
                        f"    Max Cached Repos: {final_config.repository.max_cached_repos}"
                    )
                return final_config
            except Exception as e:
                logger.error(f"Error loading configuration from {path_obj}: {e}")
                # Optionally continue to next search path or raise, depending on desired strictness
                continue

    logger.error(
        f"Failed to load or create config from search paths: {[str(p) for p in search_paths]}"
    )
    # Fallback to a default ServerConfig if all else fails
    logger.info("Returning default ServerConfig as fallback.")
    return ServerConfig()


def load_config(
    config_path: Optional[str] = None, overrides: Optional[Dict] = None
) -> ServerConfig:
    """Load configuration from YAML file with optional overrides."""
    logger = logging.getLogger(__name__)
    
    global _active_config_overrides
    
    # If no new overrides provided, use stored overrides
    if overrides is None and _active_config_overrides is not None:
        overrides = _active_config_overrides
    # If new overrides provided, store them
    elif overrides is not None:
        _active_config_overrides = overrides

    # Load base config
    config = _load_base_config(config_path)

    # Apply any overrides
    if overrides:
        logger.debug("Applying configuration overrides:")
        if "name" in overrides:
            config.name = overrides["name"]
        if "log_level" in overrides:
            config.log_level = overrides["log_level"]

        if "repository" in overrides and overrides["repository"] is not None:
            repo_overrides = overrides["repository"]
            if config.repository is None:
                config.repository = RepositoryConfig()

            if "cache_dir" in repo_overrides and repo_overrides["cache_dir"] is not None:
                config.repository.cache_dir = repo_overrides["cache_dir"]
                logger.debug(f"  Repository cache_dir override set to: {config.repository.cache_dir}")
            if "max_cached_repos" in repo_overrides and repo_overrides["max_cached_repos"] is not None:
                config.repository.max_cached_repos = repo_overrides["max_cached_repos"]
                logger.debug(f"  Repository max_cached_repos override: {config.repository.max_cached_repos}")

    # Log final configuration using the getter for cache_dir
    logger.info("Final configuration values:")
    logger.info(f"  Server Name: {config.name}")
    logger.info(f"  Log Level: {config.log_level}")
    if config.repository:
        final_cache_dir = config.repository.get_cache_dir_path()  # Ensures path is resolved and created
        logger.info(f"  Repository:")
        logger.info(f"    Cache Directory: {final_cache_dir}")
        logger.info(f"    Max Cached Repos: {config.repository.max_cached_repos}")
    if config.documentation:
        logger.info(f"  Documentation Config: {config.documentation}")

    return config
