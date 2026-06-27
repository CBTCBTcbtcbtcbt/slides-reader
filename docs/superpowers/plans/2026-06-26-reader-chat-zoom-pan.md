# Reader Chat Zoom Pan Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将阅读页会话改成“右栏展开/底部收缩”两态，并给 PDF 主阅读区增加 100%-400% 缩放和长按拖动平移。

**Architecture:** 在 `App.tsx` 保存阅读页缩放比例和平移状态，`ReaderView` 负责展示右下角缩放控件、把缩放后的宽度传给 `react-pdf`，并在 PDF 舞台上处理 pointer 拖动。会话 UI 删除底部展开面板，只保留底部收缩条和右栏完整会话。

**Tech Stack:** React、TypeScript、Vitest、Testing Library、CSS。

---

### Task 1: 锁定会话两态和缩放控件测试

**Files:**
- Modify: `frontend/src/components/ReaderView/ReaderView.test.tsx`

- [ ] **Step 1: 写失败测试**

新增测试：底部收缩栏应有“打开右侧问答”，不再出现“展开会话”；右栏会话打开时底部收缩栏不渲染；缩放控件包含缩小、放大、滑块和百分比。

- [ ] **Step 2: 运行测试确认失败**

Run: `cd frontend && npm run test -- src/components/ReaderView/ReaderView.test.tsx`

Expected: FAIL，因为旧 UI 仍有底部展开会话，且没有缩放控件。

### Task 2: 实现缩放和平移状态

**Files:**
- Modify: `frontend/src/App.tsx`
- Modify: `frontend/src/components/ReaderView/ReaderView.tsx`
- Modify: `frontend/src/types/ui.ts`

- [ ] **Step 1: 在 App 中增加缩放比例和平移状态**

添加 `pdfZoomPercent`、`pdfPanOffset` 和相关 handler。`pdfPageWidth` 改为自动适配宽度乘以缩放倍数。

- [ ] **Step 2: 在 ReaderView 中渲染缩放控件**

右下角添加 `-`、`range`、`+`、百分比文本。范围 100 到 400，步长 10。

- [ ] **Step 3: 在 PDF 舞台处理拖动**

当缩放大于 100% 时，pointer down 后捕获指针，pointer move 更新平移偏移；缩放回 100% 时重置偏移。

### Task 3: 删除底部展开会话面板

**Files:**
- Modify: `frontend/src/components/ReaderView/ReaderView.tsx`
- Modify: `frontend/src/styles/reader.css`
- Modify: `frontend/src/styles/responsive.css`

- [ ] **Step 1: 删除 ReaderView 的底部展开分支**

底部只保留收缩条。点击按钮调用 `onOpenChatSidebar`。

- [ ] **Step 2: 清理不再使用的底部展开样式**

保留 `.reader-chat-collapsed`，删除或弱化 `.reader-chat-dock` 相关使用。

### Task 4: 验证

**Files:**
- Test: `frontend/src/components/ReaderView/ReaderView.test.tsx`

- [ ] **Step 1: 运行目标测试**

Run: `cd frontend && npm run test -- src/components/ReaderView/ReaderView.test.tsx`

- [ ] **Step 2: 运行全量前端测试和构建**

Run: `cd frontend && npm run test`

Run: `cd frontend && npm run build`

- [ ] **Step 3: 真实浏览器验证**

打开 `/#/documents/<ready-document-id>/read?page=1`，验证右下角缩放、拖动和右栏会话。
