import type { Components } from "react-markdown";
import ReactMarkdown from "react-markdown";
import rehypeKatex from "rehype-katex";
import remarkGfm from "remark-gfm";
import remarkMath from "remark-math";
import "katex/dist/katex.min.css";

type MarkdownContentProps = {
  // content 是来自 LLM 或用户问答历史的 Markdown 字符串。
  content: string;
  // variant 用来按展示场景调整密度，避免同一套排版在小浮层里过大。
  variant?: "default" | "compact" | "chat" | "note";
};

const markdownComponents: Components = {
  a({ children, href, node: _node, ...props }) {
    // 链接统一新标签页打开，并阻止新页面拿到来源页面引用。
    return (
      <a {...props} href={href} target="_blank" rel="noreferrer">
        {children}
      </a>
    );
  },
  blockquote({ children, node: _node }) {
    // 引用块使用统一 class，样式里会加左边框和浅色背景。
    return <blockquote className="markdown-content__blockquote">{children}</blockquote>;
  },
  code({ children, className, node: _node, ...props }) {
    // react-markdown 会把代码块放在 pre > code 中，行内代码则没有外层 pre。
    return (
      <code className={className ? `markdown-content__code ${className}` : "markdown-content__code"} {...props}>
        {children}
      </code>
    );
  },
  pre({ children, node: _node }) {
    // 代码块允许横向滚动，避免长代码撑破侧栏或讲稿浮层。
    return <pre className="markdown-content__pre">{children}</pre>;
  },
  table({ children, node: _node }) {
    // 表格额外包一层容器，让窄侧栏内只滚动表格本身。
    return (
      <div className="markdown-content__table-wrapper">
        <table>{children}</table>
      </div>
    );
  },
  th({ children, node: _node, ...props }) {
    return <th {...props}>{children}</th>;
  },
  td({ children, node: _node, ...props }) {
    return <td {...props}>{children}</td>;
  },
};

export function MarkdownContent({ content, variant = "default" }: MarkdownContentProps) {
  const className =
    variant === "default" ? "markdown-content" : `markdown-content markdown-content--${variant}`;

  return (
    <div className={className}>
      <ReactMarkdown
        skipHtml
        remarkPlugins={[remarkGfm, remarkMath]}
        rehypePlugins={[rehypeKatex]}
        components={markdownComponents}
      >
        {content}
      </ReactMarkdown>
    </div>
  );
}
