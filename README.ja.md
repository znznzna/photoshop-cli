# photoshop-cli

[![Test](https://github.com/znznzna/photoshop-cli/actions/workflows/test.yml/badge.svg)](https://github.com/znznzna/photoshop-cli/actions/workflows/test.yml)
[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

[English](README.md)

**Adobe Photoshop を CLI/MCP 経由で AI エージェントが操作するツール。**

PSD ファイルのオープン・クローズ・保存、ドキュメント情報の取得、Photoshop ワークフローの自動化を実現します。

## アーキテクチャ

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

UXP プラグインが Photoshop 内で動作し、WebSocket クライアントとして Python SDK サーバーに接続します。`psd` CLI、Claude Desktop/Cowork 向け MCP Server、Python SDK の 3 つのインターフェースを提供します。

## クイックスタート

### 前提条件

- **Python 3.10+**
- **Adobe Photoshop**（UXP Plugin 対応版）
- macOS

### インストール

#### PyPI から

```bash
pip install photoshop-cli
```

#### ソースから

```bash
git clone https://github.com/znznzna/photoshop-cli.git
cd photoshop-cli
pip install -e ".[dev]"
```

### UXP Plugin セットアップ

1. UXP Developer Tool (UDT) を開く
2. `uxp-plugin/` ディレクトリからプラグインを読み込む
3. Photoshop でプラグインを有効化する

### 統合方法を選ぶ

#### 方法 A: Claude Code（SKILL ベース）

**Claude Code** ユーザー向け — Claude Code Plugin をインストール:

```bash
/plugin marketplace add znznzna/photoshop-cli
/plugin install photoshop-cli@photoshop-cli
```

#### 方法 B: Claude Desktop / Cowork（MCP Server）

**Claude Desktop** または **Cowork** ユーザー向け — MCP Server を登録:

```bash
psd mcp install
```

Claude Desktop / Cowork を再起動してください。

```bash
psd mcp status
psd mcp test      # Photoshop への接続テスト
```

#### 方法 C: CLI 直接使用 / スクリプティング

```bash
psd system ping
psd --output json file list
psd --output json file open /path/to/file.psd
```

### 接続確認

1. Photoshop を起動
2. UXP Plugin がロード・有効化されていることを確認
3. 実行:

```bash
psd system ping
# -> pong
```

## CLI リファレンス

### ファイル操作

```bash
psd --output json file list                          # 開いているドキュメント一覧
psd --output json file info --doc-id <ID>            # ドキュメント情報取得
psd --output json file open /path/to/file.psd        # ファイルを開く
psd --output json file close --doc-id <ID>           # ドキュメントを閉じる
psd --output json file close --doc-id <ID> --save    # 保存して閉じる
psd --output json file save --doc-id <ID>            # ドキュメントを保存
```

### システム操作

```bash
psd --output json system ping                        # 接続確認
```

### スキーマ確認

```bash
psd --output json schema                             # 全コマンド一覧
psd --output json schema file.open                   # file.open のスキーマ表示
```

### MCP Server 管理

```bash
psd mcp install                # MCP server を Claude Desktop に登録
psd mcp install --force        # 既存エントリを上書き
psd mcp uninstall              # MCP server を設定から削除
psd mcp status                 # インストール状態を表示
psd mcp test                   # 接続テスト
```

## グローバルオプション

```bash
psd --output json ...    # JSON 出力 (-o json)
psd --output table ...   # テーブル出力 (-o table)
psd --verbose ...        # デバッグログ (-v)
psd --timeout 60 ...     # タイムアウト秒数 (-t 60)
psd --dry-run ...        # 検証のみ、実行しない
psd --fields f1,f2 ...   # 出力フィールドフィルタ (-f f1,f2)
psd --version            # バージョン表示
```

## 設定

| 環境変数 | 説明 |
|---------|------|
| `PS_PORT_FILE` | WebSocket ポートファイルのパス（デフォルト: `/tmp/photoshop_ws_port.txt`） |
| `PS_VERBOSE` | 詳細ログを有効化 |

## 開発

```bash
git clone https://github.com/znznzna/photoshop-cli.git
cd photoshop-cli
pip install -e ".[dev]"

# テスト実行
python -m pytest tests/unit/ -v

# Lint
ruff check .
ruff format --check .
```

## ライセンス

[MIT](LICENSE)
