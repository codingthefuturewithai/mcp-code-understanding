### MCP Server Optional Parameters: Client Compatibility Issue and Solution

#### Overview
This page documents a client-compatibility issue with optional parameters in Python MCP servers (FastMCP) and the solution pattern we adopted.

#### Affected Components
- Python MCP SDKs using FastMCP server implementation
- Tool parameter definitions using optional types
- MCP clients that do client-side schema validation (e.g., Cursor, Ollama)

#### The Issue
Optional parameters defined with `Optional[T]` often fail client-side validation before the request reaches the server. The Pydantic/OpenAPI schema emits `anyOf` unions (e.g., `array | null`, `integer | null`), which certain MCP clients reject even when the payload is valid.

Common client errors:
- “Parameter must be one of types [integer, null], got string/number”
- “Parameter must be one of types [array, null], got array”
- “Input should be a valid string [input_type=list]”

#### Problem Examples (what fails)

```python
# Fails in some MCP clients due to anyOf unions
async def get_source_repo_map(
    repo_path: str,
    directories: Optional[List[str]] = None,  # ❌
    files: Optional[List[str]] = None,        # ❌
    max_tokens: Optional[int] = None,         # ❌
    branch: Optional[str] = None,             # ❌
    cache_strategy: str = "shared",
) -> dict:
    ...
```

Why it fails:
1. Schema is emitted as `anyOf` unions (e.g., `array|string|null`).
2. Some clients pre-validate strictly and reject values even when valid.
3. Errors occur client-side; server never receives the call.

#### Recommended Pattern (what works)

Use concrete types with sensible defaults, then treat “empty” as unset on the server side.

```python
# Works reliably across MCP clients
async def get_source_repo_map(
    repo_path: str,
    directories: List[str] = [],   # concrete list with empty default
    files: List[str] = [],         # concrete list with empty default
    max_tokens: int = 20000,       # concrete int default
    branch: str = "",              # empty string means “no branch filter”
    cache_strategy: str = "shared",
) -> dict:
    return await repo_map_builder.get_repo_map_content(
        repo_path=repo_path,
        files=files if files else None,
        directories=directories if directories else None,
        max_tokens=max_tokens,
        branch=branch or None,
        cache_strategy=cache_strategy,
    )
```

Use the same approach for other tools:
- `get_repo_structure(repo_path: str, directories: List[str] = [], include_files: bool = False, branch: str = "", cache_strategy: str = "shared")`
- `get_repo_critical_files(repo_path: str, files: List[str] = [], directories: List[str] = [], limit: int = 50, include_metrics: bool = True, branch: str = "", cache_strategy: str = "shared")`

#### Why This Works
- Schema simplicity: Emits plain `array`, `integer`, `string`, `boolean` types (no `anyOf`).
- Proven in the wild: Mirrors the Context7 MCP server (TypeScript + Zod preprocess/optional).
- Server-side flexibility: We convert `[]` and `""` to `None` internally as needed.
- Natural client behavior: Clients already send native JSON types (arrays, numbers, booleans, strings).

#### Implementation Results
- Fully exercised parameters: `List[str]`, `int`, `bool`, `str`
- Branch handling verified (`branch`, `cache_strategy: "per-branch"`)
- Mixed optional parameters in single calls work
- No client-side validation errors with Cursor

#### Migration Guide
Before (problematic):
```python
directories: Optional[List[str]] = None
files: Optional[List[str]] = None
max_tokens: Optional[int] = None
branch: Optional[str] = None
```

After (recommended):
```python
directories: List[str] = []
files: List[str] = []
max_tokens: int = 20000
branch: str = ""
```

Server-side handling:
```python
directories=directories if directories else None
files=files if files else None
branch=branch or None
```

#### Conclusion
Avoid `Optional[T]` in MCP tool signatures. Use concrete types with sensible defaults and interpret “empty” as unset in server logic. This eliminates client-side validation failures while preserving full functionality.


