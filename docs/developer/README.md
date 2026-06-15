# Slides Reader 开发者文档

这组文档是项目第一版完成后的长期开发上下文。后续如果删除 `docs/tasks/` 目录，应以这里的内容作为理解项目、扩展功能和排查问题的主要依据。

## 文档阅读顺序

建议按下面顺序阅读：

1. [项目总览](./01-项目总览.md)
2. [运行与开发环境](./02-运行与开发环境.md)
3. [后端架构](./03-后端架构.md)
4. [数据模型与状态机](./04-数据模型与状态机.md)
5. [API 接口契约](./05-API接口契约.md)
6. [LLM 工作流](./06-LLM工作流.md)
7. [前端架构](./07-前端架构.md)
8. [测试与验收](./08-测试与验收.md)
9. [后续开发路线](./09-后续开发路线.md)

## 当前版本定位

当前项目是一个本地单用户的 AI slides 阅读与授课工具。用户上传 PDF、PPT 或 PPTX slides 后，系统会完成以下流程：

1. 将上传文件统一保存或转换为系统实际使用的 PDF。
2. 用 `PyMuPDF` 解析 PDF 页数和每页文字。
3. 为每页渲染 PNG 截图。
4. 使用 OpenAI-compatible LLM 生成课程简介。
5. 在课程简介生成成功后，逐页生成老师讲稿。
6. 在阅读器中展示系统实际使用的 PDF、页面缩略图、可拖动讲稿文字块、课程简介侧栏和当前页问答。
7. 针对当前页保存独立问答历史。

这里的 `LLM` 是 `Large Language Model` 的缩写，中文通常叫“大语言模型”。本项目中，LLM 的角色不是普通摘要工具，而是模拟老师讲课、解释知识点并回答学生问题。

## 技术栈

- 后端：`Python + FastAPI`
- 数据库：`SQLite`
- PDF 处理：`PyMuPDF`
- LLM 调用：`OpenAI-compatible chat completions API`
- 前端：`React + TypeScript + Vite`
- PDF 前端渲染：`react-pdf` 和其底层依赖 `PDF.js`

`FastAPI` 是 Python Web 框架，用来编写 HTTP API。`SQLite` 是一个本地文件数据库，所有数据保存在单个 `.db` 文件中。`React` 是前端界面库，`TypeScript` 是带类型检查的 JavaScript，`Vite` 是前端开发服务器和打包工具。

## 重要设计原则

- 上传的 PDF、页面截图和数据库都是运行数据，不是源码。
- 所有 LLM 配置必须能通过 WebUI 修改，环境变量只作为第一次启动时的默认值来源。
- API Key 不允许以明文返回给前端。
- PDF 解析失败不能导致后端服务崩溃。
- 课程简介失败不能破坏 PDF 页面记录。
- 某一页讲稿失败不能影响其他页面继续生成或显示已有讲稿。
- 当前页问答失败时，用户问题仍然要保存。
- 逐页讲稿生成允许暂停和继续；暂停只阻止后续页面开始生成，已经发给 LLM 的当前请求会自然完成。
- 讲稿文字块每页第一版只保留一个，位置和尺寸由前端拖动后保存到后端。
- 前端 prompt 类设置默认折叠，展开后应完整显示全部 prompt 内容，不依赖文本框内部滚动查看。

## 当前代码结构

```text
slides-reader/
  backend/
    main.py                 # 后端单文件入口，包含 API、数据库、PDF、LLM 和后台生成逻辑
    requirements.txt        # 后端 Python 依赖
  frontend/
    src/
      App.tsx               # 前端主要 React 组件，包含三个视图和全部核心状态
      main.tsx              # React 挂载入口
      styles.css            # 全局样式和阅读器布局
    package.json            # 前端依赖和 npm scripts
    vite.config.ts          # Vite 配置和 /api 代理
  docs/
    developer/              # 长期开发者文档
    tasks/                  # 初版任务文档，可在迁移确认后删除
  storage/                  # 运行数据目录，包含 PDF、截图和 SQLite 数据库
  launch.ps1                # 一键启动前后端开发服务的 PowerShell 脚本
```

## 第一版主要限制

- 后端集中在 `backend/main.py`，还没有拆分成模块。
- 前端集中在 `frontend/src/App.tsx`，还没有拆分组件和 API 层。
- 数据库直接使用 `sqlite3`，没有 ORM。`ORM` 是对象关系映射工具，可以把数据库表映射成代码里的类；当前项目为了简单没有使用。
- 后台任务使用 `FastAPI BackgroundTasks`，适合本地开发和轻量任务，不适合多进程、多用户或长时间任务队列。
- LLM 请求使用标准库 `urllib.request`，没有使用 OpenAI 官方 SDK。
- LLM 输出按普通 Markdown 文本保存，前端当前主要以纯文本换行方式展示，还没有完整 Markdown 和 LaTeX 渲染。
- PPT/PPTX 上传通过 LibreOffice 同步转换为 PDF，后续流程继续围绕 PDF。
