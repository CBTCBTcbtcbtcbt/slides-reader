import { useCallback, useEffect, useRef, useState } from "react";
import type { CSSProperties } from "react";
import {
  Document as PdfDocument,
  Page as PdfPage,
  Thumbnail as PdfThumbnail,
  pdfjs,
} from "react-pdf";
import "react-pdf/dist/Page/AnnotationLayer.css";
import "react-pdf/dist/Page/TextLayer.css";

// React-PDF 依赖 PDF.js worker 在浏览器后台解析 PDF。
// 官方文档要求 workerSrc 和使用 <Document>/<Page> 的代码放在同一个模块里，避免模块执行顺序覆盖配置。
pdfjs.GlobalWorkerOptions.workerSrc = new URL(
  "pdfjs-dist/build/pdf.worker.min.mjs",
  import.meta.url,
).toString();

type HealthState = "checking" | "success" | "error";

type UploadState = "idle" | "uploading" | "success" | "error";

type LLMConfigState = "idle" | "loading" | "saving" | "testing" | "success" | "error";

type ReaderState = "idle" | "loading" | "ready" | "error";

type AppView = "files" | "reader" | "settings";

type ReaderRightSidebar = "none" | "summary" | "chat";

type ReaderWorkspaceSize = {
  width: number;
  height: number;
};

type PdfPageNaturalSize = {
  width: number;
  height: number;
};

type LoadedPdfPage = {
  originalWidth: number;
  originalHeight: number;
};

type HealthResponse = {
  status: string;
  service: string;
};

type UploadResponse = {
  document_id: string;
  title: string;
  filename: string;
  file_path: string;
  saved_filename: string;
  status: string;
  page_count: number;
  error_message: string | null;
  course_summary: string | null;
  course_summary_status: string;
  course_summary_error: string | null;
  lecture_notes_paused: boolean;
  created_at: string;
};

type DocumentItem = {
  document_id: string;
  title: string;
  file_path: string;
  status: string;
  page_count: number;
  error_message: string | null;
  course_summary: string | null;
  course_summary_status: string;
  course_summary_error: string | null;
  lecture_notes_paused: boolean;
  created_at: string;
};

type NoteBlockItem = {
  note_block_id: string;
  page_id: string;
  content: string;
  x: number;
  y: number;
  width: number;
  height: number;
  created_at: string;
  updated_at: string;
};

type NoteBlockLayout = Pick<NoteBlockItem, "x" | "y" | "width" | "height">;

type NoteBlockResizeDirection =
  | "top"
  | "right"
  | "bottom"
  | "left"
  | "topRight"
  | "bottomRight"
  | "bottomLeft"
  | "topLeft";

type NoteBlockInteraction = {
  noteBlockId: string;
  documentId: string;
  mode: "drag" | "resize";
  resizeDirection: NoteBlockResizeDirection | null;
  startClientX: number;
  startClientY: number;
  startLayout: NoteBlockLayout;
};

type ChatMessageItem = {
  chat_message_id: string;
  page_id: string;
  role: "user" | "assistant";
  content: string;
  created_at: string;
};

type PageItem = {
  page_id: string;
  document_id: string;
  page_number: number;
  text: string;
  image_path: string | null;
  image_url: string | null;
  status: string;
  error_message: string | null;
  lecture_notes: string | null;
  lecture_notes_status: string;
  lecture_notes_error: string | null;
  note_block: NoteBlockItem | null;
  chat_messages: ChatMessageItem[];
  created_at: string;
};

type DocumentActionState = {
  documentId: string;
  pageNumber?: number;
  action:
    | "renaming"
    | "deleting"
    | "regeneratingSummary"
    | "regeneratingLectureNotes"
    | "pausingLectureNotes"
    | "resumingLectureNotes";
} | null;

type LLMConfigResponse = {
  base_url: string;
  model: string;
  timeout_seconds: number;
  course_summary_prompt: string;
  lecture_notes_prompt: string;
  page_chat_prompt: string;
  api_key_configured: boolean;
  api_key_preview: string;
};

type LLMTestResponse = {
  status: string;
  answer: string;
};

type PageChatResponse = {
  status: string;
  page_id: string;
  user_message: ChatMessageItem;
  assistant_message: ChatMessageItem;
  messages: ChatMessageItem[];
};

type DocumentStatusPageItem = {
  page_id: string;
  page_number: number;
  status: string;
  error_message: string | null;
  lecture_notes_status: string;
  lecture_notes_error: string | null;
};

type DocumentStatusResponse = {
  document_id: string;
  title: string;
  status: string;
  error_message: string | null;
  course_summary_status: string;
  course_summary_error: string | null;
  course_summary_ready: boolean;
  total_pages: number;
  lecture_notes_ready_count: number;
  lecture_notes_failed_count: number;
  lecture_notes_processing_count: number;
  lecture_notes_pending_count: number;
  lecture_notes_paused: boolean;
  should_poll: boolean;
  pages: DocumentStatusPageItem[];
};

const MIN_THUMBNAIL_SIDEBAR_WIDTH = 28;
const MIN_COURSE_SUMMARY_SIDEBAR_WIDTH = 220;
const THUMBNAIL_RESIZER_WIDTH = 12;
const COURSE_SUMMARY_RESIZER_WIDTH = 12;
const PDF_READER_COLUMN_GAP = 16;
const MIN_PDF_PAGE_STAGE_WIDTH = 120;
const MIN_NOTE_BLOCK_WIDTH = 120;
const MIN_NOTE_BLOCK_HEIGHT = 80;
const DOCUMENT_STATUS_POLL_INTERVAL_MS = 2000;

function App() {
  // currentView 用来控制当前展示文件页、阅读页还是设置页。
  const [currentView, setCurrentView] = useState<AppView>("files");

  // connectionState 用来记录当前前端连接后端的状态。
  const [connectionState, setConnectionState] = useState<HealthState>("checking");

  // message 用来显示给用户看的连接结果说明。
  const [message, setMessage] = useState("正在检查后端连接...");

  // selectedFile 用来保存用户当前选择的 slides 文件。
  const [selectedFile, setSelectedFile] = useState<File | null>(null);

  // uploadState 用来记录上传流程的当前状态。
  const [uploadState, setUploadState] = useState<UploadState>("idle");

  // uploadMessage 用来给用户展示上传成功或失败的说明。
  const [uploadMessage, setUploadMessage] = useState("请选择一个 PDF/PPT/PPTX slides 文件。");

  // uploadedDocumentId 用来显示后端返回的 document_id。
  const [uploadedDocumentId, setUploadedDocumentId] = useState<string | null>(null);

  // documents 用来保存后端返回的已上传文档列表。
  const [documents, setDocuments] = useState<DocumentItem[]>([]);

  // documentsMessage 用来显示文档列表加载状态或错误信息。
  const [documentsMessage, setDocumentsMessage] = useState("正在加载已上传文档...");

  // documentStatusById 用来按 document_id 缓存后端状态接口返回的生成进度。
  const [documentStatusById, setDocumentStatusById] = useState<
    Record<string, DocumentStatusResponse>
  >({});

  // documentStatusMessage 用来展示状态轮询失败等不阻塞页面使用的提示。
  const [documentStatusMessage, setDocumentStatusMessage] = useState("");

  // activeReaderDocument 用来记录当前正在阅读的文档；为 null 时显示普通管理页面。
  const [activeReaderDocument, setActiveReaderDocument] = useState<DocumentItem | null>(null);

  // isCourseSummaryPanelOpen 用来控制阅读页中的课程简介区域是否展开。
  const [isCourseSummaryPanelOpen, setIsCourseSummaryPanelOpen] = useState(false);

  // readerRightSidebar 用来控制右侧栏当前展示课程简介、当前页问答还是关闭。
  const [readerRightSidebar, setReaderRightSidebar] = useState<ReaderRightSidebar>("none");

  // isReaderTopbarCollapsed 用来控制阅读页顶部工具栏是否折叠成窄条。
  const [isReaderTopbarCollapsed, setIsReaderTopbarCollapsed] = useState(false);

  // isReaderChatCollapsed 用来控制阅读页底部当前页问答栏是否折叠成窄条。
  const [isReaderChatCollapsed, setIsReaderChatCollapsed] = useState(false);

  // readerState 用来记录 PDF 阅读器当前是等待加载、加载成功还是加载失败。
  const [readerState, setReaderState] = useState<ReaderState>("idle");

  // readerMessage 用来向用户展示 PDF 加载过程中的说明或错误原因。
  const [readerMessage, setReaderMessage] = useState("");

  // currentPdfPage 用来记录用户当前正在阅读第几页，页码从 1 开始。
  const [currentPdfPage, setCurrentPdfPage] = useState(1);

  // totalPdfPages 用来记录 PDF.js 从系统实际使用的 PDF 中读取到的总页数。
  const [totalPdfPages, setTotalPdfPages] = useState(0);

  // isEditingPdfPage 用来控制页码数字是否切换成可输入状态。
  const [isEditingPdfPage, setIsEditingPdfPage] = useState(false);

  // pdfPageInputValue 用来暂存用户在页码输入框中输入的目标页码。
  const [pdfPageInputValue, setPdfPageInputValue] = useState("1");

  // readerViewportWidth 用来把 PDF 页面宽度限制在阅读区域内部，避免小屏幕横向溢出。
  const [readerViewportWidth, setReaderViewportWidth] = useState(0);

  // readerWorkspaceSize 用来保存主 PPT 工作区的真实宽高，供 PDF 按剩余空间完整缩放。
  const [readerWorkspaceSize, setReaderWorkspaceSize] = useState<ReaderWorkspaceSize>({
    width: 0,
    height: 0,
  });

  // pdfPageNaturalSize 用来保存 PDF 当前页的原始宽高比例，避免只按宽度渲染导致高度溢出。
  const [pdfPageNaturalSize, setPdfPageNaturalSize] = useState<PdfPageNaturalSize | null>(null);

  // thumbnailSidebarWidth 用来记录左侧缩略图栏宽度，用户拖动边界时会更新这个值。
  const [thumbnailSidebarWidth, setThumbnailSidebarWidth] = useState(158);

  // courseSummarySidebarWidth 用来记录右侧课程简介栏宽度，用户拖动边界时会更新这个值。
  const [courseSummarySidebarWidth, setCourseSummarySidebarWidth] = useState(320);

  // thumbnailRenderWidth 用左侧栏宽度推导每张缩略图的实际渲染宽度，让缩略图随栏宽等比例缩放。
  const thumbnailRenderWidth = Math.max(24, thumbnailSidebarWidth - 40);

  // isResizingThumbnailSidebar 用来记录当前是否正在拖动缩略图栏右侧边界。
  const [isResizingThumbnailSidebar, setIsResizingThumbnailSidebar] = useState(false);

  // isResizingCourseSummarySidebar 用来记录当前是否正在拖动课程简介栏左侧边界。
  const [isResizingCourseSummarySidebar, setIsResizingCourseSummarySidebar] = useState(false);

  // pdfPageInputRef 用来在点击页码后自动聚焦输入框，减少用户额外操作。
  const pdfPageInputRef = useRef<HTMLInputElement | null>(null);

  // readerViewportRef 用来读取 PDF 阅读区域的真实宽度，供 react-pdf 的 Page width 使用。
  const readerViewportRef = useRef<HTMLDivElement | null>(null);

  // readerWorkspaceRef 用来读取顶部栏和底部栏之外的主 PPT 可用区域。
  const readerWorkspaceRef = useRef<HTMLElement | null>(null);

  // readerContentRef 用来读取阅读区网格位置，计算拖拽分隔条后的缩略图栏宽度。
  const readerContentRef = useRef<HTMLDivElement | null>(null);

  // editingDocumentId 用来记录当前正在编辑标题的文档。
  const [editingDocumentId, setEditingDocumentId] = useState<string | null>(null);

  // editingTitle 用来暂存用户输入的新标题。
  const [editingTitle, setEditingTitle] = useState("");

  // documentActionState 用来避免同一时间重复点击重命名或删除按钮。
  const [documentActionState, setDocumentActionState] = useState<DocumentActionState>(null);

  // documentActionMessage 用来展示重命名或删除操作的结果。
  const [documentActionMessage, setDocumentActionMessage] = useState("");

  // llmConfigState 用来记录 LLM 配置加载、保存或测试的状态。
  const [llmConfigState, setLlmConfigState] = useState<LLMConfigState>("idle");

  // llmBaseUrl 用来保存用户在 WebUI 中编辑的 LLM 服务地址。
  const [llmBaseUrl, setLlmBaseUrl] = useState("");

  // llmApiKey 用来保存用户本次输入的新 API Key；为空时保存操作会保留旧值。
  const [llmApiKey, setLlmApiKey] = useState("");

  // llmApiKeyConfigured 表示后端当前是否已经保存过 API Key。
  const [llmApiKeyConfigured, setLlmApiKeyConfigured] = useState(false);

  // llmApiKeyPreview 用来显示后端返回的 API Key 掩码，避免把明文密钥发回前端。
  const [llmApiKeyPreview, setLlmApiKeyPreview] = useState("");

  // shouldClearLlmApiKey 用来让用户明确清空已经保存的 API Key。
  const [shouldClearLlmApiKey, setShouldClearLlmApiKey] = useState(false);

  // llmModel 用来保存用户选择或输入的模型名称。
  const [llmModel, setLlmModel] = useState("");

  // llmTimeoutSeconds 用来保存 LLM 请求超时时间。
  const [llmTimeoutSeconds, setLlmTimeoutSeconds] = useState("60");

  // courseSummaryPrompt 用来保存生成课程简介时发送给 LLM 的 prompt。
  const [courseSummaryPrompt, setCourseSummaryPrompt] = useState("");

  // lectureNotesPrompt 用来保存生成逐页讲稿时发送给 LLM 的 prompt。
  const [lectureNotesPrompt, setLectureNotesPrompt] = useState("");

  // pageChatPrompt 用来保存当前页问答时发送给 LLM 的 prompt。
  const [pageChatPrompt, setPageChatPrompt] = useState("");

  // isCourseSummaryPromptExpanded 用来控制课程简介 prompt 设置是否展开显示。
  const [isCourseSummaryPromptExpanded, setIsCourseSummaryPromptExpanded] = useState(false);

  // isLectureNotesPromptExpanded 用来控制逐页讲稿 prompt 设置是否展开显示。
  const [isLectureNotesPromptExpanded, setIsLectureNotesPromptExpanded] = useState(false);

  // isPageChatPromptExpanded 用来控制当前页问答 prompt 设置是否展开显示。
  const [isPageChatPromptExpanded, setIsPageChatPromptExpanded] = useState(false);

  // courseSummaryPromptTextareaRef 用来访问 prompt 文本框的真实 DOM 高度。
  const courseSummaryPromptTextareaRef = useRef<HTMLTextAreaElement | null>(null);

  // lectureNotesPromptTextareaRef 用来访问逐页讲稿 prompt 文本框的真实 DOM 高度。
  const lectureNotesPromptTextareaRef = useRef<HTMLTextAreaElement | null>(null);

  // pageChatPromptTextareaRef 用来访问当前页问答 prompt 文本框的真实 DOM 高度。
  const pageChatPromptTextareaRef = useRef<HTMLTextAreaElement | null>(null);

  // expandedLectureNotesDocumentId 用来记录当前展开页面讲稿列表的文档。
  const [expandedLectureNotesDocumentId, setExpandedLectureNotesDocumentId] = useState<
    string | null
  >(null);

  // expandedDocumentIds 用来记录文件页里哪些文档卡片已经展开；默认空对象表示全部折叠。
  const [expandedDocumentIds, setExpandedDocumentIds] = useState<Record<string, boolean>>({});

  // pagesByDocument 用来按 document_id 缓存页面和讲稿数据。
  const [pagesByDocument, setPagesByDocument] = useState<Record<string, PageItem[]>>({});

  // pagesMessageByDocument 用来按 document_id 展示页面讲稿加载状态或错误。
  const [pagesMessageByDocument, setPagesMessageByDocument] = useState<Record<string, string>>({});

  // draftNoteBlockLayouts 用来保存拖动或缩放过程中的临时布局。
  // 鼠标移动过程只改这个前端草稿，松开鼠标后再统一保存到后端。
  const [draftNoteBlockLayouts, setDraftNoteBlockLayouts] = useState<Record<string, NoteBlockLayout>>({});

  // noteBlockInteraction 用来记录当前是否正在拖动或缩放讲稿文字块。
  const [noteBlockInteraction, setNoteBlockInteraction] =
    useState<NoteBlockInteraction | null>(null);

  // pageQuestionInput 用来保存阅读页底部当前输入的问题。
  const [pageQuestionInput, setPageQuestionInput] = useState("");

  // submittingPageChatId 用来记录当前正在等待 LLM 回答的页面 ID；为 null 表示没有提交中的问题。
  const [submittingPageChatId, setSubmittingPageChatId] = useState<string | null>(null);

  // pageChatMessage 用来展示当前页问答的提交状态或失败原因。
  const [pageChatMessage, setPageChatMessage] = useState("");

  // llmConfigMessage 用来显示配置加载、保存和测试结果。
  const [llmConfigMessage, setLlmConfigMessage] = useState("正在加载 LLM 配置...");

  // llmTestPrompt 用来保存用户输入的测试提示词。
  const [llmTestPrompt, setLlmTestPrompt] = useState("请用一句中文回复：LLM 配置测试成功。");

  // llmTestAnswer 用来展示模型服务返回的测试回答。
  const [llmTestAnswer, setLlmTestAnswer] = useState("");

  useEffect(() => {
    // 使用 AbortController 可以在组件卸载时取消请求，避免无意义的状态更新。
    const controller = new AbortController();

    async function checkBackendHealth() {
      try {
        // 这里请求 Vite 代理下的 `/api/health`，实际会转发到 FastAPI 后端。
        const response = await fetch("/api/health", {
          signal: controller.signal,
        });

        // HTTP 状态码不是 2xx 时，说明后端虽然有响应，但接口结果不是正常成功。
        if (!response.ok) {
          throw new Error(`健康检查失败，HTTP 状态码：${response.status}`);
        }

        // 把后端返回的 JSON 解析成 TypeScript 对象。
        const data = (await response.json()) as HealthResponse;

        // 后端约定 status 为 ok 时，表示服务正常。
        if (data.status !== "ok") {
          throw new Error("后端返回了非正常状态。");
        }

        setConnectionState("success");
        setMessage(`后端连接成功：${data.service}`);
        await loadLlmConfig();
        await loadDocuments();
      } catch (error) {
        // 如果请求是因为组件卸载被取消，不需要向用户显示失败。
        if (error instanceof DOMException && error.name === "AbortError") {
          return;
        }

        setConnectionState("error");
        setMessage("后端连接失败，请确认 FastAPI 服务已经启动。");
      }
    }

    checkBackendHealth();

    // 组件卸载时取消仍在进行的健康检查请求。
    return () => {
      controller.abort();
    };
  }, []);

  function resizePromptTextarea(textarea: HTMLTextAreaElement | null) {
    // prompt 展开后需要让 textarea 高度跟随完整内容，避免文本框内部出现滚动条。
    if (textarea === null) {
      return;
    }

    // 先重置为 auto，让浏览器重新计算 scrollHeight，随后把高度设为完整内容高度。
    textarea.style.height = "auto";
    textarea.style.height = `${textarea.scrollHeight}px`;
  }

  useEffect(() => {
    // 折叠状态下 textarea 不存在，不需要计算课程简介 prompt 高度。
    if (!isCourseSummaryPromptExpanded) {
      return;
    }

    resizePromptTextarea(courseSummaryPromptTextareaRef.current);
  }, [courseSummaryPrompt, isCourseSummaryPromptExpanded]);

  useEffect(() => {
    // 折叠状态下 textarea 不存在，不需要计算逐页讲稿 prompt 高度。
    if (!isLectureNotesPromptExpanded) {
      return;
    }

    resizePromptTextarea(lectureNotesPromptTextareaRef.current);
  }, [lectureNotesPrompt, isLectureNotesPromptExpanded]);

  useEffect(() => {
    // 折叠状态下 textarea 不存在，不需要计算当前页问答 prompt 高度。
    if (!isPageChatPromptExpanded) {
      return;
    }

    resizePromptTextarea(pageChatPromptTextareaRef.current);
  }, [pageChatPrompt, isPageChatPromptExpanded]);

  useEffect(() => {
    // 切换阅读页时清空输入框和提示，保证每页问答交互互不干扰。
    setPageQuestionInput("");
    setPageChatMessage("");
    setPdfPageNaturalSize(null);
  }, [activeReaderDocument?.document_id, currentPdfPage]);

  useEffect(() => {
    const documentIdsNeedingStatus = documents
      .filter((document) => {
        const statusData = documentStatusById[document.document_id];

        if (statusData) {
          return shouldPollDocumentStatus(statusData);
        }

        return (
          document.status === "processing" ||
          document.course_summary_status === "processing" ||
          (document.status === "processing" && document.course_summary_status === "pending")
        );
      })
      .map((document) => document.document_id);

    if (documentIdsNeedingStatus.length === 0) {
      return;
    }

    let isCancelled = false;

    async function pollDocumentStatuses() {
      for (const documentId of documentIdsNeedingStatus) {
        if (isCancelled) {
          return;
        }

        await loadDocumentStatus(documentId);
      }
    }

    const intervalId = window.setInterval(() => {
      void pollDocumentStatuses();
    }, DOCUMENT_STATUS_POLL_INTERVAL_MS);

    return () => {
      isCancelled = true;
      window.clearInterval(intervalId);
    };
  }, [documents, documentStatusById]);

  useEffect(() => {
    // 页码进入编辑状态后自动聚焦并选中原数字，方便用户直接输入新页码。
    if (!isEditingPdfPage) {
      return;
    }

    pdfPageInputRef.current?.focus();
    pdfPageInputRef.current?.select();
  }, [isEditingPdfPage]);

  useEffect(() => {
    // 没有进入阅读界面时，主 PPT 工作区 DOM 不存在，不需要监听尺寸变化。
    if (!activeReaderDocument || currentView !== "reader") {
      setReaderViewportWidth(0);
      setReaderWorkspaceSize({ width: 0, height: 0 });
      return;
    }

    const workspaceElement = readerWorkspaceRef.current;
    if (workspaceElement === null) {
      return;
    }

    const observedWorkspaceElement = workspaceElement;

    function updateReaderWorkspaceSize() {
      const workspaceRect = observedWorkspaceElement.getBoundingClientRect();
      const isNarrowWorkspace = workspaceRect.width <= 920;
      const thumbnailColumnWidth = isNarrowWorkspace
        ? 0
        : thumbnailSidebarWidth + THUMBNAIL_RESIZER_WIDTH + PDF_READER_COLUMN_GAP * 2;
      const rightSidebarColumnWidth =
        readerRightSidebar !== "none" && !isNarrowWorkspace
          ? courseSummarySidebarWidth + COURSE_SUMMARY_RESIZER_WIDTH + PDF_READER_COLUMN_GAP * 2
          : 0;
      const thumbnailRowHeight = isNarrowWorkspace ? 138 + PDF_READER_COLUMN_GAP : 0;
      const summaryRowHeight =
        readerRightSidebar !== "none" && isNarrowWorkspace
          ? Math.max(160, Math.min(workspaceRect.height * 0.28, 260)) + PDF_READER_COLUMN_GAP
          : 0;
      const nextWidth = Math.max(0, workspaceRect.width - thumbnailColumnWidth - rightSidebarColumnWidth - 32);
      const nextHeight = Math.max(0, workspaceRect.height - thumbnailRowHeight - summaryRowHeight - 32);

      // readerViewportWidth 仍用于兼容旧计算；真正的 PDF 尺寸使用 readerWorkspaceSize。
      setReaderViewportWidth(nextWidth);
      setReaderWorkspaceSize({
        width: nextWidth,
        height: nextHeight,
      });
    }

    updateReaderWorkspaceSize();

    // ResizeObserver 会在顶部栏折叠、底部栏折叠或浏览器尺寸变化时重新计算剩余空间。
    const resizeObserver = new ResizeObserver(updateReaderWorkspaceSize);
    resizeObserver.observe(observedWorkspaceElement);

    return () => {
      resizeObserver.disconnect();
    };
  }, [
    currentView,
    activeReaderDocument,
    thumbnailSidebarWidth,
    courseSummarySidebarWidth,
    readerRightSidebar,
    isReaderTopbarCollapsed,
    isReaderChatCollapsed,
    isCourseSummaryPanelOpen,
  ]);

  useEffect(() => {
    if (!isResizingThumbnailSidebar) {
      return;
    }

    function handlePointerMove(event: PointerEvent) {
      const readerContentElement = readerContentRef.current;
      if (readerContentElement === null) {
        return;
      }

      const contentRect = readerContentElement.getBoundingClientRect();
      const rawWidth = event.clientX - contentRect.left;
      const maxAllowedWidth = Math.max(MIN_THUMBNAIL_SIDEBAR_WIDTH, contentRect.width);
      const nextWidth = Math.min(
        Math.max(rawWidth, MIN_THUMBNAIL_SIDEBAR_WIDTH),
        maxAllowedWidth,
      );

      setThumbnailSidebarWidth(nextWidth);
    }

    function handlePointerUp() {
      setIsResizingThumbnailSidebar(false);
    }

    document.body.style.userSelect = "none";
    window.addEventListener("pointermove", handlePointerMove);
    window.addEventListener("pointerup", handlePointerUp);

    return () => {
      document.body.style.userSelect = "";
      window.removeEventListener("pointermove", handlePointerMove);
      window.removeEventListener("pointerup", handlePointerUp);
    };
  }, [isResizingThumbnailSidebar]);

  useEffect(() => {
    if (!isResizingCourseSummarySidebar) {
      return;
    }

    function handlePointerMove(event: PointerEvent) {
      const readerContentElement = readerContentRef.current;
      if (readerContentElement === null) {
        return;
      }

      const contentRect = readerContentElement.getBoundingClientRect();
      const rawWidth = contentRect.right - event.clientX;
      const maxAllowedWidth = Math.max(MIN_COURSE_SUMMARY_SIDEBAR_WIDTH, contentRect.width);
      const nextWidth = Math.min(
        Math.max(rawWidth, MIN_COURSE_SUMMARY_SIDEBAR_WIDTH),
        maxAllowedWidth,
      );

      setCourseSummarySidebarWidth(nextWidth);
    }

    function handlePointerUp() {
      setIsResizingCourseSummarySidebar(false);
    }

    document.body.style.userSelect = "none";
    window.addEventListener("pointermove", handlePointerMove);
    window.addEventListener("pointerup", handlePointerUp);

    return () => {
      document.body.style.userSelect = "";
      window.removeEventListener("pointermove", handlePointerMove);
      window.removeEventListener("pointerup", handlePointerUp);
    };
  }, [isResizingCourseSummarySidebar, thumbnailSidebarWidth]);

  useEffect(() => {
    if (!noteBlockInteraction) {
      return;
    }

    const activeInteraction = noteBlockInteraction;

    function handlePointerMove(event: PointerEvent) {
      const nextLayout =
        activeInteraction.mode === "drag"
          ? buildDraggedNoteBlockLayout(activeInteraction, event)
          : buildResizedNoteBlockLayout(activeInteraction, event);

      updateDraftNoteBlockLayout(activeInteraction.noteBlockId, nextLayout);
    }

    function handlePointerUp(event: PointerEvent) {
      const finalLayout =
        activeInteraction.mode === "drag"
          ? buildDraggedNoteBlockLayout(activeInteraction, event)
          : buildResizedNoteBlockLayout(activeInteraction, event);

      updateDraftNoteBlockLayout(activeInteraction.noteBlockId, finalLayout);
      void saveNoteBlockPosition(
        activeInteraction.documentId,
        activeInteraction.noteBlockId,
        finalLayout,
      );
      setNoteBlockInteraction(null);
    }

    document.body.style.userSelect = "none";
    window.addEventListener("pointermove", handlePointerMove);
    window.addEventListener("pointerup", handlePointerUp);

    return () => {
      document.body.style.userSelect = "";
      window.removeEventListener("pointermove", handlePointerMove);
      window.removeEventListener("pointerup", handlePointerUp);
    };
  }, [noteBlockInteraction]);

  async function loadDocuments() {
    try {
      // 文档列表接口从 SQLite 数据库读取记录，刷新页面后仍然应该返回历史上传记录。
      const response = await fetch("/api/documents");

      // HTTP 状态码不是 2xx 时，说明文档列表接口没有正常返回。
      if (!response.ok) {
        throw new Error(`文档列表加载失败，HTTP 状态码：${response.status}`);
      }

      const data = (await response.json()) as DocumentItem[];

      setDocuments(data);
      setDocumentsMessage(data.length > 0 ? "" : "还没有上传过 slides 文件。");
      data.forEach((document) => {
        void loadDocumentStatus(document.document_id);
      });
    } catch (error) {
      setDocuments([]);
      setDocumentsMessage(
        error instanceof Error ? error.message : "文档列表加载失败，请稍后重试。",
      );
    }
  }

  async function loadDocumentStatus(documentId: string) {
    try {
      const response = await fetch(`/api/documents/${documentId}/status`);

      if (!response.ok) {
        const errorData = (await response.json().catch(() => null)) as { detail?: string } | null;
        throw new Error(errorData?.detail ?? `生成进度加载失败，HTTP 状态码：${response.status}`);
      }

      const data = (await response.json()) as DocumentStatusResponse;
      mergeDocumentStatus(data);
      if (
        data.document_id === activeReaderDocument?.document_id ||
        data.document_id === expandedLectureNotesDocumentId
      ) {
        void loadDocumentPages(data.document_id, false);
      }
      setDocumentStatusMessage("");
      return data;
    } catch (error) {
      setDocumentStatusMessage(
        error instanceof Error ? error.message : "生成进度加载失败，请稍后重试。",
      );
      return null;
    }
  }

  async function loadLlmConfig() {
    setLlmConfigState("loading");
    setLlmConfigMessage("正在加载 LLM 配置...");

    try {
      // LLM 配置接口会返回可展示配置，但不会返回 API Key 明文。
      const response = await fetch("/api/llm/config");

      if (!response.ok) {
        throw new Error(`LLM 配置加载失败，HTTP 状态码：${response.status}`);
      }

      const data = (await response.json()) as LLMConfigResponse;

      setLlmBaseUrl(data.base_url);
      setLlmModel(data.model);
      setLlmTimeoutSeconds(String(data.timeout_seconds));
      setCourseSummaryPrompt(data.course_summary_prompt);
      setLectureNotesPrompt(data.lecture_notes_prompt);
      setPageChatPrompt(data.page_chat_prompt);
      setLlmApiKey("");
      setShouldClearLlmApiKey(false);
      setLlmApiKeyConfigured(data.api_key_configured);
      setLlmApiKeyPreview(data.api_key_preview);
      setLlmConfigState("idle");
      setLlmConfigMessage(
        data.api_key_configured
          ? "LLM 配置已加载。API Key 已保存，输入新值才会覆盖。"
          : "LLM 配置已加载。请填写 API Key 后保存。",
      );
    } catch (error) {
      setLlmConfigState("error");
      setLlmConfigMessage(
        error instanceof Error ? error.message : "LLM 配置加载失败，请稍后重试。",
      );
    }
  }

  async function saveLlmConfig(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();

    const nextBaseUrl = llmBaseUrl.trim();
    const nextModel = llmModel.trim();
    const nextTimeoutSeconds = Number(llmTimeoutSeconds);
    const nextCourseSummaryPrompt = courseSummaryPrompt.trim();
    const nextLectureNotesPrompt = lectureNotesPrompt.trim();
    const nextPageChatPrompt = pageChatPrompt.trim();

    if (!nextBaseUrl) {
      setLlmConfigState("error");
      setLlmConfigMessage("LLM_BASE_URL 不能为空。");
      return;
    }

    if (!nextModel) {
      setLlmConfigState("error");
      setLlmConfigMessage("LLM_MODEL 不能为空。");
      return;
    }

    if (!Number.isInteger(nextTimeoutSeconds) || nextTimeoutSeconds < 5 || nextTimeoutSeconds > 300) {
      setLlmConfigState("error");
      setLlmConfigMessage("请求超时时间必须是 5 到 300 之间的整数秒。");
      return;
    }

    if (!nextCourseSummaryPrompt) {
      setLlmConfigState("error");
      setLlmConfigMessage("课程简介 prompt 不能为空。");
      return;
    }

    if (!nextLectureNotesPrompt) {
      setLlmConfigState("error");
      setLlmConfigMessage("逐页讲稿 prompt 不能为空。");
      return;
    }

    if (!nextPageChatPrompt) {
      setLlmConfigState("error");
      setLlmConfigMessage("当前页问答 prompt 不能为空。");
      return;
    }

    setLlmConfigState("saving");
    setLlmConfigMessage("正在保存 LLM 配置...");
    setLlmTestAnswer("");

    try {
      // 默认情况下，api_key 为空字符串时不发送该字段，后端会保留旧密钥。
      // 当用户勾选清空密钥时，明确发送空字符串，让后端删除已保存的 API Key。
      const requestBody: {
        base_url: string;
        model: string;
        timeout_seconds: number;
        course_summary_prompt: string;
        lecture_notes_prompt: string;
        page_chat_prompt: string;
        api_key?: string;
      } = {
        base_url: nextBaseUrl,
        model: nextModel,
        timeout_seconds: nextTimeoutSeconds,
        course_summary_prompt: nextCourseSummaryPrompt,
        lecture_notes_prompt: nextLectureNotesPrompt,
        page_chat_prompt: nextPageChatPrompt,
      };

      if (shouldClearLlmApiKey) {
        requestBody.api_key = "";
      } else if (llmApiKey.trim()) {
        requestBody.api_key = llmApiKey.trim();
      }

      const response = await fetch("/api/llm/config", {
        method: "PATCH",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify(requestBody),
      });

      if (!response.ok) {
        const errorData = (await response.json().catch(() => null)) as { detail?: string } | null;
        throw new Error(errorData?.detail ?? `保存失败，HTTP 状态码：${response.status}`);
      }

      const data = (await response.json()) as LLMConfigResponse;

      setLlmBaseUrl(data.base_url);
      setLlmModel(data.model);
      setLlmTimeoutSeconds(String(data.timeout_seconds));
      setCourseSummaryPrompt(data.course_summary_prompt);
      setLectureNotesPrompt(data.lecture_notes_prompt);
      setPageChatPrompt(data.page_chat_prompt);
      setLlmApiKey("");
      setShouldClearLlmApiKey(false);
      setLlmApiKeyConfigured(data.api_key_configured);
      setLlmApiKeyPreview(data.api_key_preview);
      setLlmConfigState("success");
      setLlmConfigMessage("LLM 配置已保存。");
    } catch (error) {
      setLlmConfigState("error");
      setLlmConfigMessage(error instanceof Error ? error.message : "保存失败，请稍后重试。");
    }
  }

  async function testLlmConfig() {
    const prompt = llmTestPrompt.trim();

    if (!prompt) {
      setLlmConfigState("error");
      setLlmConfigMessage("测试提示词不能为空。");
      return;
    }

    setLlmConfigState("testing");
    setLlmConfigMessage("正在请求 LLM 服务...");
    setLlmTestAnswer("");

    try {
      const response = await fetch("/api/llm/test", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({ prompt }),
      });

      if (!response.ok) {
        const errorData = (await response.json().catch(() => null)) as { detail?: string } | null;
        throw new Error(errorData?.detail ?? `测试失败，HTTP 状态码：${response.status}`);
      }

      const data = (await response.json()) as LLMTestResponse;

      setLlmConfigState("success");
      setLlmConfigMessage("LLM 测试请求成功。");
      setLlmTestAnswer(data.answer);
    } catch (error) {
      setLlmConfigState("error");
      setLlmConfigMessage(error instanceof Error ? error.message : "测试失败，请稍后重试。");
    }
  }

  function formatCreatedAt(value: string) {
    // 后端使用 ISO 时间字符串保存创建时间，前端转换为本地时间展示。
    const date = new Date(value);

    // 如果时间字符串无法解析，就直接显示原始值，避免页面报错。
    if (Number.isNaN(date.getTime())) {
      return value;
    }

    return date.toLocaleString();
  }

  function getStatusLabel(status: string) {
    // 后端用英文状态值保存进数据库，前端把它转换成用户更容易理解的中文。
    const statusLabels: Record<string, string> = {
      uploaded: "已上传",
      processing: "解析中",
      ready: "解析完成",
      failed: "解析失败",
    };

    return statusLabels[status] ?? status;
  }

  function getCourseSummaryStatusLabel(status: string) {
    // 课程简介状态独立于 PDF 解析状态，前端单独转换文案。
    const statusLabels: Record<string, string> = {
      pending: "等待生成",
      processing: "生成中",
      ready: "已生成",
      failed: "生成失败",
    };

    return statusLabels[status] ?? status;
  }

  function getLectureNotesStatusLabel(status: string) {
    // 逐页讲稿状态独立于页面解析状态，前端单独转换文案。
    const statusLabels: Record<string, string> = {
      pending: "等待生成",
      processing: "生成中",
      ready: "已生成",
      failed: "生成失败",
    };

    return statusLabels[status] ?? status;
  }

  function shouldPollDocumentStatus(statusData: DocumentStatusResponse | undefined) {
    // 后端会直接返回 should_poll；前端额外允许 undefined 时不继续轮询。
    return Boolean(statusData?.should_poll);
  }

  function buildLectureNotesProgressText(statusData: DocumentStatusResponse | undefined) {
    if (!statusData) {
      return "正在读取生成进度...";
    }

    if (statusData.total_pages === 0) {
      return "当前文档还没有页面记录。";
    }

    const pausedText = statusData.lecture_notes_paused ? "，已暂停" : "";
    return `讲稿进度：${statusData.lecture_notes_ready_count}/${statusData.total_pages} 页已生成，${statusData.lecture_notes_processing_count} 页生成中，${statusData.lecture_notes_pending_count} 页等待，${statusData.lecture_notes_failed_count} 页失败${pausedText}。`;
  }

  function mergeDocumentStatus(statusData: DocumentStatusResponse) {
    // 状态接口比文档列表更及时；轮询时用它覆盖列表中的状态字段。
    setDocumentStatusById((currentStatus) => ({
      ...currentStatus,
      [statusData.document_id]: statusData,
    }));
    setDocuments((currentDocuments) =>
      currentDocuments.map((document) =>
        document.document_id === statusData.document_id
          ? {
              ...document,
              status: statusData.status,
              error_message: statusData.error_message,
              page_count: statusData.total_pages,
              course_summary_status: statusData.course_summary_status,
              course_summary_error: statusData.course_summary_error,
              lecture_notes_paused: statusData.lecture_notes_paused,
            }
          : document,
      ),
    );
    setPagesByDocument((currentPages) => {
      const existingPages = currentPages[statusData.document_id];
      if (!existingPages) {
        return currentPages;
      }

      return {
        ...currentPages,
        [statusData.document_id]: existingPages.map((page) => {
          const statusPage = statusData.pages.find(
            (candidate) => candidate.page_id === page.page_id,
          );

          return statusPage
            ? {
                ...page,
                status: statusPage.status,
                error_message: statusPage.error_message,
                lecture_notes_status: statusPage.lecture_notes_status,
                lecture_notes_error: statusPage.lecture_notes_error,
              }
            : page;
        }),
      };
    });
  }

  function getChatRoleLabel(role: ChatMessageItem["role"]) {
    // 后端只保存 user 和 assistant 两种角色；这里转换成页面中更自然的中文称呼。
    return role === "user" ? "学生" : "AI 老师";
  }

  function isDocumentBusy(documentId: string) {
    // 判断某个文档是否正在执行重命名或删除操作。
    return documentActionState?.documentId === documentId;
  }

  function resolveLectureNotesPaused(document: DocumentItem) {
    // 文档状态接口比文档列表更新更及时，所以优先使用状态缓存里的暂停字段。
    return documentStatusById[document.document_id]?.lecture_notes_paused ?? document.lecture_notes_paused;
  }

  function toggleDocumentExpanded(documentId: string) {
    // 文件页默认折叠；点击展开按钮时只切换当前文档，不影响其他文档。
    setExpandedDocumentIds((currentExpandedDocumentIds) => ({
      ...currentExpandedDocumentIds,
      [documentId]: !currentExpandedDocumentIds[documentId],
    }));
  }

  function isPageLectureNotesBusy(documentId: string, pageNumber: number) {
    // 判断某一页是否正在执行讲稿重新生成操作。
    return (
      documentActionState?.documentId === documentId &&
      documentActionState.action === "regeneratingLectureNotes" &&
      documentActionState.pageNumber === pageNumber
    );
  }

  function openReader(document: DocumentItem) {
    // 每次打开阅读界面都从第一页开始，避免上一个文档的页码影响当前文档。
    setActiveReaderDocument(document);
    setCurrentView("reader");
    setIsCourseSummaryPanelOpen(false);
    setReaderRightSidebar("none");
    setIsReaderTopbarCollapsed(false);
    setIsReaderChatCollapsed(false);
    setCurrentPdfPage(1);
    setIsEditingPdfPage(false);
    setPdfPageInputValue("1");
    setTotalPdfPages(0);
    setPdfPageNaturalSize(null);
    setReaderState("loading");
    setReaderMessage("正在加载 slides PDF 文件...");
    void loadDocumentPages(document.document_id);
  }

  function closeReader() {
    // 返回文件页时保留当前打开文档，让文件页可以清楚标出当前打开的是哪份文件。
    setCurrentView("files");
  }

  function openSettings() {
    // 设置页独立展示 LLM 配置，避免文件页被配置表单拉得过长。
    setCurrentView("settings");
  }

  function returnToReader() {
    // 只有已经打开过文档时才能从设置页回到阅读页。
    if (!activeReaderDocument) {
      return;
    }

    setReaderViewportWidth(0);
    setReaderWorkspaceSize({ width: 0, height: 0 });
    setCurrentView("reader");
  }

  function clearActiveDocument() {
    // 关闭当前文档会清空阅读器状态；文件页随后显示“未打开文档”。
    setActiveReaderDocument(null);
    setCurrentView("files");
    setIsCourseSummaryPanelOpen(false);
    setReaderRightSidebar("none");
    setIsReaderTopbarCollapsed(false);
    setIsReaderChatCollapsed(false);
    setCurrentPdfPage(1);
    setIsEditingPdfPage(false);
    setPdfPageInputValue("1");
    setTotalPdfPages(0);
    setPdfPageNaturalSize(null);
    setReaderState("idle");
    setReaderMessage("");
  }

  function toggleCourseSummarySidebar() {
    setReaderRightSidebar((currentSidebar) => {
      const nextSidebar: ReaderRightSidebar = currentSidebar === "summary" ? "none" : "summary";
      setIsCourseSummaryPanelOpen(nextSidebar === "summary");
      return nextSidebar;
    });
  }

  function openChatSidebar() {
    setReaderRightSidebar("chat");
    setIsCourseSummaryPanelOpen(false);
    setIsReaderChatCollapsed(false);
  }

  function closeRightSidebar() {
    setReaderRightSidebar("none");
    setIsCourseSummaryPanelOpen(false);
  }

  const turnPdfPage = useCallback((step: -1 | 1) => {
    // 所有按钮翻页入口都走同一个函数，保证使用同一套边界规则。
    setCurrentPdfPage((currentPage) => {
      const maxPage = totalPdfPages > 0 ? totalPdfPages : currentPage;
      const nextPage = currentPage + step;

      if (nextPage < 1) {
        setPdfPageInputValue("1");
        setIsEditingPdfPage(false);
        return 1;
      }

      if (nextPage > maxPage) {
        setPdfPageInputValue(String(maxPage));
        setIsEditingPdfPage(false);
        return maxPage;
      }

      setPdfPageInputValue(String(nextPage));
      setIsEditingPdfPage(false);
      return nextPage;
    });
  }, [totalPdfPages]);

  function handlePdfLoadSuccess({ numPages }: { numPages: number }) {
    // PDF.js 成功读取文档后会返回总页数，后续翻页按钮和页码显示都依赖这个值。
    setTotalPdfPages(numPages);
    setCurrentPdfPage(1);
    setIsEditingPdfPage(false);
    setPdfPageInputValue("1");
    setReaderState("ready");
    setReaderMessage("");
  }

  function handlePdfLoadError(error: Error) {
    // PDF 加载失败通常来自后端文件不存在、接口异常或 PDF.js 无法解析原始文件。
    setReaderState("error");
    setReaderMessage(`PDF 加载失败：${error.message}`);
  }

  function handlePdfPageRenderError(error: Error) {
    // 文档已经加载但当前页渲染失败时，保留阅读界面并展示明确错误。
    setReaderState("error");
    setReaderMessage(`当前页渲染失败：${error.message}`);
  }

  function handlePdfPageLoadSuccess(page: LoadedPdfPage) {
    // React-PDF 返回当前页的原始宽高，这里只用它计算页面比例。
    setPdfPageNaturalSize({
      width: page.originalWidth,
      height: page.originalHeight,
    });
  }

  function goToPdfPage(pageNumber: number) {
    if (totalPdfPages <= 0) {
      return;
    }

    // 所有直接跳页入口都统一限制边界，避免传入 0、负数或超过总页数的页码。
    const nextPage = Math.min(Math.max(pageNumber, 1), totalPdfPages);
    setCurrentPdfPage(nextPage);
    setPdfPageInputValue(String(nextPage));
    setIsEditingPdfPage(false);
  }

  function startEditingPdfPage() {
    if (readerState !== "ready" || totalPdfPages <= 0) {
      return;
    }

    // 编辑前把输入框恢复为当前页，避免显示上一次没有提交的草稿值。
    setPdfPageInputValue(String(currentPdfPage));
    setIsEditingPdfPage(true);
  }

  function submitPdfPageInput() {
    const parsedPage = Number(pdfPageInputValue);

    // 输入不是数字时不跳页，直接回到当前页显示，避免把阅读器推入异常状态。
    if (!Number.isInteger(parsedPage)) {
      setPdfPageInputValue(String(currentPdfPage));
      setIsEditingPdfPage(false);
      return;
    }

    // 页码必须限制在 PDF 实际页数内；小于 1 跳到第一页，大于总页数跳到最后一页。
    goToPdfPage(parsedPage);
  }

  function handlePdfPageInputKeyDown(event: React.KeyboardEvent<HTMLInputElement>) {
    if (event.key === "Enter") {
      submitPdfPageInput();
      return;
    }

    if (event.key === "Escape") {
      setPdfPageInputValue(String(currentPdfPage));
      setIsEditingPdfPage(false);
    }
  }

  function startResizingThumbnailSidebar(event: React.PointerEvent<HTMLButtonElement>) {
    event.preventDefault();
    setIsResizingThumbnailSidebar(true);
  }

  function startResizingCourseSummarySidebar(event: React.PointerEvent<HTMLButtonElement>) {
    event.preventDefault();
    setIsResizingCourseSummarySidebar(true);
  }

  function handleFileChange(event: React.ChangeEvent<HTMLInputElement>) {
    // 浏览器文件选择控件会把用户选择的文件放在 files 列表中。
    const nextFile = event.target.files?.[0] ?? null;

    // 每次重新选择文件时，清空上一次上传结果。
    setUploadedDocumentId(null);

    if (!nextFile) {
      setSelectedFile(null);
      setUploadState("idle");
      setUploadMessage("请选择一个 PDF/PPT/PPTX slides 文件。");
      return;
    }

    // 前端先做一次后缀和类型检查，给用户更快的反馈。
    // 后端仍然会再次校验，不能只依赖前端校验。
    const supportedExtensions = [".pdf", ".ppt", ".pptx"];
    const hasSupportedExtension = supportedExtensions.some((extension) =>
      nextFile.name.toLowerCase().endsWith(extension),
    );

    if (!hasSupportedExtension) {
      setSelectedFile(null);
      setUploadState("error");
      setUploadMessage("请选择 .pdf、.ppt 或 .pptx 格式的 slides 文件。");
      return;
    }

    setSelectedFile(nextFile);
    setUploadState("idle");
    setUploadMessage(`已选择：${nextFile.name}`);
  }

  async function handleUploadSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();

    if (!selectedFile) {
      setUploadState("error");
      setUploadMessage("上传前需要先选择一个 PDF/PPT/PPTX slides 文件。");
      return;
    }

    // FormData 是浏览器上传文件时最常用的数据结构。
    const formData = new FormData();
    formData.append("file", selectedFile);

    setUploadState("uploading");
    setUploadMessage("正在上传 slides 文件...");
    setUploadedDocumentId(null);

    try {
      // 这里请求 Vite 代理下的 `/api/documents`，实际会转发到 FastAPI 后端。
      const response = await fetch("/api/documents", {
        method: "POST",
        body: formData,
      });

      // 如果后端拒绝上传，优先读取后端 detail 字段作为错误原因。
      if (!response.ok) {
        const errorData = (await response.json().catch(() => null)) as { detail?: string } | null;
        throw new Error(errorData?.detail ?? `上传失败，HTTP 状态码：${response.status}`);
      }

      const data = (await response.json()) as UploadResponse;

      setUploadState("success");
      setUploadedDocumentId(data.document_id);
      setUploadMessage(`上传成功：${data.title}`);
      await loadDocuments();
      await loadDocumentStatus(data.document_id);
    } catch (error) {
      setUploadState("error");
      setUploadMessage(error instanceof Error ? error.message : "上传失败，请稍后重试。");
    }
  }

  function startRename(document: DocumentItem) {
    // 开始重命名时，把当前标题放进输入框，方便用户基于原标题修改。
    setEditingDocumentId(document.document_id);
    setEditingTitle(document.title);
    setDocumentActionMessage("");
  }

  function cancelRename() {
    // 取消编辑时清空编辑状态，不提交任何请求。
    setEditingDocumentId(null);
    setEditingTitle("");
    setDocumentActionMessage("");
  }

  async function saveRename(documentId: string) {
    const nextTitle = editingTitle.trim();

    if (!nextTitle) {
      setDocumentActionMessage("文档标题不能为空。");
      return;
    }

    setDocumentActionState({ documentId, action: "renaming" });
    setDocumentActionMessage("");

    try {
      const response = await fetch(`/api/documents/${documentId}`, {
        method: "PATCH",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({ title: nextTitle }),
      });

      if (!response.ok) {
        const errorData = (await response.json().catch(() => null)) as { detail?: string } | null;
        throw new Error(errorData?.detail ?? `重命名失败，HTTP 状态码：${response.status}`);
      }

      setEditingDocumentId(null);
      setEditingTitle("");
      setDocumentActionMessage("文档标题已更新。");
      await loadDocuments();
    } catch (error) {
      setDocumentActionMessage(error instanceof Error ? error.message : "重命名失败，请稍后重试。");
    } finally {
      setDocumentActionState(null);
    }
  }

  async function deleteDocument(document: DocumentItem) {
    // 删除是不可恢复操作，所以先用浏览器确认框向用户确认。
    const confirmed = window.confirm(
      `确定要删除“${document.title}”吗？这会同时删除数据库记录、页面记录和本地 PDF 文件。`,
    );

    if (!confirmed) {
      return;
    }

    setDocumentActionState({ documentId: document.document_id, action: "deleting" });
    setDocumentActionMessage("");

    try {
      const response = await fetch(`/api/documents/${document.document_id}`, {
        method: "DELETE",
      });

      if (!response.ok) {
        const errorData = (await response.json().catch(() => null)) as { detail?: string } | null;
        throw new Error(errorData?.detail ?? `删除失败，HTTP 状态码：${response.status}`);
      }

      if (editingDocumentId === document.document_id) {
        cancelRename();
      }

      if (activeReaderDocument?.document_id === document.document_id) {
        clearActiveDocument();
      }

      setDocumentActionMessage("文档已删除。");
      await loadDocuments();
    } catch (error) {
      setDocumentActionMessage(error instanceof Error ? error.message : "删除失败，请稍后重试。");
    } finally {
      setDocumentActionState(null);
    }
  }

  async function regenerateCourseSummary(document: DocumentItem) {
    setDocumentActionState({
      documentId: document.document_id,
      action: "regeneratingSummary",
    });
    setDocumentActionMessage("");

    try {
      const response = await fetch(
        `/api/documents/${document.document_id}/course-summary/regenerate`,
        {
          method: "POST",
        },
      );

      if (!response.ok) {
        const errorData = (await response.json().catch(() => null)) as { detail?: string } | null;
        throw new Error(errorData?.detail ?? `重新生成失败，HTTP 状态码：${response.status}`);
      }

      setDocumentActionMessage("课程简介已开始重新生成。");
      await loadDocuments();
      await loadDocumentStatus(document.document_id);
    } catch (error) {
      setDocumentActionMessage(
        error instanceof Error ? error.message : "重新生成课程简介失败，请稍后重试。",
      );
    } finally {
      setDocumentActionState(null);
    }
  }

  async function loadDocumentPages(documentId: string, shouldRefreshStatus = true) {
    setPagesMessageByDocument((currentMessages) => ({
      ...currentMessages,
      [documentId]: "正在加载页面讲稿...",
    }));

    try {
      const response = await fetch(`/api/documents/${documentId}/pages`);

      if (!response.ok) {
        const errorData = (await response.json().catch(() => null)) as { detail?: string } | null;
        throw new Error(errorData?.detail ?? `页面讲稿加载失败，HTTP 状态码：${response.status}`);
      }

      const data = (await response.json()) as PageItem[];

      setPagesByDocument((currentPages) => ({
        ...currentPages,
        [documentId]: data,
      }));
      setPagesMessageByDocument((currentMessages) => ({
        ...currentMessages,
        [documentId]: data.length > 0 ? "" : "当前文档还没有页面记录。",
      }));
      if (shouldRefreshStatus) {
        void loadDocumentStatus(documentId);
      }
    } catch (error) {
      setPagesMessageByDocument((currentMessages) => ({
        ...currentMessages,
        [documentId]: error instanceof Error ? error.message : "页面讲稿加载失败，请稍后重试。",
      }));
    }
  }

  async function submitPageQuestion(page: PageItem) {
    const question = pageQuestionInput.trim();

    if (!activeReaderDocument) {
      setPageChatMessage("需要先打开一份文档，才能进行当前页问答。");
      return;
    }

    if (!question) {
      setPageChatMessage("问题不能为空。");
      return;
    }

    setSubmittingPageChatId(page.page_id);
    setPageChatMessage("正在等待 AI 老师回答...");

    try {
      const response = await fetch(`/api/pages/${page.page_id}/chat`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({ question }),
      });

      if (!response.ok) {
        const errorData = (await response.json().catch(() => null)) as { detail?: string } | null;
        throw new Error(errorData?.detail ?? `当前页问答失败，HTTP 状态码：${response.status}`);
      }

      const data = (await response.json()) as PageChatResponse;

      setPagesByDocument((currentPages) => ({
        ...currentPages,
        [activeReaderDocument.document_id]: (currentPages[activeReaderDocument.document_id] ?? []).map(
          (currentPage) =>
            currentPage.page_id === data.page_id
              ? { ...currentPage, chat_messages: data.messages }
              : currentPage,
        ),
      }));
      setPageQuestionInput("");
      setPageChatMessage("AI 老师已回答。");
    } catch (error) {
      setPageChatMessage(error instanceof Error ? error.message : "当前页问答失败，请稍后重试。");
      await loadDocumentPages(activeReaderDocument.document_id);
    } finally {
      setSubmittingPageChatId(null);
    }
  }

  async function saveNoteBlockPosition(
    documentId: string,
    noteBlockId: string,
    nextPosition: NoteBlockLayout,
  ) {
    // 先更新本地缓存，避免等待网络响应期间位置闪回旧值。
    setPagesByDocument((currentPages) => ({
      ...currentPages,
      [documentId]: (currentPages[documentId] ?? []).map((page) =>
        page.note_block?.note_block_id === noteBlockId
          ? { ...page, note_block: { ...page.note_block, ...nextPosition } }
          : page,
      ),
    }));

    try {
      // 讲稿文字块的正文不允许在本接口修改，这里只保存拖动或缩放后的几何信息。
      const response = await fetch(`/api/note-blocks/${noteBlockId}`, {
        method: "PATCH",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify(nextPosition),
      });

      if (!response.ok) {
        const errorData = (await response.json().catch(() => null)) as { detail?: string } | null;
        throw new Error(errorData?.detail ?? `讲稿文字块位置保存失败，HTTP 状态码：${response.status}`);
      }

      const updatedNoteBlock = (await response.json()) as NoteBlockItem;

      // 保存成功后同步本地缓存，保证后端返回的最终数据覆盖本地草稿。
      setPagesByDocument((currentPages) => ({
        ...currentPages,
        [documentId]: (currentPages[documentId] ?? []).map((page) =>
          page.note_block?.note_block_id === updatedNoteBlock.note_block_id
            ? { ...page, note_block: updatedNoteBlock }
            : page,
        ),
      }));
      setReaderMessage("");
      setDraftNoteBlockLayouts((currentLayouts) => {
        const nextLayouts = { ...currentLayouts };
        delete nextLayouts[noteBlockId];
        return nextLayouts;
      });
    } catch (error) {
      setReaderMessage(error instanceof Error ? error.message : "讲稿文字块位置保存失败，请稍后重试。");
    }
  }

  function updateDraftNoteBlockLayout(noteBlockId: string, nextLayout: NoteBlockLayout) {
    // 拖动和缩放过程中只更新前端临时状态，避免每一帧都请求后端。
    setDraftNoteBlockLayouts((currentLayouts) => ({
      ...currentLayouts,
      [noteBlockId]: nextLayout,
    }));
  }

  function resolveNoteBlockLayout(noteBlock: NoteBlockItem): NoteBlockLayout {
    // 如果用户正在拖动或缩放，优先使用临时布局；否则使用后端持久化布局。
    return draftNoteBlockLayouts[noteBlock.note_block_id] ?? {
      x: noteBlock.x,
      y: noteBlock.y,
      width: noteBlock.width,
      height: noteBlock.height,
    };
  }

  function clampNoteBlockLayout(layout: NoteBlockLayout): NoteBlockLayout {
    // 本地交互层只保证窗口不会缩到不可见；边界超出阅读区时交给用户继续调整。
    return {
      x: Number.isFinite(layout.x) ? layout.x : 0,
      y: Number.isFinite(layout.y) ? layout.y : 0,
      width: Math.max(MIN_NOTE_BLOCK_WIDTH, Number.isFinite(layout.width) ? layout.width : MIN_NOTE_BLOCK_WIDTH),
      height: Math.max(MIN_NOTE_BLOCK_HEIGHT, Number.isFinite(layout.height) ? layout.height : MIN_NOTE_BLOCK_HEIGHT),
    };
  }

  function buildDraggedNoteBlockLayout(
    interaction: NoteBlockInteraction,
    event: PointerEvent,
  ): NoteBlockLayout {
    // 拖动只改变左上角坐标，宽高保持操作开始时的值。
    const deltaX = event.clientX - interaction.startClientX;
    const deltaY = event.clientY - interaction.startClientY;

    return clampNoteBlockLayout({
      ...interaction.startLayout,
      x: interaction.startLayout.x + deltaX,
      y: interaction.startLayout.y + deltaY,
    });
  }

  function buildResizedNoteBlockLayout(
    interaction: NoteBlockInteraction,
    event: PointerEvent,
  ): NoteBlockLayout {
    const direction = interaction.resizeDirection;
    const deltaX = event.clientX - interaction.startClientX;
    const deltaY = event.clientY - interaction.startClientY;
    const nextLayout = { ...interaction.startLayout };

    // 左侧缩放会同时改变 x 和 width；当达到最小宽度后，x 停在右边界减最小宽度的位置。
    const normalizedDirection = direction?.toLowerCase() ?? "";

    if (normalizedDirection.includes("left")) {
      const nextWidth = Math.max(MIN_NOTE_BLOCK_WIDTH, interaction.startLayout.width - deltaX);
      nextLayout.x = interaction.startLayout.x + interaction.startLayout.width - nextWidth;
      nextLayout.width = nextWidth;
    }

    // 右侧缩放只改变 width。
    if (normalizedDirection.includes("right")) {
      nextLayout.width = Math.max(MIN_NOTE_BLOCK_WIDTH, interaction.startLayout.width + deltaX);
    }

    // 顶部缩放会同时改变 y 和 height；当达到最小高度后，y 停在下边界减最小高度的位置。
    if (normalizedDirection.includes("top")) {
      const nextHeight = Math.max(MIN_NOTE_BLOCK_HEIGHT, interaction.startLayout.height - deltaY);
      nextLayout.y = interaction.startLayout.y + interaction.startLayout.height - nextHeight;
      nextLayout.height = nextHeight;
    }

    // 底部缩放只改变 height。
    if (normalizedDirection.includes("bottom")) {
      nextLayout.height = Math.max(MIN_NOTE_BLOCK_HEIGHT, interaction.startLayout.height + deltaY);
    }

    return clampNoteBlockLayout(nextLayout);
  }

  function startNoteBlockDrag(
    event: React.PointerEvent<HTMLDivElement>,
    documentId: string,
    noteBlock: NoteBlockItem,
  ) {
    // 只响应鼠标左键和触控笔主按钮，避免右键菜单或其他按钮触发拖动。
    if (event.button !== 0) {
      return;
    }

    event.preventDefault();
    event.stopPropagation();
    setNoteBlockInteraction({
      noteBlockId: noteBlock.note_block_id,
      documentId,
      mode: "drag",
      resizeDirection: null,
      startClientX: event.clientX,
      startClientY: event.clientY,
      startLayout: resolveNoteBlockLayout(noteBlock),
    });
  }

  function startNoteBlockResize(
    event: React.PointerEvent<HTMLButtonElement>,
    documentId: string,
    noteBlock: NoteBlockItem,
    resizeDirection: NoteBlockResizeDirection,
  ) {
    if (event.button !== 0) {
      return;
    }

    event.preventDefault();
    event.stopPropagation();
    setNoteBlockInteraction({
      noteBlockId: noteBlock.note_block_id,
      documentId,
      mode: "resize",
      resizeDirection,
      startClientX: event.clientX,
      startClientY: event.clientY,
      startLayout: resolveNoteBlockLayout(noteBlock),
    });
  }

  async function toggleLectureNotesPanel(document: DocumentItem) {
    if (expandedLectureNotesDocumentId === document.document_id) {
      setExpandedLectureNotesDocumentId(null);
      return;
    }

    setExpandedLectureNotesDocumentId(document.document_id);
    await loadDocumentPages(document.document_id);
  }

  async function regenerateDocumentLectureNotes(document: DocumentItem) {
    setDocumentActionState({
      documentId: document.document_id,
      action: "regeneratingLectureNotes",
    });
    setDocumentActionMessage("");

    try {
      const response = await fetch(
        `/api/documents/${document.document_id}/lecture-notes/regenerate`,
        {
          method: "POST",
        },
      );

      if (!response.ok) {
        const errorData = (await response.json().catch(() => null)) as { detail?: string } | null;
        throw new Error(errorData?.detail ?? `重新生成讲稿失败，HTTP 状态码：${response.status}`);
      }

      setDocumentActionMessage("逐页讲稿已开始重新生成。");
      await loadDocumentStatus(document.document_id);
      await loadDocumentPages(document.document_id);
    } catch (error) {
      setDocumentActionMessage(
        error instanceof Error ? error.message : "重新生成逐页讲稿失败，请稍后重试。",
      );
    } finally {
      setDocumentActionState(null);
    }
  }

  async function toggleDocumentLectureNotesPaused(document: DocumentItem) {
    const isPaused = resolveLectureNotesPaused(document);

    setDocumentActionState({
      documentId: document.document_id,
      action: isPaused ? "resumingLectureNotes" : "pausingLectureNotes",
    });
    setDocumentActionMessage("");

    try {
      const response = await fetch(
        `/api/documents/${document.document_id}/lecture-notes/${isPaused ? "resume" : "pause"}`,
        {
          method: "POST",
        },
      );

      if (!response.ok) {
        const errorData = (await response.json().catch(() => null)) as { detail?: string } | null;
        throw new Error(
          errorData?.detail ??
            `${isPaused ? "继续" : "暂停"}逐页讲稿生成失败，HTTP 状态码：${response.status}`,
        );
      }

      setDocumentActionMessage(isPaused ? "逐页讲稿已继续生成。" : "逐页讲稿已暂停后续页面生成。");
      await loadDocumentStatus(document.document_id);
      await loadDocumentPages(document.document_id, false);
    } catch (error) {
      setDocumentActionMessage(
        error instanceof Error
          ? error.message
          : `${isPaused ? "继续" : "暂停"}逐页讲稿生成失败，请稍后重试。`,
      );
    } finally {
      setDocumentActionState(null);
    }
  }

  async function regeneratePageLectureNotes(document: DocumentItem, page: PageItem) {
    setDocumentActionState({
      documentId: document.document_id,
      pageNumber: page.page_number,
      action: "regeneratingLectureNotes",
    });
    setDocumentActionMessage("");

    try {
      const response = await fetch(
        `/api/pages/${page.page_id}/regenerate`,
        {
          method: "POST",
        },
      );

      if (!response.ok) {
        const errorData = (await response.json().catch(() => null)) as { detail?: string } | null;
        throw new Error(
          errorData?.detail ?? `重新生成第 ${page.page_number} 页讲稿失败，HTTP 状态码：${response.status}`,
        );
      }

      setDocumentActionMessage(`第 ${page.page_number} 页讲稿已开始重新生成。`);
      await loadDocumentStatus(document.document_id);
      await loadDocumentPages(document.document_id);
    } catch (error) {
      setDocumentActionMessage(
        error instanceof Error ? error.message : "重新生成单页讲稿失败，请稍后重试。",
      );
    } finally {
      setDocumentActionState(null);
    }
  }

  if (currentView === "reader" && activeReaderDocument) {
    // readerDocument 优先使用文档列表里的最新记录，避免重命名或生成状态更新后阅读页仍显示旧数据。
    const readerDocument =
      documents.find((document) => document.document_id === activeReaderDocument.document_id) ??
      activeReaderDocument;

    // fileUrl 指向后端返回系统实际使用 PDF 的接口，React-PDF 会直接从该地址加载并渲染。
    const fileUrl = `/api/documents/${readerDocument.document_id}/file`;

    // PDF 页面按主工作区的宽高共同约束，保证不依赖主 PPT 区域滚动才能看完整页。
    const pdfPageAspectRatio =
      pdfPageNaturalSize && pdfPageNaturalSize.height > 0
        ? pdfPageNaturalSize.width / pdfPageNaturalSize.height
        : null;
    const pdfPageWidthByHeight =
      pdfPageAspectRatio && readerWorkspaceSize.height > 0
        ? readerWorkspaceSize.height * pdfPageAspectRatio
        : readerWorkspaceSize.width;
    const pdfPageWidth =
      readerWorkspaceSize.width > 0
        ? Math.max(120, Math.min(readerWorkspaceSize.width, pdfPageWidthByHeight))
        : readerViewportWidth > 0
          ? readerViewportWidth
          : undefined;
    const readerPages = pagesByDocument[readerDocument.document_id] ?? [];
    const currentReaderPage = readerPages.find((page) => page.page_number === currentPdfPage);
    const activeDocumentStatus = documentStatusById[readerDocument.document_id];
    const currentNoteBlock =
      currentReaderPage?.lecture_notes_status === "ready" ? currentReaderPage.note_block : null;
    const currentNoteBlockLayout = currentNoteBlock
      ? resolveNoteBlockLayout(currentNoteBlock)
      : null;
    const isSubmittingCurrentPageChat =
      currentReaderPage !== undefined && submittingPageChatId === currentReaderPage.page_id;
    const currentPageChatCount = currentReaderPage?.chat_messages.length ?? 0;
    const pageChatContent = currentReaderPage ? (
      <>
        <div className="page-chat-history">
          {currentReaderPage.chat_messages.length > 0 ? (
            currentReaderPage.chat_messages.map((chatMessage) => (
              <article
                className={`page-chat-message page-chat-message--${chatMessage.role}`}
                key={chatMessage.chat_message_id}
              >
                <div className="page-chat-message__meta">
                  <strong>{getChatRoleLabel(chatMessage.role)}</strong>
                  <span>{formatCreatedAt(chatMessage.created_at)}</span>
                </div>
                <p>{chatMessage.content}</p>
              </article>
            ))
          ) : (
            <p className="page-chat-empty">本页还没有问答历史。</p>
          )}
        </div>

        <form
          className="page-chat-form"
          onSubmit={(event) => {
            event.preventDefault();
            void submitPageQuestion(currentReaderPage);
          }}
        >
          <label className="page-chat-input-label">
            <span>向 AI 老师提问</span>
            <textarea
              value={pageQuestionInput}
              onChange={(event) => setPageQuestionInput(event.target.value)}
              disabled={isSubmittingCurrentPageChat}
              placeholder="输入你想问当前页的问题"
            />
          </label>
          <button
            type="submit"
            className="page-turn-button"
            disabled={isSubmittingCurrentPageChat}
          >
            {isSubmittingCurrentPageChat ? "回答中..." : "提交问题"}
          </button>
        </form>
      </>
    ) : (
      <p className="page-chat-empty">正在加载当前页数据，稍后即可提问。</p>
    );
    const pageChatStatus = pageChatMessage ? (
      <p
        className={`page-chat-status${
          pageChatMessage.includes("失败") || pageChatMessage.includes("不能为空")
            || pageChatMessage.includes("错误")
            || pageChatMessage.includes("无法")
            || pageChatMessage.includes("超时")
            ? " page-chat-status--error"
            : ""
        }`}
      >
        {pageChatMessage}
      </p>
    ) : null;
    const pageTurnControls = (
      <div className="pdf-reader-toolbar">
        <button
          type="button"
          className="page-turn-button"
          onClick={() => turnPdfPage(-1)}
          disabled={currentPdfPage <= 1 || totalPdfPages <= 0}
        >
          上一页
        </button>
        <span className="pdf-page-indicator">
          第{" "}
          {isEditingPdfPage ? (
            <input
              ref={pdfPageInputRef}
              className="pdf-page-input"
              value={pdfPageInputValue}
              onChange={(event) => setPdfPageInputValue(event.target.value)}
              onBlur={submitPdfPageInput}
              onKeyDown={handlePdfPageInputKeyDown}
              inputMode="numeric"
              aria-label="输入要跳转的页码"
            />
          ) : (
            <button
              type="button"
              className="pdf-current-page-button"
              onClick={startEditingPdfPage}
              disabled={readerState !== "ready" || totalPdfPages <= 0}
              title="点击输入页码"
            >
              {currentPdfPage}
            </button>
          )}{" "}
          / {totalPdfPages || readerDocument.page_count || "-"} 页
        </span>
        <button
          type="button"
          className="page-turn-button"
          onClick={() => turnPdfPage(1)}
          disabled={totalPdfPages <= 0 || currentPdfPage >= totalPdfPages}
        >
          下一页
        </button>
      </div>
    );

    return (
      <main className="app-shell app-shell--reader">
        <section
          className={`reader-shell${
            isReaderTopbarCollapsed ? " reader-shell--topbar-collapsed" : ""
          }${isReaderChatCollapsed ? " reader-shell--chat-collapsed" : ""}`}
        >
          {isReaderTopbarCollapsed ? (
            <header className="reader-collapsed-topbar">
              <button
                type="button"
                className="topbar-button topbar-button--primary"
                onClick={() => setIsReaderTopbarCollapsed(false)}
              >
                展开顶部
              </button>
              <span className="reader-collapsed-title">{readerDocument.title}</span>
              <span className="reader-collapsed-page">
                第 {currentPdfPage} / {totalPdfPages || readerDocument.page_count || "-"} 页
              </span>
            </header>
          ) : (
            <header className="reader-topbar">
              <div className="reader-topbar-left">
                <div className="reader-main-actions">
                  <button
                    type="button"
                    className="topbar-button topbar-button--primary"
                    onClick={closeReader}
                  >
                    文件
                  </button>
                  <button type="button" className="topbar-button" onClick={openSettings}>
                    设置
                  </button>
                </div>
                <div className="reader-title-group">
                  <span className="reader-kicker">PDF 阅读</span>
                  <h1>{readerDocument.title}</h1>
                  <div className="reader-status-row">
                    <span className={`document-status document-status--${readerDocument.status}`}>
                      PDF：{getStatusLabel(readerDocument.status)}
                    </span>
                    <span
                      className={`document-status document-status--${readerDocument.course_summary_status}`}
                    >
                      简介：{getCourseSummaryStatusLabel(readerDocument.course_summary_status)}
                    </span>
                    <span className="reader-progress-text">
                      {buildLectureNotesProgressText(activeDocumentStatus)}
                    </span>
                  </div>
                </div>
              </div>
              <div className="reader-topbar-center">{pageTurnControls}</div>
              <div className="reader-secondary-actions">
                <button
                  type="button"
                  className="topbar-button"
                  onClick={toggleCourseSummarySidebar}
                >
                  {readerRightSidebar === "summary" ? "收起简介" : "课程简介"}
                </button>
                <button type="button" className="topbar-button" onClick={clearActiveDocument}>
                  关闭文档
                </button>
                <button
                  type="button"
                  className="topbar-button"
                  onClick={() => {
                    setIsCourseSummaryPanelOpen(false);
                    setReaderRightSidebar((currentSidebar) =>
                      currentSidebar === "summary" ? "none" : currentSidebar,
                    );
                    setIsReaderTopbarCollapsed(true);
                  }}
                >
                  折叠顶部
                </button>
              </div>
            </header>
          )}

          {readerMessage || activeDocumentStatus?.course_summary_error ? (
          <div className="reader-status-stack">
            {readerMessage ? (
              <p className={`pdf-reader-message pdf-reader-message--${readerState}`}>
                {readerMessage}
              </p>
            ) : null}

            {activeDocumentStatus?.course_summary_error ? (
              <div className="reader-generation-strip">
                <strong>AI 生成进度</strong>
                <p>{buildLectureNotesProgressText(activeDocumentStatus)}</p>
                <p className="document-error">{activeDocumentStatus.course_summary_error}</p>
              </div>
            ) : null}
          </div>
          ) : null}

          <section ref={readerWorkspaceRef} className="reader-workspace">
            <div ref={readerViewportRef} className="pdf-reader-viewport">
              <PdfDocument
                file={fileUrl}
                className="pdf-document"
                loading={<div className="pdf-loading">正在加载 PDF...</div>}
                error={<div className="pdf-error">PDF 加载失败，请返回列表后重试。</div>}
                onLoadSuccess={handlePdfLoadSuccess}
                onLoadError={handlePdfLoadError}
              >
                {totalPdfPages > 0 ? (
                  <div
                    ref={readerContentRef}
                    className={`pdf-reader-content${
                      isResizingThumbnailSidebar || isResizingCourseSummarySidebar
                        ? " pdf-reader-content--resizing"
                        : ""
                    }`}
                    style={{
                      "--thumbnail-sidebar-width": `${thumbnailSidebarWidth}px`,
                      "--course-summary-sidebar-width": `${courseSummarySidebarWidth}px`,
                    } as CSSProperties}
                  >
                    <aside className="pdf-thumbnail-sidebar" aria-label="PDF 页面缩略图列表">
                      {Array.from({ length: totalPdfPages }, (_, index) => {
                        const pageNumber = index + 1;
                        const isCurrentPage = pageNumber === currentPdfPage;

                        return (
                          <button
                            type="button"
                            className={`pdf-thumbnail-button${
                              isCurrentPage ? " pdf-thumbnail-button--active" : ""
                            }`}
                            key={pageNumber}
                            onClick={() => goToPdfPage(pageNumber)}
                            aria-current={isCurrentPage ? "page" : undefined}
                          >
                            <PdfThumbnail
                              pageNumber={pageNumber}
                              width={thumbnailRenderWidth}
                              loading={
                                <span
                                  className="pdf-thumbnail-loading"
                                  style={{ minHeight: `${thumbnailRenderWidth * 1.35}px` }}
                                >
                                  加载中
                                </span>
                              }
                            />
                            <span>第 {pageNumber} 页</span>
                          </button>
                        );
                      })}
                    </aside>

                    <button
                      type="button"
                      className="pdf-thumbnail-resizer"
                      onPointerDown={startResizingThumbnailSidebar}
                      aria-label="拖动调整缩略图栏宽度"
                    />

                    <div className="pdf-page-stage">
                      <PdfPage
                        key={`${readerDocument.document_id}-${currentPdfPage}`}
                        pageNumber={currentPdfPage}
                        width={pdfPageWidth}
                        loading={<div className="pdf-loading">正在渲染当前页...</div>}
                        renderAnnotationLayer={true}
                        renderTextLayer={true}
                        onLoadSuccess={handlePdfPageLoadSuccess}
                        onRenderError={handlePdfPageRenderError}
                      />
                      {currentNoteBlock ? (
                        <div
                          className="lecture-note-block"
                          style={{
                            left: currentNoteBlockLayout?.x ?? currentNoteBlock.x,
                            top: currentNoteBlockLayout?.y ?? currentNoteBlock.y,
                            width: currentNoteBlockLayout?.width ?? currentNoteBlock.width,
                            height: currentNoteBlockLayout?.height ?? currentNoteBlock.height,
                          }}
                        >
                          <div className="lecture-note-block__shell">
                            <div
                              className="lecture-note-block__handle"
                              onPointerDown={(event) =>
                                startNoteBlockDrag(
                                  event,
                                  readerDocument.document_id,
                                  currentNoteBlock,
                                )
                              }
                            >
                              <span>本页讲稿</span>
                              <button
                                type="button"
                                className="lecture-note-block__regenerate"
                                onPointerDown={(event) => event.stopPropagation()}
                                onClick={() => {
                                  if (currentReaderPage) {
                                    regeneratePageLectureNotes(readerDocument, currentReaderPage);
                                  }
                                }}
                                disabled={
                                  !currentReaderPage ||
                                  isDocumentBusy(readerDocument.document_id) ||
                                  readerDocument.course_summary_status !== "ready" ||
                                  !readerDocument.course_summary
                                }
                              >
                                {currentReaderPage &&
                                isPageLectureNotesBusy(
                                  readerDocument.document_id,
                                  currentReaderPage.page_number,
                                )
                                  ? "提交中..."
                                  : "重生成"}
                              </button>
                            </div>
                            <div className="lecture-note-block__content">
                              {currentNoteBlock.content}
                            </div>
                            {(
                              [
                                "top",
                                "right",
                                "bottom",
                                "left",
                                "topRight",
                                "bottomRight",
                                "bottomLeft",
                                "topLeft",
                              ] satisfies NoteBlockResizeDirection[]
                            ).map((resizeDirection) => (
                              <button
                                type="button"
                                key={resizeDirection}
                                className={`lecture-note-block__resize-handle lecture-note-block__resize-handle--${resizeDirection}`}
                                onPointerDown={(event) =>
                                  startNoteBlockResize(
                                    event,
                                    readerDocument.document_id,
                                    currentNoteBlock,
                                    resizeDirection,
                                  )
                                }
                                aria-label="调整讲稿文字块大小"
                              />
                            ))}
                          </div>
                        </div>
                      ) : null}
                    </div>

                    {readerRightSidebar !== "none" ? (
                      <>
                        <button
                          type="button"
                          className="course-summary-resizer"
                          onPointerDown={startResizingCourseSummarySidebar}
                          aria-label="拖动调整右侧栏宽度"
                        />

                        <aside className="course-summary-sidebar" aria-label={readerRightSidebar === "summary" ? "课程简介" : "当前页问答"}>
                          <div className="course-summary-sidebar__header">
                            <div>
                              <h2>{readerRightSidebar === "summary" ? "课程简介" : "当前页问答"}</h2>
                              {readerRightSidebar === "summary" ? (
                                <span
                                  className={`document-status document-status--${readerDocument.course_summary_status}`}
                                >
                                  {getCourseSummaryStatusLabel(readerDocument.course_summary_status)}
                                </span>
                              ) : (
                                <span className="page-chat-page-badge">
                                  第 {currentReaderPage?.page_number ?? currentPdfPage} 页
                                </span>
                              )}
                            </div>
                            <button
                              type="button"
                              className="course-summary-close-button"
                              onClick={closeRightSidebar}
                              aria-label="关闭右侧栏"
                            >
                              ×
                            </button>
                          </div>

                          <div className="course-summary-sidebar__content">
                            {readerRightSidebar === "summary" ? (
                              <>
                                {readerDocument.course_summary_status === "ready" &&
                                readerDocument.course_summary ? (
                                  <p>{readerDocument.course_summary}</p>
                                ) : null}
                                {readerDocument.course_summary_status === "processing" ? (
                                  <p>课程简介正在生成，生成完成后会自动更新状态。</p>
                                ) : null}
                                {readerDocument.course_summary_status === "pending" ? (
                                  <p>课程简介还没有开始生成。</p>
                                ) : null}
                                {readerDocument.course_summary_status === "failed" ? (
                                  <p className="document-error">
                                    {readerDocument.course_summary_error ?? "课程简介生成失败。"}
                                  </p>
                                ) : null}
                              </>
                            ) : (
                              pageChatContent
                            )}
                          </div>

                          {readerRightSidebar === "summary" ? (
                            <button
                              type="button"
                              className="secondary-action-button"
                              onClick={() => regenerateCourseSummary(readerDocument)}
                              disabled={isDocumentBusy(readerDocument.document_id)}
                            >
                              {documentActionState?.documentId === readerDocument.document_id &&
                              documentActionState.action === "regeneratingSummary"
                                ? "提交中..."
                                : readerDocument.course_summary_status === "pending"
                                  ? "生成简介"
                                  : "重新生成简介"}
                            </button>
                          ) : (
                            pageChatStatus
                          )}
                        </aside>
                      </>
                    ) : null}
                  </div>
                ) : null}
              </PdfDocument>
            </div>
          </section>

          {readerRightSidebar === "chat" ? null : isReaderChatCollapsed ? (
            <section className="reader-chat-collapsed">
              <button
                type="button"
                className="topbar-button topbar-button--primary"
                onClick={() => setIsReaderChatCollapsed(false)}
              >
                展开会话
              </button>
              <span>当前页问答：第 {currentPdfPage} 页</span>
              <span>{currentPageChatCount > 0 ? `${currentPageChatCount} 条历史` : "暂无问答历史"}</span>
            </section>
          ) : (
            <section className="reader-chat-dock page-chat-panel">
              <div className="page-chat-header">
                <div>
                  <h2>当前页问答</h2>
                  <p>
                    这里的历史只属于第 {currentPdfPage} 页，切换页面后会显示新页面自己的问答。
                  </p>
                </div>
                <div className="page-chat-header-actions">
                  {currentReaderPage ? (
                    <span className="page-chat-page-badge">
                      第 {currentReaderPage.page_number} 页
                    </span>
                  ) : null}
                  <button
                    type="button"
                    className="topbar-button"
                    onClick={openChatSidebar}
                  >
                    移到右侧栏
                  </button>
                  <button
                    type="button"
                    className="topbar-button"
                    onClick={() => setIsReaderChatCollapsed(true)}
                  >
                    折叠会话
                  </button>
                </div>
              </div>

              {pageChatContent}
              {pageChatStatus}
            </section>
          )}
        </section>
      </main>
    );
  }

  const visibleView: AppView = currentView === "reader" ? "files" : currentView;
  const currentOpenedDocument =
    activeReaderDocument === null
      ? null
      : documents.find((document) => document.document_id === activeReaderDocument.document_id) ??
        activeReaderDocument;

  return (
    <main className={`app-shell app-shell--${visibleView}`}>
      <section className="status-panel app-page-panel">
        <header className="app-page-header">
          <div>
            <p className="eyebrow">Slides Reader</p>
            <h1>{visibleView === "settings" ? "设置" : "文件"}</h1>
            <p className="description">
              {visibleView === "settings"
                ? "修改 LLM 配置，用于生成课程简介、逐页讲稿和当前页问答。"
                : "上传、选择、重命名或删除 slides 文件。"}
            </p>
          </div>
          <div className="app-page-actions">
            <button
              type="button"
              className={`topbar-button${visibleView === "files" ? " topbar-button--primary" : ""}`}
              onClick={closeReader}
            >
              文件
            </button>
            <button
              type="button"
              className={`topbar-button${
                visibleView === "settings" ? " topbar-button--primary" : ""
              }`}
              onClick={openSettings}
            >
              设置
            </button>
            <button
              type="button"
              className="topbar-button"
              onClick={returnToReader}
              disabled={!activeReaderDocument}
            >
              返回阅读
            </button>
          </div>
        </header>

        <div className={`connection-card connection-card--${connectionState}`}>
          <span className="status-dot" />
          <div>
            <strong>{connectionState === "checking" ? "正在连接后端" : message}</strong>
            <p>
              {connectionState === "success"
                ? "现在可以上传 PDF/PPT/PPTX slides。"
                : "请先启动后端，再刷新当前前端页面。"}
            </p>
          </div>
        </div>

        {visibleView === "files" ? (
          <div className="current-document-banner">
            <span>当前打开</span>
            <strong>{currentOpenedDocument ? currentOpenedDocument.title : "未打开文档"}</strong>
            {currentOpenedDocument ? (
              <button type="button" className="secondary-action-button" onClick={returnToReader}>
                返回阅读
              </button>
            ) : null}
          </div>
        ) : null}

        {visibleView === "files" ? (
        <form className="upload-panel" onSubmit={handleUploadSubmit}>
          <div>
            <h2>上传 slides</h2>
            <p>请选择 `.pdf`、`.ppt` 或 `.pptx` 格式文件。上传成功后，后端会统一转换并使用 PDF。</p>
          </div>

          <label className="file-input-label">
            <span>选择 slides 文件</span>
            <input
              type="file"
              accept="application/pdf,.pdf,.ppt,.pptx"
              onChange={handleFileChange}
            />
          </label>

          <button
            className="upload-button"
            type="submit"
            disabled={!selectedFile || uploadState === "uploading"}
          >
            {uploadState === "uploading" ? "上传中..." : "上传 slides"}
          </button>

          <div className={`upload-message upload-message--${uploadState}`}>{uploadMessage}</div>

          {uploadedDocumentId ? (
            <div className="document-id-box">
              <span>document_id</span>
              <code>{uploadedDocumentId}</code>
            </div>
          ) : null}
        </form>
        ) : null}

        {visibleView === "settings" ? (
        <form className="llm-config-panel" onSubmit={saveLlmConfig}>
          <div>
            <h2>LLM 配置</h2>
            <p>
              LLM 是 Large Language Model，也就是“大语言模型”。这里配置
              OpenAI-compatible API，用于后续生成课程简介、逐页讲稿和回答问题。
            </p>
          </div>

          <label className="config-field">
            <span>LLM_BASE_URL</span>
            <input
              value={llmBaseUrl}
              onChange={(event) => setLlmBaseUrl(event.target.value)}
              placeholder="https://api.openai.com/v1"
              disabled={llmConfigState === "saving" || llmConfigState === "testing"}
            />
          </label>

          <label className="config-field">
            <span>LLM_API_KEY</span>
            <input
              value={llmApiKey}
              onChange={(event) => setLlmApiKey(event.target.value)}
              type="password"
              placeholder={
                llmApiKeyConfigured
                  ? `已保存：${llmApiKeyPreview}，留空表示不修改`
                  : "请输入 API Key"
              }
              disabled={
                shouldClearLlmApiKey ||
                llmConfigState === "saving" ||
                llmConfigState === "testing"
              }
            />
          </label>

          <label className="config-checkbox">
            <input
              type="checkbox"
              checked={shouldClearLlmApiKey}
              onChange={(event) => {
                setShouldClearLlmApiKey(event.target.checked);
                if (event.target.checked) {
                  setLlmApiKey("");
                }
              }}
              disabled={llmConfigState === "saving" || llmConfigState === "testing"}
            />
            <span>清空已保存的 LLM_API_KEY</span>
          </label>

          <label className="config-field">
            <span>LLM_MODEL</span>
            <input
              value={llmModel}
              onChange={(event) => setLlmModel(event.target.value)}
              placeholder="gpt-4.1-mini"
              disabled={llmConfigState === "saving" || llmConfigState === "testing"}
            />
          </label>

          <label className="config-field">
            <span>请求超时时间（秒）</span>
            <input
              value={llmTimeoutSeconds}
              onChange={(event) => setLlmTimeoutSeconds(event.target.value)}
              inputMode="numeric"
              disabled={llmConfigState === "saving" || llmConfigState === "testing"}
            />
          </label>

          <div className="prompt-setting">
            <div className="prompt-setting-header">
              <span>课程简介 prompt</span>
              <button
                type="button"
                className="prompt-toggle-button"
                onClick={() => setIsCourseSummaryPromptExpanded((isExpanded) => !isExpanded)}
                disabled={llmConfigState === "saving" || llmConfigState === "testing"}
              >
                {isCourseSummaryPromptExpanded ? "折叠" : "展开"}
              </button>
            </div>
            {isCourseSummaryPromptExpanded ? (
              <label className="config-field">
                <textarea
                  ref={courseSummaryPromptTextareaRef}
                  className="prompt-textarea"
                  value={courseSummaryPrompt}
                  onChange={(event) => setCourseSummaryPrompt(event.target.value)}
                  disabled={llmConfigState === "saving" || llmConfigState === "testing"}
                />
              </label>
            ) : null}
          </div>

          <div className="prompt-setting">
            <div className="prompt-setting-header">
              <span>逐页讲稿 prompt</span>
              <button
                type="button"
                className="prompt-toggle-button"
                onClick={() => setIsLectureNotesPromptExpanded((isExpanded) => !isExpanded)}
                disabled={llmConfigState === "saving" || llmConfigState === "testing"}
              >
                {isLectureNotesPromptExpanded ? "折叠" : "展开"}
              </button>
            </div>
            {isLectureNotesPromptExpanded ? (
              <label className="config-field">
                <textarea
                  ref={lectureNotesPromptTextareaRef}
                  className="prompt-textarea"
                  value={lectureNotesPrompt}
                  onChange={(event) => setLectureNotesPrompt(event.target.value)}
                  disabled={llmConfigState === "saving" || llmConfigState === "testing"}
                />
              </label>
            ) : null}
          </div>

          <div className="prompt-setting">
            <div className="prompt-setting-header">
              <span>当前页问答 prompt</span>
              <button
                type="button"
                className="prompt-toggle-button"
                onClick={() => setIsPageChatPromptExpanded((isExpanded) => !isExpanded)}
                disabled={llmConfigState === "saving" || llmConfigState === "testing"}
              >
                {isPageChatPromptExpanded ? "折叠" : "展开"}
              </button>
            </div>
            {isPageChatPromptExpanded ? (
              <label className="config-field">
                <textarea
                  ref={pageChatPromptTextareaRef}
                  className="prompt-textarea"
                  value={pageChatPrompt}
                  onChange={(event) => setPageChatPrompt(event.target.value)}
                  disabled={llmConfigState === "saving" || llmConfigState === "testing"}
                />
              </label>
            ) : null}
          </div>

          <label className="config-field">
            <span>测试提示词</span>
            <textarea
              value={llmTestPrompt}
              onChange={(event) => setLlmTestPrompt(event.target.value)}
              disabled={llmConfigState === "saving" || llmConfigState === "testing"}
            />
          </label>

          <div className="llm-config-actions">
            <button
              className="upload-button"
              type="submit"
              disabled={llmConfigState === "saving" || llmConfigState === "testing"}
            >
              {llmConfigState === "saving" ? "保存中..." : "保存配置"}
            </button>
            <button
              type="button"
              className="secondary-action-button"
              onClick={testLlmConfig}
              disabled={llmConfigState === "saving" || llmConfigState === "testing"}
            >
              {llmConfigState === "testing" ? "测试中..." : "测试连接"}
            </button>
          </div>

          <div className={`llm-config-message llm-config-message--${llmConfigState}`}>
            {llmConfigMessage}
          </div>

          {llmTestAnswer ? (
            <div className="llm-test-answer">
              <span>模型回答</span>
              <p>{llmTestAnswer}</p>
            </div>
          ) : null}
        </form>
        ) : null}

        {visibleView === "files" ? (
        <section className="documents-panel">
          <div>
            <h2>已上传文档</h2>
            <p>这些记录来自 SQLite 数据库，后端重启后仍然会保留。</p>
          </div>

          {documents.length > 0 ? (
            <ul className="document-list">
              {documents.map((document) => {
                const statusData = documentStatusById[document.document_id];
                const isDocumentExpanded = Boolean(expandedDocumentIds[document.document_id]);
                const isLectureNotesPaused = resolveLectureNotesPaused(document);
                const lectureNotesToggleLabel = isLectureNotesPaused
                  ? "继续生成讲稿"
                  : "暂停生成讲稿";

                return (
                <li
                  className={`document-list-item${
                    activeReaderDocument?.document_id === document.document_id
                      ? " document-list-item--active"
                      : ""
                  }${isDocumentExpanded ? " document-list-item--expanded" : ""}`}
                  key={document.document_id}
                >
                  <div className="document-header">
                    {editingDocumentId === document.document_id ? (
                      <div className="rename-form">
                        <label>
                          <span>新标题</span>
                          <input
                            value={editingTitle}
                            onChange={(event) => setEditingTitle(event.target.value)}
                            disabled={isDocumentBusy(document.document_id)}
                          />
                        </label>
                        <div className="document-actions">
                          <button
                            type="button"
                            onClick={() => saveRename(document.document_id)}
                            disabled={isDocumentBusy(document.document_id)}
                          >
                            {documentActionState?.documentId === document.document_id &&
                            documentActionState.action === "renaming"
                              ? "保存中..."
                              : "保存"}
                          </button>
                          <button
                            type="button"
                            className="secondary-button"
                            onClick={cancelRename}
                            disabled={isDocumentBusy(document.document_id)}
                          >
                            取消
                          </button>
                        </div>
                      </div>
                    ) : (
                      <div>
                        <div className="document-title-row">
                          <strong>{document.title}</strong>
                          {activeReaderDocument?.document_id === document.document_id ? (
                            <span className="document-active-badge">当前打开</span>
                          ) : null}
                        </div>
                        <span>{formatCreatedAt(document.created_at)}</span>
                      </div>
                    )}
                    <div className="document-actions">
                      <button
                        type="button"
                        className={`lecture-notes-toggle-button${
                          isLectureNotesPaused ? " lecture-notes-toggle-button--resume" : ""
                        }`}
                        onClick={() => toggleDocumentLectureNotesPaused(document)}
                        disabled={
                          isDocumentBusy(document.document_id) ||
                          document.course_summary_status !== "ready" ||
                          !document.course_summary
                        }
                        aria-label={lectureNotesToggleLabel}
                        title={lectureNotesToggleLabel}
                      >
                        <span
                          className={`lecture-notes-toggle-button__icon${
                            isLectureNotesPaused
                              ? " lecture-notes-toggle-button__icon--resume"
                              : ""
                          }`}
                          aria-hidden="true"
                        />
                      </button>
                      <button
                        type="button"
                        onClick={() => openReader(document)}
                        disabled={isDocumentBusy(document.document_id) || document.page_count <= 0}
                      >
                        阅读 slides
                      </button>
                      <button
                        type="button"
                        className="secondary-button"
                        onClick={() => startRename(document)}
                        disabled={isDocumentBusy(document.document_id)}
                      >
                        重命名
                      </button>
                      <button
                        type="button"
                        className="danger-button"
                        onClick={() => deleteDocument(document)}
                        disabled={isDocumentBusy(document.document_id)}
                      >
                        {documentActionState?.documentId === document.document_id &&
                        documentActionState.action === "deleting"
                          ? "删除中..."
                          : "删除"}
                      </button>
                      <button
                        type="button"
                        className="secondary-button"
                        onClick={() => toggleDocumentExpanded(document.document_id)}
                        disabled={isDocumentBusy(document.document_id)}
                      >
                        {isDocumentExpanded ? "收起" : "展开"}
                      </button>
                    </div>
                  </div>
                  <div className="generation-progress-box generation-progress-box--compact">
                    <div>
                      <strong>AI 生成进度</strong>
                      <p>{buildLectureNotesProgressText(statusData)}</p>
                    </div>
                    {isLectureNotesPaused ? (
                      <span className="document-status document-status--failed">已暂停</span>
                    ) : statusData?.should_poll ? (
                      <span className="document-status document-status--processing">
                        自动刷新中
                      </span>
                    ) : null}
                  </div>
                  {isDocumentExpanded ? (
                    <>
                  <dl>
                    <div>
                      <dt>document_id</dt>
                      <dd>{document.document_id}</dd>
                    </div>
                    <div>
                      <dt>状态</dt>
                      <dd>
                        <span className={`document-status document-status--${document.status}`}>
                          {getStatusLabel(document.status)}
                        </span>
                      </dd>
                    </div>
                    <div>
                      <dt>总页数</dt>
                      <dd>{document.page_count}</dd>
                    </div>
                    <div>
                      <dt>课程简介</dt>
                      <dd>
                        <span
                          className={`document-status document-status--${document.course_summary_status}`}
                        >
                          {getCourseSummaryStatusLabel(document.course_summary_status)}
                        </span>
                      </dd>
                    </div>
                  </dl>
                  {document.error_message ? (
                    <p className="document-error">{document.error_message}</p>
                  ) : null}
                  <div className="generation-progress-box">
                    <div>
                      <strong>AI 生成进度</strong>
                      <p>{buildLectureNotesProgressText(statusData)}</p>
                    </div>
                    {statusData?.should_poll ? (
                      <span className="document-status document-status--processing">
                        自动刷新中
                      </span>
                    ) : null}
                    {isLectureNotesPaused ? (
                      <span className="document-status document-status--failed">已暂停</span>
                    ) : null}
                    {statusData?.lecture_notes_failed_count ? (
                      <p className="document-error">
                        有 {statusData.lecture_notes_failed_count} 页讲稿生成失败，可展开页面讲稿后单页重试。
                      </p>
                    ) : null}
                    {documentStatusMessage ? (
                      <p className="document-error">{documentStatusMessage}</p>
                    ) : null}
                  </div>
                  <div className="course-summary-box">
                    {document.course_summary_status === "ready" && document.course_summary ? (
                      <>
                        <span>课程简介</span>
                        <p>{document.course_summary}</p>
                        <button
                          type="button"
                          className="secondary-action-button"
                          onClick={() => regenerateCourseSummary(document)}
                          disabled={isDocumentBusy(document.document_id)}
                        >
                          {documentActionState?.documentId === document.document_id &&
                          documentActionState.action === "regeneratingSummary"
                            ? "提交中..."
                            : "重新生成简介"}
                        </button>
                      </>
                    ) : null}
                    {document.course_summary_status === "processing" ? (
                      <p>课程简介正在生成，稍后刷新文档列表查看结果。</p>
                    ) : null}
                    {document.course_summary_status === "pending" ? (
                      <>
                        <p>课程简介还没有开始生成。</p>
                        <button
                          type="button"
                          className="secondary-action-button"
                          onClick={() => regenerateCourseSummary(document)}
                          disabled={isDocumentBusy(document.document_id)}
                        >
                          {documentActionState?.documentId === document.document_id &&
                          documentActionState.action === "regeneratingSummary"
                            ? "提交中..."
                            : "生成简介"}
                        </button>
                      </>
                    ) : null}
                    {document.course_summary_status === "failed" ? (
                      <>
                        <p className="document-error">
                          {document.course_summary_error ?? "课程简介生成失败。"}
                        </p>
                        <button
                          type="button"
                          className="secondary-action-button"
                          onClick={() => regenerateCourseSummary(document)}
                          disabled={isDocumentBusy(document.document_id)}
                        >
                          {documentActionState?.documentId === document.document_id &&
                          documentActionState.action === "regeneratingSummary"
                            ? "提交中..."
                            : "重新生成简介"}
                        </button>
                      </>
                    ) : null}
                  </div>
                  <div className="lecture-notes-box">
                    <div className="lecture-notes-header">
                      <span>逐页讲稿</span>
                      <div className="lecture-notes-actions">
                        <button
                          type="button"
                          className="secondary-action-button"
                          onClick={() => toggleLectureNotesPanel(document)}
                          disabled={isDocumentBusy(document.document_id)}
                        >
                          {expandedLectureNotesDocumentId === document.document_id
                            ? "收起页面讲稿"
                            : "查看页面讲稿"}
                        </button>
                        <button
                          type="button"
                          className="secondary-action-button"
                          onClick={() => regenerateDocumentLectureNotes(document)}
                          disabled={
                            isDocumentBusy(document.document_id) ||
                            document.course_summary_status !== "ready" ||
                            !document.course_summary
                          }
                        >
                          {documentActionState?.documentId === document.document_id &&
                          documentActionState.action === "regeneratingLectureNotes" &&
                          documentActionState.pageNumber === undefined
                            ? "提交中..."
                            : "重新生成全部讲稿"}
                        </button>
                        <button
                          type="button"
                          className="secondary-action-button"
                          onClick={() => toggleDocumentLectureNotesPaused(document)}
                          disabled={
                            isDocumentBusy(document.document_id) ||
                            document.course_summary_status !== "ready" ||
                            !document.course_summary
                          }
                        >
                          {documentActionState?.documentId === document.document_id &&
                          (documentActionState.action === "pausingLectureNotes" ||
                            documentActionState.action === "resumingLectureNotes")
                            ? "提交中..."
                            : lectureNotesToggleLabel}
                        </button>
                      </div>
                    </div>
                    {document.course_summary_status !== "ready" || !document.course_summary ? (
                      <p>逐页讲稿会等待课程简介生成成功后再生成。</p>
                    ) : null}
                    {expandedLectureNotesDocumentId === document.document_id ? (
                      <div className="lecture-notes-panel">
                        {pagesMessageByDocument[document.document_id] ? (
                          <p>{pagesMessageByDocument[document.document_id]}</p>
                        ) : null}
                        {(pagesByDocument[document.document_id] ?? []).length > 0 ? (
                          <ul className="lecture-notes-list">
                            {(pagesByDocument[document.document_id] ?? []).map((page) => (
                              <li className="lecture-notes-item" key={page.page_id}>
                                <div className="lecture-notes-item-header">
                                  <strong>第 {page.page_number} 页</strong>
                                  <span
                                    className={`document-status document-status--${page.lecture_notes_status}`}
                                  >
                                    {getLectureNotesStatusLabel(page.lecture_notes_status)}
                                  </span>
                                </div>
                                {page.lecture_notes_status === "ready" && page.lecture_notes ? (
                                  <p>{page.lecture_notes}</p>
                                ) : null}
                                {page.lecture_notes_status === "processing" ||
                                page.lecture_notes_status === "pending" ? (
                                  <p>本页讲稿正在等待或生成中。</p>
                                ) : null}
                                {page.status === "failed" && page.error_message ? (
                                  <p className="document-error">{page.error_message}</p>
                                ) : null}
                                {page.lecture_notes_status === "failed" ? (
                                  <p className="document-error">
                                    {page.lecture_notes_error ?? "本页讲稿生成失败。"}
                                  </p>
                                ) : null}
                                <button
                                  type="button"
                                  className="secondary-action-button"
                                  onClick={() => regeneratePageLectureNotes(document, page)}
                                  disabled={
                                    isDocumentBusy(document.document_id) ||
                                    document.course_summary_status !== "ready" ||
                                    !document.course_summary
                                  }
                                >
                                  {isPageLectureNotesBusy(document.document_id, page.page_number)
                                    ? "提交中..."
                                    : page.lecture_notes_status === "failed"
                                      ? "重试本页讲稿"
                                      : "重新生成本页讲稿"}
                                </button>
                              </li>
                            ))}
                          </ul>
                        ) : null}
                      </div>
                    ) : null}
                  </div>
                    </>
                  ) : null}
                </li>
              );
              })}
            </ul>
          ) : (
            <p className="documents-empty">{documentsMessage}</p>
          )}

          {documentActionMessage ? (
            <p className="document-action-message">{documentActionMessage}</p>
          ) : null}
        </section>
        ) : null}
      </section>
    </main>
  );
}

export default App;
