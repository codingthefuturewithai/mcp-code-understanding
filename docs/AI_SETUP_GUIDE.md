# AI Assistant Setup Prompt for MCP Code Understanding Server

Copy and paste this entire prompt to your AI coding assistant to help you install and configure the MCP Code Understanding Server.

---

## Instructions for AI Assistant

You are helping me set up the MCP Code Understanding Server. Please follow these steps:

### Step 1: Verify Prerequisites

First, check if the user has `uv` installed:

```bash
which uv
```

If not installed, guide them to install it:

```bash
# macOS/Linux
curl -sSf https://astral.sh/uv/install.sh | sh

# Windows PowerShell
irm https://astral.sh/uv/install.ps1 | iex
```

### Step 2: Install the MCP Server

Preferred quick start using `uvx` (no global install):

```bash
uvx code-understanding-mcp-server --help
```

Optional persistent install in a dedicated virtual environment:

```bash
# Create and activate a virtual environment
uv venv ~/.venvs/mcp-code-understanding
source ~/.venvs/mcp-code-understanding/bin/activate

# Install the package
uv pip install code-understanding-mcp-server

# Verify it runs
code-understanding-mcp-server --help
```

### Step 3: Verify Installation

Depending on the method used:

```bash
# If using uvx (no persistent binary)
uvx --version

# If using the virtual environment install
which code-understanding-mcp-server
# Expected example: /Users/username/.venvs/mcp-code-understanding/bin/code-understanding-mcp-server
```

### Step 4: Configure MCP Client

Help the user configure their MCP client. Recommend `uvx` for simplicity, or a direct venv path if installed into a venv.

```json
{
  "mcpServers": {
    "code-understanding": {
      "command": "uvx",
      "args": [
        "code-understanding-mcp-server"
      ],
      "env": {
        "GITHUB_PERSONAL_ACCESS_TOKEN": "your-github-token-here"
      }
    }
  }
}

If using a virtual environment install instead of `uvx`, point directly to the binary path:

```json
{
  "mcpServers": {
    "code-understanding": {
      "command": "/Users/username/.venvs/mcp-code-understanding/bin/code-understanding-mcp-server",
      "args": [],
      "env": {
        "GITHUB_PERSONAL_ACCESS_TOKEN": "your-github-token-here"
      }
    }
  }
}
```
```

### Important Notes

1. **Recommended**: Use `uvx` for simple, isolated execution without a persistent install
2. **Optional**: Use a dedicated virtual environment for a persistent binary path
3. **Use absolute paths** when referencing a venv binary in configuration
4. **Windows is unverified** - inform Windows users that it has not been tested yet

### Troubleshooting Common Issues

If the user encounters issues:

1. **Binary not found (venv method)**: Confirm the venv is activated or use the absolute venv path
2. **Dependency conflicts (uvx method)**: Switch to the virtual environment installation
3. **Permission errors**: Verify write access to cache directories

## Example User Interaction

**User**: "Help me set up the MCP code understanding server"

**AI Assistant**: "I'll help you set up the MCP Code Understanding Server. Let me guide you through the installation process.

First, let's check if you have `uv` installed:

```bash
which uv
```

[Continue with the steps above based on the user's responses]"

## Available MCP Tools

Once configured, the following tools will be available:

- `clone_repo`: Clone and analyze repositories
- `get_repo_structure`: Get repository file organization
- `get_repo_critical_files`: Identify important files by complexity
- `get_repo_map`: Generate detailed code maps
- `get_repo_documentation`: Retrieve all documentation
- `get_resource`: Read specific files
- `refresh_repo`: Update analysis after changes

## Configuration Options

The server supports these command-line options:

- `--cache-dir`: Custom cache directory (default: `~/.cache/mcp-code-understanding`)
- `--max-cached-repos`: Maximum cached repositories (default: 10)
- `--transport`: Transport type (`stdio` or `sse`, default: `stdio`)
- `--port`: SSE transport port (default: 3001)

## Environment Variables

- `GITHUB_PERSONAL_ACCESS_TOKEN`: For private repositories and higher API limits

Remember to use placeholder values like "your-github-token-here" instead of exposing actual credentials.