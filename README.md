# ⚠️ Platform Support Notice

**This MCP server has been tested on macOS and Linux. Windows support is currently unverified (not yet tested).**

If you try Windows and encounter issues, please open an issue so we can improve cross-platform support.

# Code Understanding MCP Server

An MCP (Model Context Protocol) server designed to understand codebases and provide intelligent context to AI coding assistants. This server handles both local and remote GitHub repositories and supports standard MCP-compliant operations.

## 🤖 AI Assistant Installation

**Have an AI coding assistant help you install this server!** Copy and paste the contents of our [Setup Assistant Prompt](SETUP_ASSISTANT_PROMPT.md) to your AI assistant (Claude, ChatGPT, Cursor, etc.) and it will guide you through the entire installation process.

## Features

- Clone and analyze GitHub repositories or local codebases
- Get repository structure and file organization
- Identify critical files based on complexity metrics and code structure
- Generate detailed repository maps showing:
  - Function signatures and relationships
  - Class definitions and hierarchies
  - Code structure and dependencies
- Retrieve and analyze repository documentation
- Target analysis to specific files or directories
- Keep analysis up-to-date with repository changes via refresh

## Quick Start: MCP Client Configuration

### Prerequisites

**Required: `uv` Installation**

This server requires `uv`, a modern Python package manager. If you don't already have `uv` installed:

```bash
# Install UV (macOS/Linux)
curl -sSf https://astral.sh/uv/install.sh | sh

# Install UV (Windows PowerShell)
irm https://astral.sh/uv/install.ps1 | iex
```

For more installation options, visit the official `uv` installation guide at [astral.sh/uv](https://astral.sh/uv).

### Installation Methods

#### Method 1: Direct execution with uvx (Recommended)

```bash
# Run directly without installing a global binary
uvx code-understanding-mcp-server
```

This launches the server in an isolated environment managed by UV each time.

#### Method 2: Virtual environment install (Optional)

If you prefer a persistent binary inside a dedicated virtual environment:

```bash
# Create a dedicated virtual environment
uv venv ~/.venvs/mcp-code-understanding

# Activate it (macOS/Linux)
source ~/.venvs/mcp-code-understanding/bin/activate

# Install the package into the venv
uv pip install code-understanding-mcp-server

# Run the server
code-understanding-mcp-server
```

### Verify Installation

Depending on your chosen method:

```bash
# Method 1 (uvx): runs via uvx; no persistent binary is installed
uvx --version

# Method 2 (venv install): verify the binary inside your venv
which code-understanding-mcp-server
# Expected output example: /Users/username/.venvs/mcp-code-understanding/bin/code-understanding-mcp-server
```

### Configure Your MCP Client

Use one of the following configurations for your MCP client:

```json
{
  "mcpServers": {
    "code-understanding": {
      "command": "uvx",
      "args": [
        "code-understanding-mcp-server"
      ]
    }
  }
}
```

Alternatively, if you installed into a virtual environment, point directly to the binary in that environment:

```json
{
  "mcpServers": {
    "code-understanding": {
      "command": "/path/to/.venvs/mcp-code-understanding/bin/code-understanding-mcp-server",
      "args": []
    }
  }
}
```

## Why Use this MCP Server?

# MCP Code Understanding Server

## Value Proposition

The MCP Code Understanding Server empowers AI assistants with comprehensive code comprehension capabilities, enabling them to provide more accurate, contextual, and practical assistance with software development tasks. By creating a semantic bridge between repositories and AI systems, this server dramatically reduces the time and friction involved in code exploration, analysis, and implementation guidance.

## Common Use Cases

### Reference Repository Analysis
- Examine external repositories (libraries, dependencies, etc.) to inform current development
- Find implementation patterns and examples in open-source projects
- Understand how specific libraries work internally when documentation is insufficient
- Compare implementation approaches across similar projects
- Identify best practices from high-quality codebases

### Knowledge Extraction and Documentation
- Generate comprehensive documentation for poorly documented codebases
- Create architectural overviews and component relationship diagrams
- Develop progressive learning paths for developer onboarding
- Extract business logic and domain knowledge embedded in code
- Identify and document system integration points and dependencies

### Codebase Assessment and Improvement
- Analyze technical debt and prioritize refactoring efforts
- Identify security vulnerabilities and compliance issues
- Assess test coverage and quality
- Detect dead code, duplicated logic, and optimization opportunities
- Evaluate implementation against design patterns and architectural principles

### Legacy System Understanding
- Recover knowledge from systems with minimal documentation
- Support migration planning by understanding system boundaries
- Analyze complex dependencies before making changes
- Trace feature implementations across multiple components
- Understand historical design decisions and their rationales

### Cross-Project Knowledge Transfer
- Apply patterns from one project to another
- Bridge knowledge gaps between teams working on related systems
- Identify reusable components across multiple projects
- Understand differences in implementation approaches between teams
- Facilitate knowledge sharing in distributed development environments

For detailed examples of how the MCP Code Understanding Server can be used in real-world scenarios, see our [Example Scenarios](docs/Code_Understanding_Scenarios.md) document. It includes step-by-step walkthroughs of:
- Accelerating developer onboarding to a complex codebase
- Planning and executing API migrations
- Conducting security vulnerability assessments

## How It Works

The MCP Code Understanding Server processes repositories through a series of analysis steps:

1. **Repository Cloning**: The server clones the target repository into its cache
2. **Structure Analysis**: Analysis of directories, files, and their organization
3. **Critical File Identification**: Determination of structurally significant components
4. **Documentation Retrieval**: Collection of all documentation files
5. **Semantic Mapping**: Creation of a detailed map showing relationships between components
6. **Content Analysis**: Examination of specific files as needed for deeper understanding

AI assistants integrate with the server by making targeted requests for each analytical stage, building a comprehensive understanding of the codebase that can be used to address specific user questions and needs.

### Recommended Workflow for AI Assistants

When working with repositories, AI assistants should follow this workflow for optimal results:

1. **Check Cache First**: Use `list_cached_repository_branches` to see if the repository is already cached
   - If cached: Skip to step 3 (refresh)
   - If not cached: Continue to step 2

2. **Discover Branch Names**: Many repositories use "master", "develop", or other names instead of "main"
   - Use `list_remote_branches` to discover available branches
   - Identify the correct default branch before cloning

3. **Refresh Before Analysis**: Cached repositories become stale over time
   - Use `refresh_repo` to pull latest changes before any analysis
   - This ensures analysis is based on current code, not outdated cache

4. **Perform Analysis**: Once repository is current, use analysis tools
   - `get_source_repo_map` for code structure
   - `get_repo_critical_files` for identifying key components
   - `get_repo_documentation` for documentation discovery

This workflow prevents common issues like clone failures from incorrect branch names, redundant clone attempts, and analysis based on stale cached data.

## Design Considerations for Large Codebases

The server employs several strategies to maintain performance and usability even with enterprise-scale repositories:

- **Asynchronous Processing**: Repository cloning and analysis occur in background threads, providing immediate feedback while deeper analysis continues
- **Progressive Analysis**: Initial quick analysis enables immediate interaction, with more detailed understanding building over time
- **Scope Control**: Parameters for `max_tokens`, `files`, and `directories` enable targeted analysis of specific areas of interest
- **Threshold Management**: Automatic detection of repository size with appropriate guidance for analysis strategies
- **Hierarchical Understanding**: Repository structure is analyzed first, enabling intelligent prioritization of critical components for deeper semantic analysis

These design choices ensure that developers can start working immediately with large codebases while the system builds a progressively deeper understanding in the background, striking an optimal balance between analysis depth and responsiveness.

### GitHub Authentication (Optional)

If you need to access private repositories or want to avoid GitHub API rate limits, add your GitHub token to the configuration:

```json
{
  "mcpServers": {
    "code-understanding": {
      "command": "/path/to/code-understanding-mcp-server",
      "args": [],
      "env": {
        "GITHUB_PERSONAL_ACCESS_TOKEN": "your-github-token-here"
      }
    }
  }
}
```

### Advanced Configuration Options

For advanced users, the server supports several configuration options:

```json
{
  "mcpServers": {
    "code-understanding": {
      "command": "/path/to/code-understanding-mcp-server",
      "args": [
        "--cache-dir", "~/custom-cache-dir",     // Override repository cache location
        "--max-cached-repos", "20",              // Override maximum number of cached repos
        "--transport", "stdio",                  // Transport type (stdio or sse)
        "--port", "3001"                         // Port for SSE transport (only used with sse)
      ],
      "env": {
        "GITHUB_PERSONAL_ACCESS_TOKEN": "your-github-token-here"
      }
    }
  }
}
```

Available options:
- `--cache-dir`: Override the repository cache directory location (default: ~/.cache/mcp-code-understanding)
- `--max-cached-repos`: Set maximum number of cached repositories (default: 10)
- `--transport`: Choose transport type (stdio or sse, default: stdio)
- `--port`: Set port for SSE transport (default: 3001, only used with sse transport)

### Platform-Specific Notes

#### macOS
- With `uvx`, no persistent binary is installed; no PATH changes are required
- With a virtual environment, ensure you activate it or reference the full path to the venv binary

#### Linux
- With `uvx`, no persistent binary is installed; no PATH changes are required
- With a virtual environment, you may prefer adding a helper alias or activating the venv before use

#### Windows
- **Not currently supported** - Windows support is planned for a future release
- Development work is ongoing to enable Windows compatibility

### Troubleshooting

#### Dependency Conflicts

If you encounter dependency conflicts when using `uvx`, create an isolated environment and install the package there:

```bash
# Create a dedicated virtual environment
uv venv ~/.venvs/mcp-code-understanding

# Activate it (macOS/Linux)
source ~/.venvs/mcp-code-understanding/bin/activate

# Install the package
uv pip install code-understanding-mcp-server

# Run the server
code-understanding-mcp-server
```

#### Binary Not Found

If the installed binary is not found:

1. Check installation location:
   ```bash
   # macOS/Linux
   find ~/.local -name "code-understanding-mcp-server" 2>/dev/null
   ```

2. Add to PATH if needed:
   ```bash
   # Add to ~/.bashrc, ~/.zshrc, or appropriate shell config
   export PATH="$HOME/.local/bin:$PATH"
   ```

3. Use the absolute path to your venv binary in MCP configuration if not activating the venv

## Server Configuration

The server uses a `config.yaml` file for base configuration. This file is automatically created in the standard configuration directory (`~/.config/mcp-code-understanding/config.yaml`) when the server first runs. You can also place a `config.yaml` file in your current directory to override the default configuration.

Here's the default configuration structure:

```yaml
name: "Code Understanding Server"
log_level: "debug"

repository:
  cache_dir: "~/.cache/mcp-code-understanding"
  max_cached_repos: 10

documentation:
  include_tags:
    - markdown
    - rst
    - adoc
  include_extensions:
    - .md
    - .markdown
    - .rst
    - .txt
    - .adoc
    - .ipynb
  format_mapping:
    tag:markdown: markdown
    tag:rst: restructuredtext
    tag:adoc: asciidoc
    ext:.md: markdown
    ext:.markdown: markdown
    ext:.rst: restructuredtext
    ext:.txt: plaintext
    ext:.adoc: asciidoc
    ext:.ipynb: jupyter
  category_patterns:
    readme: 
      - readme
    api: 
      - api
    documentation:
      - docs
      - documentation
    examples:
      - examples
      - sample
```

## For Developers

### Prerequisites

- **Python 3.11 or 3.12**: Required for both development and usage
  ```bash
  # Verify your Python version
  python --version
  # or
  python3 --version
  ```
- **UV Package Manager**: The modern Python package installer
  ```bash
  # Install UV
  curl -sSf https://astral.sh/uv/install.sh | sh
  ```

### Development Setup

To contribute or run this project locally:

```bash
# 1. Clone the repository
git clone https://github.com/yourusername/mcp-code-understanding.git
cd mcp-code-understanding

# 2. Create virtual environment
uv venv

# 3. Activate the virtual environment
#    Choose the command appropriate for your operating system and shell:

#    Linux/macOS (bash/zsh):
source .venv/bin/activate

#    Windows (Command Prompt - cmd.exe):
.venv\\Scripts\\activate.bat

#    Windows (PowerShell):
#    Note: You might need to adjust your execution policy first.
#    Run: Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope Process
.venv\\Scripts\\Activate.ps1

# 4. Install dependencies (editable mode with dev extras)
#    (Ensure your virtual environment is activated first!)
uv pip install -e ".[dev]"

# 5. Set up pre-commit hooks
pre-commit install

# 6. Run tests
uv run pytest

# 7. Test the server using MCP inspector
# Without GitHub authentication:
uv run mcp dev src/code_understanding/mcp/server/app.py

# With GitHub authentication (for testing private repos):
GITHUB_PERSONAL_ACCESS_TOKEN=your_token_here uv run mcp dev src/code_understanding/mcp/server/app.py
```

This will launch an interactive console where you can test all MCP server endpoints directly.

### Development Tools

The following development tools are available after installing with dev extras (`.[dev]`):

Run tests with coverage:
```bash
uv run pytest
```

Format code (using black and isort):
```bash
# Format with black
uv run black .

# Sort imports
uv run isort .
```

Type checking with mypy:
```bash
uv run mypy .
```

All tools are configured via pyproject.toml with settings optimized for this project.

### Publishing to PyPI

When you're ready to publish a new version to PyPI, follow these steps:

1. Update the version number in `pyproject.toml`:
   ```bash
   # Edit pyproject.toml and change the version field
   # For example: version = "0.1.1"
   ```

2. Clean previous build artifacts:
   ```bash
   # Remove previous distribution packages and build directories
   rm -rf dist/ 2>/dev/null || true
   rm -rf build/ 2>/dev/null || true
   rm -rf src/*.egg-info/ 2>/dev/null || true
   ```

3. Build the distribution packages:
   ```bash
   uv run python -m build
   ```

4. Verify the built packages:
   ```bash
   ls dist/
   ```

5. Upload to PyPI (use TestPyPI first if unsure):
   ```bash
   # Install twine if you haven't already
   uv pip install twine
   
   # For PyPI release:
   uv run python -m twine upload dist/*
   ```

You'll need PyPI credentials configured or you'll be prompted to enter them during upload.

## Version History

### v0.1.6 (Latest)
- **Dependency Fix**: Explicitly pinned `configargparse==1.7` to resolve installation issues caused by the yanked version in PyPI
- This ensures clean installation with `uvx` and other package managers by preventing dependency resolution failures
- No functional changes to the server capabilities

## License

MIT