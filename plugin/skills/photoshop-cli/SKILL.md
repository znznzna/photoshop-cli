# photoshop-cli Skill

Adobe Photoshop を CLI/MCP 経由で制御するスキル。

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

## 利用可能コマンド

### ファイル操作

```bash
# 開いているドキュメント一覧
psd file list

# ドキュメント情報取得
psd file info --doc-id <ID>

# ファイルを開く
psd file open /path/to/file.psd

# ドキュメントを閉じる
psd file close --doc-id <ID>
psd file close --doc-id <ID> --save  # 保存してから閉じる

# ドキュメントを保存
psd file save --doc-id <ID>
```

### 出力形式

```bash
# JSON 出力（デフォルト: non-TTY）
psd --output json file list

# テキスト出力
psd --output text file list

# テーブル出力
psd --output table file list
```

### exit codes

| Code | 意味 |
|------|------|
| 0 | 成功 |
| 1 | 一般エラー |
| 2 | 接続エラー（Photoshop未起動/プラグイン未接続） |
| 3 | タイムアウト |
| 4 | バリデーションエラー |

## トラブルシューティング

### "UXP Plugin is not connected" エラー

1. Photoshop が起動しているか確認
2. UXP Developer Tool でプラグインが Active になっているか確認
3. `/tmp/photoshop_ws_port.txt` が存在するか確認: `cat /tmp/photoshop_ws_port.txt`
4. `psd file list` を再実行

### タイムアウトエラー

- `psd --timeout 120 file open /large/file.psd` でタイムアウトを延長

## 開発情報

- リポジトリ: `/Users/motokiendo/dev/photoshop-cli/`
- Python SDK: `photoshop_sdk/`
- UXP Plugin: `uxp-plugin/src/`
- テスト: `python -m pytest tests/unit/ -v`

## エージェント不変条件（Agent Invariants）

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

必要なフィールドだけを取得すること。全フィールドを取得するとコンテキストウィンドウを浪費する。

```bash
# ドキュメント一覧から名前とIDだけ取得
psd --output json --fields documentId,name file list

# ドキュメントのサイズ情報だけ取得
psd --output json --fields width,height,resolution file info --doc-id 1
```

### 4. `--dry-run` で事前検証する

変更操作を実行する前に `--dry-run` で検証すること。
バリデーションエラーを事前に検出し、不要な Photoshop 操作を防ぐ。

```bash
# まず dry-run で検証
psd --output json file open --dry-run /path/to/file.psd

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
# file.open の引数を確認
psd --output json schema file.open

# 全コマンド一覧
psd --output json schema
```
