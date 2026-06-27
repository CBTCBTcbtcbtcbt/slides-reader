import { render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { resolvePdfPageWidth, usePdfSizing } from "./usePdfSizing";

const originalResizeObserver = globalThis.ResizeObserver;

afterEach(() => {
  vi.restoreAllMocks();
  if (originalResizeObserver) {
    vi.stubGlobal("ResizeObserver", originalResizeObserver);
  } else {
    vi.unstubAllGlobals();
  }
});

function installLayoutMocks() {
  class TestResizeObserver {
    observe = vi.fn();
    disconnect = vi.fn();
  }

  vi.stubGlobal("ResizeObserver", TestResizeObserver);
  vi.spyOn(HTMLElement.prototype, "getBoundingClientRect").mockImplementation(function (
    this: HTMLElement,
  ) {
    const element = this as HTMLElement;
    const isWorkspaceElement = element.getAttribute("data-testid") === "workspace";
    const isStageElement = element.getAttribute("data-testid") === "stage";
    const width = isWorkspaceElement || isStageElement ? 1180 : 0;
    const height = isStageElement ? 700 : isWorkspaceElement ? 360 : 0;

    return {
      x: 0,
      y: 0,
      top: 0,
      left: 0,
      right: width,
      bottom: height,
      width,
      height,
      toJSON: () => ({}),
    } as DOMRect;
  });
}

function DelayedWorkspaceHarness({ showWorkspace }: { showWorkspace: boolean }) {
  const sizing = usePdfSizing({
    isReaderActive: true,
    readerRightSidebar: "none",
    isReaderTopbarCollapsed: false,
    isReaderChatCollapsed: true,
    isCourseSummaryPanelOpen: false,
    minThumbnailSidebarWidth: 28,
    minCourseSummarySidebarWidth: 220,
    thumbnailResizerWidth: 12,
    courseSummaryResizerWidth: 12,
    pdfReaderColumnGap: 16,
  });

  return (
    <>
      <output data-testid="size">
        {sizing.readerWorkspaceSize.width}x{sizing.readerWorkspaceSize.height}
      </output>
      {showWorkspace ? <section ref={sizing.readerWorkspaceRef} data-testid="workspace" /> : null}
    </>
  );
}

function StageMeasurementHarness() {
  const sizing = usePdfSizing({
    isReaderActive: true,
    readerRightSidebar: "none",
    isReaderTopbarCollapsed: false,
    isReaderChatCollapsed: true,
    isCourseSummaryPanelOpen: false,
    minThumbnailSidebarWidth: 28,
    minCourseSummarySidebarWidth: 220,
    thumbnailResizerWidth: 12,
    courseSummaryResizerWidth: 12,
    pdfReaderColumnGap: 16,
  });

  return (
    <>
      <output data-testid="size">
        {sizing.readerWorkspaceSize.width}x{sizing.readerWorkspaceSize.height}
      </output>
      <section ref={sizing.readerWorkspaceRef} data-testid="workspace">
        <div ref={sizing.readerPageStageRef} data-testid="stage" />
      </section>
    </>
  );
}

describe("resolvePdfPageWidth", () => {
  it("实际 PDF 舞台高度足够时，页面宽度填满舞台宽度", () => {
    const pdfPageWidth = resolvePdfPageWidth({
      readerWorkspaceSize: {
        width: 1180,
        height: 700,
      },
      readerViewportWidth: 1180,
      pdfPageNaturalSize: {
        width: 1600,
        height: 900,
      },
      minPdfPageStageWidth: 120,
    });

    expect(pdfPageWidth).toBe(1180);
  });

  it("没有测到实际舞台宽度时，继续使用旧的 viewport 宽度兜底", () => {
    const pdfPageWidth = resolvePdfPageWidth({
      readerWorkspaceSize: {
        width: 0,
        height: 0,
      },
      readerViewportWidth: 760,
      pdfPageNaturalSize: null,
      minPdfPageStageWidth: 120,
    });

    expect(pdfPageWidth).toBe(760);
  });
});

describe("usePdfSizing", () => {
  it("阅读器 DOM 在 active 后才挂载时仍会重新测量尺寸", async () => {
    installLayoutMocks();

    const { rerender } = render(<DelayedWorkspaceHarness showWorkspace={false} />);
    expect(screen.getByTestId("size")).toHaveTextContent("0x0");

    rerender(<DelayedWorkspaceHarness showWorkspace={true} />);

    await waitFor(() => {
      expect(screen.getByTestId("size")).not.toHaveTextContent("0x0");
    });
  });

  it("实际 PPT 舞台已挂载后优先使用舞台尺寸，而不是外层估算尺寸", async () => {
    installLayoutMocks();

    render(<StageMeasurementHarness />);

    await waitFor(() => {
      expect(screen.getByTestId("size")).toHaveTextContent("1180x700");
    });
  });
});
