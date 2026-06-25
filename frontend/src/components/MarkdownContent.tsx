import type { Components } from "react-markdown";
import ReactMarkdown from "react-markdown";
import rehypeKatex from "rehype-katex";
import remarkGfm from "remark-gfm";
import remarkMath from "remark-math";
import "katex/dist/katex.min.css";

const MATH_FENCE_LANGUAGES = new Set(["math", "tex", "latex", "katex"]);
const MATH_COMMAND_PATTERN =
  /\\(?:frac|sqrt|sum|prod|int|lim|left|right|begin|end|partial|nabla|theta|alpha|beta|gamma|delta|epsilon|varepsilon|sigma|lambda|mu|mathbb|mathbf|mathrm|text|cdot|times|infty|approx|propto|leq|geq|neq|hat|bar|tilde|vec|overline|underline|operatorname)\b/;
const MATH_SYMBOL_PATTERN = /[∇∞∂∑∏∫≈≠≤≥±×÷√∝θαβγδελμσπΩ]/;
const CJK_CHARACTER_PATTERN = /[\u3400-\u9fff]/;
const LATIN_WORD_PATTERN = /[A-Za-z]{3,}/g;
const FORMULA_ALLOWED_TEXT_PATTERN =
  /^[\s\\A-Za-z0-9_$^{}[\]()+\-*/=.,:;|<>!&%'"`~?∇∞∂∑∏∫≈≠≤≥±×÷√∝θαβγδελμσπΩ]+$/;

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

function isFenceStart(line: string) {
  // Markdown 代码围栏以三个以上反引号或波浪线开头，后面可以带语言名。
  return line.match(/^(\s*)(`{3,}|~{3,})\s*(\S*)\s*$/);
}

function normalizeMathFence(fenceLanguage: string, lines: string[]) {
  // LLM 常把纯公式放进 ```math / ```latex 代码块，这里转回展示公式。
  if (!MATH_FENCE_LANGUAGES.has(fenceLanguage.toLowerCase())) {
    return null;
  }

  const formula = lines.join("\n").trim();
  if (!formula) {
    return "";
  }

  return `$$\n${formula}\n$$`;
}

function isLikelyFormulaLine(value: string) {
  const text = value.trim();

  if (!text) {
    return false;
  }

  if (CJK_CHARACTER_PATTERN.test(text) || !FORMULA_ALLOWED_TEXT_PATTERN.test(text)) {
    return false;
  }

  const latinWords = text.match(LATIN_WORD_PATTERN) ?? [];
  const allowedLatexWords = latinWords.filter((word) => text.includes(`\\${word}`));
  if (latinWords.length > allowedLatexWords.length + 2) {
    return false;
  }

  if (text.includes("\\begin") && text.includes("\\end")) {
    return true;
  }

  if (MATH_COMMAND_PATTERN.test(text)) {
    return /[=_^{}+\-*/∇∞∂∑∏∫≈≠≤≥±×÷√∝]/.test(text);
  }

  return MATH_SYMBOL_PATTERN.test(text) && /[=+\-/*_^()[\]{}]/.test(text);
}

function normalizeIndentedMathBlocks(markdown: string) {
  // Markdown 会把四个空格开头的段落当作代码块；公式被 LLM 缩进时需要转成展示公式。
  const lines = markdown.split("\n");
  const normalizedLines: string[] = [];
  let index = 0;

  while (index < lines.length) {
    const line = lines[index];
    if (!/^( {4}|\t)/.test(line)) {
      normalizedLines.push(line);
      index += 1;
      continue;
    }

    const blockLines: string[] = [];
    while (index < lines.length && /^( {4}|\t)/.test(lines[index])) {
      blockLines.push(lines[index].replace(/^( {4}|\t)/, ""));
      index += 1;
    }

    const blockText = blockLines.join("\n").trim();
    if (isLikelyFormulaLine(blockText)) {
      normalizedLines.push(`$$\n${blockText}\n$$`);
    } else {
      normalizedLines.push(...blockLines.map((blockLine) => `    ${blockLine}`));
    }
  }

  return normalizedLines.join("\n");
}

function normalizeMathDelimiters(markdown: string) {
  // remark-math 默认识别 $...$ 和 $$...$$，不直接识别 LaTeX 文档风格的 \(...\) 与 \[...\]。
  return markdown
    .replace(/\\\[([\s\S]*?)\\\]/g, (_match, formula: string) => `$$\n${formula.trim()}\n$$`)
    .replace(/\\\(([\s\S]*?)\\\)/g, (_match, formula: string) => `$${formula.trim()}$`);
}

function stripOuterMarkdownFence(content: string) {
  // LLM 有时把整份讲稿包进 ```markdown 代码块；显示时应按普通 Markdown 渲染。
  const trimmedContent = content.trim();
  for (const language of ["markdown", "md"]) {
    const openingFence = "```" + language;
    if (trimmedContent.toLowerCase().startsWith(openingFence) && trimmedContent.endsWith("```")) {
      return trimmedContent.slice(openingFence.length, -3).trim();
    }
  }

  if (trimmedContent.startsWith("```") && trimmedContent.endsWith("```")) {
    const innerContent = trimmedContent.slice(3, -3).trim();
    if (innerContent.startsWith("#") || innerContent.includes("\n#") || innerContent.includes("\n- ")) {
      return innerContent;
    }
  }

  return content;
}

function normalizeLooseStrongMarkers(markdown: string) {
  // LLM 偶尔会把 **加粗** 写成 * *加粗* *，这里修成标准 Markdown 语法。
  return markdown.replace(/\*\s+\*([\s\S]*?)\*\s+\*/g, (_match, strongText: string) => {
    const trimmedStrongText = strongText.trim();
    return trimmedStrongText ? `**${trimmedStrongText}**` : _match;
  });
}

function normalizeStandaloneFormulaLines(markdown: string) {
  const lines = markdown.split("\n");
  const normalizedLines: string[] = [];
  let isInsideFence = false;
  let fenceMarker = "";
  let isInsideDisplayMath = false;

  for (const line of lines) {
    const fenceMatch = isFenceStart(line);
    if (fenceMatch) {
      const marker = fenceMatch[2][0];
      if (!isInsideFence) {
        isInsideFence = true;
        fenceMarker = marker;
      } else if (marker === fenceMarker) {
        isInsideFence = false;
        fenceMarker = "";
      }
      normalizedLines.push(line);
      continue;
    }

    const trimmedLine = line.trim();
    if (!isInsideFence && trimmedLine === "$$") {
      isInsideDisplayMath = !isInsideDisplayMath;
      normalizedLines.push(line);
      continue;
    }

    if (
      !isInsideFence &&
      !isInsideDisplayMath &&
      isLikelyFormulaLine(line) &&
      !trimmedLine.startsWith("$")
    ) {
      normalizedLines.push(`$$\n${line.trim()}\n$$`);
    } else {
      normalizedLines.push(line);
    }
  }

  return normalizedLines.join("\n");
}

function normalizeMathFences(markdown: string) {
  const lines = markdown.split("\n");
  const normalizedLines: string[] = [];
  let index = 0;

  while (index < lines.length) {
    const fenceMatch = isFenceStart(lines[index]);
    if (!fenceMatch) {
      normalizedLines.push(lines[index]);
      index += 1;
      continue;
    }

    const fenceMarker = fenceMatch[2][0];
    const fenceLanguage = fenceMatch[3] ?? "";
    const fenceContent: string[] = [];
    const fenceStartLine = lines[index];
    index += 1;

    while (index < lines.length) {
      const maybeFenceEnd = isFenceStart(lines[index]);
      if (maybeFenceEnd && maybeFenceEnd[2][0] === fenceMarker) {
        break;
      }

      fenceContent.push(lines[index]);
      index += 1;
    }

    const convertedFence = normalizeMathFence(fenceLanguage, fenceContent);
    if (convertedFence === null) {
      normalizedLines.push(fenceStartLine, ...fenceContent);
      if (index < lines.length) {
        normalizedLines.push(lines[index]);
      }
    } else if (convertedFence) {
      normalizedLines.push(convertedFence);
    }

    if (index < lines.length) {
      index += 1;
    }
  }

  return normalizedLines.join("\n");
}

function normalizeMarkdownMath(content: string) {
  // 归一化顺序要先处理围栏，再处理缩进和行级公式，避免误改普通代码块里的内容。
  const withMathFences = normalizeMathFences(content);
  const withStrongMarkers = normalizeOutsideFences(withMathFences, normalizeLooseStrongMarkers);
  const withMathDelimiters = normalizeOutsideFences(withStrongMarkers, normalizeMathDelimiters);
  const withIndentedMath = normalizeOutsideFences(withMathDelimiters, normalizeIndentedMathBlocks);

  return normalizeOutsideFences(
    withIndentedMath,
    normalizeStandaloneFormulaLines,
  );
}

function normalizeOutsideFences(markdown: string, normalizeSegment: (segment: string) => string) {
  // 普通代码围栏里的内容必须原样保留，只处理围栏外的自然语言和公式。
  const lines = markdown.split("\n");
  const normalizedLines: string[] = [];
  let pendingOutsideLines: string[] = [];
  let isInsideFence = false;
  let fenceMarker = "";

  function flushOutsideLines() {
    if (pendingOutsideLines.length === 0) {
      return;
    }

    normalizedLines.push(normalizeSegment(pendingOutsideLines.join("\n")));
    pendingOutsideLines = [];
  }

  for (const line of lines) {
    const fenceMatch = isFenceStart(line);
    if (fenceMatch) {
      const marker = fenceMatch[2][0];
      if (!isInsideFence) {
        flushOutsideLines();
        isInsideFence = true;
        fenceMarker = marker;
        normalizedLines.push(line);
        continue;
      }

      if (marker === fenceMarker) {
        isInsideFence = false;
        fenceMarker = "";
      }
      normalizedLines.push(line);
      continue;
    }

    if (isInsideFence) {
      normalizedLines.push(line);
    } else {
      pendingOutsideLines.push(line);
    }
  }

  flushOutsideLines();
  return normalizedLines.join("\n");
}

export function MarkdownContent({ content, variant = "default" }: MarkdownContentProps) {
  const className =
    variant === "default" ? "markdown-content" : `markdown-content markdown-content--${variant}`;
  const normalizedContent = normalizeMarkdownMath(stripOuterMarkdownFence(content));

  return (
    <div className={className}>
      <ReactMarkdown
        skipHtml
        remarkPlugins={[remarkGfm, remarkMath]}
        rehypePlugins={[[rehypeKatex, { strict: false, throwOnError: false }]]}
        components={markdownComponents}
      >
        {normalizedContent}
      </ReactMarkdown>
    </div>
  );
}
