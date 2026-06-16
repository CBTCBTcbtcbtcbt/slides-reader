# Markdown 与 LaTeX 渲染规划

本文档记录前端支持 Markdown 和 LaTeX 公式渲染的技术实现路线。

这里的 `Markdown` 是一种轻量级标记语言，可以用普通文本写出标题、列表、表格、代码块等结构。`LaTeX` 是常用于数学、物理和工程领域的公式排版语言。本项目中的课程简介、逐页讲稿和当前页问答都来自 LLM，这些内容天然适合使用 Markdown 保存和展示。

## 目标

本次改造目标是让所有 AI 生成内容看起来接近商业 AI 产品的前端界面：

- 支持 Markdown 标题、段落、列表、表格、引用、代码块和链接。
- 支持行内公式，例如 `$E=mc^2$`。
- 支持块级公式，例如：

```text
$$
\int_0^1 x^2 dx = \frac{1}{3}
$$
```

- 保持后端 API、数据库字段和 LLM 存储格式不变。
- 不执行 Markdown 里的 HTML，避免 XSS 风险。

`XSS` 是 `Cross-Site Scripting` 的缩写，中文通常叫“跨站脚本攻击”。它指的是恶意内容被浏览器当成脚本执行，从而窃取信息或破坏页面行为。

## 推荐技术路径

采用以下前端依赖：

```text
react-markdown
remark-gfm
remark-math
rehype-katex
katex
```

这些库的作用如下：

- `react-markdown`：把 Markdown 文本解析成 React 组件。
- `remark-gfm`：支持 GitHub Flavored Markdown，例如表格、任务列表、删除线。
- `remark-math`：识别 `$...$` 和 `$$...$$` 数学公式。
- `rehype-katex`：把识别出的数学公式交给 KaTeX 渲染。
- `katex`：快速渲染数学公式的库。

`GitHub Flavored Markdown` 是 GitHub 使用的 Markdown 扩展语法，常见能力包括表格、任务列表和删除线。`KaTeX` 是一个前端数学公式渲染库，速度快，适合聊天和讲稿这种需要频繁渲染的场景。

## 不采用的方案

### 不使用 markdown-it 作为第一版方案

`markdown-it` 是另一个 Markdown 解析库，插件生态比较丰富。但它通常会把 Markdown 转成 HTML 字符串，再通过 `dangerouslySetInnerHTML` 放进 React 页面。

`dangerouslySetInnerHTML` 是 React 提供的直接插入 HTML 的能力。它很强，但如果内容来自用户或 LLM，就必须额外做安全清洗，否则存在 XSS 风险。

当前项目第一版不需要这么底层的控制，所以优先使用 `react-markdown`。

### 不使用 MDX

`MDX` 可以理解为“Markdown 里可以写 React 组件”。它适合文档站或教程站，但不适合直接渲染 LLM 输出。

原因是：LLM 输出不应该被当成可执行组件代码处理，否则安全边界会变复杂。

### 不在后端预渲染 HTML

后端把 Markdown 转成 HTML 后再返回给前端也可行，但会带来几个问题：

- 前后端职责混乱。
- 前端仍然要安全插入 HTML。
- 样式调整会牵涉后端渲染逻辑。
- 当前项目本来就把 LLM 输出作为 Markdown 字符串保存，前端渲染更直接。

因此第一版只改前端展示层。

## 组件设计

新增统一组件：

```text
frontend/src/components/MarkdownContent.tsx
```

组件输入：

```ts
type MarkdownContentProps = {
  content: string;
  variant?: "default" | "compact" | "chat" | "note";
};
```

字段含义：

- `content`：需要渲染的 Markdown 字符串。
- `variant`：展示场景，用来控制样式密度。

`variant` 约定：

- `default`：普通正文，用于课程简介。
- `compact`：更紧凑的正文，用于文档列表里的简介和逐页讲稿列表。
- `chat`：问答消息，用于当前页聊天历史。
- `note`：讲稿浮层，用于 PDF 页面上的可拖动讲稿文字块。

组件内部使用：

```tsx
<ReactMarkdown
  skipHtml
  remarkPlugins={[remarkGfm, remarkMath]}
  rehypePlugins={[rehypeKatex]}
  components={...}
>
  {content}
</ReactMarkdown>
```

关键规则：

- 必须设置 `skipHtml`，让 Markdown 里的 HTML 不作为真实 DOM 渲染。
- 不引入 `rehype-raw`。
- 不使用 `dangerouslySetInnerHTML`。
- 链接统一加上 `target="_blank"` 和 `rel="noreferrer"`。

`target="_blank"` 表示链接在新标签页打开。`rel="noreferrer"` 可以减少新页面获取来源页面信息的风险。

## 自定义渲染规则

`MarkdownContent` 应自定义这些 HTML 标签对应的 React 渲染：

- `a`：外部链接，新标签页打开。
- `p`：段落，控制上下间距。
- `ul` / `ol`：列表，控制缩进和项目间距。
- `blockquote`：引用块，使用左边框和浅色背景。
- `code`：行内代码，使用等宽字体和浅色底。
- `pre`：代码块，允许横向滚动。
- `table`：表格外层包一层滚动容器，避免撑破侧栏。
- `th` / `td`：表头和单元格，使用清晰边框和内边距。

表格必须特别处理，因为课程简介侧栏和问答侧栏宽度有限。如果表格太宽，应该在表格自身内部横向滚动，而不是撑破整个页面。

## 样式设计

在 `frontend/src/styles.css` 增加以下样式模块：

```text
.markdown-content
.markdown-content--compact
.markdown-content--chat
.markdown-content--note
.markdown-content__table-wrapper
```

基础样式要求：

- 字体大小继承所在区域，不使用过大的标题。
- 标题层级清晰，但不能像页面 hero 一样夸张。
- 段落之间有适度间距。
- 列表缩进稳定，不挤压文字。
- 表格边框清晰，窄容器内可以横向滚动。
- 代码块使用等宽字体，保留换行。
- 公式块居中或自然换行，不遮挡其他内容。
- 链接颜色清晰，hover 状态可识别。

`note` 变体需要更紧凑：

- 标题字号不能太大。
- 段落间距更小。
- 列表缩进更浅。
- 代码块和表格允许滚动。

原因是讲稿浮层是可拖动的小窗口，如果 Markdown 排版过大，会挤占 PDF 页面视野。

## 替换范围

第一版需要替换所有 AI 输出位置。

### 课程简介

替换位置：

- 文档列表中的课程简介。
- 阅读器右侧课程简介。

当前类似：

```tsx
<p>{document.course_summary}</p>
```

目标：

```tsx
<MarkdownContent content={document.course_summary} variant="compact" />
```

阅读器右侧课程简介可使用：

```tsx
<MarkdownContent content={readerDocument.course_summary} />
```

### 逐页讲稿

替换位置：

- 文件页展开后的逐页讲稿列表。
- 阅读器 PDF 页面上的讲稿浮层。

讲稿列表可使用：

```tsx
<MarkdownContent content={page.lecture_notes} variant="compact" />
```

讲稿浮层可使用：

```tsx
<MarkdownContent content={currentNoteBlock.content} variant="note" />
```

### 当前页问答

替换位置：

- 阅读器底部或右侧问答历史里的每条消息。

建议：

```tsx
<MarkdownContent content={chatMessage.content} variant="chat" />
```

用户消息也可以走 Markdown 渲染，但要保持安全规则一致。因为组件禁用 HTML，所以用户输入不会直接执行 HTML。

### LLM 测试回答

替换位置：

- 设置页里模型连接测试返回的回答。

建议：

```tsx
<MarkdownContent content={llmTestAnswer} variant="compact" />
```

## 不替换范围

以下内容继续使用普通文本：

- 错误提示。
- 状态提示。
- 按钮文案。
- 文档标题。
- 页码。
- 进度说明。

原因是这些内容不是 LLM 正文，不需要 Markdown 解析。保持普通文本更简单、更安全。

## 任务拆解

### 任务 1：安装依赖

目标：

- 在 `frontend` 目录安装渲染依赖。

命令：

```powershell
cd frontend
npm install react-markdown remark-gfm remark-math rehype-katex katex
```

验收标准：

- `frontend/package.json` 出现新增依赖。
- `frontend/package-lock.json` 更新。
- `npm run build` 不因为依赖缺失失败。

### 任务 2：创建 MarkdownContent 组件

目标：

- 新建统一渲染组件。

实现要求：

- 文件路径：`frontend/src/components/MarkdownContent.tsx`。
- 使用 `ReactMarkdown`、`remarkGfm`、`remarkMath`、`rehypeKatex`。
- 设置 `skipHtml`。
- 自定义链接、代码、表格、引用块等常见元素。

验收标准：

- 组件可以被 `App.tsx` 导入。
- TypeScript 编译通过。
- 组件不使用 `dangerouslySetInnerHTML`。

### 任务 3：引入 KaTeX 样式和 Markdown 样式

目标：

- 让 Markdown 和公式有稳定、专业的视觉表现。

实现要求：

- 在 `MarkdownContent.tsx` 或 `main.tsx` 导入：

```ts
import "katex/dist/katex.min.css";
```

- 在 `styles.css` 增加 `.markdown-content` 相关样式。
- 表格增加横向滚动容器样式。

验收标准：

- 标题、列表、表格、代码块、公式看起来清晰。
- 窄侧栏内表格不会撑破布局。
- 讲稿浮层内 Markdown 不会挤爆窗口。

### 任务 4：替换 AI 输出位置

目标：

- 所有 LLM 输出统一使用 `MarkdownContent`。

替换范围：

- 文档列表课程简介。
- 阅读器右侧课程简介。
- 页面讲稿列表。
- 阅读器讲稿浮层。
- 当前页问答消息。
- LLM 测试回答。

验收标准：

- 普通纯文本仍能显示。
- Markdown 标题和列表能显示。
- 公式能显示。
- 页面无 React key、类型或样式错误。

### 任务 5：构造测试内容并手动验收

建议测试内容：

````markdown
# 课程主题

这是一段包含 **加粗**、*斜体* 和 `inline code` 的文字。

## 列表

- 第一项
- 第二项

1. 第一步
2. 第二步

## 表格

| 概念 | 含义 |
| --- | --- |
| Token | 模型处理文本的基本单位 |
| Context | 模型一次请求能看到的上下文 |

行内公式：$E=mc^2$

块级公式：

$$
\int_0^1 x^2 dx = \frac{1}{3}
$$

```python
def hello():
    print("hello")
```
````

验收位置：

- 课程简介。
- 逐页讲稿。
- 当前页问答回答。
- 讲稿浮层。
- LLM 测试回答。

验收标准：

- Markdown 正常渲染。
- 公式正常渲染。
- 表格不撑破侧栏。
- 代码块可读。
- HTML 不执行。

### 任务 6：构建检查

目标：

- 确保前端生产构建通过。

命令：

```powershell
cd frontend
npm run build
```

验收标准：

- 构建成功。
- 如果只出现 Vite chunk size 警告，可以接受。

## 安全要求

必须遵守：

- 不使用 `dangerouslySetInnerHTML`。
- 不引入 `rehype-raw`。
- `ReactMarkdown` 开启 `skipHtml`。
- 外部链接使用 `rel="noreferrer"`。

原因：

- AI 输出和用户输入都不能被信任为安全 HTML。
- Markdown 渲染应只负责文本结构和公式显示，不应该执行脚本或事件。

## 后续增强

第一版完成后，可以考虑：

- 支持代码块复制按钮。
- 支持 Mermaid 图表。
- 支持脚注。
- 支持目录锚点。
- 支持问答消息里的引用来源。
- 为 Markdown 渲染组件补充前端单元测试。

这些增强不进入第一版验收范围。
