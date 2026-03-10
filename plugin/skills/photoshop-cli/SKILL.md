---
name: photoshop-cli
description: |
  Control Adobe Photoshop via CLI (psd command) and MCP server.
  Use when user asks to open, close, or save PSD files, list open documents,
  get document info, or automate Photoshop workflows.
  Triggers: "Photoshopで開いて", "PSDファイルを", "ドキュメント一覧",
  "psd file", "photoshop操作", "レイヤー情報", "画像を保存".
  Do NOT use for Lightroom (use lightroom-cli skill), Figma, or other design tools.
---

# photoshop-cli

Adobe Photoshop を CLI/MCP 経由で制御するスキル。

## CRITICAL: エージェント不変条件

以下のルールは **必ず** 遵守すること。違反するとデータ損失やユーザーの信頼を損なう。

### 1. 変更操作の前にユーザー確認を取る

`file open`, `file close`, `file save` は Photoshop の状態を変更する。
実行前に必ずユーザーに確認を取ること。

```
NG: psd file close --doc-id 1
OK: 「Document 1 (photo.psd) を閉じてもよいですか？」→ 承認後に実行
```

### 2. 読み取り操作は `--output json` で呼ぶ

`file list` と `file info` は必ず `--output json` を指定すること。
テキスト出力はパースが不安定で、エージェントのハルシネーションの原因になる。

```bash
# 正しい
psd --output json file list
psd --output json file info --doc-id 1

# 間違い（パースエラーの原因）
psd file list
```

### 3. `--fields` でコンテキストウィンドウを節約する

必要なフィールドだけを取得すること。

```bash
psd --output json --fields documentId,name file list
psd --output json --fields width,height,resolution file info --doc-id 1
```

### 4. `--dry-run` で事前検証する

変更操作を実行する前に `--dry-run` で検証すること。

```bash
# まず dry-run で検証
psd --dry-run --output json file open /path/to/file.psd

# 成功を確認してから実行
psd --output json file open /path/to/file.psd
```

### 5. エラーハンドリング

exit code を確認し、適切に対処すること:

| Exit Code | 意味 | 対処 |
|---|---|---|
| 0 | 成功 | 続行 |
| 1 | 一般エラー | エラーメッセージを確認し、ユーザーに報告 |
| 2 | 接続エラー | Photoshop/プラグインの起動状態を確認するようユーザーに案内 |
| 3 | タイムアウト | `--timeout` を延長して再試行 |
| 4 | バリデーションエラー | 入力パラメータを修正して再試行 |

### 6. スキーマイントロスペクション

コマンドの引数やオプションが不明な場合は `psd schema` で確認すること。
ハルシネーションでパラメータを推測してはいけない。

```bash
psd --output json schema file.open   # file.open の引数を確認
psd --output json schema             # 全コマンド一覧
```

## 前提条件

1. Photoshop が起動していること
2. UXP Plugin（photoshop-cli-bridge）がインストール・アクティブであること
3. Python SDK が起動していること（`psd` コマンドが使えること）

## 接続フロー

```
Claude Code
    ↓ psd file list
CLI (psd)
    ↓ WebSocket送信
Python SDK (ResilientWSBridge) ← WS Server listening on port from /tmp/photoshop_ws_port.txt
    ↑ WebSocket接続
UXP Plugin (ws_client.ts) → Photoshop app API
```

## コマンドリファレンス

### ファイル操作

```bash
psd --output json file list                          # ドキュメント一覧
psd --output json file info --doc-id <ID>            # ドキュメント情報
psd --output json file open /path/to/file.psd        # ファイルを開く
psd --output json file close --doc-id <ID>           # 閉じる
psd --output json file close --doc-id <ID> --save    # 保存して閉じる
psd --output json file save --doc-id <ID>            # 保存
```

### グローバルオプション

| オプション | 短縮 | 説明 |
|---|---|---|
| `--output json\|text\|table` | `-o` | 出力形式（non-TTYデフォルト: json） |
| `--fields f1,f2` | `-f` | 出力フィールド絞り込み |
| `--dry-run` | | 検証のみ、実行しない |
| `--timeout <秒>` | `-t` | コマンドタイムアウト |
| `--verbose` | `-v` | デバッグログ出力 |

### exit codes

| Code | 意味 |
|------|------|
| 0 | 成功 |
| 1 | 一般エラー |
| 2 | 接続エラー（Photoshop未起動/プラグイン未接続） |
| 3 | タイムアウト |
| 4 | バリデーションエラー |

## Troubleshooting / Error Handling

### "UXP Plugin is not connected" error

1. Photoshop が起動しているか確認
2. UXP Developer Tool でプラグインが Active になっているか確認
3. ポートファイルが存在するか確認: `cat /tmp/photoshop_ws_port.txt`
4. `psd --output json file list` を再実行

### Timeout error

```bash
# Example: extend timeout for large files
psd --timeout 120 --output json file open /large/file.psd
```
