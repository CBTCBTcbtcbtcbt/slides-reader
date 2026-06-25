import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { AppIcon } from "./AppIcon";

describe("AppIcon", () => {
  it("设置齿轮图标使用纯色 currentColor，并包含中心圆孔路径", () => {
    render(<AppIcon name="settings" ariaLabel="设置" />);

    const icon = screen.getByRole("img", { name: "设置" });
    const paths = icon.querySelectorAll("path");

    expect(icon).toHaveClass("app-icon");
    expect(icon).toHaveAttribute("viewBox", "0 0 24 24");
    expect(paths.length).toBeGreaterThanOrEqual(1);
    expect(paths[0]?.getAttribute("d")).toContain("a3.5 3.5");
    expect(paths[0]?.getAttribute("d")).toContain("a1.4 1.4");
  });

  it("装饰性图标默认从无障碍树中隐藏", () => {
    const { container } = render(<AppIcon name="upload" />);
    const icon = container.querySelector("svg");

    expect(icon).toHaveAttribute("aria-hidden", "true");
    expect(icon).not.toHaveAttribute("role");
  });
});
