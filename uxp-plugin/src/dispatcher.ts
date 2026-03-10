/**
 * dispatcher.ts - コマンドディスパッチャ
 *
 * コマンド名に応じて適切なハンドラを呼び出す。
 */

import {
  handleFileOpen,
  handleFileClose,
  handleFileSave,
  handleFileInfo,
  handleFileList,
} from "./handlers/file";

type Handler = (params: Record<string, unknown>) => Promise<unknown>;

const COMMAND_MAP: Record<string, Handler> = {
  "file.open": handleFileOpen as Handler,
  "file.close": handleFileClose as Handler,
  "file.save": handleFileSave as Handler,
  "file.info": handleFileInfo as Handler,
  "file.list": handleFileList as Handler,
  "system.ping": async () => ({ status: "ok", timestamp: Date.now() }),
};

export async function dispatch(
  command: string,
  params: Record<string, unknown>
): Promise<unknown> {
  const handler = COMMAND_MAP[command];
  if (!handler) {
    const err = new Error(`Unknown command: ${command}`);
    (err as any).code = "UNKNOWN_COMMAND";
    throw err;
  }
  return handler(params);
}
