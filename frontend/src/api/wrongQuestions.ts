// 错题本相关 API。

import type { WrongQuestionItem } from "../types/api";
import { requestJson, requestNoContent } from "./http";

export function listWrongQuestions(): Promise<WrongQuestionItem[]> {
  return requestJson<WrongQuestionItem[]>("api/wrong-questions", undefined, "错题本加载失败");
}

export function listDocumentWrongQuestions(documentId: string): Promise<WrongQuestionItem[]> {
  return requestJson<WrongQuestionItem[]>(
    `api/documents/${documentId}/wrong-questions`,
    undefined,
    "错题本加载失败",
  );
}

export function deleteWrongQuestion(wrongId: string): Promise<void> {
  return requestNoContent(
    `api/wrong-questions/${wrongId}`,
    { method: "DELETE" },
    "删除错题失败",
  );
}

export function reviewWrongQuestion(wrongId: string): Promise<{ status: string }> {
  return requestJson<{ status: string }>(
    `api/wrong-questions/${wrongId}/review`,
    { method: "POST" },
    "标记复习失败",
  );
}
