import { readFileSync } from "node:fs";
import { resolve } from "node:path";

import { describe, expect, it } from "vitest";

// base.css 是文件页、设置页和状态横幅的基础样式来源。
const baseCss = readFileSync(resolve(process.cwd(), "src/styles/base.css"), "utf8");
// reader.css 是阅读页桌面布局和折叠顶部栏布局的基础样式来源。
const readerCss = readFileSync(resolve(process.cwd(), "src/styles/reader.css"), "utf8");
// responsive.css 负责不同屏幕宽度下的布局降级规则。
const responsiveCss = readFileSync(resolve(process.cwd(), "src/styles/responsive.css"), "utf8");

describe("移动端响应式 CSS", () => {
  it("状态横幅的文字区域允许收缩并换行，避免撑出横向滚动", () => {
    // flex 子项默认的 min-width 是 auto，长文本会把卡片撑宽。
    expect(baseCss).toMatch(/\.connection-card\s*>\s*div\s*\{[^}]*min-width:\s*0;/s);

    // 后端错误文案包含 FastAPI 等英文片段，需要允许任意位置断行。
    expect(baseCss).toMatch(/\.connection-card\s+strong\s*\{[^}]*overflow-wrap:\s*anywhere;/s);
    expect(baseCss).toMatch(/\.connection-card\s+p\s*\{[^}]*overflow-wrap:\s*anywhere;/s);
  });

  it("阅读页顶部栏在 1080p 宽度下把翻页控件放到独立行，避免按钮和状态文字重叠", () => {
    // 1080p 笔记本浏览器可用宽度通常低于大屏桌面，需要在 920px 移动端断点前先降级顶部栏。
    expect(responsiveCss).toMatch(/@media\s*\(max-width:\s*1280px\)\s*\{[\s\S]*\.reader-topbar\s*\{/);

    // 翻页控件跨完整网格宽度后，不再和左侧文档状态、右侧操作按钮争抢同一行空间。
    expect(responsiveCss).toMatch(
      /@media\s*\(max-width:\s*1280px\)\s*\{[\s\S]*\.reader-topbar-center\s*\{[^}]*grid-column:\s*1\s*\/\s*-1;/,
    );

    // 讲稿进度文本必须允许收缩并保持省略号，否则长状态文案会重新把顶部栏撑开。
    expect(responsiveCss).toMatch(
      /@media\s*\(max-width:\s*1280px\)\s*\{[\s\S]*\.reader-progress-text\s*\{[^}]*max-width:\s*min\(100%,\s*720px\);/,
    );
  });

  it("折叠后的阅读页顶部栏为翻页控件保留右侧布局区域", () => {
    // 折叠态顶部栏需要继续显示上一页和下一页，所以翻页容器必须参与布局而不是被隐藏。
    expect(readerCss).toMatch(/\.reader-collapsed-page-controls\s*\{[^}]*display:\s*flex;/s);
    expect(readerCss).toMatch(
      /\.reader-collapsed-page-controls\s+\.pdf-reader-toolbar\s*\{[^}]*justify-content:\s*flex-end;/s,
    );

    // 920px 以下折叠栏变成单列，翻页控件靠左排列，避免小屏继续挤压标题。
    expect(responsiveCss).toMatch(
      /@media\s*\(max-width:\s*920px\)\s*\{[\s\S]*\.reader-collapsed-page-controls,\s*[\s\S]*\.reader-collapsed-page-controls\s+\.pdf-reader-toolbar\s*\{[^}]*justify-content:\s*flex-start;/,
    );
  });
});
