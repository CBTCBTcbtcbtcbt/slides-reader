import type { DocumentItem, NoteBlockItem } from "../../types/api";
import type { NoteBlockLayout, NoteBlockResizeDirection } from "../../types/ui";
import { MarkdownContent } from "../MarkdownContent";

type NoteBlockProps = {
  // readerDocument 是当前阅读器打开的文档。
  readerDocument: DocumentItem;
  // noteBlock 是当前页讲稿文字块。
  noteBlock: NoteBlockItem;
  // layout 是拖拽或缩放过程中的当前布局。
  layout: NoteBlockLayout;
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
  noteBlock,
  layout,
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
        </div>
        <div className="lecture-note-block__content">
          <MarkdownContent content={noteBlock.content} variant="note" />
        </div>
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
