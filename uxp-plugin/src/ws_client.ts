/**
 * ws_client.ts - WebSocket クライアント
 *
 * Python SDK (ResilientWSBridge) が起動する WS サーバーに接続する。
 * 固定ポート 49152 を使用（ポートファイル不要）。
 *
 * 自動再接続: 切断時に指数バックオフで再接続を試みる。
 */

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

const DEFAULT_PORT = 49152;
const RECONNECT_BASE_DELAY_MS = 2000;
const RECONNECT_MAX_DELAY_MS = 60000;

export class WSClient {
  private ws: WebSocket | null = null;
  private handler: CommandHandler | null = null;
  private isShuttingDown = false;
  private reconnectAttempts = 0;
  private reconnectTimer: ReturnType<typeof setTimeout> | null = null;

  setHandler(handler: CommandHandler): void {
    this.handler = handler;
  }

  async connect(): Promise<void> {
    const uri = `ws://localhost:${DEFAULT_PORT}`;
    console.log(`[WS] Connecting to ${uri}`);

    return new Promise<void>((resolve, reject) => {
      this.ws = new WebSocket(uri);

      this.ws.addEventListener("open", () => {
        console.log("[WS] Connected to Python SDK");
        this.reconnectAttempts = 0;
        resolve();
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
        if (this.ws?.readyState !== WebSocket.OPEN) {
          reject(new Error("WebSocket connection failed"));
        }
      });
    });
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
    const delay = Math.min(
      RECONNECT_BASE_DELAY_MS * Math.pow(2, this.reconnectAttempts),
      RECONNECT_MAX_DELAY_MS
    );
    this.reconnectAttempts++;
    console.log(`[WS] Reconnecting in ${delay / 1000}s (attempt ${this.reconnectAttempts})`);
    this.reconnectTimer = setTimeout(async () => {
      try {
        await this.connect();
      } catch (e) {
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
