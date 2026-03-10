---
name: photoshop-cli
description: |
  Control Adobe Photoshop via CLI (psd command) and MCP server.
  Use when user asks to open, close, or save PSD files, list open documents,
  get document info, or automate Photoshop workflows.
  Triggers: "open in Photoshop", "PSD file", "document list", "psd file",
  "photoshop automation", "layer info", "save image", "Photoshopで開いて",
  "PSDファイルを", "ドキュメント一覧".
  Do NOT use for Lightroom (use lightroom-cli skill), Figma, or other design tools.
---

# photoshop-cli

Control Adobe Photoshop via CLI/MCP.

## CRITICAL: Agent Invariants

The following rules **MUST** be followed. Violations can cause data loss or break user trust.

### 1. Confirm with user before mutation operations

`file open`, `file close`, `file save` modify Photoshop state.
Always ask for user confirmation before executing.

```
BAD:  psd file close --doc-id 1
GOOD: "Close Document 1 (photo.psd)?" → execute after approval
```

### 2. Always use `--output json` for read operations

Always specify `--output json` for `file list` and `file info`.
Text output is unstable for parsing and causes agent hallucinations.

```bash
# Correct
psd --output json file list
psd --output json file info --doc-id 1

# Wrong (causes parse errors)
psd file list
```

### 3. Use `--fields` to save context window

Only fetch the fields you need.

```bash
psd --output json --fields documentId,name file list
psd --output json --fields width,height,resolution file info --doc-id 1
```

### 4. Use `--dry-run` for pre-validation

Validate mutation operations with `--dry-run` before executing.

```bash
# Validate first
psd --dry-run --output json file open /path/to/file.psd

# Execute after successful validation
psd --output json file open /path/to/file.psd
```

### 5. Error handling

Check exit codes and respond appropriately:

| Exit Code | Meaning | Action |
|---|---|---|
| 0 | Success | Continue |
| 1 | General error | Check error message, report to user |
| 2 | Connection error | Ask user to verify Photoshop/plugin is running |
| 3 | Timeout | Retry with extended `--timeout` |
| 4 | Validation error | Fix input parameters and retry |

### 6. Schema introspection

When unsure about command arguments or options, use `psd schema`.
Never hallucinate parameters.

```bash
psd --output json schema file.open   # Check file.open arguments
psd --output json schema             # List all commands
```

## Prerequisites

1. Photoshop is running
2. UXP Plugin (photoshop-cli-bridge) is installed and active
3. Python SDK is running (`psd` command is available)

## Connection Flow

```
Claude Code
    ↓ psd file list
CLI (psd)
    ↓ WebSocket
Python SDK (ResilientWSBridge) ← WS Server listening on port from /tmp/photoshop_ws_port.txt
    ↑ WebSocket connection
UXP Plugin (ws_client.ts) → Photoshop app API
```

## Command Reference

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
psd --output json system ping                        # Check connection to Photoshop
```

### Schema Introspection

```bash
psd --output json schema                             # List all available commands
psd --output json schema file.open                   # Show JSON schema for file.open
psd --output json schema system.ping                 # Show JSON schema for system.ping
```

### Global Options

| Option | Short | Description |
|---|---|---|
| `--output json\|text\|table` | `-o` | Output format (default: json for non-TTY) |
| `--fields f1,f2` | `-f` | Filter output fields |
| `--dry-run` | | Validate only, do not execute |
| `--timeout <sec>` | `-t` | Command timeout in seconds |
| `--verbose` | `-v` | Enable debug logging |

### Exit Codes

| Code | Meaning |
|------|---------|
| 0 | Success |
| 1 | General error |
| 2 | Connection error (Photoshop not running / plugin not connected) |
| 3 | Timeout |
| 4 | Validation error |

## Troubleshooting / Error Handling

### "UXP Plugin is not connected" error

1. Verify Photoshop is running
2. Check that the plugin is Active in UXP Developer Tool
3. Verify port file exists: `cat /tmp/photoshop_ws_port.txt`
4. Retry: `psd --output json file list`

### Timeout error

```bash
# Example: extend timeout for large files
psd --timeout 120 --output json file open /large/file.psd
```
