import { describe, expect, it } from "vitest";
import { isAsyncExamStatus, pruneRecordToDocumentIds } from "./useExamWorkflows";

describe("isAsyncExamStatus", () => {
  it("只把 pending 和 processing 视为仍需轮询的考试生成状态", () => {
    // pending 表示后端已经创建任务，但后台生成还没有完成。
    expect(isAsyncExamStatus("pending")).toBe(true);

    // processing 表示后台生成正在执行，前端仍然需要继续刷新列表。
    expect(isAsyncExamStatus("processing")).toBe(true);

    // ready 表示试卷已经可以使用，不应该继续占用轮询资源。
    expect(isAsyncExamStatus("ready")).toBe(false);

    // failed 表示生成失败，前端需要展示失败状态，而不是继续等待。
    expect(isAsyncExamStatus("failed")).toBe(false);
  });
});

describe("pruneRecordToDocumentIds", () => {
  it("删除已经不在文档列表里的按 document_id 保存的缓存", () => {
    // 这个缓存结构常用于 examsByDocument：key 是 document_id，value 是该文档的业务数据。
    const cachedByDocument = {
      "doc-existing": ["exam-1"],
      "doc-deleted": ["exam-2"],
    };

    // allowedDocumentIds 表示当前仍存在的文档；被删除文档的缓存不能继续留在 hook 状态里。
    const prunedRecord = pruneRecordToDocumentIds(cachedByDocument, new Set(["doc-existing"]));

    expect(prunedRecord).toEqual({
      "doc-existing": ["exam-1"],
    });
  });
});
