# photoshop-cli

Adobe Photoshop を CLI / MCP 経由で AI エージェントが操作するツール。

## Architecture

```
Claude Code → CLI(psd) / MCP → Python SDK (WS Server) ← UXP Plugin (WS Client) → Photoshop
```

- Python SDK が WebSocket **サーバー**として起動（逆転接続）
- UXP Plugin が WebSocket **クライアント**として Photoshop 内から接続

## Install

```bash
uv venv && source .venv/bin/activate
uv pip install -e ".[dev]"
```

## Usage

```bash
psd file list
psd file open /path/to/file.psd
psd file info --doc-id 1
psd file close --doc-id 1
psd file save --doc-id 1
```

## License

MIT
