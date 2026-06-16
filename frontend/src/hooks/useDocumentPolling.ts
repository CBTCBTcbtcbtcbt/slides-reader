import { useEffect, useRef } from "react";
import type { DocumentItem, DocumentStatusResponse } from "../types/api";

type UseDocumentPollingOptions = {
  // documents 是当前文档列表，hook 会从中找出仍需轮询生成状态的文档。
  documents: DocumentItem[];
  // documentStatusById 保存最近一次状态接口返回，后端的 should_poll 会决定是否继续轮询。
  documentStatusById: Record<string, DocumentStatusResponse>;
  // intervalMs 是轮询间隔，单位是毫秒。
  intervalMs: number;
  // loadDocumentStatus 由 App 提供，负责真正请求状态接口并合并结果。
  loadDocumentStatus: (documentId: string) => Promise<DocumentStatusResponse | null>;
};

function shouldPollDocumentStatus(statusData: DocumentStatusResponse | undefined) {
  // 后端会直接返回 should_poll；前端额外允许 undefined 时不继续轮询。
  return Boolean(statusData?.should_poll);
}

function shouldPollDocumentWithoutCachedStatus(document: DocumentItem) {
  // 首次状态接口尚未返回时，用文档列表里的粗略状态判断是否需要开始轮询。
  return (
    document.status === "processing" ||
    document.course_summary_status === "processing" ||
    (document.status === "processing" && document.course_summary_status === "pending")
  );
}

export function useDocumentPolling({
  documents,
  documentStatusById,
  intervalMs,
  loadDocumentStatus,
}: UseDocumentPollingOptions) {
  const latestLoadDocumentStatusRef = useRef(loadDocumentStatus);

  useEffect(() => {
    // 定时器回调使用最新的请求函数，但不因为函数身份变化反复重建定时器。
    latestLoadDocumentStatusRef.current = loadDocumentStatus;
  }, [loadDocumentStatus]);

  useEffect(() => {
    const documentIdsNeedingStatus = documents
      .filter((document) => {
        const statusData = documentStatusById[document.document_id];

        if (statusData) {
          return shouldPollDocumentStatus(statusData);
        }

        return shouldPollDocumentWithoutCachedStatus(document);
      })
      .map((document) => document.document_id);

    if (documentIdsNeedingStatus.length === 0) {
      return;
    }

    let isCancelled = false;

    async function pollDocumentStatuses() {
      for (const documentId of documentIdsNeedingStatus) {
        if (isCancelled) {
          return;
        }

        await latestLoadDocumentStatusRef.current(documentId);
      }
    }

    const intervalId = window.setInterval(() => {
      void pollDocumentStatuses();
    }, intervalMs);

    return () => {
      isCancelled = true;
      window.clearInterval(intervalId);
    };
  }, [documents, documentStatusById, intervalMs]);
}
