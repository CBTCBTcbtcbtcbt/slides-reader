import { readFileSync } from "node:fs";
import { resolve } from "node:path";

import { describe, expect, it } from "vitest";

// 这里直接读取 CSS 源文件，用来保护应用外壳这种纯样式行为不被后续修改破坏。
const appShellCss = readFileSync(resolve(process.cwd(), "src/styles/app-shell.css"), "utf8");

describe("AppShell CSS", () => {
  it("左侧主导航固定跟随视口，而不是跟随长页面内容滚动", () => {
    // position: sticky 让左侧栏在普通文档流中保留占位，同时滚动时粘在视口顶部。
    expect(appShellCss).toMatch(/\.app-shell-rail\s*\{[^}]*position:\s*sticky;/s);
    expect(appShellCss).toMatch(/\.app-shell-rail\s*\{[^}]*top:\s*0;/s);

    // height: 100vh 让设置按钮始终落在屏幕左下，而不是长页面底部。
    expect(appShellCss).toMatch(/\.app-shell-rail\s*\{[^}]*height:\s*100vh;/s);
  });
});
