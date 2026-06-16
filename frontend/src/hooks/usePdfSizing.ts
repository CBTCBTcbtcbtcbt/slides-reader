import { useEffect, useRef, useState } from "react";
import type { ReaderRightSidebar, ReaderWorkspaceSize } from "../types/ui";

type UsePdfSizingOptions = {
  // isReaderActive 表示当前是否正在展示阅读器。
  isReaderActive: boolean;
  // readerRightSidebar 表示右侧栏是否打开，用来扣除可用宽度或高度。
  readerRightSidebar: ReaderRightSidebar;
  // isReaderTopbarCollapsed 和 isReaderChatCollapsed 会影响工作区高度。
  isReaderTopbarCollapsed: boolean;
  isReaderChatCollapsed: boolean;
  // isCourseSummaryPanelOpen 保留为依赖项，保证右侧简介切换时重新计算。
  isCourseSummaryPanelOpen: boolean;
  // 以下常量来自阅读器布局尺寸。
  minThumbnailSidebarWidth: number;
  minCourseSummarySidebarWidth: number;
  thumbnailResizerWidth: number;
  courseSummaryResizerWidth: number;
  pdfReaderColumnGap: number;
};

type UsePdfSizingResult = {
  readerViewportWidth: number;
  readerWorkspaceSize: ReaderWorkspaceSize;
  thumbnailSidebarWidth: number;
  courseSummarySidebarWidth: number;
  thumbnailRenderWidth: number;
  isResizingThumbnailSidebar: boolean;
  isResizingCourseSummarySidebar: boolean;
  readerViewportRef: React.RefObject<HTMLDivElement | null>;
  readerWorkspaceRef: React.RefObject<HTMLElement | null>;
  readerContentRef: React.RefObject<HTMLDivElement | null>;
  setReaderViewportWidth: React.Dispatch<React.SetStateAction<number>>;
  setReaderWorkspaceSize: React.Dispatch<React.SetStateAction<ReaderWorkspaceSize>>;
  startResizingThumbnailSidebar: (event: React.PointerEvent<HTMLButtonElement>) => void;
  startResizingCourseSummarySidebar: (event: React.PointerEvent<HTMLButtonElement>) => void;
};

export function usePdfSizing(options: UsePdfSizingOptions): UsePdfSizingResult {
  // readerViewportWidth 保留兼容旧计算，readerWorkspaceSize 是 PDF 页面实际尺寸依据。
  const [readerViewportWidth, setReaderViewportWidth] = useState(0);
  const [readerWorkspaceSize, setReaderWorkspaceSize] = useState<ReaderWorkspaceSize>({
    width: 0,
    height: 0,
  });

  // 左右侧栏宽度由用户拖动分隔条调整。
  const [thumbnailSidebarWidth, setThumbnailSidebarWidth] = useState(158);
  const [courseSummarySidebarWidth, setCourseSummarySidebarWidth] = useState(320);
  const [isResizingThumbnailSidebar, setIsResizingThumbnailSidebar] = useState(false);
  const [isResizingCourseSummarySidebar, setIsResizingCourseSummarySidebar] = useState(false);

  // 这些 ref 交给 ReaderView 的 DOM 元素使用。
  const readerViewportRef = useRef<HTMLDivElement | null>(null);
  const readerWorkspaceRef = useRef<HTMLElement | null>(null);
  const readerContentRef = useRef<HTMLDivElement | null>(null);

  // 缩略图渲染宽度从侧栏宽度推导，保持旧逻辑一致。
  const thumbnailRenderWidth = Math.max(24, thumbnailSidebarWidth - 40);

  useEffect(() => {
    if (!options.isReaderActive) {
      setReaderViewportWidth(0);
      setReaderWorkspaceSize({ width: 0, height: 0 });
      return;
    }

    const workspaceElement = readerWorkspaceRef.current;
    if (workspaceElement === null) {
      return;
    }

    const observedWorkspaceElement = workspaceElement;

    function updateReaderWorkspaceSize() {
      const workspaceRect = observedWorkspaceElement.getBoundingClientRect();
      const isNarrowWorkspace = workspaceRect.width <= 920;
      const thumbnailColumnWidth = isNarrowWorkspace
        ? 0
        : thumbnailSidebarWidth + options.thumbnailResizerWidth + options.pdfReaderColumnGap * 2;
      const rightSidebarColumnWidth =
        options.readerRightSidebar !== "none" && !isNarrowWorkspace
          ? courseSummarySidebarWidth + options.courseSummaryResizerWidth + options.pdfReaderColumnGap * 2
          : 0;
      const thumbnailRowHeight = isNarrowWorkspace ? 138 + options.pdfReaderColumnGap : 0;
      const summaryRowHeight =
        options.readerRightSidebar !== "none" && isNarrowWorkspace
          ? Math.max(160, Math.min(workspaceRect.height * 0.28, 260)) + options.pdfReaderColumnGap
          : 0;
      const nextWidth = Math.max(0, workspaceRect.width - thumbnailColumnWidth - rightSidebarColumnWidth - 32);
      const nextHeight = Math.max(0, workspaceRect.height - thumbnailRowHeight - summaryRowHeight - 32);

      setReaderViewportWidth(nextWidth);
      setReaderWorkspaceSize({ width: nextWidth, height: nextHeight });
    }

    updateReaderWorkspaceSize();

    const resizeObserver = new ResizeObserver(updateReaderWorkspaceSize);
    resizeObserver.observe(observedWorkspaceElement);

    return () => {
      resizeObserver.disconnect();
    };
  }, [
    options.isReaderActive,
    thumbnailSidebarWidth,
    courseSummarySidebarWidth,
    options.readerRightSidebar,
    options.isReaderTopbarCollapsed,
    options.isReaderChatCollapsed,
    options.isCourseSummaryPanelOpen,
    options.thumbnailResizerWidth,
    options.courseSummaryResizerWidth,
    options.pdfReaderColumnGap,
  ]);

  useEffect(() => {
    if (!isResizingThumbnailSidebar) {
      return;
    }

    function handlePointerMove(event: PointerEvent) {
      const readerContentElement = readerContentRef.current;
      if (readerContentElement === null) {
        return;
      }

      const contentRect = readerContentElement.getBoundingClientRect();
      const rawWidth = event.clientX - contentRect.left;
      const maxAllowedWidth = Math.max(options.minThumbnailSidebarWidth, contentRect.width);
      const nextWidth = Math.min(
        Math.max(rawWidth, options.minThumbnailSidebarWidth),
        maxAllowedWidth,
      );

      setThumbnailSidebarWidth(nextWidth);
    }

    function handlePointerUp() {
      setIsResizingThumbnailSidebar(false);
    }

    document.body.style.userSelect = "none";
    window.addEventListener("pointermove", handlePointerMove);
    window.addEventListener("pointerup", handlePointerUp);

    return () => {
      document.body.style.userSelect = "";
      window.removeEventListener("pointermove", handlePointerMove);
      window.removeEventListener("pointerup", handlePointerUp);
    };
  }, [isResizingThumbnailSidebar, options.minThumbnailSidebarWidth]);

  useEffect(() => {
    if (!isResizingCourseSummarySidebar) {
      return;
    }

    function handlePointerMove(event: PointerEvent) {
      const readerContentElement = readerContentRef.current;
      if (readerContentElement === null) {
        return;
      }

      const contentRect = readerContentElement.getBoundingClientRect();
      const rawWidth = contentRect.right - event.clientX;
      const maxAllowedWidth = Math.max(options.minCourseSummarySidebarWidth, contentRect.width);
      const nextWidth = Math.min(
        Math.max(rawWidth, options.minCourseSummarySidebarWidth),
        maxAllowedWidth,
      );

      setCourseSummarySidebarWidth(nextWidth);
    }

    function handlePointerUp() {
      setIsResizingCourseSummarySidebar(false);
    }

    document.body.style.userSelect = "none";
    window.addEventListener("pointermove", handlePointerMove);
    window.addEventListener("pointerup", handlePointerUp);

    return () => {
      document.body.style.userSelect = "";
      window.removeEventListener("pointermove", handlePointerMove);
      window.removeEventListener("pointerup", handlePointerUp);
    };
  }, [isResizingCourseSummarySidebar, options.minCourseSummarySidebarWidth]);

  function startResizingThumbnailSidebar(event: React.PointerEvent<HTMLButtonElement>) {
    event.preventDefault();
    setIsResizingThumbnailSidebar(true);
  }

  function startResizingCourseSummarySidebar(event: React.PointerEvent<HTMLButtonElement>) {
    event.preventDefault();
    setIsResizingCourseSummarySidebar(true);
  }

  return {
    readerViewportWidth,
    readerWorkspaceSize,
    thumbnailSidebarWidth,
    courseSummarySidebarWidth,
    thumbnailRenderWidth,
    isResizingThumbnailSidebar,
    isResizingCourseSummarySidebar,
    readerViewportRef,
    readerWorkspaceRef,
    readerContentRef,
    setReaderViewportWidth,
    setReaderWorkspaceSize,
    startResizingThumbnailSidebar,
    startResizingCourseSummarySidebar,
  };
}
