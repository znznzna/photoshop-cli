"""MCP Server instructions for AI agents."""

MCP_INSTRUCTIONS = """\
Adobe Photoshop control server.
Use the available tools to open, close, save, and inspect Photoshop documents.
Photoshop must be running with the UXP Plugin active.

## Risk Levels
- [risk:read] — Safe read-only operations
- [risk:write] — Modifies document state
- [risk:destructive] — Irreversible changes (none currently)

## Tags
- [mutating] — Changes Photoshop state
- [requires-confirm] — Confirm with user before executing
- [supports-dry-run] — Pass dry_run=true to validate without executing
"""
