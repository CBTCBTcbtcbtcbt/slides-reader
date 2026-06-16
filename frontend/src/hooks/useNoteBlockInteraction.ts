import { useEffect, useState } from "react";
import type { NoteBlockItem } from "../types/api";
import type {
  NoteBlockInteraction,
  NoteBlockLayout,
  NoteBlockResizeDirection,
} from "../types/ui";

type UseNoteBlockInteractionOptions = {
  // minWidth/minHeight 是讲稿文字块在前端交互层允许保存的最小尺寸。
  minWidth: number;
  minHeight: number;
  // saveNoteBlockPosition 会在用户松开鼠标时把最终位置保存到后端。
  saveNoteBlockPosition: (
    documentId: string,
    noteBlockId: string,
    nextPosition: NoteBlockLayout,
  ) => void | Promise<void>;
};

type UseNoteBlockInteractionResult = {
  draftNoteBlockLayouts: Record<string, NoteBlockLayout>;
  setDraftNoteBlockLayouts: React.Dispatch<React.SetStateAction<Record<string, NoteBlockLayout>>>;
  resolveNoteBlockLayout: (noteBlock: NoteBlockItem) => NoteBlockLayout;
  startNoteBlockDrag: (
    event: React.PointerEvent<HTMLDivElement>,
    documentId: string,
    noteBlock: NoteBlockItem,
  ) => void;
  startNoteBlockResize: (
    event: React.PointerEvent<HTMLButtonElement>,
    documentId: string,
    noteBlock: NoteBlockItem,
    resizeDirection: NoteBlockResizeDirection,
  ) => void;
};

export function useNoteBlockInteraction(
  options: UseNoteBlockInteractionOptions,
): UseNoteBlockInteractionResult {
  const [draftNoteBlockLayouts, setDraftNoteBlockLayouts] = useState<Record<string, NoteBlockLayout>>({});
  const [noteBlockInteraction, setNoteBlockInteraction] = useState<NoteBlockInteraction | null>(null);

  function updateDraftNoteBlockLayout(noteBlockId: string, nextLayout: NoteBlockLayout) {
    setDraftNoteBlockLayouts((currentLayouts) => ({
      ...currentLayouts,
      [noteBlockId]: nextLayout,
    }));
  }

  function resolveNoteBlockLayout(noteBlock: NoteBlockItem): NoteBlockLayout {
    return draftNoteBlockLayouts[noteBlock.note_block_id] ?? {
      x: noteBlock.x,
      y: noteBlock.y,
      width: noteBlock.width,
      height: noteBlock.height,
    };
  }

  function clampNoteBlockLayout(layout: NoteBlockLayout): NoteBlockLayout {
    return {
      x: Number.isFinite(layout.x) ? layout.x : 0,
      y: Number.isFinite(layout.y) ? layout.y : 0,
      width: Math.max(options.minWidth, Number.isFinite(layout.width) ? layout.width : options.minWidth),
      height: Math.max(options.minHeight, Number.isFinite(layout.height) ? layout.height : options.minHeight),
    };
  }

  function buildDraggedNoteBlockLayout(
    interaction: NoteBlockInteraction,
    event: PointerEvent,
  ): NoteBlockLayout {
    const deltaX = event.clientX - interaction.startClientX;
    const deltaY = event.clientY - interaction.startClientY;

    return clampNoteBlockLayout({
      ...interaction.startLayout,
      x: interaction.startLayout.x + deltaX,
      y: interaction.startLayout.y + deltaY,
    });
  }

  function buildResizedNoteBlockLayout(
    interaction: NoteBlockInteraction,
    event: PointerEvent,
  ): NoteBlockLayout {
    const direction = interaction.resizeDirection;
    const deltaX = event.clientX - interaction.startClientX;
    const deltaY = event.clientY - interaction.startClientY;
    const nextLayout = { ...interaction.startLayout };
    const normalizedDirection = direction?.toLowerCase() ?? "";

    if (normalizedDirection.includes("left")) {
      const nextWidth = Math.max(options.minWidth, interaction.startLayout.width - deltaX);
      nextLayout.x = interaction.startLayout.x + interaction.startLayout.width - nextWidth;
      nextLayout.width = nextWidth;
    }

    if (normalizedDirection.includes("right")) {
      nextLayout.width = Math.max(options.minWidth, interaction.startLayout.width + deltaX);
    }

    if (normalizedDirection.includes("top")) {
      const nextHeight = Math.max(options.minHeight, interaction.startLayout.height - deltaY);
      nextLayout.y = interaction.startLayout.y + interaction.startLayout.height - nextHeight;
      nextLayout.height = nextHeight;
    }

    if (normalizedDirection.includes("bottom")) {
      nextLayout.height = Math.max(options.minHeight, interaction.startLayout.height + deltaY);
    }

    return clampNoteBlockLayout(nextLayout);
  }

  useEffect(() => {
    if (!noteBlockInteraction) {
      return;
    }

    const activeInteraction = noteBlockInteraction;

    function handlePointerMove(event: PointerEvent) {
      const nextLayout =
        activeInteraction.mode === "drag"
          ? buildDraggedNoteBlockLayout(activeInteraction, event)
          : buildResizedNoteBlockLayout(activeInteraction, event);

      updateDraftNoteBlockLayout(activeInteraction.noteBlockId, nextLayout);
    }

    function handlePointerUp(event: PointerEvent) {
      const finalLayout =
        activeInteraction.mode === "drag"
          ? buildDraggedNoteBlockLayout(activeInteraction, event)
          : buildResizedNoteBlockLayout(activeInteraction, event);

      updateDraftNoteBlockLayout(activeInteraction.noteBlockId, finalLayout);
      void options.saveNoteBlockPosition(
        activeInteraction.documentId,
        activeInteraction.noteBlockId,
        finalLayout,
      );
      setNoteBlockInteraction(null);
    }

    document.body.style.userSelect = "none";
    window.addEventListener("pointermove", handlePointerMove);
    window.addEventListener("pointerup", handlePointerUp);

    return () => {
      document.body.style.userSelect = "";
      window.removeEventListener("pointermove", handlePointerMove);
      window.removeEventListener("pointerup", handlePointerUp);
    };
  }, [noteBlockInteraction, options]);

  function startNoteBlockDrag(
    event: React.PointerEvent<HTMLDivElement>,
    documentId: string,
    noteBlock: NoteBlockItem,
  ) {
    if (event.button !== 0) {
      return;
    }

    event.preventDefault();
    event.stopPropagation();
    setNoteBlockInteraction({
      noteBlockId: noteBlock.note_block_id,
      documentId,
      mode: "drag",
      resizeDirection: null,
      startClientX: event.clientX,
      startClientY: event.clientY,
      startLayout: resolveNoteBlockLayout(noteBlock),
    });
  }

  function startNoteBlockResize(
    event: React.PointerEvent<HTMLButtonElement>,
    documentId: string,
    noteBlock: NoteBlockItem,
    resizeDirection: NoteBlockResizeDirection,
  ) {
    if (event.button !== 0) {
      return;
    }

    event.preventDefault();
    event.stopPropagation();
    setNoteBlockInteraction({
      noteBlockId: noteBlock.note_block_id,
      documentId,
      mode: "resize",
      resizeDirection,
      startClientX: event.clientX,
      startClientY: event.clientY,
      startLayout: resolveNoteBlockLayout(noteBlock),
    });
  }

  return {
    draftNoteBlockLayouts,
    setDraftNoteBlockLayouts,
    resolveNoteBlockLayout,
    startNoteBlockDrag,
    startNoteBlockResize,
  };
}
