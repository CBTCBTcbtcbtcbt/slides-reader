// 文档、页面、讲稿和当前页问答相关 API。

import type {
  DocumentItem,
  DocumentStatusResponse,
  NoteBlockItem,
  PageChatResponse,
  PageItem,
  UploadResponse,
} from "../types/api";
import type { NoteBlockLayout } from "../types/ui";
import { requestJson, requestNoContent } from "./http";

export function listDocuments(): Promise<DocumentItem[]> {
  return requestJson<DocumentItem[]>("/api/documents", undefined, "文档列表加载失败");
}

export function readDocumentStatus(documentId: string): Promise<DocumentStatusResponse> {
  return requestJson<DocumentStatusResponse>(
    `/api/documents/${documentId}/status`,
    undefined,
    "生成进度加载失败",
  );
}

export function uploadDocument(file: File): Promise<UploadResponse> {
  // FormData 是浏览器上传文件时最常用的数据结构。
  const formData = new FormData();
  formData.append("file", file);

  return requestJson<UploadResponse>(
    "/api/documents",
    {
      method: "POST",
      body: formData,
    },
    "上传失败",
  );
}

export function renameDocument(documentId: string, title: string): Promise<DocumentItem> {
  return requestJson<DocumentItem>(
    `/api/documents/${documentId}`,
    {
      method: "PATCH",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ title }),
    },
    "重命名失败",
  );
}

export function deleteDocument(documentId: string): Promise<void> {
  return requestNoContent(
    `/api/documents/${documentId}`,
    {
      method: "DELETE",
    },
    "删除失败",
  );
}

export function regenerateCourseSummary(documentId: string): Promise<{ status: string; document_id: string }> {
  return requestJson(
    `/api/documents/${documentId}/course-summary/regenerate`,
    { method: "POST" },
    "重新生成失败",
  );
}

export function listDocumentPages(documentId: string): Promise<PageItem[]> {
  return requestJson<PageItem[]>(
    `/api/documents/${documentId}/pages`,
    undefined,
    "页面讲稿加载失败",
  );
}

export function submitPageChat(pageId: string, question: string): Promise<PageChatResponse> {
  return requestJson<PageChatResponse>(
    `/api/pages/${pageId}/chat`,
    {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ question }),
    },
    "当前页问答失败",
  );
}

export function updateNoteBlockPosition(
  noteBlockId: string,
  nextPosition: NoteBlockLayout,
): Promise<NoteBlockItem> {
  return requestJson<NoteBlockItem>(
    `/api/note-blocks/${noteBlockId}`,
    {
      method: "PATCH",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify(nextPosition),
    },
    "讲稿文字块位置保存失败",
  );
}

export function regenerateDocumentLectureNotes(
  documentId: string,
): Promise<{ status: string; document_id: string }> {
  return requestJson(
    `/api/documents/${documentId}/lecture-notes/regenerate`,
    { method: "POST" },
    "重新生成讲稿失败",
  );
}

export function toggleDocumentLectureNotesPaused(
  documentId: string,
  isPaused: boolean,
): Promise<{ status: string; document_id: string; lecture_notes_paused: boolean }> {
  const nextAction = isPaused ? "resume" : "pause";
  const errorPrefix = isPaused ? "继续逐页讲稿生成失败" : "暂停逐页讲稿生成失败";

  return requestJson(
    `/api/documents/${documentId}/lecture-notes/${nextAction}`,
    { method: "POST" },
    errorPrefix,
  );
}

export function regeneratePageLectureNotes(
  pageId: string,
): Promise<{ status: string; document_id: string; page_id: string; page_number: number }> {
  return requestJson(
    `/api/pages/${pageId}/regenerate`,
    { method: "POST" },
    "重新生成单页讲稿失败",
  );
}
