import { createRef } from "react";
import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import type { DocumentItem, DocumentStatusResponse } from "../../types/api";
import type { ReaderRightSidebar } from "../../types/ui";
import { ReaderView } from "./ReaderView";

// react-pdf 需要浏览器 PDF worker 和 canvas；这个测试只关心阅读页 UI 是否展示错误提示，
// 因此用轻量组件替代 PDF 渲染组件，避免把测试和 PDF 引擎绑定在一起。
vi.mock("react-pdf", () => ({
  Document: ({ children }: { children: React.ReactNode }) => (
    <div data-testid="pdf-document">{children}</div>
  ),
  Page: () => <div data-testid="pdf-page" />,
  Thumbnail: () => <span>缩略图</span>,
  pdfjs: {
    GlobalWorkerOptions: {
      workerSrc: "",
    },
  },
}));

function buildDocument(): DocumentItem {
  return {
    document_id: "doc-1",
    title: "测试课件",
    file_path: "storage/test.pdf",
    status: "ready",
    page_count: 1,
    error_message: null,
    course_summary: null,
    course_summary_status: "failed",
    course_summary_error: "课程简介生成失败：504: LLM 请求超时",
    lecture_notes_paused: false,
    created_at: "2026-01-01T00:00:00Z",
  };
}

function buildStatus(): DocumentStatusResponse {
  return {
    document_id: "doc-1",
    title: "测试课件",
    status: "ready",
    error_message: null,
    course_summary_status: "failed",
    course_summary_error: "课程简介生成失败：504: LLM 请求超时",
    course_summary_ready: false,
    total_pages: 1,
    lecture_notes_ready_count: 0,
    lecture_notes_failed_count: 0,
    lecture_notes_processing_count: 0,
    lecture_notes_pending_count: 1,
    lecture_notes_paused: false,
    should_poll: false,
    pages: [],
  };
}

function renderReaderView(options: { readerRightSidebar?: ReaderRightSidebar } = {}) {
  const readerWorkspaceRef = createRef<HTMLElement>();
  const readerViewportRef = createRef<HTMLDivElement>();
  const readerContentRef = createRef<HTMLDivElement>();

  return render(
    <ReaderView
      readerDocument={buildDocument()}
      readerRightSidebar={options.readerRightSidebar ?? "none"}
      isReaderTopbarCollapsed={false}
      isReaderChatCollapsed={true}
      currentPdfPage={1}
      totalPdfPages={1}
      readerState="ready"
      readerMessage=""
      activeDocumentStatus={buildStatus()}
      currentReaderPage={undefined}
      currentPageChatCount={0}
      pageTurnControls={<div>翻页控件</div>}
      pageChatContent={<div>问答内容</div>}
      pageChatStatus={<div>问答状态</div>}
      noteSidebarContent={<div>讲稿内容</div>}
      noteBlockElement={null}
      pdfPageWidth={320}
      thumbnailRenderWidth={120}
      thumbnailSidebarWidth={160}
      courseSummarySidebarWidth={320}
      isResizingThumbnailSidebar={false}
      isResizingCourseSummarySidebar={false}
      readerWorkspaceRef={readerWorkspaceRef}
      readerViewportRef={readerViewportRef}
      readerContentRef={readerContentRef}
      documentActionState={null}
      getStatusLabel={(status) => status}
      getCourseSummaryStatusLabel={(status) => status}
      buildLectureNotesProgressText={() => "讲稿进度：0/1 页已有讲稿。"}
      isDocumentBusy={() => false}
      onCloseReader={vi.fn()}
      onOpenSettings={vi.fn()}
      onToggleCourseSummarySidebar={vi.fn()}
      onClearActiveDocument={vi.fn()}
      onCollapseTopbar={vi.fn()}
      onExpandTopbar={vi.fn()}
      onCloseRightSidebar={vi.fn()}
      onToggleNoteSidebar={vi.fn()}
      onOpenChatSidebar={vi.fn()}
      onSetReaderChatCollapsed={vi.fn()}
      onGoToPdfPage={vi.fn()}
      onPdfLoadSuccess={vi.fn()}
      onPdfLoadError={vi.fn()}
      onPdfPageLoadSuccess={vi.fn()}
      onPdfPageRenderError={vi.fn()}
      onStartResizingThumbnailSidebar={vi.fn()}
      onStartResizingCourseSummarySidebar={vi.fn()}
      onRegenerateCourseSummary={vi.fn()}
      onRegeneratePageLectureNotes={vi.fn()}
    />,
  );
}

describe("ReaderView", () => {
  it("阅读页不展示课程简介生成失败的详细错误，错误只保留在文件页查看", () => {
    renderReaderView();

    expect(screen.queryByText(/LLM 请求超时/)).not.toBeInTheDocument();
    expect(screen.queryByText("AI 生成进度")).not.toBeInTheDocument();
  });

  it("阅读页右侧课程简介栏也不展示课程简介失败详情", () => {
    renderReaderView({ readerRightSidebar: "summary" });

    expect(screen.queryByText(/LLM 请求超时/)).not.toBeInTheDocument();
    expect(screen.getByText("课程简介生成失败，请回到课件库查看详情或重新生成。")).toBeInTheDocument();
  });
});
