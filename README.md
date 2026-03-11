# photoshop-cli

[![Test](https://github.com/znznzna/photoshop-cli/actions/workflows/test.yml/badge.svg)](https://github.com/znznzna/photoshop-cli/actions/workflows/test.yml)
[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

[Japanese / 日本語](README.ja.md)

**Control Adobe Photoshop from the command line via AI agents.**

Open, close, save PSD files, inspect document info, and automate Photoshop workflows through CLI or MCP server.

## Architecture

```
+---------------------+     WebSocket      +---------------+
|  Adobe Photoshop    |<------------------->|  Python SDK   |
|  (UXP Plugin)       |  WS Client → Server |               |
+---------------------+                    +-------+-------+
                                                   |
                                     +-------------+-------------+
                                     |             |             |
                              +------+------+ +----+-------+ +---+--------+
                              |  CLI (psd)  | | MCP Server | | Python SDK |
                              |  Click app  | | (psd-mcp)  | |   Direct   |
                              +-------------+ +------------+ +------------+
```

A UXP plugin runs inside Photoshop and connects as a WebSocket client to the Python SDK server. Three interfaces are available: the `psd` CLI, the MCP Server for Claude Desktop/Cowork, and the Python SDK for direct integration.

## Quick Start

### Prerequisites

- **Python 3.10+**
- **Adobe Photoshop** (with UXP Plugin support)
- macOS (Windows support planned)

### Installation

#### From PyPI

```bash
pip install photoshop-cli
```

#### From Source

```bash
git clone https://github.com/znznzna/photoshop-cli.git
cd photoshop-cli
pip install -e ".[dev]"
```

### UXP Plugin Setup

1. Open UXP Developer Tool (UDT)
2. Load the plugin from `uxp-plugin/` directory
3. Enable the plugin in Photoshop

### Choose Your Integration

#### Option A: Claude Code (SKILL-based)

For **Claude Code** users — install the Claude Code Plugin:

```bash
/plugin marketplace add znznzna/photoshop-cli
/plugin install photoshop-cli@photoshop-cli
```

The agent reads `SKILL.md` to discover available commands. No manual typing needed.

#### Option B: Claude Desktop / Cowork (MCP Server)

For **Claude Desktop** or **Cowork** users — register the MCP Server:

```bash
psd mcp install
```

Restart Claude Desktop / Cowork. Commands are available as MCP tools with `psd_` prefix.

Check MCP status:

```bash
psd mcp status
psd mcp test      # Test connection to Photoshop
```

#### Option C: Direct CLI / Scripting

Use the `psd` command directly:

```bash
psd system ping
psd --output json file list
psd --output json file open /path/to/file.psd
```

### Verify Connection

1. Open Photoshop
2. Ensure the UXP Plugin is loaded and active
3. Run:

```bash
psd system ping
# -> pong
```

## CLI Reference

### File Operations

```bash
psd --output json file list                          # List open documents
psd --output json file info --doc-id <ID>            # Get document info
psd --output json file open /path/to/file.psd        # Open file
psd --output json file close --doc-id <ID>           # Close document
psd --output json file close --doc-id <ID> --save    # Save and close
psd --output json file save --doc-id <ID>            # Save document
```

### System Operations

```bash
psd --output json system ping                        # Check connection
```

### Schema Introspection

```bash
psd --output json schema                             # List all commands
psd --output json schema file.open                   # Show schema for file.open
```

### MCP Server Management

```bash
psd mcp install                # Install MCP server to Claude Desktop
psd mcp install --force        # Overwrite existing entry
psd mcp uninstall              # Remove MCP server entry
psd mcp status                 # Show installation status
psd mcp test                   # Test connection via MCP
```

## Global Options

```bash
psd --output json ...    # JSON output (-o json)
psd --output table ...   # Table output (-o table)
psd --verbose ...        # Debug logging (-v)
psd --timeout 60 ...     # Timeout in seconds (-t 60)
psd --dry-run ...        # Validate only, do not execute
psd --fields f1,f2 ...   # Filter output fields (-f f1,f2)
psd --version            # Show version
```

## Configuration

| Environment Variable | Description |
|---------------------|-------------|
| `PS_PORT_FILE` | Path to the WebSocket port file (default: `/tmp/photoshop_ws_port.txt`) |
| `PS_VERBOSE` | Enable verbose logging |

## Features

- **Reverse WebSocket**: Python SDK runs as WS server, UXP Plugin connects as client
- **Auto-reconnect**: Automatically retries when connection drops (exponential backoff)
- **3 output formats**: `text` / `json` / `table`
- **Dry-run mode**: Validate commands without executing
- **Field filtering**: Return only the fields you need
- **Schema introspection**: Discover commands and parameters at runtime
- **MCP Server**: Native integration with Claude Desktop and Cowork

## Development

### For Contributors Only

> **Regular users can skip this section.** `pip install photoshop-cli` is all you need.

```bash
git clone https://github.com/znznzna/photoshop-cli.git
cd photoshop-cli
pip install -e ".[dev]"
```

```bash
# Run tests
python -m pytest tests/unit/ -v

# With coverage
python -m pytest tests/unit/ -v --cov=photoshop_sdk --cov=cli --cov=mcp_server

# Lint
ruff check .
ruff format --check .
```

## Project Structure

```
photoshop-cli/
+-- cli/                      # Click CLI application
|   +-- main.py               # Entry point (psd command)
|   +-- commands/             # Command groups
|       +-- file.py           # psd file
|       +-- system.py         # psd system
|       +-- schema.py         # psd schema
|       +-- mcp.py            # psd mcp
+-- mcp_server/               # MCP Server (FastMCP)
|   +-- server.py             # Entry point (psd-mcp command)
+-- photoshop_sdk/            # Python SDK
|   +-- client.py             # PhotoshopClient
|   +-- ws_bridge.py          # WebSocket bridge (server)
|   +-- schema.py             # Command schemas
|   +-- exceptions.py         # Exception hierarchy
+-- uxp-plugin/               # TypeScript UXP Plugin
|   +-- src/                  # Plugin source
|   +-- manifest.json         # UXP manifest
+-- tests/                    # pytest test suite
```

## Requirements

- Python >= 3.10
- Adobe Photoshop (with UXP support)
- macOS

### Python Dependencies

- [click](https://click.palletsprojects.com/) >= 8.1 — CLI framework
- [rich](https://rich.readthedocs.io/) >= 13.0 — Table output
- [pydantic](https://docs.pydantic.dev/) >= 2.0 — Data validation
- [websockets](https://websockets.readthedocs.io/) >= 12.0 — WebSocket communication
- [fastmcp](https://github.com/jlowin/fastmcp) >= 3.0 — MCP Server framework

## License

[MIT](LICENSE)
