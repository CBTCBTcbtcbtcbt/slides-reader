import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import type { PageItem } from "../../types/api";
import { PageChatContent } from "./PageChat";

function buildPage(): PageItem {
  return {
    page_id: "page-1",
    document_id: "doc-1",
    page_number: 1,
    text: "",
    image_path: "storage/page-1.png",
    image_url: "/api/documents/doc-1/pages/1/image",
    status: "ready",
    error_message: null,
    lecture_notes: null,
    lecture_notes_status: "ready",
    lecture_notes_error: null,
    note_block: null,
    chat_messages: [],
    created_at: "2026-01-01T00:00:00Z",
  };
}

describe("PageChatContent", () => {
  it("使用浅色输入框，并能继续输入和提交问题", async () => {
    const user = userEvent.setup();
    const handleInputChange = vi.fn();
    const handleSubmit = vi.fn();
    const currentPage = buildPage();

    const { container } = render(
      <PageChatContent
        currentReaderPage={currentPage}
        currentPdfPage={1}
        pageQuestionInput=""
        isSubmittingCurrentPageChat={false}
        pendingAttachments={[]}
        formatCreatedAt={(value) => value}
        onQuestionInputChange={handleInputChange}
        onAddPendingAttachments={vi.fn()}
        onRemovePendingAttachment={vi.fn()}
        onSubmitPageQuestion={handleSubmit}
      />,
    );

    expect(container.querySelector(".page-chat-composer")).toHaveClass("page-chat-composer--light");

    await user.type(screen.getByLabelText("向 AI 老师提问"), "这页重点是什么？");
    await user.click(screen.getByRole("button", { name: "发送问题" }));

    expect(handleInputChange).toHaveBeenCalled();
    expect(handleSubmit).toHaveBeenCalledWith(currentPage);
  });
});
