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
