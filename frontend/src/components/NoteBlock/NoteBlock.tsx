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
  // isCollapsed 表示讲稿正文是否被折叠成 PDF 页面上的小浮动条。
  isCollapsed: boolean;
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
  // onCollapse 把当前讲稿浮层折叠成小浮动条。
  onCollapse: (noteBlockId: string) => void;
  // onExpand 从小浮动条恢复完整讲稿浮层。
  onExpand: (noteBlockId: string) => void;
  // onOpenInSidebar 把当前讲稿正文移到右侧栏展示。
  onOpenInSidebar: (noteBlockId: string) => void;
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
  isCollapsed,
  onStartDrag,
  onStartResize,
  onCollapse,
  onExpand,
  onOpenInSidebar,
}: NoteBlockProps) {
  const blockStyle = isCollapsed
    ? {
        left: layout.x,
        top: layout.y,
        width: Math.min(Math.max(layout.width, 180), 280),
      }
    : {
        left: layout.x,
        top: layout.y,
        width: layout.width,
        height: layout.height,
      };

  if (isCollapsed) {
    return (
      <div className="lecture-note-block lecture-note-block--collapsed" style={blockStyle}>
        <div
          className="lecture-note-block__collapsed-bar"
          onPointerDown={(event) => onStartDrag(event, readerDocument.document_id, noteBlock)}
        >
          <span>本页讲稿</span>
          <button
            type="button"
            onPointerDown={(event) => event.stopPropagation()}
            onClick={() => onExpand(noteBlock.note_block_id)}
          >
            展开
          </button>
        </div>
      </div>
    );
  }

  return (
    <div
      className="lecture-note-block"
      style={blockStyle}
    >
      <div className="lecture-note-block__shell">
        <div
          className="lecture-note-block__handle"
          onPointerDown={(event) => onStartDrag(event, readerDocument.document_id, noteBlock)}
        >
          <span>本页讲稿</span>
          <div className="lecture-note-block__actions">
            <button
              type="button"
              onPointerDown={(event) => event.stopPropagation()}
              onClick={() => onCollapse(noteBlock.note_block_id)}
            >
              折叠
            </button>
            <button
              type="button"
              onPointerDown={(event) => event.stopPropagation()}
              onClick={() => onOpenInSidebar(noteBlock.note_block_id)}
            >
              右栏
            </button>
          </div>
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
