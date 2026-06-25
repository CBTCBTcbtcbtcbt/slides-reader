import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import type { DocumentItem } from "../../types/api";
import { PhaseExamCreateView } from "./PhaseExamCreateView";

function buildDocument(overrides: Partial<DocumentItem>): DocumentItem {
  // 测试只关心 document_id、title 和 page_count，但组件 props 需要完整 DocumentItem。
  return {
    document_id: "doc-default",
    title: "默认课件",
    file_path: "storage/default.pdf",
    status: "ready",
    page_count: 10,
    error_message: null,
    course_summary: null,
    course_summary_status: "ready",
    course_summary_error: null,
    lecture_notes_paused: false,
    created_at: "2026-01-01T00:00:00Z",
    ...overrides,
  };
}

describe("PhaseExamCreateView", () => {
  it("提交阶段考试时传出选中的文档、名称和难度", async () => {
    const user = userEvent.setup();
    const handleCreate = vi.fn().mockResolvedValue(undefined);
    const documents = [
      buildDocument({ document_id: "doc-a", title: "线性代数", page_count: 12 }),
      buildDocument({ document_id: "doc-b", title: "概率论", page_count: 18 }),
    ];

    render(
      <PhaseExamCreateView
        documents={documents}
        onBack={vi.fn()}
        onCreate={handleCreate}
      />,
    );

    // 用户可以像真实页面一样勾选两份课件。
    await user.click(screen.getByRole("checkbox", { name: /线性代数/ }));
    await user.click(screen.getByRole("checkbox", { name: /概率论/ }));

    // 输入名称并选择难度后，提交按钮会调用父组件传入的创建函数。
    await user.type(screen.getByLabelText("阶段考试名称"), "期中复习卷");
    await user.selectOptions(screen.getByLabelText("难度"), "hard");
    await user.click(screen.getByRole("button", { name: "生成阶段考试" }));

    expect(handleCreate).toHaveBeenCalledWith(["doc-a", "doc-b"], "期中复习卷", "hard");
    expect(await screen.findByText("阶段考试已开始生成。")).toBeInTheDocument();
  });
});
