// 文档、页面、讲稿和当前页问答相关 API。

import type {
  DocumentItem,
  DocumentStatusResponse,
  NoteBlockItem,
  PageChatResponse,
  PageChatStreamEvent,
  PageItem,
  UploadResponse,
} from "../types/api";
import type { NoteBlockLayout } from "../types/ui";
import { readErrorMessage, requestJson, requestNoContent } from "./http";

export function listDocuments(): Promise<DocumentItem[]> {
  return requestJson<DocumentItem[]>("api/documents", undefined, "文档列表加载失败");
}

export function readDocumentStatus(documentId: string): Promise<DocumentStatusResponse> {
  return requestJson<DocumentStatusResponse>(
    `api/documents/${documentId}/status`,
    undefined,
    "生成进度加载失败",
  );
}

export function uploadDocument(file: File): Promise<UploadResponse> {
  // FormData 是浏览器上传文件时最常用的数据结构。
  const formData = new FormData();
  formData.append("file", file);

  return requestJson<UploadResponse>(
    "api/documents",
    {
      method: "POST",
      body: formData,
    },
    "上传失败",
  );
}

export function renameDocument(documentId: string, title: string): Promise<DocumentItem> {
  return requestJson<DocumentItem>(
    `api/documents/${documentId}`,
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
    `api/documents/${documentId}`,
    {
      method: "DELETE",
    },
    "删除失败",
  );
}

export function regenerateCourseSummary(documentId: string): Promise<{ status: string; document_id: string }> {
  return requestJson(
    `api/documents/${documentId}/course-summary/regenerate`,
    { method: "POST" },
    "重新生成失败",
  );
}

export function listDocumentPages(documentId: string): Promise<PageItem[]> {
  return requestJson<PageItem[]>(
    `api/documents/${documentId}/pages`,
    undefined,
    "页面讲稿加载失败",
  );
}

export function submitPageChat(
  pageId: string,
  question: string,
  attachments: File[] = [],
): Promise<PageChatResponse> {
  if (attachments.length > 0) {
    // 有图片时必须使用 FormData，浏览器会自动生成 multipart 边界。
    const formData = new FormData();
    formData.append("question", question);
    attachments.forEach((attachment) => {
      formData.append("attachments", attachment, attachment.name);
    });

    return requestJson<PageChatResponse>(
      `api/pages/${pageId}/chat`,
      {
        method: "POST",
        body: formData,
      },
      "当前页问答失败",
    );
  }

  return requestJson<PageChatResponse>(
    `api/pages/${pageId}/chat`,
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

type SubmitPageChatStreamOptions = {
  // signal 用于 AbortController 中断正在进行的流式请求。
  signal: AbortSignal;
  // onEvent 会在每读取到一行 NDJSON 事件时被调用，组件据此实时更新界面。
  onEvent: (event: PageChatStreamEvent) => void;
};

export async function submitPageChatStream(
  pageId: string,
  question: string,
  attachments: File[] = [],
  options: SubmitPageChatStreamOptions,
): Promise<void> {
  // 有图片时使用 FormData；无图片时仍使用 JSON，保持和非流式接口一致的兼容规则。
  const requestInit: RequestInit =
    attachments.length > 0
      ? {
          method: "POST",
          body: (() => {
            const formData = new FormData();
            formData.append("question", question);
            attachments.forEach((attachment) => {
              formData.append("attachments", attachment, attachment.name);
            });
            return formData;
          })(),
          signal: options.signal,
        }
      : {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
          },
          body: JSON.stringify({ question }),
          signal: options.signal,
        };

  const response = await fetch(`api/pages/${pageId}/chat/stream`, requestInit);
  if (!response.ok) {
    const message = await readErrorMessage(
      response,
      `当前页问答失败，HTTP 状态码：${response.status}`,
    );
    throw new Error(message);
  }

  if (!response.body) {
    throw new Error("浏览器没有返回可读取的流式响应。");
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let bufferedText = "";

  while (true) {
    const { value, done } = await reader.read();
    bufferedText += decoder.decode(value, { stream: !done });

    const lines = bufferedText.split("\n");
    bufferedText = lines.pop() ?? "";
    for (const line of lines) {
      const trimmedLine = line.trim();
      if (!trimmedLine) {
        continue;
      }
      options.onEvent(JSON.parse(trimmedLine) as PageChatStreamEvent);
    }

    if (done) {
      break;
    }
  }

  const remainingLine = bufferedText.trim();
  if (remainingLine) {
    options.onEvent(JSON.parse(remainingLine) as PageChatStreamEvent);
  }
}

export function updateNoteBlockPosition(
  noteBlockId: string,
  nextPosition: NoteBlockLayout,
): Promise<NoteBlockItem> {
  return requestJson<NoteBlockItem>(
    `api/note-blocks/${noteBlockId}`,
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
    `api/documents/${documentId}/lecture-notes/regenerate`,
    { method: "POST" },
    "重新生成讲稿失败",
  );
}

export function clearDocumentLectureNotesQueue(
  documentId: string,
): Promise<{ status: string; document_id: string; cleared_count: number }> {
  return requestJson(
    `api/documents/${documentId}/lecture-notes/queue`,
    { method: "DELETE" },
    "清空待生成队列失败",
  );
}

export function generateRemainingLectureNotes(
  documentId: string,
): Promise<{ status: string; document_id: string; queued_count: number; started: boolean }> {
  return requestJson(
    `api/documents/${documentId}/lecture-notes/remaining`,
    { method: "POST" },
    "生成剩余讲稿失败",
  );
}

export function toggleDocumentLectureNotesPaused(
  documentId: string,
  isPaused: boolean,
): Promise<{ status: string; document_id: string; lecture_notes_paused: boolean }> {
  const nextAction = isPaused ? "resume" : "pause";
  const errorPrefix = isPaused ? "继续逐页讲稿生成失败" : "暂停逐页讲稿生成失败";

  return requestJson(
    `api/documents/${documentId}/lecture-notes/${nextAction}`,
    { method: "POST" },
    errorPrefix,
  );
}

export function regeneratePageLectureNotes(
  pageId: string,
): Promise<{ status: string; document_id: string; page_id: string; page_number: number }> {
  return requestJson(
    `api/pages/${pageId}/regenerate`,
    { method: "POST" },
    "重新生成单页讲稿失败",
  );
}
