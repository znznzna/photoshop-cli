/**
 * ws_client.ts - WebSocket クライアント
 *
 * Python SDK (ResilientWSBridge) が起動する WS サーバーに接続する。
 * ポートは /tmp/photoshop_ws_port.txt から読み込む。
 *
 * 自動再接続: 切断時に指数バックオフで再接続を試みる。
 */

// UXP の fs モジュール（ポートファイル読み込み用）
const fs = require("uxp").storage.localFileSystem;

export type CommandHandler = (command: string, params: Record<string, unknown>) => Promise<unknown>;

interface CommandMessage {
  id: string;
  command: string;
  params: Record<string, unknown>;
}

interface ResponseMessage {
  id: string;
  success: boolean;
  result?: unknown;
  error?: { code: string; message: string };
}

const PORT_FILE_PATH = "/tmp/photoshop_ws_port.txt";
const MAX_RECONNECT_ATTEMPTS = 10;
const RECONNECT_BASE_DELAY_MS = 1000;

export class WSClient {
  private ws: WebSocket | null = null;
  private handler: CommandHandler | null = null;
  private reconnectAttempts = 0;
  private isShuttingDown = false;
  private reconnectTimer: ReturnType<typeof setTimeout> | null = null;

  setHandler(handler: CommandHandler): void {
    this.handler = handler;
  }

  async connect(): Promise<void> {
    const port = await this._readPort();
    const uri = `ws://localhost:${port}`;
    console.log(`[WS] Connecting to ${uri}`);

    this.ws = new WebSocket(uri);

    this.ws.addEventListener("open", () => {
      console.log("[WS] Connected to Python SDK");
      this.reconnectAttempts = 0;
    });

    this.ws.addEventListener("message", (event: MessageEvent) => {
      this._handleMessage(event.data as string);
    });

    this.ws.addEventListener("close", () => {
      console.log("[WS] Connection closed");
      this.ws = null;
      if (!this.isShuttingDown) {
        this._scheduleReconnect();
      }
    });

    this.ws.addEventListener("error", (event: Event) => {
      console.error("[WS] WebSocket error:", event);
    });
  }

  private async _readPort(): Promise<number> {
    try {
      // UXP の file API でポートファイルを読む
      const entry = await fs.getEntryWithUrl(`file://${PORT_FILE_PATH}`);
      const content = await entry.read({ format: "utf8" });
      return parseInt((content as string).trim(), 10);
    } catch (e) {
      throw new Error(`Failed to read port file at ${PORT_FILE_PATH}: ${e}`);
    }
  }

  private async _handleMessage(raw: string): Promise<void> {
    let msg: CommandMessage;
    try {
      msg = JSON.parse(raw) as CommandMessage;
    } catch (e) {
      console.error("[WS] Invalid JSON received:", raw);
      return;
    }

    if (!this.handler) {
      console.error("[WS] No handler registered");
      return;
    }

    let response: ResponseMessage;
    try {
      const result = await this.handler(msg.command, msg.params);
      response = { id: msg.id, success: true, result };
    } catch (e: unknown) {
      const error = e as Error & { code?: string };
      response = {
        id: msg.id,
        success: false,
        error: {
          code: error.code || "HANDLER_ERROR",
          message: error.message || String(e),
        },
      };
    }

    this._send(response);
  }

  private _send(data: unknown): void {
    if (this.ws && this.ws.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify(data));
    } else {
      console.error("[WS] Cannot send: not connected");
    }
  }

  private _scheduleReconnect(): void {
    if (this.reconnectAttempts >= MAX_RECONNECT_ATTEMPTS) {
      console.error("[WS] Max reconnect attempts reached");
      return;
    }
    const delay = RECONNECT_BASE_DELAY_MS * Math.pow(2, this.reconnectAttempts);
    console.log(`[WS] Reconnecting in ${delay}ms (attempt ${this.reconnectAttempts + 1})`);
    this.reconnectAttempts++;
    this.reconnectTimer = setTimeout(async () => {
      try {
        await this.connect();
      } catch (e) {
        console.error("[WS] Reconnect failed:", e);
        this._scheduleReconnect();
      }
    }, delay);
  }

  disconnect(): void {
    this.isShuttingDown = true;
    if (this.reconnectTimer) {
      clearTimeout(this.reconnectTimer);
    }
    if (this.ws) {
      this.ws.close();
      this.ws = null;
    }
  }
}

// シングルトン
export const wsClient = new WSClient();
