# Slides Reader 开发者文档

本目录面向开发者，用来说明当前代码已经实现的结构、接口、状态流转、测试方式和启动器打包方式。根目录 `README.md` 面向普通用户，只说明如何启动和使用；开发细节统一放在这里。

## 阅读顺序

建议按下面顺序阅读：

1. [项目总览](./01-项目总览.md)
2. [运行与开发环境](./02-运行与开发环境.md)
3. [后端架构](./03-后端架构.md)
4. [数据模型与状态机](./04-数据模型与状态机.md)
5. [API 接口契约](./05-API接口契约.md)
6. [LLM 工作流](./06-LLM工作流.md)
7. [前端架构](./07-前端架构.md)
8. [测试与验收](./08-测试与验收.md)
9. [考试、错题本与阶段考试](./09-考试错题本与阶段考试.md)
10. [启动器、日志与轻量 EXE](./10-启动器日志与轻量EXE.md)

## 当前系统定位

Slides Reader 是一个本地单用户 AI slides 阅读与授课工具。用户上传 PDF、PPT 或 PPTX 后，后端会统一保存或转换为 PDF，再解析每页文字和截图，并调用 OpenAI-compatible LLM 完成课程简介、逐页讲稿、当前页问答、试卷生成和阶段考试生成。

`LLM` 是 `Large Language Model` 的缩写，中文通常叫“大语言模型”。本项目中，LLM 的角色不是普通摘要工具，而是模拟老师讲课、解释知识点、围绕当前页回答问题，并根据课件生成练习题。

## 技术栈

- 后端：`Python + FastAPI`
- 数据库：`SQLite`
- PDF 处理：`PyMuPDF`
- PPT/PPTX 转 PDF：`LibreOffice`
- LLM 调用：`OpenAI-compatible chat completions API`
- 前端：`React + TypeScript + Vite`
- PDF 前端渲染：`react-pdf` 和 `PDF.js`
- 前端测试：`Vitest + Testing Library`
- 后端测试：`pytest`

`FastAPI` 是 Python Web 框架。`SQLite` 是本地文件数据库。`React` 是前端界面库。`TypeScript` 是带类型检查的 JavaScript。`Vite` 是前端开发服务器和构建工具。

## 已实现的主要能力

- 一键启动器 `start.py`：自动检查依赖、构建前端、启动 FastAPI、等待服务就绪并打开浏览器。
- 统一日志目录 `storage/logs/`：记录启动器、依赖安装、前端构建、后端服务和诊断信息。
- PDF/PPT/PPTX 上传：PPT/PPTX 通过 LibreOffice 转换成 PDF。
- PDF 页面解析：使用 PyMuPDF 提取每页文字并渲染 PNG 截图。
- 文档管理：列表、重命名、删除和生成状态轮询。
- LLM 设置页：保存模型服务地址、API Key、模型名、超时时间和 prompt。
- 课程简介生成：上传解析成功后自动生成，也支持手动重新生成。
- 逐页讲稿生成：课程简介完成后自动逐页生成，支持暂停、继续、整份重新生成和单页重新生成。
- 阅读器：PDF 阅读、缩略图导航、课程简介侧栏、当前页问答侧栏和可拖动讲稿文字块。
- 当前页问答：支持按页保存历史，支持流式输出，支持用户上传或粘贴 PNG/JPEG/WebP 图片。
- Markdown 和 LaTeX 渲染：统一使用安全的 Markdown 组件展示 LLM 输出和公式。
- 普通试卷：基于单份课件生成试卷、答题、判分和删除。
- 错题本：保存答错题目，支持标记已复习和移除。
- 阶段考试：基于多份课件生成综合试卷，支持刷新、开始和删除。
- 自动化测试：后端 API 契约测试、前端 hook 与组件测试。

## 代码边界

源码目录：

```text
backend/
frontend/
docs/
start.py
README.md
```

运行数据目录：

```text
storage/
```

`storage/` 不是源码，包含 SQLite 数据库、上传后的 PDF、页面截图、聊天附件和日志。测试和临时运行可以通过 `SLIDES_READER_STORAGE_DIR` 指向其他目录，避免污染真实开发数据。
