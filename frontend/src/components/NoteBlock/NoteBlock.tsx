import type { DocumentItem, NoteBlockItem, PageItem } from "../../types/api";
import type { NoteBlockLayout, NoteBlockResizeDirection } from "../../types/ui";

type NoteBlockProps = {
  // readerDocument 是当前阅读器打开的文档。
  readerDocument: DocumentItem;
  // currentReaderPage 是当前页数据，用于触发单页重生成。
  currentReaderPage: PageItem | undefined;
  // noteBlock 是当前页讲稿文字块。
  noteBlock: NoteBlockItem;
  // layout 是拖拽或缩放过程中的当前布局。
  layout: NoteBlockLayout;
  // isDocumentBusy 判断文档是否正在执行其他操作。
  isDocumentBusy: (documentId: string) => boolean;
  // isPageLectureNotesBusy 判断当前页讲稿是否正在重新生成。
  isPageLectureNotesBusy: (documentId: string, pageNumber: number) => boolean;
  // onRegeneratePageLectureNotes 触发单页讲稿重生成。
  onRegeneratePageLectureNotes: (document: DocumentItem, page: PageItem) => void;
  // onStartDrag 开始拖动文字块。
  onStartDrag: (
    event: React.PointerEvent<HTMLDivElement>,
    documentId: string,
    noteBlock: NoteBlockItem,
  ) => void;
  // onStartResize 开始缩放文字块。
  onStartResize: (
    event: React.PointerEvent<HTMLButtonElement>,
    documentId: string,
    noteBlock: NoteBlockItem,
    resizeDirection: NoteBlockResizeDirection,
  ) => void;
};

const RESIZE_DIRECTIONS = [
  "top",
  "right",
  "bottom",
  "left",
  "topRight",
  "bottomRight",
  "bottomLeft",
  "topLeft",
] satisfies NoteBlockResizeDirection[];

export function NoteBlock({
  readerDocument,
  currentReaderPage,
  noteBlock,
  layout,
  isDocumentBusy,
  isPageLectureNotesBusy,
  onRegeneratePageLectureNotes,
  onStartDrag,
  onStartResize,
}: NoteBlockProps) {
  return (
    <div
      className="lecture-note-block"
      style={{
        left: layout.x,
        top: layout.y,
        width: layout.width,
        height: layout.height,
      }}
    >
      <div className="lecture-note-block__shell">
        <div
          className="lecture-note-block__handle"
          onPointerDown={(event) => onStartDrag(event, readerDocument.document_id, noteBlock)}
        >
          <span>本页讲稿</span>
          <button
            type="button"
            className="lecture-note-block__regenerate"
            onPointerDown={(event) => event.stopPropagation()}
            onClick={() => {
              if (currentReaderPage) {
                onRegeneratePageLectureNotes(readerDocument, currentReaderPage);
              }
            }}
            disabled={
              !currentReaderPage ||
              isDocumentBusy(readerDocument.document_id) ||
              readerDocument.course_summary_status !== "ready" ||
              !readerDocument.course_summary
            }
          >
            {currentReaderPage &&
            isPageLectureNotesBusy(readerDocument.document_id, currentReaderPage.page_number)
              ? "提交中..."
              : "重生成"}
          </button>
        </div>
        <div className="lecture-note-block__content">{noteBlock.content}</div>
        {RESIZE_DIRECTIONS.map((resizeDirection) => (
          <button
            type="button"
            key={resizeDirection}
            className={`lecture-note-block__resize-handle lecture-note-block__resize-handle--${resizeDirection}`}
            onPointerDown={(event) =>
              onStartResize(event, readerDocument.document_id, noteBlock, resizeDirection)
            }
            aria-label="调整讲稿文字块大小"
          />
        ))}
      </div>
    </div>
  );
}
