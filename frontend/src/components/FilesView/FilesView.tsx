import type { DocumentItem, DocumentStatusResponse, PageItem } from "../../types/api";
import type { DocumentActionState, UploadState } from "../../types/ui";
import { MarkdownContent } from "../MarkdownContent";

type FilesViewProps = {
  selectedFile: File | null;
  uploadState: UploadState;
  uploadMessage: string;
  uploadedDocumentId: string | null;
  currentOpenedDocument: DocumentItem | null;
  documents: DocumentItem[];
  documentsMessage: string;
  documentStatusById: Record<string, DocumentStatusResponse>;
  documentStatusMessage: string;
  activeReaderDocument: DocumentItem | null;
  editingDocumentId: string | null;
  editingTitle: string;
  documentActionState: DocumentActionState;
  documentActionMessage: string;
  expandedDocumentIds: Record<string, boolean>;
  expandedLectureNotesDocumentId: string | null;
  pagesByDocument: Record<string, PageItem[]>;
  pagesMessageByDocument: Record<string, string>;
  onReturnToReader: () => void;
  onFileChange: (event: React.ChangeEvent<HTMLInputElement>) => void;
  onUploadSubmit: (event: React.FormEvent<HTMLFormElement>) => void;
  onEditingTitleChange: (value: string) => void;
  onSaveRename: (documentId: string) => void;
  onCancelRename: () => void;
  onToggleDocumentLectureNotesPaused: (document: DocumentItem) => void;
  onOpenReader: (document: DocumentItem) => void;
  onStartRename: (document: DocumentItem) => void;
  onDeleteDocument: (document: DocumentItem) => void;
  onToggleDocumentExpanded: (documentId: string) => void;
  onRegenerateCourseSummary: (document: DocumentItem) => void;
  onToggleLectureNotesPanel: (document: DocumentItem) => void;
  onRegenerateDocumentLectureNotes: (document: DocumentItem) => void;
  onGenerateRemainingLectureNotes: (document: DocumentItem) => void;
  onClearLectureNotesQueue: (document: DocumentItem) => void;
  onRegeneratePageLectureNotes: (document: DocumentItem, page: PageItem) => void;
  isDocumentBusy: (documentId: string) => boolean;
  isPageLectureNotesBusy: (documentId: string, pageNumber: number) => boolean;
  resolveLectureNotesPaused: (document: DocumentItem) => boolean;
  formatCreatedAt: (value: string) => string;
  getStatusLabel: (status: string) => string;
  getCourseSummaryStatusLabel: (status: string) => string;
  getLectureNotesStatusLabel: (status: string) => string;
  buildLectureNotesProgressText: (statusData: DocumentStatusResponse | undefined) => string;
};

export function FilesView({
  selectedFile,
  uploadState,
  uploadMessage,
  uploadedDocumentId,
  currentOpenedDocument,
  documents,
  documentsMessage,
  documentStatusById,
  documentStatusMessage,
  activeReaderDocument,
  editingDocumentId,
  editingTitle,
  documentActionState,
  documentActionMessage,
  expandedDocumentIds,
  expandedLectureNotesDocumentId,
  pagesByDocument,
  pagesMessageByDocument,
  onReturnToReader,
  onFileChange,
  onUploadSubmit,
  onEditingTitleChange,
  onSaveRename,
  onCancelRename,
  onToggleDocumentLectureNotesPaused,
  onOpenReader,
  onStartRename,
  onDeleteDocument,
  onToggleDocumentExpanded,
  onRegenerateCourseSummary,
  onToggleLectureNotesPanel,
  onRegenerateDocumentLectureNotes,
  onGenerateRemainingLectureNotes,
  onClearLectureNotesQueue,
  onRegeneratePageLectureNotes,
  isDocumentBusy,
  isPageLectureNotesBusy,
  resolveLectureNotesPaused,
  formatCreatedAt,
  getStatusLabel,
  getCourseSummaryStatusLabel,
  getLectureNotesStatusLabel,
  buildLectureNotesProgressText,
}: FilesViewProps) {
  return (
    <>
      <div className="current-document-banner">
        <span>当前打开</span>
        <strong>{currentOpenedDocument ? currentOpenedDocument.title : "未打开文档"}</strong>
        {currentOpenedDocument ? (
          <button type="button" className="secondary-action-button" onClick={onReturnToReader}>
            返回阅读
          </button>
        ) : null}
      </div>

      <form className="upload-panel" onSubmit={onUploadSubmit}>
        <div>
          <h2>上传 slides</h2>
          <p>请选择 `.pdf`、`.ppt` 或 `.pptx` 格式文件。上传成功后，后端会统一转换并使用 PDF。</p>
        </div>

        <label className="file-input-label">
          <span>选择 slides 文件</span>
          <input type="file" accept="application/pdf,.pdf,.ppt,.pptx" onChange={onFileChange} />
        </label>

        <button
          className="upload-button"
          type="submit"
          disabled={!selectedFile || uploadState === "uploading"}
        >
          {uploadState === "uploading" ? "上传中..." : "上传 slides"}
        </button>

        <div className={`upload-message upload-message--${uploadState}`}>{uploadMessage}</div>

        {uploadedDocumentId ? (
          <div className="document-id-box">
            <span>document_id</span>
            <code>{uploadedDocumentId}</code>
          </div>
        ) : null}
      </form>

      <section className="documents-panel">
        <div>
          <h2>已上传文档</h2>
          <p>这些记录来自 SQLite 数据库，后端重启后仍然会保留。</p>
        </div>

        {documents.length > 0 ? (
          <ul className="document-list">
            {documents.map((document) => {
              const statusData = documentStatusById[document.document_id];
              const isDocumentExpanded = Boolean(expandedDocumentIds[document.document_id]);
              const isLectureNotesPaused = resolveLectureNotesPaused(document);
              const lectureNotesToggleLabel = isLectureNotesPaused ? "继续生成讲稿" : "暂停生成讲稿";

              return (
                <li
                  className={`document-list-item${
                    activeReaderDocument?.document_id === document.document_id
                      ? " document-list-item--active"
                      : ""
                  }${isDocumentExpanded ? " document-list-item--expanded" : ""}`}
                  key={document.document_id}
                >
                  <div className="document-header">
                    {editingDocumentId === document.document_id ? (
                      <div className="rename-form">
                        <label>
                          <span>新标题</span>
                          <input
                            value={editingTitle}
                            onChange={(event) => onEditingTitleChange(event.target.value)}
                            disabled={isDocumentBusy(document.document_id)}
                          />
                        </label>
                        <div className="document-actions">
                          <button
                            type="button"
                            onClick={() => onSaveRename(document.document_id)}
                            disabled={isDocumentBusy(document.document_id)}
                          >
                            {documentActionState?.documentId === document.document_id &&
                            documentActionState.action === "renaming"
                              ? "保存中..."
                              : "保存"}
                          </button>
                          <button
                            type="button"
                            className="secondary-button"
                            onClick={onCancelRename}
                            disabled={isDocumentBusy(document.document_id)}
                          >
                            取消
                          </button>
                        </div>
                      </div>
                    ) : (
                      <div>
                        <div className="document-title-row">
                          <strong>{document.title}</strong>
                          {activeReaderDocument?.document_id === document.document_id ? (
                            <span className="document-active-badge">当前打开</span>
                          ) : null}
                        </div>
                        <span>{formatCreatedAt(document.created_at)}</span>
                      </div>
                    )}
                    <div className="document-actions">
                      <button
                        type="button"
                        className={`lecture-notes-toggle-button${
                          isLectureNotesPaused ? " lecture-notes-toggle-button--resume" : ""
                        }`}
                        onClick={() => onToggleDocumentLectureNotesPaused(document)}
                        disabled={
                          isDocumentBusy(document.document_id) ||
                          document.course_summary_status !== "ready" ||
                          !document.course_summary
                        }
                        aria-label={lectureNotesToggleLabel}
                        title={lectureNotesToggleLabel}
                      >
                        <span
                          className={`lecture-notes-toggle-button__icon${
                            isLectureNotesPaused ? " lecture-notes-toggle-button__icon--resume" : ""
                          }`}
                          aria-hidden="true"
                        />
                      </button>
                      <button
                        type="button"
                        onClick={() => onOpenReader(document)}
                        disabled={isDocumentBusy(document.document_id) || document.page_count <= 0}
                      >
                        阅读 slides
                      </button>
                      <button
                        type="button"
                        className="secondary-button"
                        onClick={() => onStartRename(document)}
                        disabled={isDocumentBusy(document.document_id)}
                      >
                        重命名
                      </button>
                      <button
                        type="button"
                        className="danger-button"
                        onClick={() => onDeleteDocument(document)}
                        disabled={isDocumentBusy(document.document_id)}
                      >
                        {documentActionState?.documentId === document.document_id &&
                        documentActionState.action === "deleting"
                          ? "删除中..."
                          : "删除"}
                      </button>
                      <button
                        type="button"
                        className="secondary-button"
                        onClick={() => onToggleDocumentExpanded(document.document_id)}
                        disabled={isDocumentBusy(document.document_id)}
                      >
                        {isDocumentExpanded ? "收起" : "展开"}
                      </button>
                    </div>
                  </div>

                  <div className="generation-progress-box generation-progress-box--compact">
                    <div>
                      <strong>AI 生成进度</strong>
                      <p>{buildLectureNotesProgressText(statusData)}</p>
                    </div>
                    {isLectureNotesPaused ? (
                      <span className="document-status document-status--failed">已暂停</span>
                    ) : statusData?.should_poll ? (
                      <span className="document-status document-status--processing">自动刷新中</span>
                    ) : null}
                  </div>

                  {isDocumentExpanded ? (
                    <>
                      <dl>
                        <div>
                          <dt>document_id</dt>
                          <dd>{document.document_id}</dd>
                        </div>
                        <div>
                          <dt>状态</dt>
                          <dd>
                            <span className={`document-status document-status--${document.status}`}>
                              {getStatusLabel(document.status)}
                            </span>
                          </dd>
                        </div>
                        <div>
                          <dt>总页数</dt>
                          <dd>{document.page_count}</dd>
                        </div>
                        <div>
                          <dt>课程简介</dt>
                          <dd>
                            <span className={`document-status document-status--${document.course_summary_status}`}>
                              {getCourseSummaryStatusLabel(document.course_summary_status)}
                            </span>
                          </dd>
                        </div>
                      </dl>

                      {document.error_message ? <p className="document-error">{document.error_message}</p> : null}

                      <div className="generation-progress-box">
                        <div>
                          <strong>AI 生成进度</strong>
                          <p>{buildLectureNotesProgressText(statusData)}</p>
                        </div>
                        {statusData?.should_poll ? (
                          <span className="document-status document-status--processing">自动刷新中</span>
                        ) : null}
                        {isLectureNotesPaused ? (
                          <span className="document-status document-status--failed">已暂停</span>
                        ) : null}
                        {statusData?.lecture_notes_failed_count ? (
                          <p className="document-error">
                            有 {statusData.lecture_notes_failed_count} 页讲稿生成失败，可展开页面讲稿后单页重试。
                          </p>
                        ) : null}
                        {documentStatusMessage ? <p className="document-error">{documentStatusMessage}</p> : null}
                      </div>

                      <div className="course-summary-box">
                        {document.course_summary_status === "ready" && document.course_summary ? (
                          <>
                            <span>课程简介</span>
                            <MarkdownContent content={document.course_summary} variant="compact" />
                            <button
                              type="button"
                              className="secondary-action-button"
                              onClick={() => onRegenerateCourseSummary(document)}
                              disabled={isDocumentBusy(document.document_id)}
                            >
                              {documentActionState?.documentId === document.document_id &&
                              documentActionState.action === "regeneratingSummary"
                                ? "提交中..."
                                : "重新生成简介"}
                            </button>
                          </>
                        ) : null}
                        {document.course_summary_status === "processing" ? (
                          <p>课程简介正在生成，稍后刷新文档列表查看结果。</p>
                        ) : null}
                        {document.course_summary_status === "pending" ? (
                          <>
                            <p>课程简介还没有开始生成。</p>
                            <button
                              type="button"
                              className="secondary-action-button"
                              onClick={() => onRegenerateCourseSummary(document)}
                              disabled={isDocumentBusy(document.document_id)}
                            >
                              {documentActionState?.documentId === document.document_id &&
                              documentActionState.action === "regeneratingSummary"
                                ? "提交中..."
                                : "生成简介"}
                            </button>
                          </>
                        ) : null}
                        {document.course_summary_status === "failed" ? (
                          <>
                            <p className="document-error">
                              {document.course_summary_error ?? "课程简介生成失败。"}
                            </p>
                            <button
                              type="button"
                              className="secondary-action-button"
                              onClick={() => onRegenerateCourseSummary(document)}
                              disabled={isDocumentBusy(document.document_id)}
                            >
                              {documentActionState?.documentId === document.document_id &&
                              documentActionState.action === "regeneratingSummary"
                                ? "提交中..."
                                : "重新生成简介"}
                            </button>
                          </>
                        ) : null}
                      </div>

                      <div className="lecture-notes-box">
                        <div className="lecture-notes-header">
                          <span>逐页讲稿</span>
                          <div className="lecture-notes-actions">
                            <button
                              type="button"
                              className="secondary-action-button"
                              onClick={() => onToggleLectureNotesPanel(document)}
                              disabled={isDocumentBusy(document.document_id)}
                            >
                              {expandedLectureNotesDocumentId === document.document_id
                                ? "收起页面讲稿"
                                : "查看页面讲稿"}
                            </button>
                            <button
                              type="button"
                              className="secondary-action-button"
                              onClick={() => onGenerateRemainingLectureNotes(document)}
                              disabled={
                                isDocumentBusy(document.document_id) ||
                                document.course_summary_status !== "ready" ||
                                !document.course_summary
                              }
                            >
                              {documentActionState?.documentId === document.document_id &&
                              documentActionState.action === "generatingRemainingLectureNotes"
                                ? "提交中..."
                                : "生成剩余讲稿"}
                            </button>
                            <button
                              type="button"
                              className="secondary-action-button"
                              onClick={() => onRegenerateDocumentLectureNotes(document)}
                              disabled={
                                isDocumentBusy(document.document_id) ||
                                document.course_summary_status !== "ready" ||
                                !document.course_summary
                              }
                            >
                              {documentActionState?.documentId === document.document_id &&
                              documentActionState.action === "regeneratingLectureNotes" &&
                              documentActionState.pageNumber === undefined
                                ? "提交中..."
                                : "重新生成全部讲稿"}
                            </button>
                            <button
                              type="button"
                              className="secondary-action-button"
                              onClick={() => onClearLectureNotesQueue(document)}
                              disabled={isDocumentBusy(document.document_id)}
                            >
                              {documentActionState?.documentId === document.document_id &&
                              documentActionState.action === "clearingLectureNotesQueue"
                                ? "清空中..."
                                : "清空待生成队列"}
                            </button>
                          </div>
                        </div>

                        {document.course_summary_status !== "ready" || !document.course_summary ? (
                          <p>请先手动生成课程简介，再手动生成逐页讲稿。</p>
                        ) : null}

                        {expandedLectureNotesDocumentId === document.document_id ? (
                          <div className="lecture-notes-panel">
                            {pagesMessageByDocument[document.document_id] ? (
                              <p>{pagesMessageByDocument[document.document_id]}</p>
                            ) : null}
                            {(pagesByDocument[document.document_id] ?? []).length > 0 ? (
                              <ul className="lecture-notes-list">
                                {(pagesByDocument[document.document_id] ?? []).map((page) => (
                                  <li className="lecture-notes-item" key={page.page_id}>
                                    <div className="lecture-notes-item-header">
                                      <strong>第 {page.page_number} 页</strong>
                                      <span className={`document-status document-status--${page.lecture_notes_status}`}>
                                        {getLectureNotesStatusLabel(page.lecture_notes_status)}
                                      </span>
                                    </div>
                                    {page.lecture_notes ? (
                                      <MarkdownContent content={page.lecture_notes} variant="compact" />
                                    ) : null}
                                    {page.lecture_notes_status === "processing" ||
                                    page.lecture_notes_status === "pending" ? (
                                      <p>
                                        {page.lecture_notes
                                          ? "本页已有旧讲稿，新讲稿正在等待或生成中，完成后会自动替换。"
                                          : "本页讲稿正在等待或生成中。"}
                                      </p>
                                    ) : null}
                                    {page.status === "failed" && page.error_message ? (
                                      <p className="document-error">{page.error_message}</p>
                                    ) : null}
                                    {page.lecture_notes_status === "failed" ? (
                                      <p className="document-error">
                                        {page.lecture_notes_error ?? "本页讲稿生成失败。"}
                                      </p>
                                    ) : null}
                                    <button
                                      type="button"
                                      className="secondary-action-button"
                                      onClick={() => onRegeneratePageLectureNotes(document, page)}
                                      disabled={
                                        isDocumentBusy(document.document_id) ||
                                        document.course_summary_status !== "ready" ||
                                        !document.course_summary
                                      }
                                    >
                                      {isPageLectureNotesBusy(document.document_id, page.page_number)
                                        ? "提交中..."
                                        : page.lecture_notes_status === "failed"
                                          ? "重试本页讲稿"
                                          : "重新生成本页讲稿"}
                                    </button>
                                  </li>
                                ))}
                              </ul>
                            ) : null}
                          </div>
                        ) : null}
                      </div>
                    </>
                  ) : null}
                </li>
              );
            })}
          </ul>
        ) : (
          <p className="documents-empty">{documentsMessage}</p>
        )}

        {documentActionMessage ? (
          <p className="document-action-message">{documentActionMessage}</p>
        ) : null}
      </section>
    </>
  );
}
