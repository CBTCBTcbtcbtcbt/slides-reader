// 试卷、答题相关 API。

import type {
  ExamAttemptResult,
  ExamAttemptItem,
  ExamItem,
  ExamQuestionForTaking,
  ExamWithQuestions,
} from "../types/api";
import { requestJson, requestNoContent } from "./http";

export function listExams(): Promise<ExamItem[]> {
  return requestJson<ExamItem[]>("api/exams", undefined, "试卷列表加载失败");
}

export function listDocumentExams(documentId: string): Promise<ExamItem[]> {
  return requestJson<ExamItem[]>(
    `api/documents/${documentId}/exams`,
    undefined,
    "试卷列表加载失败",
  );
}

export function generateExam(
  documentId: string,
  difficulty: string = "medium",
): Promise<{ status: string; exam_id: string }> {
  return requestJson<{ status: string; exam_id: string }>(
    `api/documents/${documentId}/exams/generate`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ difficulty }),
    },
    "试卷生成失败",
  );
}

export function readExam(examId: string): Promise<ExamWithQuestions> {
  return requestJson<ExamWithQuestions>(`api/exams/${examId}`, undefined, "试卷加载失败");
}

export function readExamMetadata(examId: string): Promise<ExamItem> {
  return requestJson<ExamItem>(
    `api/exams/${examId}?include_questions=false`,
    undefined,
    "试卷加载失败",
  );
}

export function readExamQuestions(
  examId: string,
  includeAnswer: boolean = true,
): Promise<ExamWithQuestions["questions"] | ExamQuestionForTaking[]> {
  return requestJson<ExamWithQuestions["questions"] | ExamQuestionForTaking[]>(
    `api/exams/${examId}/questions?include_answer=${includeAnswer}`,
    undefined,
    "题目加载失败",
  );
}

export function submitExamAttempt(
  examId: string,
  answers: Record<string, string>,
): Promise<ExamAttemptResult> {
  return requestJson<ExamAttemptResult>(
    `api/exams/${examId}/attempts`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ answers }),
    },
    "答题提交失败",
  );
}

export function listExamAttempts(examId: string): Promise<ExamAttemptItem[]> {
  return requestJson<ExamAttemptItem[]>(
    `api/exams/${examId}/attempts`,
    undefined,
    "答题记录加载失败",
  );
}

export function readExamAttemptResult(
  examId: string,
  attemptId: string,
): Promise<ExamAttemptResult> {
  return requestJson<ExamAttemptResult>(
    `api/exams/${examId}/attempts/${attemptId}/result`,
    undefined,
    "考试结果加载失败",
  );
}

export function deleteExam(examId: string): Promise<void> {
  return requestNoContent(
    `api/exams/${examId}`,
    { method: "DELETE" },
    "试卷删除失败",
  );
}
