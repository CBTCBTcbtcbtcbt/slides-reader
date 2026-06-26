import { readFileSync } from "node:fs";
import { resolve } from "node:path";

import { describe, expect, it } from "vitest";

// base.css 放全局通用按钮样式，返回按钮属于多个页面共享的控件。
const baseCss = readFileSync(resolve(process.cwd(), "src/styles/base.css"), "utf8");

describe("页面返回按钮 CSS", () => {
  it("返回按钮使用统一工具型按钮风格，避免浏览器默认按钮外观", () => {
    expect(baseCss).toMatch(/\.page-back-button\s*\{[^}]*display:\s*inline-flex;/s);
    expect(baseCss).toMatch(/\.page-back-button\s*\{[^}]*border:\s*1px solid #c7d2e3;/s);
    expect(baseCss).toMatch(/\.page-back-button\s*\{[^}]*border-radius:\s*8px;/s);
    expect(baseCss).toMatch(/\.page-back-button\s*\{[^}]*background:\s*#ffffff;/s);
    expect(baseCss).toMatch(/\.page-back-button\s+\.app-icon\s*\{[^}]*width:\s*18px;/s);
  });
});
