import { useCallback, useEffect, useLayoutEffect, useRef, useState } from "react";
import type { PdfPageNaturalSize, ReaderRightSidebar, ReaderWorkspaceSize } from "../types/ui";

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
  readerViewportRef: React.RefCallback<HTMLDivElement>;
  readerWorkspaceRef: React.RefCallback<HTMLElement>;
  readerContentRef: React.RefCallback<HTMLDivElement>;
  readerPageStageRef: React.RefCallback<HTMLDivElement>;
  setReaderViewportWidth: React.Dispatch<React.SetStateAction<number>>;
  setReaderWorkspaceSize: React.Dispatch<React.SetStateAction<ReaderWorkspaceSize>>;
  startResizingThumbnailSidebar: (event: React.PointerEvent<HTMLButtonElement>) => void;
  startResizingCourseSummarySidebar: (event: React.PointerEvent<HTMLButtonElement>) => void;
};

type ResolvePdfPageWidthOptions = {
  readerWorkspaceSize: ReaderWorkspaceSize;
  readerViewportWidth: number;
  pdfPageNaturalSize: PdfPageNaturalSize | null;
  minPdfPageStageWidth: number;
};

export function resolvePdfPageWidth({
  readerWorkspaceSize,
  readerViewportWidth,
  pdfPageNaturalSize,
  minPdfPageStageWidth,
}: ResolvePdfPageWidthOptions) {
  // readerWorkspaceSize 现在表示真实 PDF 舞台尺寸；宽高都可用时按比例完整放下当前页。
  if (readerWorkspaceSize.width > 0) {
    const pdfPageAspectRatio =
      pdfPageNaturalSize && pdfPageNaturalSize.height > 0
        ? pdfPageNaturalSize.width / pdfPageNaturalSize.height
        : null;
    const pdfPageWidthByHeight =
      pdfPageAspectRatio && readerWorkspaceSize.height > 0
        ? readerWorkspaceSize.height * pdfPageAspectRatio
        : readerWorkspaceSize.width;

    return Math.max(
      minPdfPageStageWidth,
      Math.min(readerWorkspaceSize.width, pdfPageWidthByHeight),
    );
  }

  // PDF 舞台还没有挂载时保留旧兜底，避免 React-PDF 收到无意义的 0 宽度。
  return readerViewportWidth > 0 ? readerViewportWidth : undefined;
}

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
  const readerViewportElementRef = useRef<HTMLDivElement | null>(null);
  const readerWorkspaceElementRef = useRef<HTMLElement | null>(null);
  const readerContentElementRef = useRef<HTMLDivElement | null>(null);
  const readerPageStageElementRef = useRef<HTMLDivElement | null>(null);
  const [readerElementVersion, setReaderElementVersion] = useState(0);

  // 缩略图渲染宽度从侧栏宽度推导，保持旧逻辑一致。
  const thumbnailRenderWidth = Math.max(24, thumbnailSidebarWidth - 40);

  const readerViewportRef = useCallback((element: HTMLDivElement | null) => {
    if (readerViewportElementRef.current === element) {
      return;
    }

    readerViewportElementRef.current = element;
    setReaderElementVersion((version) => version + 1);
  }, []);

  const readerWorkspaceRef = useCallback((element: HTMLElement | null) => {
    if (readerWorkspaceElementRef.current === element) {
      return;
    }

    readerWorkspaceElementRef.current = element;
    setReaderElementVersion((version) => version + 1);
  }, []);

  const readerContentRef = useCallback((element: HTMLDivElement | null) => {
    if (readerContentElementRef.current === element) {
      return;
    }

    readerContentElementRef.current = element;
    setReaderElementVersion((version) => version + 1);
  }, []);

  const readerPageStageRef = useCallback((element: HTMLDivElement | null) => {
    if (readerPageStageElementRef.current === element) {
      return;
    }

    readerPageStageElementRef.current = element;
    setReaderElementVersion((version) => version + 1);
  }, []);

  useLayoutEffect(() => {
    if (!options.isReaderActive) {
      setReaderViewportWidth(0);
      setReaderWorkspaceSize({ width: 0, height: 0 });
      return;
    }

    const hasObservedElement =
      readerWorkspaceElementRef.current !== null ||
      readerViewportElementRef.current !== null ||
      readerContentElementRef.current !== null ||
      readerPageStageElementRef.current !== null;
    if (!hasObservedElement) {
      return;
    }

    function commitReaderWorkspaceSize(nextSize: ReaderWorkspaceSize) {
      setReaderViewportWidth((currentWidth) =>
        currentWidth === nextSize.width ? currentWidth : nextSize.width,
      );
      setReaderWorkspaceSize((currentSize) =>
        currentSize.width === nextSize.width && currentSize.height === nextSize.height
          ? currentSize
          : nextSize,
      );
    }

    function updateReaderWorkspaceSize() {
      const pageStageElement = readerPageStageElementRef.current;

      if (pageStageElement !== null) {
        // 真实的 PDF 舞台区域已经挂载后，以它的尺寸为准，避免外层估算在刷新时拿到过小值。
        const stageRect = pageStageElement.getBoundingClientRect();
        commitReaderWorkspaceSize({
          width: Math.max(0, stageRect.width),
          height: Math.max(0, stageRect.height),
        });
        return;
      }

      const workspaceElement = readerWorkspaceElementRef.current;
      if (workspaceElement === null) {
        return;
      }

      // PDF 页真正挂载前只能用外层工作区估算一次，保证加载状态和 React-PDF 初始渲染有兜底宽度。
      const workspaceRect = workspaceElement.getBoundingClientRect();
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

      commitReaderWorkspaceSize({ width: nextWidth, height: nextHeight });
    }

    updateReaderWorkspaceSize();

    const resizeObserver = new ResizeObserver(updateReaderWorkspaceSize);
    const observedElements = [
      readerWorkspaceElementRef.current,
      readerViewportElementRef.current,
      readerContentElementRef.current,
      readerPageStageElementRef.current,
    ].filter((element): element is HTMLElement => element !== null);

    observedElements.forEach((element) => {
      resizeObserver.observe(element);
    });

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
    readerElementVersion,
  ]);

  useEffect(() => {
    if (!isResizingThumbnailSidebar) {
      return;
    }

    function handlePointerMove(event: PointerEvent) {
      const readerContentElement = readerContentElementRef.current;
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
      const readerContentElement = readerContentElementRef.current;
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
    readerPageStageRef,
    setReaderViewportWidth,
    setReaderWorkspaceSize,
    startResizingThumbnailSidebar,
    startResizingCourseSummarySidebar,
  };
}
