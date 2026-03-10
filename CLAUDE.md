# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## プロジェクト概要

Adobe Photoshop を CLI/MCP 経由で AI エージェントが操作するツール。

## アーキテクチャ

```
Claude Code → CLI(psd) / MCP → Python SDK (WSサーバー) ← UXP Plugin (WSクライアント) → Photoshop
```

- **逆転WebSocket接続**: Python SDK が WebSocket **サーバー**、UXP Plugin が WebSocket **クライアント**
- ポートファイル: `/tmp/photoshop_ws_port.txt`（`PS_PORT_FILE` 環境変数でオーバーライド可）
- CLI と MCP Server は共通の `_impl` 関数を呼び出す（ロジック重複禁止）

### コンポーネント構成

| ディレクトリ | 役割 |
|---|---|
| `photoshop_sdk/` | WebSocket通信・スキーマ・例外等のコアSDK |
| `cli/` | Click ベースの CLI (`psd` コマンド) |
| `cli/commands/` | CLI サブコマンド群 |
| `mcp_server/` | FastMCP ベースの MCP サーバー (`psd-mcp` コマンド) |
| `uxp-plugin/` | TypeScript 製 UXP Plugin (Photoshop側) |
| `tests/unit/` | ユニットテスト |
| `tests/integration/` | 統合テスト（mock使用、Photoshop不要） |
| `tests/fixtures/` | テストフィクスチャ（mock_uxp_client等） |

## 開発環境セットアップ

```bash
uv venv && source .venv/bin/activate
uv pip install -e ".[dev]"
```

## コマンド

```bash
# テスト
python -m pytest tests/unit/ -v                          # 全ユニットテスト
python -m pytest tests/unit/sdk/test_exceptions.py -v    # 単一テストファイル
python -m pytest tests/unit/ -v -k "test_name"           # 単一テスト

# Lint
ruff check .
ruff format .

# CLI 実行
psd file open /path/to/file.psd
psd file info --doc-id 1
psd file list
```

## Tech Stack

- Python 3.10+, Click 8.x, Pydantic 2.x, websockets 12.x, FastMCP 3.x, Rich
- TypeScript 5.x (UXP Plugin)
- テスト: pytest, pytest-asyncio
- Lint: ruff (line-length=120, select=E,F,W,I)

## 設計規約

- `asyncio_mode = "auto"` — テストの async は自動検出
- エラーは `photoshop_sdk/exceptions.py` の階層を使い、`ERROR_CODE_MAP` でUXP応答コードとマッピング
- WebSocket通信のスキーマは `photoshop_sdk/schema.py` で Pydantic モデルとして定義
- `ws_bridge.py` の `ResilientWSBridge` が接続管理・再接続を担当

## モデル設定

**Sonnetモデルのみ使用** - Taskツール起動時も `model: "sonnet"` を指定
