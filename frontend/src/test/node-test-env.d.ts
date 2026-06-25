// 这个声明文件只补足测试代码读取本地 CSS 文件时需要的极少量 Node.js 类型。
// 项目没有安装 @types/node，因此这里避免把完整 Node 类型依赖引入前端生产代码。
declare module "node:fs" {
  export function readFileSync(path: string, encoding: "utf8"): string;
}

declare module "node:path" {
  export function resolve(...paths: string[]): string;
}

declare const process: {
  cwd(): string;
};
