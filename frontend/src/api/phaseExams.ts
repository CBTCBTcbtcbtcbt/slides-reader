// 阶段考试相关 API。

import type { PhaseExamItem } from "../types/api";
import { requestJson, requestNoContent } from "./http";

export function listPhaseExams(): Promise<PhaseExamItem[]> {
  return requestJson<PhaseExamItem[]>("api/phase-exams", undefined, "阶段考试列表加载失败");
}

export function generatePhaseExam(
  documentIds: string[],
  name: string,
  difficulty: string = "medium",
): Promise<{ status: string; phase_exam_id: string; exam_id: string | null }> {
  return requestJson<{ status: string; phase_exam_id: string; exam_id: string | null }>(
    "api/phase-exams/generate",
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ document_ids: documentIds, name, difficulty }),
    },
    "阶段考试生成失败",
  );
}

export function readPhaseExam(phaseExamId: string): Promise<PhaseExamItem> {
  return requestJson<PhaseExamItem>(
    `api/phase-exams/${phaseExamId}`,
    undefined,
    "阶段考试加载失败",
  );
}

export async function deletePhaseExam(phaseExamId: string): Promise<void> {
  await requestNoContent(
    `api/phase-exams/${phaseExamId}`,
    { method: "DELETE" },
    "阶段考试删除失败",
  );
}
