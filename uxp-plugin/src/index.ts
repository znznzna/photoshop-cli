/**
 * index.ts - UXP Plugin エントリポイント
 *
 * 1. WS クライアントを起動してポートファイルからサーバーアドレスを取得
 * 2. dispatcher を WS クライアントのハンドラとして登録
 * 3. Photoshop UXP Panel の entrypoint を export
 */

import { wsClient } from "./ws_client";
import { dispatch } from "./dispatcher";

// dispatcher を WS ハンドラとして登録
wsClient.setHandler(async (command, params) => {
  console.log(`[Plugin] Dispatching command: ${command}`);
  return dispatch(command, params);
});

// UXP entrypoint
module.exports = {
  panels: {
    mainPanel: {
      show({ node }: { node: Element }) {
        // Panel UI（最小限）
        node.innerHTML = `
          <sp-body>
            <h3>Photoshop CLI Bridge</h3>
            <p id="status">Starting...</p>
          </sp-body>
        `;

        const statusEl = node.querySelector("#status");

        // WS 接続開始
        wsClient
          .connect()
          .then(() => {
            if (statusEl) statusEl.textContent = "Connected to CLI";
          })
          .catch((e: Error) => {
            console.error("[Plugin] Failed to connect:", e);
            if (statusEl) statusEl.textContent = `Connection failed: ${e.message}`;
          });
      },
    },
  },
};
