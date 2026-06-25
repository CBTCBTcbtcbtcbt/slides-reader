// 这个 setup 文件会在 Vitest 运行每个测试文件前加载。
// jest-dom 会给 expect 增加面向 DOM 的断言，例如 toBeInTheDocument。
import "@testing-library/jest-dom/vitest";
import { cleanup } from "@testing-library/react";
import { afterEach } from "vitest";

// 每个组件测试结束后清理 jsdom，避免前一个 render 残留到下一个测试。
afterEach(() => {
  cleanup();
});
