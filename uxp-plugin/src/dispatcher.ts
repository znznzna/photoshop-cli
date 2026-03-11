/**
 * dispatcher.ts - コマンドディスパッチャ
 *
 * group.action 形式のコマンドを適切なハンドラモジュールにルーティングする。
 */

import { HANDLERS as documentHandlers } from "./handlers/file";

type Handler = (params: Record<string, unknown>) => Promise<unknown>;

const HANDLER_MODULES: Record<string, Record<string, Handler>> = {
  document: documentHandlers,
  file: documentHandlers, // alias
};

const SYSTEM_HANDLERS: Record<string, Handler> = {
  ping: async () => ({ status: "ok", timestamp: Date.now() }),
};
HANDLER_MODULES["system"] = SYSTEM_HANDLERS;

export async function dispatch(
  command: string,
  params: Record<string, unknown>
): Promise<unknown> {
  const dotIndex = command.indexOf(".");
  if (dotIndex === -1) {
    throw Object.assign(new Error(`Invalid command format: ${command}`), {
      code: "UNKNOWN_COMMAND",
    });
  }
  const group = command.substring(0, dotIndex);
  const action = command.substring(dotIndex + 1);
  const handlers = HANDLER_MODULES[group];
  if (!handlers || !handlers[action]) {
    throw Object.assign(new Error(`Unknown command: ${command}`), {
      code: "UNKNOWN_COMMAND",
    });
  }
  return handlers[action](params);
}
