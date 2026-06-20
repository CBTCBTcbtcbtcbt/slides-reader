// 这里保存前端内部状态和交互类型。
// 这些类型不属于后端 API 契约，只用于组织 React 状态和组件 props。

import type { NoteBlockItem } from "./api";

export type HealthState = "checking" | "success" | "error";

export type UploadState = "idle" | "uploading" | "success" | "error";

export type LLMConfigState = "idle" | "loading" | "saving" | "testing" | "success" | "error";

export type ReaderState = "idle" | "loading" | "ready" | "error";

export type ReaderRightSidebar = "none" | "summary" | "chat" | "note";

export type ReaderWorkspaceSize = {
  width: number;
  height: number;
};

export type PdfPageNaturalSize = {
  width: number;
  height: number;
};

export type LoadedPdfPage = {
  originalWidth: number;
  originalHeight: number;
};

export type NoteBlockLayout = Pick<NoteBlockItem, "x" | "y" | "width" | "height">;

export type PendingChatAttachment = {
  id: string;
  file: File;
  previewUrl: string;
};

export type NoteBlockResizeDirection =
  | "top"
  | "right"
  | "bottom"
  | "left"
  | "topRight"
  | "bottomRight"
  | "bottomLeft"
  | "topLeft";

export type NoteBlockInteraction = {
  noteBlockId: string;
  layoutKey: string;
  documentId: string;
  mode: "drag" | "resize";
  resizeDirection: NoteBlockResizeDirection | null;
  startClientX: number;
  startClientY: number;
  startLayout: NoteBlockLayout;
};

export type DocumentActionState = {
  documentId: string;
  pageNumber?: number;
  action:
    | "renaming"
    | "deleting"
    | "regeneratingSummary"
    | "regeneratingLectureNotes"
    | "generatingRemainingLectureNotes"
    | "clearingLectureNotesQueue"
    | "pausingLectureNotes"
    | "resumingLectureNotes";
} | null;
