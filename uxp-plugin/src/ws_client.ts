/**
 * ws_client.ts - WebSocket クライアント
 *
 * Python SDK (ResilientWSBridge) が起動する WS サーバーに接続する。
 * 固定ポート 49152 を使用（ポートファイル不要）。
 *
 * 自動再接続: 切断時に指数バックオフで再接続を試みる。
 *
 * FDリーク対策:
 * - イベントリスナーをメンバ変数に保持し、同じ参照で add/remove
 * - _cleanupSocket() でリスナー除去・close・null 化を一括実行
 * - isConnecting ガードで重複接続を防止
 * - ハンドラ内で const ws = this.ws ガードにより stale socket イベントを無視
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
  private isConnecting = false;
  private reconnectAttempts = 0;
  private reconnectTimer: ReturnType<typeof setTimeout> | null = null;

  // イベントリスナーをメンバ変数に保持（同じ参照で add/remove するため）
  private _onOpen: (() => void) | null = null;
  private _onMessage: ((event: MessageEvent) => void) | null = null;
  private _onClose: (() => void) | null = null;
  private _onError: ((event: Event) => void) | null = null;

  setHandler(handler: CommandHandler): void {
    this.handler = handler;
  }

  async connect(): Promise<void> {
    if (this.isConnecting) {
      console.log("[WS] Already connecting, skipping duplicate attempt");
      return;
    }
    this.isConnecting = true;

    // 古いソケットをクリーンアップ
    this._cleanupSocket();

    const uri = `ws://localhost:${DEFAULT_PORT}`;
    console.log(`[WS] Connecting to ${uri}`);

    return new Promise<void>((resolve, reject) => {
      let settled = false;

      const ws = new WebSocket(uri);
      this.ws = ws;

      this._onOpen = () => {
        if (ws !== this.ws) return; // stale socket guard
        console.log("[WS] Connected to Python SDK");
        this.reconnectAttempts = 0;
        this.isConnecting = false;
        if (!settled) {
          settled = true;
          resolve();
        }
      };

      this._onMessage = (event: MessageEvent) => {
        if (ws !== this.ws) return; // stale socket guard
        this._handleMessage(event.data as string);
      };

      this._onClose = () => {
        if (ws !== this.ws) return; // stale socket guard
        console.log("[WS] Connection closed");
        this._cleanupSocket();
        this.isConnecting = false;
        if (!this.isShuttingDown) {
          this._scheduleReconnect();
        }
        if (!settled) {
          settled = true;
          reject(new Error("WebSocket connection closed before open"));
        }
      };

      this._onError = (event: Event) => {
        if (ws !== this.ws) return; // stale socket guard
        console.error("[WS] WebSocket error:", event);
        this.isConnecting = false;
        if (!settled) {
          settled = true;
          reject(new Error("WebSocket connection failed"));
        }
      };

      ws.addEventListener("open", this._onOpen);
      ws.addEventListener("message", this._onMessage);
      ws.addEventListener("close", this._onClose);
      ws.addEventListener("error", this._onError);
    });
  }

  private _cleanupSocket(): void {
    const ws = this.ws;
    if (!ws) return;

    // リスナーを参照で除去
    if (this._onOpen) ws.removeEventListener("open", this._onOpen);
    if (this._onMessage) ws.removeEventListener("message", this._onMessage);
    if (this._onClose) ws.removeEventListener("close", this._onClose);
    if (this._onError) ws.removeEventListener("error", this._onError);

    // ソケットがまだ開いている/接続中ならクローズ
    if (ws.readyState === WebSocket.OPEN || ws.readyState === WebSocket.CONNECTING) {
      ws.close();
    }

    this.ws = null;
    this._onOpen = null;
    this._onMessage = null;
    this._onClose = null;
    this._onError = null;
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
    // 既存タイマーをクリアして重複防止
    if (this.reconnectTimer) {
      clearTimeout(this.reconnectTimer);
      this.reconnectTimer = null;
    }

    const delay = Math.min(
      RECONNECT_BASE_DELAY_MS * Math.pow(2, this.reconnectAttempts),
      RECONNECT_MAX_DELAY_MS
    );
    this.reconnectAttempts++;
    console.log(`[WS] Reconnecting in ${delay / 1000}s (attempt ${this.reconnectAttempts})`);
    this.reconnectTimer = setTimeout(async () => {
      this.reconnectTimer = null;
      try {
        await this.connect();
      } catch (e) {
        // connect 内の _onClose が _scheduleReconnect を呼ぶので
        // ここでは追加の再接続スケジュールは不要
      }
    }, delay);
  }

  disconnect(): void {
    this.isShuttingDown = true;
    if (this.reconnectTimer) {
      clearTimeout(this.reconnectTimer);
      this.reconnectTimer = null;
    }
    this._cleanupSocket();
  }
}

// シングルトン
export const wsClient = new WSClient();
