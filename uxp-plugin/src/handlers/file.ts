/**
 * file.ts - Photoshop ファイル操作ハンドラ
 *
 * コマンド: file.open, file.close, file.save, file.info, file.list
 */

const photoshop = require("photoshop");
const app = photoshop.app;

interface DocumentParams {
  documentId?: number;
  path?: string;
  save?: boolean;
}

function serializeDocument(doc: any): Record<string, unknown> {
  return {
    documentId: doc.id,
    name: doc.name,
    path: doc.path || null,
    width: doc.width,
    height: doc.height,
    colorMode: doc.mode?.toString() ?? null,
    resolution: doc.resolution ?? null,
    hasUnsavedChanges: doc.saved === false,
  };
}

export async function handleFileOpen(params: DocumentParams): Promise<unknown> {
  const { path } = params;
  if (!path) {
    const err = new Error("Parameter 'path' is required");
    (err as any).code = "VALIDATION_ERROR";
    throw err;
  }

  const doc = await app.open(path);
  return serializeDocument(doc);
}

export async function handleFileClose(params: DocumentParams): Promise<unknown> {
  const { documentId, save = false } = params;
  if (documentId === undefined) {
    const err = new Error("Parameter 'documentId' is required");
    (err as any).code = "VALIDATION_ERROR";
    throw err;
  }

  const doc = app.documents.find((d: any) => d.id === documentId);
  if (!doc) {
    const err = new Error(`Document with ID '${documentId}' not found`);
    (err as any).code = "DOCUMENT_NOT_FOUND";
    throw err;
  }

  if (save) {
    await doc.save();
  }
  await doc.close(save ? photoshop.constants.SaveOptions.SAVECHANGES : photoshop.constants.SaveOptions.DONOTSAVECHANGES);

  return { closed: true, documentId };
}

export async function handleFileSave(params: DocumentParams): Promise<unknown> {
  const { documentId } = params;
  if (documentId === undefined) {
    const err = new Error("Parameter 'documentId' is required");
    (err as any).code = "VALIDATION_ERROR";
    throw err;
  }

  const doc = app.documents.find((d: any) => d.id === documentId);
  if (!doc) {
    const err = new Error(`Document with ID '${documentId}' not found`);
    (err as any).code = "DOCUMENT_NOT_FOUND";
    throw err;
  }

  await doc.save();
  return { saved: true, documentId };
}

export async function handleFileInfo(params: DocumentParams): Promise<unknown> {
  const { documentId } = params;
  if (documentId === undefined) {
    const err = new Error("Parameter 'documentId' is required");
    (err as any).code = "VALIDATION_ERROR";
    throw err;
  }

  const doc = app.documents.find((d: any) => d.id === documentId);
  if (!doc) {
    const err = new Error(`Document with ID '${documentId}' not found`);
    (err as any).code = "DOCUMENT_NOT_FOUND";
    throw err;
  }

  return serializeDocument(doc);
}

export async function handleFileList(_params: DocumentParams): Promise<unknown> {
  const documents = Array.from(app.documents).map((doc: any) => serializeDocument(doc));
  return { documents };
}
