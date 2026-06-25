import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { AppShell } from "./AppShell";

const defaultProps = {
  activeSection: "files" as const,
  canReturnToReader: true,
  onNavigateFiles: vi.fn(),
  onNavigateReader: vi.fn(),
  onNavigateWrongBook: vi.fn(),
  onNavigatePhaseExam: vi.fn(),
  onNavigateSettings: vi.fn(),
};

describe("AppShell", () => {
  const originalMatchMedia = window.matchMedia;

  afterEach(() => {
    window.matchMedia = originalMatchMedia;
  });

  it("渲染主导航并高亮当前页面", () => {
    render(
      <AppShell {...defaultProps}>
        <div>页面内容</div>
      </AppShell>,
    );

    expect(screen.getByRole("button", { name: "课件库" })).toHaveAttribute("aria-current", "page");
    expect(screen.getByRole("button", { name: "阅读" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "错题本" })).toBeInTheDocument();
    expect(screen.getByText("页面内容")).toBeInTheDocument();
  });

  it("深度折叠后只保留圆弧朝右的半圆展开按钮", async () => {
    const user = userEvent.setup();

    render(
      <AppShell {...defaultProps}>
        <div>页面内容</div>
      </AppShell>,
    );

    await user.click(screen.getByRole("button", { name: "折叠主导航" }));

    const shell = screen.getByTestId("app-shell");
    const toggleButton = screen.getByRole("button", { name: "展开主导航" });

    expect(shell).toHaveClass("app-shell-layout--collapsed");
    expect(toggleButton).toHaveClass("app-shell-collapse-tab");
    expect(toggleButton).toHaveClass("app-shell-collapse-tab--collapsed");
    expect(screen.queryByRole("button", { name: "课件库" })).not.toBeInTheDocument();
  });

  it("窄屏下默认深度折叠，避免左侧栏挤压内容", () => {
    window.matchMedia = vi.fn().mockImplementation((query: string) => ({
      matches: query === "(max-width: 560px)",
      media: query,
      onchange: null,
      addListener: vi.fn(),
      removeListener: vi.fn(),
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
      dispatchEvent: vi.fn(),
    }));

    render(
      <AppShell {...defaultProps}>
        <div>页面内容</div>
      </AppShell>,
    );

    expect(screen.getByTestId("app-shell")).toHaveClass("app-shell-layout--collapsed");
    expect(screen.getByRole("button", { name: "展开主导航" })).toHaveClass(
      "app-shell-collapse-tab--collapsed",
    );
  });
});
