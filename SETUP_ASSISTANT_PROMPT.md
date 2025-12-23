# Setup Assistant Prompt for MCP Code Understanding Server

Copy and paste this entire prompt to your AI coding assistant to help you install and configure the MCP Code Understanding Server.

## Your Task

Guide me through installing and configuring the MCP Code Understanding Server so I can use it with my AI coding tools. Use safe, copy-pastable commands and avoid exposing any sensitive information.

## What This Server Does

The MCP Code Understanding Server analyzes repositories and provides rich code context to AI assistants, including:
- Repository structure and organization
- Critical file identification using complexity/structure
- Documentation discovery and categorization
- Repository maps of functions, classes, and relationships

## Prerequisites You Should Check

Before installation, verify:
- Python 3.11 or 3.12 is available
- Git is installed
- `uv` (modern Python package manager) is installed
- macOS or Linux (Windows is currently unverified/not yet tested)

Commands to check:
```bash
python3 --version || python --version
git --version
which uv || command -v uv
```

If `uv` is missing, install it:
```bash
# macOS/Linux
curl -sSf https://astral.sh/uv/install.sh | sh

# Windows PowerShell (Windows usage unverified for this server; included for completeness)
irm https://astral.sh/uv/install.ps1 | iex
```

## Installation Paths

Choose ONE of these paths depending on whether I want to run from PyPI (simplest) or from the cloned source (development).

### Path A: Use PyPI (Recommended for most users)

Run the server directly with `uvx` (no persistent install):
```bash
uvx code-understanding-mcp-server --help
```

Optional: Create a dedicated virtual environment for a persistent binary:
```bash
uv venv ~/.venvs/mcp-code-understanding
source ~/.venvs/mcp-code-understanding/bin/activate
uv pip install code-understanding-mcp-server
code-understanding-mcp-server --help
```

### Path B: Run from Cloned Source (Development)

Assuming I have already cloned the repo and am in its root directory:
```bash
# 1) Create a virtual environment
uv venv

# 2) Activate it (macOS/Linux)
source .venv/bin/activate

# 3) Install in editable mode with dev extras
uv pip install -e ".[dev]"

# 4) Run tests to validate setup (optional)
uv run pytest

# 5) Launch the server for local testing (stdio transport by default)
uv run code-understanding-mcp-server --help

# 6) Alternatively, use the MCP inspector (optional)
uv run mcp dev src/code_understanding/mcp/server/app.py
```

## Configure an MCP Client

You should propose one of the following configurations:

### Option 1: Use `uvx` directly (simple and robust)
```json
{
  "mcpServers": {
    "code-understanding": {
      "command": "uvx",
      "args": ["code-understanding-mcp-server"],
      "env": {
        "GITHUB_PERSONAL_ACCESS_TOKEN": "your-github-token-here"
      }
    }
  }
}
```

### Option 2: Use the binary inside a dedicated virtual environment
Replace the command path with my actual venv path.
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

Notes:
- Windows is currently not supported. If I am on Windows, tell me this and stop.
- If I don’t use a venv, prefer Option 1 with `uvx`.

## Optional: GitHub Authentication

If I need access to private repos or to avoid rate limits, include the environment variable in the MCP config:
```json
{
  "mcpServers": {
    "code-understanding": {
      "command": "uvx",
      "args": ["code-understanding-mcp-server"],
      "env": {
        "GITHUB_PERSONAL_ACCESS_TOKEN": "your-github-token-here"
      }
    }
  }
}
```
Do not ask me to paste tokens into chat. Use placeholders and tell me where to set them.

## Advanced Options (Optional)

If I ask for advanced config, show how to pass arguments:
```json
{
  "mcpServers": {
    "code-understanding": {
      "command": "uvx",
      "args": [
        "code-understanding-mcp-server",
        "--cache-dir", "~/.cache/mcp-code-understanding",
        "--max-cached-repos", "10",
        "--transport", "stdio",
        "--port", "3001"
      ]
    }
  }
}
```
Available options:
- `--cache-dir`: Override repository cache directory (default: `~/.cache/mcp-code-understanding`)
- `--max-cached-repos`: Maximum cached repositories (default: 10)
- `--transport`: `stdio` or `sse` (default: `stdio`)
- `--port`: Port for SSE transport (default: 3001; only for `sse`)

## Validate the Setup

Have me run a quick validation:
```bash
# If using uvx
uvx code-understanding-mcp-server --help

# If using a venv binary
code-understanding-mcp-server --help
```

If I’m developing locally, you can also suggest:
```bash
uv run pytest
```

## Troubleshooting

Common issues and fixes:
1. Binary not found (venv): Ensure the venv is activated or use the absolute venv path in configuration
2. Dependency conflicts using `uvx`: Prefer the dedicated virtual environment install
3. Permission issues for cache: Ensure write access to `~/.cache/mcp-code-understanding` (or the configured cache directory)
4. Windows: Inform me that Windows is not supported yet

## Your Helpful Actions

You CAN safely:
- Run non-interactive commands on my behalf (e.g., verifying versions, installing dependencies with `uv`)
- Detect my OS and tailor instructions (macOS/Linux only; Windows not supported)
- Determine my home directory for example paths
- Generate MCP configuration JSON with placeholders
- Validate the server runs with `--help`

You CANNOT:
- Ask for or handle my GitHub token
- Modify my secret environment variables directly
- Access private repositories unless I configure the token myself

## Success Criteria

When finished, I should be able to:
- Launch the server with `uvx code-understanding-mcp-server --help` (or via a venv binary)
- Add the MCP server to my AI client configuration and connect over stdio
- Optionally set `GITHUB_PERSONAL_ACCESS_TOKEN` for private repos
- Use the server to analyze repositories via my AI assistant

# Setup Assistant Prompt for RAG Retriever

Read this entire prompt, then help me set up RAG Retriever - a semantic search system that crawls websites, indexes content, and provides AI-powered search capabilities through an MCP server.

## Your Task

I need you to guide me through installing and configuring RAG Retriever so I can:
- Index websites and documents into searchable collections
- Perform semantic search across my indexed content
- Use it as an MCP server with Claude Code for knowledge management

## What RAG Retriever Does

RAG Retriever is a semantic search system that:
- Crawls websites with Playwright or Crawl4AI (20x faster)
- Indexes content into ChromaDB vector collections
- Provides semantic search via OpenAI embeddings
- Offers MCP server integration for AI coding assistants
- Supports multiple collections for organized knowledge management

## Prerequisites You Should Check

Before we start, verify I have:
- Python 3.10+ installed
- OpenAI API key (but DON'T ask me to show it to you)
- Git installed
- Sufficient disk space (ChromaDB and browser dependencies)

## Installation Steps You'll Help Me With

### 1. Install RAG Retriever

#### Recommended Method (Most Reliable)
Use `uv tool install` for complete isolation from other Python projects:

```bash
# Install uv if not already installed
curl -LsSf https://astral.sh/uv/install.sh | sh  # macOS/Linux
# Or visit https://github.com/astral-sh/uv for Windows

# Install using uv tool (recommended)
uv tool install rag-retriever

# Find where the executable is installed (needed for MCP server setup later)
uv tool dir
```

The executable will be installed in something like:
- **macOS**: `/Users/YOUR_USERNAME/.local/share/uv/tools/rag-retriever/bin/rag-retriever`
- **Windows**: `C:\Users\YOUR_USERNAME\AppData\Roaming\uv\tools\rag-retriever\Scripts\rag-retriever.exe`
- **Linux**: `/home/YOUR_USERNAME/.local/share/uv/tools/rag-retriever/bin/rag-retriever`

#### Quick Start with uvx (Less Desirable)
For quick testing only - may cause Python dependency conflicts:

```bash
# Quick test (shared environment - may have conflicts)
uvx rag-retriever --help
```

⚠️ **Warning**: Using `uvx` runs packages in a shared environment which can lead to dependency conflicts with other Python tools. For any real usage, always prefer `uv tool install`.

**Note**: If you want to use pip, pipx, or development installation, you're on your own. We only support and recommend uv tool install (preferred) or uvx (quick testing only).

### 2. Initialize Configuration
Run the initialization command:
```bash
rag-retriever --init
```

This creates a config file with ALL settings pre-configured:
- **macOS/Linux**: `~/.config/rag-retriever/config.yaml`
- **Windows**: `%APPDATA%\rag-retriever\config.yaml`

### 3. Configure API Key (ONLY Required Change)
**CRITICAL**: The config file has everything pre-configured EXCEPT the OpenAI API key.

**You should:**
- Tell me the exact location of my config file
- Show me that I only need to replace `null` with my API key
- Remind me to keep my API key secret
- **NEVER** ask me to show you the API key

**Find this section in config.yaml and replace `null`:**
```yaml
api:
  openai_api_key: sk-your-actual-api-key-here  # Change from: null
```

**Everything else in the config can stay as-is for basic usage.**

### 4. Verify Browser Installation (Usually Not Needed)
The pipx installation should have automatically installed browsers. Test:
```bash
rag-retriever --help
```

If you see browser-related errors, run:
```bash
python -m playwright install chromium
```

### 5. System Validation
Test that everything is working:
```bash
rag-retriever --help
```

### 6. MCP Server Setup (Optional but Recommended)
If I want to use RAG Retriever with Claude Code:

#### For Claude Desktop
Add to your Claude Desktop configuration file:

**macOS**: `~/Library/Application Support/Claude/claude_desktop_config.json`
**Windows**: `%APPDATA%\Claude\claude_desktop_config.json`

```json
{
  "mcpServers": {
    "rag-retriever": {
      "command": "/absolute/path/to/uv/tools/rag-retriever/bin/rag-retriever",
      "args": ["--mcp"],
      "env": {
        "OPENAI_API_KEY": "your-api-key-here"
      }
    }
  }
}
```

Replace `/absolute/path/to/uv/tools/rag-retriever` with the actual path from `uv tool dir`.

#### For Claude Code CLI
**You should automatically determine the uv tools directory:**
Run this to get the tools directory:
```bash
uv tool dir
```

Then use that path to construct the command. For example, if the tools directory is `/Users/username/.local/share/uv/tools`, the command would be:
```bash
claude mcp add-json -s user rag-retriever '{"type":"stdio","command":"/Users/username/.local/share/uv/tools/rag-retriever/bin/mcp-rag-retriever"}'
```

**Important**: Replace the path with MY actual tools directory from the `uv tool dir` command above.

#### For Other AI Assistants (Windsurf, Cursor, etc.)
If I want to use RAG Retriever with other AI coding assistants, provide this JSON configuration (use path from `uv tool dir`):
```json
"rag-retriever": {
  "command": "/path/from/uv/tool/dir/rag-retriever/bin/mcp-rag-retriever"
}
```

**Windows users**: The path will use backslashes, like `C:\Users\...\AppData\Roaming\uv\tools\rag-retriever\Scripts\mcp-rag-retriever.exe`

**Grant Permissions in Claude Code:**
Edit `~/.claude/settings.json` to add:
```json
"mcp__rag-retriever__*"
```

### 7. Test Basic Installation
Create a simple test collection:
```bash
rag-retriever --fetch "https://example.com" --collection test
```

Then search it:
```bash
rag-retriever --search "test query" --collection test
```

### 8. Test MCP Integration with Real Content
If MCP setup was completed, test with Claude Code by indexing the official Claude Code documentation:

**In Claude Code, run this command to index Claude Code docs:**
```
/index-website "https://docs.anthropic.com/en/docs/claude-code/overview 3 claude_code_docs"
```

This will:
- Crawl the Claude Code documentation site
- Index to depth 3 (comprehensive coverage)
- Store in a collection named "claude_code_docs"
- Take 1-2 minutes to complete

**Wait 1-2 minutes for crawling to complete, then test search:**
```
/search-knowledge "setup MCP server claude_code_docs"
```

This should return relevant information about MCP server setup from the Claude Code documentation, proving the system is working end-to-end.

## Important Configuration Options

### Crawler Selection
RAG Retriever supports two crawlers:
- **Playwright**: Reliable, standard web crawling
- **Crawl4AI**: 20x faster with aggressive content filtering

To use Crawl4AI, edit config.yaml:
```yaml
crawler:
  type: "crawl4ai"
```

### Collection Organization
Plan collection naming strategy:
- Use descriptive names: `python_docs`, `company_wiki`, `claude_code_docs`
- Consider topic-based organization
- Default collection is called `default`

## Common Issues to Watch For

### 1. System Dependencies
- If playwright install fails, try: `pip install playwright==1.49.0`
- If Git is missing, install from: https://git-scm.com/
- If Python is too old, upgrade to 3.10+

### 2. API Key Issues
- Key must start with `sk-`
- Set environment variable: `export OPENAI_API_KEY=sk-...` (but don't show me the key)
- Verify key has credits in OpenAI dashboard

### 3. Crawler Dependencies
- Chromium download can be slow/fail - retry if needed
- Crawl4AI requires additional system dependencies
- System validation runs automatically and shows clear error messages

### 4. Permission Issues
- Config directory may need creation
- MCP server needs proper permissions in Claude Code
- Use `--verbose` flag for debugging

## Advanced Options

### UI Interface
Launch web interface:
```bash
rag-retriever --ui
```

### Custom Configuration
Edit config.yaml to customize:
- Embedding models
- Chunk sizes
- Browser settings
- Search thresholds

## Your Helpful Actions

**You CAN safely:**
- Run installation commands on my behalf (pipx, pip, playwright install)
- Check system requirements (python --version, git --version)
- Determine my home directory path (echo $HOME)
- Create directories and copy configuration templates
- Run help commands and system validation
- Test basic functionality
- Build the correct MCP command with my actual home directory path

**You CANNOT:**
- See or handle my API key
- Modify API key configuration directly
- Access my existing collections or data
- Run commands that might expose sensitive information

## Success Verification

After setup, I should be able to:
- Run `rag-retriever --help` without errors
- See config file at the correct OS path with only API key needing configuration
- Have chromium browser automatically installed
- Create and search collections via command line
- Use MCP server with Claude Code (if configured)
- Index Claude Code documentation and search it successfully

## Next Steps After Setup

Once installed, I can:
- Use `/list-collections` to see available collections
- Use `/index-website` to crawl and index websites
- Use `/search-knowledge` to search across collections
- Use `/audit-collections` to review collection health

Please guide me through each step, run safe commands on my behalf when possible, and help troubleshoot any issues that arise. Remember - never ask to see my API key!