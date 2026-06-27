import { fireEvent, render, screen } from "@testing-library/react";
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

function renderReaderView(
  options: {
    readerRightSidebar?: ReaderRightSidebar;
    isReaderChatCollapsed?: boolean;
    pdfZoomPercent?: number;
    pdfPanOffset?: { x: number; y: number };
    onOpenChatSidebar?: () => void;
    onPdfZoomChange?: (zoomPercent: number) => void;
    onPdfPanChange?: (offset: { x: number; y: number }) => void;
  } = {},
) {
  const onOpenChatSidebar = options.onOpenChatSidebar ?? vi.fn();
  const onPdfZoomChange = options.onPdfZoomChange ?? vi.fn();
  const onPdfPanChange = options.onPdfPanChange ?? vi.fn();

  return render(
    <ReaderView
      readerDocument={buildDocument()}
      readerRightSidebar={options.readerRightSidebar ?? "none"}
      isReaderTopbarCollapsed={false}
      isReaderChatCollapsed={options.isReaderChatCollapsed ?? true}
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
      pdfZoomPercent={options.pdfZoomPercent ?? 100}
      pdfPanOffset={options.pdfPanOffset ?? { x: 0, y: 0 }}
      thumbnailRenderWidth={120}
      thumbnailSidebarWidth={160}
      courseSummarySidebarWidth={320}
      isResizingThumbnailSidebar={false}
      isResizingCourseSummarySidebar={false}
      readerWorkspaceRef={vi.fn()}
      readerViewportRef={vi.fn()}
      readerContentRef={vi.fn()}
      readerPageStageRef={vi.fn()}
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
      onOpenChatSidebar={onOpenChatSidebar}
      onPdfZoomChange={onPdfZoomChange}
      onPdfPanChange={onPdfPanChange}
      onPdfPanReset={vi.fn()}
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

  it("底部会话只保留收缩栏，并点击后打开右侧问答", () => {
    const onOpenChatSidebar = vi.fn();
    renderReaderView({
      isReaderChatCollapsed: false,
      onOpenChatSidebar,
    });

    expect(screen.queryByText("展开会话")).not.toBeInTheDocument();
    expect(screen.queryByText("折叠会话")).not.toBeInTheDocument();
    expect(screen.queryByText("移到右侧栏")).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "打开右侧问答" }));

    expect(onOpenChatSidebar).toHaveBeenCalledTimes(1);
  });

  it("右侧问答打开时不再渲染底部会话收缩栏", () => {
    renderReaderView({ readerRightSidebar: "chat" });

    expect(screen.queryByText("当前页问答：第 1 页")).not.toBeInTheDocument();
    expect(screen.getByRole("complementary", { name: "当前页问答" })).toBeInTheDocument();
  });

  it("PDF 主阅读区右下角提供 100% 到 400% 的缩放控件", () => {
    const onPdfZoomChange = vi.fn();
    renderReaderView({
      pdfZoomPercent: 150,
      onPdfZoomChange,
    });

    const slider = screen.getByRole("slider", { name: "PDF 缩放比例" });
    expect(screen.getByRole("button", { name: "缩小 PDF" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "放大 PDF" })).toBeInTheDocument();
    expect(screen.getByText("150%")).toBeInTheDocument();
    expect(slider).toHaveAttribute("min", "100");
    expect(slider).toHaveAttribute("max", "400");

    fireEvent.change(slider, { target: { value: "220" } });

    expect(onPdfZoomChange).toHaveBeenCalledWith(220);
  });

  it("PDF 放大后主阅读区支持按住拖动平移", () => {
    const onPdfPanChange = vi.fn();
    renderReaderView({
      pdfZoomPercent: 200,
      pdfPanOffset: { x: 10, y: 20 },
      onPdfPanChange,
    });

    const stage = screen.getByRole("region", { name: "PDF 主阅读区" });

    fireEvent.pointerDown(stage, {
      pointerId: 1,
      button: 0,
      clientX: 100,
      clientY: 120,
    });
    fireEvent.pointerMove(stage, {
      pointerId: 1,
      clientX: 145,
      clientY: 90,
    });

    expect(onPdfPanChange).toHaveBeenCalledWith({ x: 55, y: -10 });
  });
});
