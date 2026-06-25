import { readFileSync } from "node:fs";
import { resolve } from "node:path";

import { describe, expect, it } from "vitest";

// base.css 是文件页、设置页和状态横幅的基础样式来源。
const baseCss = readFileSync(resolve(process.cwd(), "src/styles/base.css"), "utf8");

describe("移动端响应式 CSS", () => {
  it("状态横幅的文字区域允许收缩并换行，避免撑出横向滚动", () => {
    // flex 子项默认的 min-width 是 auto，长文本会把卡片撑宽。
    expect(baseCss).toMatch(/\.connection-card\s*>\s*div\s*\{[^}]*min-width:\s*0;/s);

    // 后端错误文案包含 FastAPI 等英文片段，需要允许任意位置断行。
    expect(baseCss).toMatch(/\.connection-card\s+strong\s*\{[^}]*overflow-wrap:\s*anywhere;/s);
    expect(baseCss).toMatch(/\.connection-card\s+p\s*\{[^}]*overflow-wrap:\s*anywhere;/s);
  });
});
