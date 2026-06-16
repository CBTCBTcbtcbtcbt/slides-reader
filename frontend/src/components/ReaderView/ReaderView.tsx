import type { CSSProperties, ReactNode } from "react";
import {
  Document as PdfDocument,
  Page as PdfPage,
  Thumbnail as PdfThumbnail,
  pdfjs,
} from "react-pdf";
import "react-pdf/dist/Page/AnnotationLayer.css";
import "react-pdf/dist/Page/TextLayer.css";
import type { DocumentItem, DocumentStatusResponse, PageItem } from "../../types/api";
import type { DocumentActionState, LoadedPdfPage, ReaderRightSidebar, ReaderState } from "../../types/ui";

// React-PDF 依赖 PDF.js worker 在浏览器后台解析 PDF。
// workerSrc 和 <Document>/<Page> 放在同一模块，避免模块执行顺序覆盖配置。
pdfjs.GlobalWorkerOptions.workerSrc = new URL(
  "pdfjs-dist/build/pdf.worker.min.mjs",
  import.meta.url,
).toString();

type ReaderViewProps = {
  readerDocument: DocumentItem;
  readerRightSidebar: ReaderRightSidebar;
  isReaderTopbarCollapsed: boolean;
  isReaderChatCollapsed: boolean;
  currentPdfPage: number;
  totalPdfPages: number;
  readerState: ReaderState;
  readerMessage: string;
  activeDocumentStatus: DocumentStatusResponse | undefined;
  currentReaderPage: PageItem | undefined;
  currentPageChatCount: number;
  pageTurnControls: ReactNode;
  pageChatContent: ReactNode;
  pageChatStatus: ReactNode;
  noteBlockElement: ReactNode;
  pdfPageWidth: number | undefined;
  thumbnailRenderWidth: number;
  thumbnailSidebarWidth: number;
  courseSummarySidebarWidth: number;
  isResizingThumbnailSidebar: boolean;
  isResizingCourseSummarySidebar: boolean;
  readerWorkspaceRef: React.RefObject<HTMLElement | null>;
  readerViewportRef: React.RefObject<HTMLDivElement | null>;
  readerContentRef: React.RefObject<HTMLDivElement | null>;
  documentActionState: DocumentActionState;
  getStatusLabel: (status: string) => string;
  getCourseSummaryStatusLabel: (status: string) => string;
  buildLectureNotesProgressText: (statusData: DocumentStatusResponse | undefined) => string;
  isDocumentBusy: (documentId: string) => boolean;
  onCloseReader: () => void;
  onOpenSettings: () => void;
  onToggleCourseSummarySidebar: () => void;
  onClearActiveDocument: () => void;
  onCollapseTopbar: () => void;
  onExpandTopbar: () => void;
  onCloseRightSidebar: () => void;
  onOpenChatSidebar: () => void;
  onSetReaderChatCollapsed: (isCollapsed: boolean) => void;
  onGoToPdfPage: (pageNumber: number) => void;
  onPdfLoadSuccess: ({ numPages }: { numPages: number }) => void;
  onPdfLoadError: (error: Error) => void;
  onPdfPageLoadSuccess: (page: LoadedPdfPage) => void;
  onPdfPageRenderError: (error: Error) => void;
  onStartResizingThumbnailSidebar: (event: React.PointerEvent<HTMLButtonElement>) => void;
  onStartResizingCourseSummarySidebar: (event: React.PointerEvent<HTMLButtonElement>) => void;
  onRegenerateCourseSummary: (document: DocumentItem) => void;
};

export function ReaderView({
  readerDocument,
  readerRightSidebar,
  isReaderTopbarCollapsed,
  isReaderChatCollapsed,
  currentPdfPage,
  totalPdfPages,
  readerState,
  readerMessage,
  activeDocumentStatus,
  currentReaderPage,
  currentPageChatCount,
  pageTurnControls,
  pageChatContent,
  pageChatStatus,
  noteBlockElement,
  pdfPageWidth,
  thumbnailRenderWidth,
  thumbnailSidebarWidth,
  courseSummarySidebarWidth,
  isResizingThumbnailSidebar,
  isResizingCourseSummarySidebar,
  readerWorkspaceRef,
  readerViewportRef,
  readerContentRef,
  documentActionState,
  getStatusLabel,
  getCourseSummaryStatusLabel,
  buildLectureNotesProgressText,
  isDocumentBusy,
  onCloseReader,
  onOpenSettings,
  onToggleCourseSummarySidebar,
  onClearActiveDocument,
  onCollapseTopbar,
  onExpandTopbar,
  onCloseRightSidebar,
  onOpenChatSidebar,
  onSetReaderChatCollapsed,
  onGoToPdfPage,
  onPdfLoadSuccess,
  onPdfLoadError,
  onPdfPageLoadSuccess,
  onPdfPageRenderError,
  onStartResizingThumbnailSidebar,
  onStartResizingCourseSummarySidebar,
  onRegenerateCourseSummary,
}: ReaderViewProps) {
  const fileUrl = `/api/documents/${readerDocument.document_id}/file`;

  return (
    <main className="app-shell app-shell--reader">
      <section
        className={`reader-shell${
          isReaderTopbarCollapsed ? " reader-shell--topbar-collapsed" : ""
        }${isReaderChatCollapsed ? " reader-shell--chat-collapsed" : ""}`}
      >
        {isReaderTopbarCollapsed ? (
          <header className="reader-collapsed-topbar">
            <button
              type="button"
              className="topbar-button topbar-button--primary"
              onClick={onExpandTopbar}
            >
              展开顶部
            </button>
            <span className="reader-collapsed-title">{readerDocument.title}</span>
            <span className="reader-collapsed-page">
              第 {currentPdfPage} / {totalPdfPages || readerDocument.page_count || "-"} 页
            </span>
          </header>
        ) : (
          <header className="reader-topbar">
            <div className="reader-topbar-left">
              <div className="reader-main-actions">
                <button
                  type="button"
                  className="topbar-button topbar-button--primary"
                  onClick={onCloseReader}
                >
                  文件
                </button>
                <button type="button" className="topbar-button" onClick={onOpenSettings}>
                  设置
                </button>
              </div>
              <div className="reader-title-group">
                <span className="reader-kicker">PDF 阅读</span>
                <h1>{readerDocument.title}</h1>
                <div className="reader-status-row">
                  <span className={`document-status document-status--${readerDocument.status}`}>
                    PDF：{getStatusLabel(readerDocument.status)}
                  </span>
                  <span
                    className={`document-status document-status--${readerDocument.course_summary_status}`}
                  >
                    简介：{getCourseSummaryStatusLabel(readerDocument.course_summary_status)}
                  </span>
                  <span className="reader-progress-text">
                    {buildLectureNotesProgressText(activeDocumentStatus)}
                  </span>
                </div>
              </div>
            </div>
            <div className="reader-topbar-center">{pageTurnControls}</div>
            <div className="reader-secondary-actions">
              <button type="button" className="topbar-button" onClick={onToggleCourseSummarySidebar}>
                {readerRightSidebar === "summary" ? "收起简介" : "课程简介"}
              </button>
              <button type="button" className="topbar-button" onClick={onClearActiveDocument}>
                关闭文档
              </button>
              <button type="button" className="topbar-button" onClick={onCollapseTopbar}>
                折叠顶部
              </button>
            </div>
          </header>
        )}

        {readerMessage || activeDocumentStatus?.course_summary_error ? (
          <div className="reader-status-stack">
            {readerMessage ? (
              <p className={`pdf-reader-message pdf-reader-message--${readerState}`}>
                {readerMessage}
              </p>
            ) : null}

            {activeDocumentStatus?.course_summary_error ? (
              <div className="reader-generation-strip">
                <strong>AI 生成进度</strong>
                <p>{buildLectureNotesProgressText(activeDocumentStatus)}</p>
                <p className="document-error">{activeDocumentStatus.course_summary_error}</p>
              </div>
            ) : null}
          </div>
        ) : null}

        <section ref={readerWorkspaceRef} className="reader-workspace">
          <div ref={readerViewportRef} className="pdf-reader-viewport">
            <PdfDocument
              file={fileUrl}
              className="pdf-document"
              loading={<div className="pdf-loading">正在加载 PDF...</div>}
              error={<div className="pdf-error">PDF 加载失败，请返回列表后重试。</div>}
              onLoadSuccess={onPdfLoadSuccess}
              onLoadError={onPdfLoadError}
            >
              {totalPdfPages > 0 ? (
                <div
                  ref={readerContentRef}
                  className={`pdf-reader-content${
                    isResizingThumbnailSidebar || isResizingCourseSummarySidebar
                      ? " pdf-reader-content--resizing"
                      : ""
                  }`}
                  style={{
                    "--thumbnail-sidebar-width": `${thumbnailSidebarWidth}px`,
                    "--course-summary-sidebar-width": `${courseSummarySidebarWidth}px`,
                  } as CSSProperties}
                >
                  <aside className="pdf-thumbnail-sidebar" aria-label="PDF 页面缩略图列表">
                    {Array.from({ length: totalPdfPages }, (_, index) => {
                      const pageNumber = index + 1;
                      const isCurrentPage = pageNumber === currentPdfPage;

                      return (
                        <button
                          type="button"
                          className={`pdf-thumbnail-button${
                            isCurrentPage ? " pdf-thumbnail-button--active" : ""
                          }`}
                          key={pageNumber}
                          onClick={() => onGoToPdfPage(pageNumber)}
                          aria-current={isCurrentPage ? "page" : undefined}
                        >
                          <PdfThumbnail
                            pageNumber={pageNumber}
                            width={thumbnailRenderWidth}
                            loading={
                              <span
                                className="pdf-thumbnail-loading"
                                style={{ minHeight: `${thumbnailRenderWidth * 1.35}px` }}
                              >
                                加载中
                              </span>
                            }
                          />
                          <span>第 {pageNumber} 页</span>
                        </button>
                      );
                    })}
                  </aside>

                  <button
                    type="button"
                    className="pdf-thumbnail-resizer"
                    onPointerDown={onStartResizingThumbnailSidebar}
                    aria-label="拖动调整缩略图栏宽度"
                  />

                  <div className="pdf-page-stage">
                    <PdfPage
                      key={`${readerDocument.document_id}-${currentPdfPage}`}
                      pageNumber={currentPdfPage}
                      width={pdfPageWidth}
                      loading={<div className="pdf-loading">正在渲染当前页...</div>}
                      renderAnnotationLayer={true}
                      renderTextLayer={true}
                      onLoadSuccess={onPdfPageLoadSuccess}
                      onRenderError={onPdfPageRenderError}
                    />
                    {noteBlockElement}
                  </div>

                  {readerRightSidebar !== "none" ? (
                    <>
                      <button
                        type="button"
                        className="course-summary-resizer"
                        onPointerDown={onStartResizingCourseSummarySidebar}
                        aria-label="拖动调整右侧栏宽度"
                      />

                      <aside
                        className="course-summary-sidebar"
                        aria-label={readerRightSidebar === "summary" ? "课程简介" : "当前页问答"}
                      >
                        <div className="course-summary-sidebar__header">
                          <div>
                            <h2>{readerRightSidebar === "summary" ? "课程简介" : "当前页问答"}</h2>
                            {readerRightSidebar === "summary" ? (
                              <span
                                className={`document-status document-status--${readerDocument.course_summary_status}`}
                              >
                                {getCourseSummaryStatusLabel(readerDocument.course_summary_status)}
                              </span>
                            ) : (
                              <span className="page-chat-page-badge">
                                第 {currentReaderPage?.page_number ?? currentPdfPage} 页
                              </span>
                            )}
                          </div>
                          <button
                            type="button"
                            className="course-summary-close-button"
                            onClick={onCloseRightSidebar}
                            aria-label="关闭右侧栏"
                          >
                            ×
                          </button>
                        </div>

                        <div className="course-summary-sidebar__content">
                          {readerRightSidebar === "summary" ? (
                            <>
                              {readerDocument.course_summary_status === "ready" &&
                              readerDocument.course_summary ? (
                                <p>{readerDocument.course_summary}</p>
                              ) : null}
                              {readerDocument.course_summary_status === "processing" ? (
                                <p>课程简介正在生成，生成完成后会自动更新状态。</p>
                              ) : null}
                              {readerDocument.course_summary_status === "pending" ? (
                                <p>课程简介还没有开始生成。</p>
                              ) : null}
                              {readerDocument.course_summary_status === "failed" ? (
                                <p className="document-error">
                                  {readerDocument.course_summary_error ?? "课程简介生成失败。"}
                                </p>
                              ) : null}
                            </>
                          ) : (
                            pageChatContent
                          )}
                        </div>

                        {readerRightSidebar === "summary" ? (
                          <button
                            type="button"
                            className="secondary-action-button"
                            onClick={() => onRegenerateCourseSummary(readerDocument)}
                            disabled={isDocumentBusy(readerDocument.document_id)}
                          >
                            {documentActionState?.documentId === readerDocument.document_id &&
                            documentActionState.action === "regeneratingSummary"
                              ? "提交中..."
                              : readerDocument.course_summary_status === "pending"
                                ? "生成简介"
                                : "重新生成简介"}
                          </button>
                        ) : (
                          pageChatStatus
                        )}
                      </aside>
                    </>
                  ) : null}
                </div>
              ) : null}
            </PdfDocument>
          </div>
        </section>

        {readerRightSidebar === "chat" ? null : isReaderChatCollapsed ? (
          <section className="reader-chat-collapsed">
            <button
              type="button"
              className="topbar-button topbar-button--primary"
              onClick={() => onSetReaderChatCollapsed(false)}
            >
              展开会话
            </button>
            <span>当前页问答：第 {currentPdfPage} 页</span>
            <span>{currentPageChatCount > 0 ? `${currentPageChatCount} 条历史` : "暂无问答历史"}</span>
          </section>
        ) : (
          <section className="reader-chat-dock page-chat-panel">
            <div className="page-chat-header">
              <div>
                <h2>当前页问答</h2>
                <p>这里的历史只属于第 {currentPdfPage} 页，切换页面后会显示新页面自己的问答。</p>
              </div>
              <div className="page-chat-header-actions">
                {currentReaderPage ? (
                  <span className="page-chat-page-badge">第 {currentReaderPage.page_number} 页</span>
                ) : null}
                <button type="button" className="topbar-button" onClick={onOpenChatSidebar}>
                  移到右侧栏
                </button>
                <button
                  type="button"
                  className="topbar-button"
                  onClick={() => onSetReaderChatCollapsed(true)}
                >
                  折叠会话
                </button>
              </div>
            </div>

            {pageChatContent}
            {pageChatStatus}
          </section>
        )}
      </section>
    </main>
  );
}
