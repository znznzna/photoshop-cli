/**
 * index.ts - UXP Plugin エントリポイント
 */

const { entrypoints } = require("uxp");

import { wsClient } from "./ws_client";
import { dispatch } from "./dispatcher";

// dispatcher を WS ハンドラとして登録
wsClient.setHandler(async (command, params) => {
  console.log(`[Plugin] Dispatching command: ${command}`);
  return dispatch(command, params);
});

entrypoints.setup({
  panels: {
    mainPanel: {
      create(rootNode: any) {
        rootNode.innerHTML = `
          <sp-body>
            <h3>Photoshop CLI Bridge</h3>
            <p id="status">Starting...</p>
          </sp-body>
        `;

        const statusEl = rootNode.querySelector("#status");

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
      show() {},
    },
  },
});
