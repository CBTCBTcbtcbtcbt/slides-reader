import { lazy, Suspense, useEffect, useRef, useState } from "react";
import {
  Navigate,
  useLocation,
  useMatch,
  useNavigate,
  useSearchParams,
} from "react-router-dom";
import {
  clearDocumentLectureNotesQueue as clearDocumentLectureNotesQueueRequest,
  deleteDocument as deleteDocumentRequest,
  generateRemainingLectureNotes as generateRemainingLectureNotesRequest,
  listDocumentPages,
  listDocuments,
  readDocumentStatus,
  regenerateCourseSummary as regenerateCourseSummaryRequest,
  regenerateDocumentLectureNotes as regenerateDocumentLectureNotesRequest,
  regeneratePageLectureNotes as regeneratePageLectureNotesRequest,
  renameDocument,
  submitPageChatStream,
  toggleDocumentLectureNotesPaused as toggleDocumentLectureNotesPausedRequest,
  updateNoteBlockPosition,
  uploadDocument,
} from "./api/documents";
import {
  checkHealth,
  readLlmConfig,
  saveLlmConfig as saveLlmConfigRequest,
  testLlmConfig as testLlmConfigRequest,
} from "./api/llm";
import {
  deleteExam as deleteExamRequest,
  generateExam as generateExamRequest,
  listDocumentExams,
  readExamAttemptResult,
  readExamMetadata,
  readExamQuestions,
  submitExamAttempt,
} from "./api/exams";
import { generatePhaseExam, listPhaseExams } from "./api/phaseExams";
import {
  deleteWrongQuestion,
  listWrongQuestions,
  reviewWrongQuestion,
} from "./api/wrongQuestions";
import { ExamResultView } from "./components/ExamResultView/ExamResultView";
import { ExamTakeView } from "./components/ExamTakeView/ExamTakeView";
import { FilesView } from "./components/FilesView/FilesView";
import { MarkdownContent } from "./components/MarkdownContent";
import { NoteBlock } from "./components/NoteBlock/NoteBlock";
import { PageChatContent, PageChatStatus } from "./components/PageChat/PageChat";
import { PhaseExamCreateView } from "./components/PhaseExamCreateView/PhaseExamCreateView";
import { SettingsView } from "./components/SettingsView/SettingsView";
import { WrongBookView } from "./components/WrongBookView/WrongBookView";
import { useDocumentPolling } from "./hooks/useDocumentPolling";
import { useNoteBlockInteraction } from "./hooks/useNoteBlockInteraction";
import { usePdfSizing } from "./hooks/usePdfSizing";
import type {
  ChatMessageItem,
  DocumentItem,
  DocumentStatusResponse,
  ExamAttemptResult,
  ExamItem,
  ExamQuestionForTaking,
  LLMConfigResponse,
  LLMConfigUpdatePayload,
  PageItem,
  PhaseExamItem,
  WrongQuestionItem,
} from "./types/api";
const ReaderView = lazy(() =>
  import("./components/ReaderView/ReaderView").then((module) => ({ default: module.ReaderView })),
);

import type {
  DocumentActionState,
  HealthState,
  LLMConfigState,
  LoadedPdfPage,
  NoteBlockLayout,
  PendingChatAttachment,
  PdfPageNaturalSize,
  ReaderRightSidebar,
  ReaderState,
  UploadState,
} from "./types/ui";

const MIN_THUMBNAIL_SIDEBAR_WIDTH = 28;
const MIN_COURSE_SUMMARY_SIDEBAR_WIDTH = 220;
const THUMBNAIL_RESIZER_WIDTH = 12;
const COURSE_SUMMARY_RESIZER_WIDTH = 12;
const PDF_READER_COLUMN_GAP = 16;
const MIN_PDF_PAGE_STAGE_WIDTH = 120;
const MIN_NOTE_BLOCK_WIDTH = 120;
const MIN_NOTE_BLOCK_HEIGHT = 80;
const DOCUMENT_STATUS_POLL_INTERVAL_MS = 2000;
const PAGE_CHAT_MAX_ATTACHMENTS = 4;
const FILES_ROUTE = "/";
const SETTINGS_ROUTE = "/settings";
const READER_ROUTE_TEMPLATE = "/documents/:documentId/read";
const EXAM_TAKE_ROUTE_TEMPLATE = "/exams/:examId/take";
const EXAM_RESULT_ROUTE_TEMPLATE = "/exams/:examId/attempts/:attemptId/result";
const WRONG_BOOK_ROUTE = "/wrong-book";
const PHASE_EXAM_CREATE_ROUTE = "/phase-exams/create";

function buildReaderPath(documentId: string, pageNumber: number) {
  // 文档 ID 放进 URL path 前需要编码，避免特殊字符破坏路由结构。
  const safePageNumber = Math.max(1, pageNumber);
  return `/documents/${encodeURIComponent(documentId)}/read?page=${safePageNumber}`;
}

function decodeRouteSegment(value: string) {
  // URL path 可能包含损坏的百分号编码；解析失败时返回 null，让上层按未知路由处理。
  try {
    return decodeURIComponent(value);
  } catch {
    return null;
  }
}

function parsePositiveInteger(value: string | null) {
  // query string 中的 page 必须是从 1 开始的整数；非法值交给调用方修正为第一页。
  if (value === null) {
    return null;
  }

  const parsedValue = Number(value);
  if (!Number.isInteger(parsedValue) || parsedValue < 1) {
    return null;
  }

  return parsedValue;
}

function App() {
  const location = useLocation();
  const navigate = useNavigate();
  const readerRouteMatch = useMatch(READER_ROUTE_TEMPLATE);
  const [searchParams] = useSearchParams();
  const routeDocumentId = readerRouteMatch?.params.documentId
    ? decodeRouteSegment(readerRouteMatch.params.documentId)
    : null;
  const examTakeRouteMatch = useMatch(EXAM_TAKE_ROUTE_TEMPLATE);
  const examResultRouteMatch = useMatch(EXAM_RESULT_ROUTE_TEMPLATE);
  const wrongBookRouteMatch = useMatch(WRONG_BOOK_ROUTE);
  const phaseExamCreateRouteMatch = useMatch(PHASE_EXAM_CREATE_ROUTE);
  const routeExamId =
    examTakeRouteMatch?.params.examId ?? examResultRouteMatch?.params.examId ?? null;
  const routeAttemptId = examResultRouteMatch?.params.attemptId ?? null;

  const isReaderRoute = routeDocumentId !== null;
  const isExamTakeRoute = examTakeRouteMatch !== null;
  const isExamResultRoute = examResultRouteMatch !== null;
  const isWrongBookRoute = wrongBookRouteMatch !== null;
  const isPhaseExamCreateRoute = phaseExamCreateRouteMatch !== null;
  const isSettingsRoute = location.pathname === SETTINGS_ROUTE;
  const isKnownRoute =
    location.pathname === FILES_ROUTE ||
    isSettingsRoute ||
    isReaderRoute ||
    isExamTakeRoute ||
    isExamResultRoute ||
    isWrongBookRoute ||
    isPhaseExamCreateRoute;
  const visibleView = isSettingsRoute ? "settings" : "files";
  const requestedPdfPage = parsePositiveInteger(searchParams.get("page")) ?? 1;

  // connectionState 记录前端连接 FastAPI 后端的状态，用于顶部提示。
  const [connectionState, setConnectionState] = useState<HealthState>("checking");
  const [message, setMessage] = useState("正在检查后端连接...");

  // 文件上传相关状态只属于文件页，刷新阅读路由时不会依赖这些临时值。
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [uploadState, setUploadState] = useState<UploadState>("idle");
  const [uploadMessage, setUploadMessage] = useState("请选择一个 PDF/PPT/PPTX slides 文件。");
  const [uploadedDocumentId, setUploadedDocumentId] = useState<string | null>(null);

  // documents 是后端数据库中的文档列表；hasLoadedDocuments 用来区分“还没加载完”和“确实不存在”。
  const [documents, setDocuments] = useState<DocumentItem[]>([]);
  const [hasLoadedDocuments, setHasLoadedDocuments] = useState(false);
  const [documentsMessage, setDocumentsMessage] = useState("正在加载已上传文档...");
  const [documentStatusById, setDocumentStatusById] = useState<
    Record<string, DocumentStatusResponse>
  >({});
  const [documentStatusMessage, setDocumentStatusMessage] = useState("");

  // activeReaderDocument 是当前阅读器打开的文档；路由刷新后会从 URL 和文档列表恢复。
  const [activeReaderDocument, setActiveReaderDocument] = useState<DocumentItem | null>(null);
  const [isCourseSummaryPanelOpen, setIsCourseSummaryPanelOpen] = useState(false);
  const [readerRightSidebar, setReaderRightSidebar] = useState<ReaderRightSidebar>("none");
  const [isReaderTopbarCollapsed, setIsReaderTopbarCollapsed] = useState(false);
  const [isReaderChatCollapsed, setIsReaderChatCollapsed] = useState(true);
  const [isReaderNoteBlockCollapsed, setIsReaderNoteBlockCollapsed] = useState(false);
  const [readerState, setReaderState] = useState<ReaderState>("idle");
  const [readerMessage, setReaderMessage] = useState("");
  const [currentPdfPage, setCurrentPdfPage] = useState(1);
  const [totalPdfPages, setTotalPdfPages] = useState(0);
  const [isEditingPdfPage, setIsEditingPdfPage] = useState(false);
  const [pdfPageInputValue, setPdfPageInputValue] = useState("1");
  const [pdfPageNaturalSize, setPdfPageNaturalSize] = useState<PdfPageNaturalSize | null>(null);
  const pdfPageInputRef = useRef<HTMLInputElement | null>(null);

  // 文档重命名、删除和重新生成操作共用一组状态，避免重复点击同一文档的操作按钮。
  const [editingDocumentId, setEditingDocumentId] = useState<string | null>(null);
  const [editingTitle, setEditingTitle] = useState("");
  const [documentActionState, setDocumentActionState] = useState<DocumentActionState>(null);
  const [documentActionMessage, setDocumentActionMessage] = useState("");

  // LLM 配置状态由设置页展示；这些值来自后端配置接口，不从 URL 保存。
  const [llmConfigState, setLlmConfigState] = useState<LLMConfigState>("idle");
  const [llmBaseUrl, setLlmBaseUrl] = useState("");
  const [llmApiKey, setLlmApiKey] = useState("");
  const [llmApiKeyConfigured, setLlmApiKeyConfigured] = useState(false);
  const [llmApiKeyPreview, setLlmApiKeyPreview] = useState("");
  const [shouldClearLlmApiKey, setShouldClearLlmApiKey] = useState(false);
  const [llmModel, setLlmModel] = useState("");
  const [llmTimeoutSeconds, setLlmTimeoutSeconds] = useState("60");
  const [courseSummaryPrompt, setCourseSummaryPrompt] = useState("");
  const [lectureNotesPrompt, setLectureNotesPrompt] = useState("");
  const [pageChatPrompt, setPageChatPrompt] = useState("");
  const [examGenerationPrompt, setExamGenerationPrompt] = useState("");
  const [isCourseSummaryPromptExpanded, setIsCourseSummaryPromptExpanded] = useState(false);
  const [isLectureNotesPromptExpanded, setIsLectureNotesPromptExpanded] = useState(false);
  const [isPageChatPromptExpanded, setIsPageChatPromptExpanded] = useState(false);
  const [isExamGenerationPromptExpanded, setIsExamGenerationPromptExpanded] = useState(false);
  const [llmConfigMessage, setLlmConfigMessage] = useState("正在加载 LLM 配置...");
  const [llmTestPrompt, setLlmTestPrompt] = useState("请用一句中文回复：LLM 配置测试成功。");
  const [llmTestAnswer, setLlmTestAnswer] = useState("");
  const courseSummaryPromptTextareaRef = useRef<HTMLTextAreaElement | null>(null);
  const lectureNotesPromptTextareaRef = useRef<HTMLTextAreaElement | null>(null);
  const pageChatPromptTextareaRef = useRef<HTMLTextAreaElement | null>(null);
  const examGenerationPromptTextareaRef = useRef<HTMLTextAreaElement | null>(null);

  // 试卷、错题本、阶段考试相关状态。
  const [examsByDocument, setExamsByDocument] = useState<Record<string, ExamItem[]>>({});
  const [examsLoadingByDocument, setExamsLoadingByDocument] = useState<Record<string, boolean>>({});
  const [currentExam, setCurrentExam] = useState<ExamItem | null>(null);
  const [currentExamQuestionsWithoutAnswer, setCurrentExamQuestionsWithoutAnswer] = useState<
    ExamQuestionForTaking[]
  >([]);
  const [currentExamResult, setCurrentExamResult] = useState<ExamAttemptResult | null>(null);
  const [examTakeLoading, setExamTakeLoading] = useState(false);
  const [wrongQuestions, setWrongQuestions] = useState<WrongQuestionItem[]>([]);
  const [wrongQuestionsLoading, setWrongQuestionsLoading] = useState(false);
  const [phaseExamCreating, setPhaseExamCreating] = useState(false);
  const [phaseExams, setPhaseExams] = useState<PhaseExamItem[]>([]);
  const [phaseExamsLoading, setPhaseExamsLoading] = useState(false);

  // 页面讲稿、文档展开状态和当前页问答都按 document_id 或 page_id 保存，方便阅读器和文件页复用。
  const [expandedLectureNotesDocumentId, setExpandedLectureNotesDocumentId] = useState<
    string | null
  >(null);
  const [expandedDocumentIds, setExpandedDocumentIds] = useState<Record<string, boolean>>({});
  const [pagesByDocument, setPagesByDocument] = useState<Record<string, PageItem[]>>({});
  const [pagesMessageByDocument, setPagesMessageByDocument] = useState<Record<string, string>>({});
  const [pageQuestionInput, setPageQuestionInput] = useState("");
  const [pendingPageChatAttachments, setPendingPageChatAttachments] = useState<
    PendingChatAttachment[]
  >([]);
  const pendingPageChatAttachmentsRef = useRef<PendingChatAttachment[]>([]);
  const [submittingPageChatId, setSubmittingPageChatId] = useState<string | null>(null);
  const pageChatAbortControllerRef = useRef<AbortController | null>(null);
  const pageChatStreamContextRef = useRef<{
    documentId: string;
    pageId: string;
    assistantMessageId: string;
  } | null>(null);
  const [pageChatMessage, setPageChatMessage] = useState("");

  const {
    readerViewportWidth,
    readerWorkspaceSize,
    thumbnailSidebarWidth,
    courseSummarySidebarWidth,
    thumbnailRenderWidth,
    isResizingThumbnailSidebar,
    isResizingCourseSummarySidebar,
    readerViewportRef,
    readerWorkspaceRef,
    readerContentRef,
    setReaderViewportWidth,
    setReaderWorkspaceSize,
    startResizingThumbnailSidebar,
    startResizingCourseSummarySidebar,
  } = usePdfSizing({
    isReaderActive: Boolean(activeReaderDocument && isReaderRoute),
    readerRightSidebar,
    isReaderTopbarCollapsed,
    isReaderChatCollapsed,
    isCourseSummaryPanelOpen,
    minThumbnailSidebarWidth: MIN_THUMBNAIL_SIDEBAR_WIDTH,
    minCourseSummarySidebarWidth: MIN_COURSE_SUMMARY_SIDEBAR_WIDTH,
    thumbnailResizerWidth: THUMBNAIL_RESIZER_WIDTH,
    courseSummaryResizerWidth: COURSE_SUMMARY_RESIZER_WIDTH,
    pdfReaderColumnGap: PDF_READER_COLUMN_GAP,
  });

  useDocumentPolling({
    documents,
    documentStatusById,
    intervalMs: DOCUMENT_STATUS_POLL_INTERVAL_MS,
    loadDocumentStatus,
  });

  const {
    resolveNoteBlockLayout,
    startNoteBlockDrag,
    startNoteBlockResize,
  } = useNoteBlockInteraction({
    minWidth: MIN_NOTE_BLOCK_WIDTH,
    minHeight: MIN_NOTE_BLOCK_HEIGHT,
    saveNoteBlockPosition,
  });

  useEffect(() => {
    // 应用启动时先检查后端，再加载 LLM 配置和文档列表。
    let isCancelled = false;

    async function initializeApplication() {
      try {
        const data = await checkHealth();

        if (isCancelled) {
          return;
        }

        if (data.status !== "ok") {
          throw new Error("后端返回了非正常状态。");
        }

        setConnectionState("success");
        setMessage(`后端连接成功：${data.service}`);
        await Promise.all([loadLlmConfig(), loadDocuments()]);
      } catch {
        if (isCancelled) {
          return;
        }

        setConnectionState("error");
        setMessage("后端连接失败，请确认 FastAPI 服务已经启动。");
      }
    }

    void initializeApplication();

    return () => {
      isCancelled = true;
    };
  }, []);

  useEffect(() => {
    // BrowserRouter 直接使用真实路径；非法或缺失 page 参数需要规范化，避免刷新后状态不确定。
    if (!isReaderRoute || !routeDocumentId) {
      return;
    }

    const rawPageValue = searchParams.get("page");
    const parsedPage = parsePositiveInteger(rawPageValue);
    if (parsedPage === null || rawPageValue !== String(requestedPdfPage)) {
      navigate(buildReaderPath(routeDocumentId, requestedPdfPage), { replace: true });
    }
  }, [isReaderRoute, navigate, requestedPdfPage, routeDocumentId, searchParams]);

  useEffect(() => {
    // 文档列表加载完成后，用 URL 中的 documentId 恢复阅读器。
    if (!isReaderRoute || !routeDocumentId || !hasLoadedDocuments) {
      return;
    }

    const routeDocument = documents.find((document) => document.document_id === routeDocumentId);
    if (!routeDocument) {
      resetReaderState();
      setDocumentsMessage("文档不存在或已被删除，已返回文件页。");
      setDocumentActionMessage("文档不存在或已被删除，已返回文件页。");
      navigate(FILES_ROUTE, { replace: true });
      return;
    }

    if (activeReaderDocument?.document_id !== routeDocument.document_id) {
      prepareReaderForDocument(routeDocument, requestedPdfPage);
      void loadDocumentStatus(routeDocument.document_id);
      void loadDocumentPages(routeDocument.document_id);
      return;
    }

    // 文档被重命名或状态更新后，保持阅读器引用同步为最新列表记录。
    setActiveReaderDocument(routeDocument);
  }, [
    activeReaderDocument?.document_id,
    documents,
    hasLoadedDocuments,
    isReaderRoute,
    navigate,
    requestedPdfPage,
    routeDocumentId,
  ]);

  useEffect(() => {
    // URL 是阅读器页码的来源；浏览器前进/后退或手动改 URL 时，同步到本地状态。
    if (!isReaderRoute || !routeDocumentId || !activeReaderDocument) {
      return;
    }

    const boundedPage =
      totalPdfPages > 0 ? Math.min(requestedPdfPage, totalPdfPages) : requestedPdfPage;

    if (totalPdfPages > 0 && boundedPage !== requestedPdfPage) {
      navigate(buildReaderPath(routeDocumentId, boundedPage), { replace: true });
      return;
    }

    if (currentPdfPage !== boundedPage) {
      setCurrentPdfPage(boundedPage);
      setPdfPageInputValue(String(boundedPage));
      setIsEditingPdfPage(false);
    }
  }, [
    activeReaderDocument,
    currentPdfPage,
    isReaderRoute,
    navigate,
    requestedPdfPage,
    routeDocumentId,
    totalPdfPages,
  ]);

  useEffect(() => {
    // 切换文档或页码后，当前页问答输入框和 PDF 原始尺寸都需要重新计算。
    stopPageQuestion("已切换页面，已中断上一轮回答。");
    setPageQuestionInput("");
    setPageChatMessage("");
    setPdfPageNaturalSize(null);
    clearPendingPageChatAttachments();
  }, [activeReaderDocument?.document_id, currentPdfPage]);

  useEffect(() => {
    // ref 保存最新附件列表，让卸载清理不依赖某一次渲染时的旧状态。
    pendingPageChatAttachmentsRef.current = pendingPageChatAttachments;
  }, [pendingPageChatAttachments]);

  useEffect(() => {
    // 组件卸载时释放所有 object URL，避免浏览器一直占用本地图片预览内存。
    return () => {
      pageChatAbortControllerRef.current?.abort();
      pendingPageChatAttachmentsRef.current.forEach((attachment) => {
        URL.revokeObjectURL(attachment.previewUrl);
      });
    };
  }, []);

  useEffect(() => {
    // 页码输入框进入编辑状态后自动聚焦，并选中旧页码方便直接覆盖。
    if (!isEditingPdfPage) {
      return;
    }

    pdfPageInputRef.current?.focus();
    pdfPageInputRef.current?.select();
  }, [isEditingPdfPage]);

  useEffect(() => {
    // prompt 展开后根据内容高度扩展 textarea，避免内部滚动条影响编辑。
    if (!isCourseSummaryPromptExpanded) {
      return;
    }

    resizePromptTextarea(courseSummaryPromptTextareaRef.current);
  }, [courseSummaryPrompt, isCourseSummaryPromptExpanded]);

  useEffect(() => {
    // 文件页可见且文档列表加载完成后，自动加载每份文档的试卷列表和阶段考试列表。
    if (visibleView !== "files" || !hasLoadedDocuments) {
      return;
    }

    documents.forEach((document) => {
      void loadDocumentExams(document.document_id);
    });
    void loadPhaseExams();
  }, [visibleView, hasLoadedDocuments, documents]);

  useEffect(() => {
    // 进入错题本页面时自动加载错题数据。
    if (isWrongBookRoute) {
      void loadWrongQuestions();
    }
  }, [isWrongBookRoute]);

  useEffect(() => {
    // 直接访问或刷新答题页时，根据 URL 中的 examId 重新加载无答案题目。
    if (isExamTakeRoute && routeExamId) {
      void loadExamForTaking(routeExamId);
    }
  }, [isExamTakeRoute, routeExamId]);

  useEffect(() => {
    // 直接访问或刷新结果页时，根据 URL 中的 examId 和 attemptId 重新加载判分结果。
    if (isExamResultRoute && routeExamId && routeAttemptId) {
      void loadExamAttemptResult(routeExamId, routeAttemptId);
    }
  }, [isExamResultRoute, routeExamId, routeAttemptId]);

  useEffect(() => {
    if (!isLectureNotesPromptExpanded) {
      return;
    }

    resizePromptTextarea(lectureNotesPromptTextareaRef.current);
  }, [lectureNotesPrompt, isLectureNotesPromptExpanded]);

  useEffect(() => {
    if (!isPageChatPromptExpanded) {
      return;
    }

    resizePromptTextarea(pageChatPromptTextareaRef.current);
  }, [pageChatPrompt, isPageChatPromptExpanded]);

  useEffect(() => {
    if (!isExamGenerationPromptExpanded) {
      return;
    }

    resizePromptTextarea(examGenerationPromptTextareaRef.current);
  }, [examGenerationPrompt, isExamGenerationPromptExpanded]);

  function resizePromptTextarea(textarea: HTMLTextAreaElement | null) {
    if (textarea === null) {
      return;
    }

    textarea.style.height = "auto";
    textarea.style.height = `${textarea.scrollHeight}px`;
  }

  function applyLlmConfig(data: LLMConfigResponse) {
    // 后端不会返回 API Key 明文，只返回是否已配置和掩码预览。
    setLlmBaseUrl(data.base_url);
    setLlmModel(data.model);
    setLlmTimeoutSeconds(String(data.timeout_seconds));
    setCourseSummaryPrompt(data.course_summary_prompt);
    setLectureNotesPrompt(data.lecture_notes_prompt);
    setPageChatPrompt(data.page_chat_prompt);
    setExamGenerationPrompt(data.exam_generation_prompt);
    setLlmApiKey("");
    setShouldClearLlmApiKey(false);
    setLlmApiKeyConfigured(data.api_key_configured);
    setLlmApiKeyPreview(data.api_key_preview);
  }

  async function loadLlmConfig() {
    setLlmConfigState("loading");
    setLlmConfigMessage("正在加载 LLM 配置...");

    try {
      const data = await readLlmConfig();

      applyLlmConfig(data);
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
    const nextExamGenerationPrompt = examGenerationPrompt.trim();

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

    if (!nextExamGenerationPrompt) {
      setLlmConfigState("error");
      setLlmConfigMessage("试卷生成 prompt 不能为空。");
      return;
    }

    const payload: LLMConfigUpdatePayload = {
      base_url: nextBaseUrl,
      model: nextModel,
      timeout_seconds: nextTimeoutSeconds,
      course_summary_prompt: nextCourseSummaryPrompt,
      lecture_notes_prompt: nextLectureNotesPrompt,
      page_chat_prompt: nextPageChatPrompt,
      exam_generation_prompt: nextExamGenerationPrompt,
    };

    // 不填写新密钥时不发送 api_key 字段，后端会保留旧密钥；勾选清空时发送空字符串。
    if (shouldClearLlmApiKey) {
      payload.api_key = "";
    } else if (llmApiKey.trim()) {
      payload.api_key = llmApiKey.trim();
    }

    setLlmConfigState("saving");
    setLlmConfigMessage("正在保存 LLM 配置...");
    setLlmTestAnswer("");

    try {
      const data = await saveLlmConfigRequest(payload);

      applyLlmConfig(data);
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
      const data = await testLlmConfigRequest(prompt);

      setLlmConfigState("success");
      setLlmConfigMessage("LLM 测试请求成功。");
      setLlmTestAnswer(data.answer);
    } catch (error) {
      setLlmConfigState("error");
      setLlmConfigMessage(error instanceof Error ? error.message : "测试失败，请稍后重试。");
    }
  }

  async function loadDocuments() {
    try {
      const data = await listDocuments();

      setDocuments(data);
      setHasLoadedDocuments(true);
      setDocumentsMessage(data.length > 0 ? "" : "还没有上传过 slides 文件。");
      data.forEach((document) => {
        void loadDocumentStatus(document.document_id);
      });
    } catch (error) {
      setHasLoadedDocuments(false);
      setDocuments([]);
      setDocumentsMessage(
        error instanceof Error ? error.message : "文档列表加载失败，请稍后重试。",
      );
    }
  }

  async function loadDocumentStatus(documentId: string) {
    try {
      const data = await readDocumentStatus(documentId);

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

  function mergeDocumentStatus(statusData: DocumentStatusResponse) {
    // 状态接口比文档列表更及时；轮询时用它覆盖列表中的状态字段。
    setDocumentStatusById((currentStatus) => {
      const previousStatus = currentStatus[statusData.document_id];
      // 如果 should_poll 等核心字段没有变化，复用旧对象避免触发不必要的重渲染。
      if (
        previousStatus &&
        previousStatus.status === statusData.status &&
        previousStatus.course_summary_status === statusData.course_summary_status &&
        previousStatus.lecture_notes_ready_count === statusData.lecture_notes_ready_count &&
        previousStatus.lecture_notes_failed_count === statusData.lecture_notes_failed_count &&
        previousStatus.lecture_notes_processing_count === statusData.lecture_notes_processing_count &&
        previousStatus.lecture_notes_pending_count === statusData.lecture_notes_pending_count &&
        previousStatus.lecture_notes_paused === statusData.lecture_notes_paused &&
        previousStatus.should_poll === statusData.should_poll &&
        previousStatus.error_message === statusData.error_message &&
        previousStatus.course_summary_error === statusData.course_summary_error
      ) {
        return currentStatus;
      }

      return {
        ...currentStatus,
        [statusData.document_id]: statusData,
      };
    });
    setDocuments((currentDocuments) => {
      const documentIndex = currentDocuments.findIndex(
        (document) => document.document_id === statusData.document_id,
      );
      if (documentIndex === -1) {
        return currentDocuments;
      }

      const document = currentDocuments[documentIndex];
      const nextDocument = {
        ...document,
        status: statusData.status,
        error_message: statusData.error_message,
        page_count: statusData.total_pages,
        course_summary_status: statusData.course_summary_status,
        course_summary_error: statusData.course_summary_error,
        lecture_notes_paused: statusData.lecture_notes_paused,
      };

      // 只有真正发生变化时才创建新数组，避免轮询稳定后仍反复重渲染阅读器。
      if (
        document.status === nextDocument.status &&
        document.error_message === nextDocument.error_message &&
        document.page_count === nextDocument.page_count &&
        document.course_summary_status === nextDocument.course_summary_status &&
        document.course_summary_error === nextDocument.course_summary_error &&
        document.lecture_notes_paused === nextDocument.lecture_notes_paused
      ) {
        return currentDocuments;
      }

      const nextDocuments = [...currentDocuments];
      nextDocuments[documentIndex] = nextDocument;
      return nextDocuments;
    });
    setPagesByDocument((currentPages) => {
      const existingPages = currentPages[statusData.document_id];
      if (!existingPages) {
        return currentPages;
      }

      let hasPageChanges = false;
      const nextPages = existingPages.map((page) => {
        const statusPage = statusData.pages.find(
          (candidate) => candidate.page_id === page.page_id,
        );

        if (!statusPage) {
          return page;
        }

        if (
          page.status === statusPage.status &&
          page.error_message === statusPage.error_message &&
          page.lecture_notes_status === statusPage.lecture_notes_status &&
          page.lecture_notes_error === statusPage.lecture_notes_error
        ) {
          return page;
        }

        hasPageChanges = true;
        return {
          ...page,
          status: statusPage.status,
          error_message: statusPage.error_message,
          lecture_notes_status: statusPage.lecture_notes_status,
          lecture_notes_error: statusPage.lecture_notes_error,
        };
      });

      if (!hasPageChanges) {
        return currentPages;
      }

      return {
        ...currentPages,
        [statusData.document_id]: nextPages,
      };
    });
  }

  function prepareReaderForDocument(document: DocumentItem, pageNumber: number) {
    // 打开新文档时重置阅读器 UI，但保留 URL 中请求的页码，等待 PDF 总页数加载后再做上界修正。
    const nextPageNumber = Math.max(1, pageNumber);

    setActiveReaderDocument(document);
    setIsCourseSummaryPanelOpen(false);
    // 默认把本页讲稿放在右侧栏，并折叠底部会话，优先留出 PDF 阅读空间。
    setReaderRightSidebar("note");
    setIsReaderTopbarCollapsed(false);
    setIsReaderChatCollapsed(true);
    setIsReaderNoteBlockCollapsed(false);
    setCurrentPdfPage(nextPageNumber);
    setPdfPageInputValue(String(nextPageNumber));
    setIsEditingPdfPage(false);
    setTotalPdfPages(0);
    setPdfPageNaturalSize(null);
    setReaderViewportWidth(0);
    setReaderWorkspaceSize({ width: 0, height: 0 });
    setReaderState("loading");
    setReaderMessage("正在加载 slides PDF 文件...");
  }

  function resetReaderState() {
    // 清空阅读器内部状态，但不主动改 URL；调用方决定是否跳转。
    setActiveReaderDocument(null);
    setIsCourseSummaryPanelOpen(false);
    setReaderRightSidebar("none");
    setIsReaderTopbarCollapsed(false);
    setIsReaderChatCollapsed(true);
    setIsReaderNoteBlockCollapsed(false);
    setCurrentPdfPage(1);
    setPdfPageInputValue("1");
    setIsEditingPdfPage(false);
    setTotalPdfPages(0);
    setPdfPageNaturalSize(null);
    setReaderViewportWidth(0);
    setReaderWorkspaceSize({ width: 0, height: 0 });
    setReaderState("idle");
    setReaderMessage("");
  }

  function openReader(document: DocumentItem) {
    prepareReaderForDocument(document, 1);
    navigate(buildReaderPath(document.document_id, 1));
    void loadDocumentPages(document.document_id);
  }

  function closeReader() {
    // 返回文件页时保留 activeReaderDocument，方便用户稍后点击“返回阅读”。
    navigate(FILES_ROUTE);
  }

  function openSettings() {
    navigate(SETTINGS_ROUTE);
  }

  function returnToReader() {
    if (!activeReaderDocument) {
      return;
    }

    navigate(buildReaderPath(activeReaderDocument.document_id, currentPdfPage));
  }

  function clearActiveDocument() {
    resetReaderState();
    navigate(FILES_ROUTE);
  }

  function toggleCourseSummarySidebar() {
    setIsReaderChatCollapsed(true);
    setReaderRightSidebar((currentSidebar) => {
      const nextSidebar: ReaderRightSidebar = currentSidebar === "summary" ? "none" : "summary";
      setIsCourseSummaryPanelOpen(nextSidebar === "summary");
      return nextSidebar;
    });
  }

  function openChatSidebar() {
    setReaderRightSidebar("chat");
    setIsCourseSummaryPanelOpen(false);
    setIsReaderChatCollapsed(true);
  }

  function toggleNoteSidebar() {
    setIsReaderChatCollapsed(true);
    setReaderRightSidebar((currentSidebar) => (currentSidebar === "note" ? "none" : "note"));
    setIsCourseSummaryPanelOpen(false);
  }

  function closeRightSidebar() {
    if (readerRightSidebar === "chat") {
      setIsReaderChatCollapsed(true);
    }

    setReaderRightSidebar("none");
    setIsCourseSummaryPanelOpen(false);
  }

  function openCurrentNoteBlockInSidebar(noteBlockId: string) {
    // 移入右栏只依赖 readerRightSidebar 临时折叠，不写入手动折叠状态。
    void noteBlockId;
    setReaderRightSidebar("note");
    setIsCourseSummaryPanelOpen(false);
    setIsReaderChatCollapsed(true);
  }

  function expandCurrentNoteBlock(noteBlockId: string) {
    void noteBlockId;
    setIsReaderNoteBlockCollapsed(false);
    if (readerRightSidebar === "note") {
      setReaderRightSidebar("none");
    }
  }

  function turnPdfPage(step: -1 | 1) {
    const maxPage = totalPdfPages > 0 ? totalPdfPages : currentPdfPage;
    goToPdfPage(currentPdfPage + step, true, maxPage);
  }

  function handlePdfLoadSuccess({ numPages }: { numPages: number }) {
    // PDF 成功加载后只修正页码边界，不强制回第一页，避免刷新后丢失当前页。
    const boundedPage = Math.min(Math.max(requestedPdfPage, 1), numPages);

    setTotalPdfPages(numPages);
    setCurrentPdfPage(boundedPage);
    setPdfPageInputValue(String(boundedPage));
    setIsEditingPdfPage(false);
    setReaderState("ready");
    setReaderMessage("");

    if (isReaderRoute && routeDocumentId && boundedPage !== requestedPdfPage) {
      navigate(buildReaderPath(routeDocumentId, boundedPage), { replace: true });
    }
  }

  function handlePdfLoadError(error: Error) {
    setReaderState("error");
    setReaderMessage(`PDF 加载失败：${error.message}`);
  }

  function handlePdfPageRenderError(error: Error) {
    setReaderState("error");
    setReaderMessage(`当前页渲染失败：${error.message}`);
  }

  function handlePdfPageLoadSuccess(page: LoadedPdfPage) {
    setPdfPageNaturalSize({
      width: page.originalWidth,
      height: page.originalHeight,
    });
  }

  function goToPdfPage(pageNumber: number, shouldReplaceHistory = true, fallbackMaxPage = totalPdfPages) {
    const maxPage = fallbackMaxPage > 0 ? fallbackMaxPage : pageNumber;
    const nextPage = Math.min(Math.max(pageNumber, 1), maxPage);

    setCurrentPdfPage(nextPage);
    setPdfPageInputValue(String(nextPage));
    setIsEditingPdfPage(false);

    if (isReaderRoute && activeReaderDocument) {
      navigate(buildReaderPath(activeReaderDocument.document_id, nextPage), {
        replace: shouldReplaceHistory,
      });
    }
  }

  function startEditingPdfPage() {
    if (readerState !== "ready" || totalPdfPages <= 0) {
      return;
    }

    setPdfPageInputValue(String(currentPdfPage));
    setIsEditingPdfPage(true);
  }

  function submitPdfPageInput() {
    const parsedPage = Number(pdfPageInputValue);

    if (!Number.isInteger(parsedPage)) {
      setPdfPageInputValue(String(currentPdfPage));
      setIsEditingPdfPage(false);
      return;
    }

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

  function handleFileChange(event: React.ChangeEvent<HTMLInputElement>) {
    const nextFile = event.target.files?.[0] ?? null;

    setUploadedDocumentId(null);

    if (!nextFile) {
      setSelectedFile(null);
      setUploadState("idle");
      setUploadMessage("请选择一个 PDF/PPT/PPTX slides 文件。");
      return;
    }

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

    setUploadState("uploading");
    setUploadMessage("正在上传 slides 文件...");
    setUploadedDocumentId(null);

    try {
      const data = await uploadDocument(selectedFile);

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
    setEditingDocumentId(document.document_id);
    setEditingTitle(document.title);
    setDocumentActionMessage("");
  }

  function cancelRename() {
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
      await renameDocument(documentId, nextTitle);

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
    const confirmed = window.confirm(
      `确定要删除“${document.title}”吗？这会同时删除数据库记录、页面记录和本地 PDF 文件。`,
    );

    if (!confirmed) {
      return;
    }

    setDocumentActionState({ documentId: document.document_id, action: "deleting" });
    setDocumentActionMessage("");

    try {
      await deleteDocumentRequest(document.document_id);

      if (editingDocumentId === document.document_id) {
        cancelRename();
      }

      if (activeReaderDocument?.document_id === document.document_id) {
        resetReaderState();
        navigate(FILES_ROUTE, { replace: true });
      }

      setDocumentStatusById((current) => {
        const next = { ...current };
        delete next[document.document_id];
        return next;
      });
      setExpandedDocumentIds((current) => {
        const next = { ...current };
        delete next[document.document_id];
        return next;
      });
      setPagesByDocument((current) => {
        const next = { ...current };
        delete next[document.document_id];
        return next;
      });
      setPagesMessageByDocument((current) => {
        const next = { ...current };
        delete next[document.document_id];
        return next;
      });
      setExamsByDocument((current) => {
        const next = { ...current };
        delete next[document.document_id];
        return next;
      });
      setExamsLoadingByDocument((current) => {
        const next = { ...current };
        delete next[document.document_id];
        return next;
      });
      if (expandedLectureNotesDocumentId === document.document_id) {
        setExpandedLectureNotesDocumentId(null);
      }

      setDocumentActionMessage("文档已删除。");
      await loadDocuments();
      await loadPhaseExams();
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
      await regenerateCourseSummaryRequest(document.document_id);

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
      const data = await listDocumentPages(documentId);

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

  function clearPendingPageChatAttachments() {
    // 待发送图片的预览 URL 是浏览器临时资源，清空状态前必须主动释放。
    setPendingPageChatAttachments((currentAttachments) => {
      currentAttachments.forEach((attachment) => {
        URL.revokeObjectURL(attachment.previewUrl);
      });
      return [];
    });
  }

  function addPendingPageChatAttachments(files: File[]) {
    // PageChat 组件已经做了图片类型过滤；这里主要负责数量限制和预览 URL 创建。
    if (files.length === 0) {
      return;
    }

    setPendingPageChatAttachments((currentAttachments) => {
      const availableSlots = PAGE_CHAT_MAX_ATTACHMENTS - currentAttachments.length;
      if (availableSlots <= 0) {
        setPageChatMessage(`每次最多只能上传 ${PAGE_CHAT_MAX_ATTACHMENTS} 张图片。`);
        return currentAttachments;
      }

      const acceptedFiles = files.slice(0, availableSlots);
      const nextAttachments = acceptedFiles.map((file) => ({
        id: `${crypto.randomUUID()}-${file.name}`,
        file,
        previewUrl: URL.createObjectURL(file),
      }));

      if (files.length > acceptedFiles.length) {
        setPageChatMessage(
          `每次最多只能上传 ${PAGE_CHAT_MAX_ATTACHMENTS} 张图片，已只保留前 ${availableSlots} 张。`,
        );
      } else {
        setPageChatMessage("");
      }

      return [...currentAttachments, ...nextAttachments];
    });
  }

  function removePendingPageChatAttachment(attachmentId: string) {
    setPendingPageChatAttachments((currentAttachments) => {
      const removedAttachment = currentAttachments.find((attachment) => attachment.id === attachmentId);
      if (removedAttachment) {
        URL.revokeObjectURL(removedAttachment.previewUrl);
      }

      return currentAttachments.filter((attachment) => attachment.id !== attachmentId);
    });
  }

  function updatePageChatMessages(
    documentId: string,
    pageId: string,
    resolveMessages: (messages: ChatMessageItem[]) => ChatMessageItem[],
  ) {
    // 所有聊天历史更新都集中到这里，避免流式增量更新时重复编写页面查找逻辑。
    setPagesByDocument((currentPages) => ({
      ...currentPages,
      [documentId]: (currentPages[documentId] ?? []).map((currentPage) =>
        currentPage.page_id === pageId
          ? { ...currentPage, chat_messages: resolveMessages(currentPage.chat_messages) }
          : currentPage,
      ),
    }));
  }

  function replacePageChatMessages(
    documentId: string,
    pageId: string,
    messages: ChatMessageItem[],
  ) {
    // done 事件返回的是后端完整历史，直接覆盖可以消除乐观更新产生的临时消息。
    updatePageChatMessages(documentId, pageId, () => messages);
  }

  function removeStreamingAssistantMessage(
    documentId: string,
    pageId: string,
    assistantMessageId: string,
  ) {
    // 用户中断或模型报错时，前端临时 assistant 消息不能继续留在历史列表中。
    updatePageChatMessages(documentId, pageId, (messages) =>
      messages.filter((message) => message.chat_message_id !== assistantMessageId),
    );
  }

  function stopPageQuestion(message = "回答已中断。") {
    const abortController = pageChatAbortControllerRef.current;
    const streamContext = pageChatStreamContextRef.current;

    // 没有正在进行的流式请求时不做任何状态变更，避免切页时误报中断。
    if (!abortController || !streamContext) {
      return;
    }

    abortController.abort();
    pageChatAbortControllerRef.current = null;
    pageChatStreamContextRef.current = null;
    setSubmittingPageChatId(null);
    removeStreamingAssistantMessage(
      streamContext.documentId,
      streamContext.pageId,
      streamContext.assistantMessageId,
    );
    setPageChatMessage(message);
  }

  async function submitPageQuestion(page: PageItem) {
    const question = pageQuestionInput.trim();

    if (!activeReaderDocument) {
      setPageChatMessage("需要先打开一份文档，才能进行当前页问答。");
      return;
    }

    if (submittingPageChatId === page.page_id) {
      stopPageQuestion();
      return;
    }

    if (!question) {
      setPageChatMessage("问题不能为空。");
      return;
    }

    const documentId = activeReaderDocument.document_id;
    const attachments = pendingPageChatAttachments.map((attachment) => attachment.file);
    const abortController = new AbortController();
    const assistantMessageId = `streaming-${crypto.randomUUID()}`;
    const now = new Date().toISOString();
    let hasCompletedStream = false;
    let streamErrorMessage = "";

    setSubmittingPageChatId(page.page_id);
    setPageChatMessage("正在连接 AI 老师...");
    pageChatAbortControllerRef.current = abortController;
    pageChatStreamContextRef.current = {
      documentId,
      pageId: page.page_id,
      assistantMessageId,
    };

    try {
      await submitPageChatStream(page.page_id, question, attachments, {
        signal: abortController.signal,
        onEvent(event) {
          if (event.type === "user_message") {
            // 后端发出 user_message 表示用户消息和附件已经持久化，可以清空输入区。
            const streamingAssistantMessage: ChatMessageItem = {
              chat_message_id: assistantMessageId,
              page_id: page.page_id,
              role: "assistant",
              content: "",
              attachments: [],
              created_at: now,
            };
            updatePageChatMessages(documentId, page.page_id, (messages) => [
              ...messages,
              event.message,
              streamingAssistantMessage,
            ]);
            setPageQuestionInput("");
            clearPendingPageChatAttachments();
            setPageChatMessage("AI 老师正在回答...");
            return;
          }

          if (event.type === "delta") {
            // 每个 delta 都是模型新生成的一段文本，追加到临时 assistant 消息中。
            updatePageChatMessages(documentId, page.page_id, (messages) =>
              messages.map((message) =>
                message.chat_message_id === assistantMessageId
                  ? { ...message, content: `${message.content}${event.content}` }
                  : message,
              ),
            );
            return;
          }

          if (event.type === "done") {
            // done 事件说明模型正常结束，后端已经保存 assistant 消息。
            hasCompletedStream = true;
            replacePageChatMessages(documentId, page.page_id, event.messages);
            setPageChatMessage("AI 老师已回答。");
            return;
          }

          if (event.type === "error") {
            // error 事件表示后端保留了用户消息，但没有保存 assistant 回答。
            streamErrorMessage = event.message;
            removeStreamingAssistantMessage(documentId, page.page_id, assistantMessageId);
            setPageChatMessage(event.message);
          }
        },
      });

      if (streamErrorMessage) {
        await loadDocumentPages(documentId);
        return;
      }

      if (!hasCompletedStream) {
        removeStreamingAssistantMessage(documentId, page.page_id, assistantMessageId);
        setPageChatMessage("流式回答提前结束，已刷新当前页问答历史。");
        await loadDocumentPages(documentId);
      }
    } catch (error) {
      if (error instanceof DOMException && error.name === "AbortError") {
        // AbortError 是用户主动中断或切页造成的正常结果，刷新历史以对齐后端已保存的 user 消息。
        const activeStreamContext = pageChatStreamContextRef.current;
        if (
          !activeStreamContext ||
          activeStreamContext.assistantMessageId === assistantMessageId
        ) {
          await loadDocumentPages(documentId);
        }
      } else {
        removeStreamingAssistantMessage(documentId, page.page_id, assistantMessageId);
        setPageChatMessage(error instanceof Error ? error.message : "当前页问答失败，请稍后重试。");
        await loadDocumentPages(documentId);
      }
    } finally {
      if (pageChatAbortControllerRef.current === abortController) {
        pageChatAbortControllerRef.current = null;
        pageChatStreamContextRef.current = null;
        setSubmittingPageChatId(null);
      }
    }
  }

  async function saveNoteBlockPosition(
    documentId: string,
    noteBlockId: string,
    nextPosition: NoteBlockLayout,
  ) {
    // 先做乐观更新，避免拖拽结束后文字块闪回旧位置。
    setPagesByDocument((currentPages) => ({
      ...currentPages,
      [documentId]: (currentPages[documentId] ?? []).map((page) =>
        page.note_block?.note_block_id === noteBlockId
          ? { ...page, note_block: { ...page.note_block, ...nextPosition } }
          : page,
      ),
    }));

    try {
      const updatedNoteBlock = await updateNoteBlockPosition(noteBlockId, nextPosition);

      setPagesByDocument((currentPages) => ({
        ...currentPages,
        [documentId]: (currentPages[documentId] ?? []).map((page) =>
          page.note_block?.note_block_id === updatedNoteBlock.note_block_id
            ? { ...page, note_block: updatedNoteBlock }
            : page,
        ),
      }));
      setReaderMessage("");
    } catch (error) {
      setReaderMessage(error instanceof Error ? error.message : "讲稿文字块位置保存失败，请稍后重试。");
    }
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
      await regenerateDocumentLectureNotesRequest(document.document_id);

      setDocumentActionMessage("所有页面已加入逐页讲稿待生成队列。");
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

  async function generateRemainingLectureNotes(document: DocumentItem) {
    setDocumentActionState({
      documentId: document.document_id,
      action: "generatingRemainingLectureNotes",
    });
    setDocumentActionMessage("");

    try {
      const result = await generateRemainingLectureNotesRequest(document.document_id);

      setDocumentActionMessage(`已将 ${result.queued_count} 个缺少讲稿的页面加入待生成队列。`);
      await loadDocumentStatus(document.document_id);
      await loadDocumentPages(document.document_id, false);
    } catch (error) {
      setDocumentActionMessage(
        error instanceof Error ? error.message : "生成剩余讲稿失败，请稍后重试。",
      );
    } finally {
      setDocumentActionState(null);
    }
  }

  async function clearDocumentLectureNotesQueue(document: DocumentItem) {
    setDocumentActionState({
      documentId: document.document_id,
      action: "clearingLectureNotesQueue",
    });
    setDocumentActionMessage("");

    try {
      const result = await clearDocumentLectureNotesQueueRequest(document.document_id);

      setDocumentActionMessage(`已清空 ${result.cleared_count} 个待生成讲稿任务。`);
      await loadDocumentStatus(document.document_id);
      await loadDocumentPages(document.document_id, false);
    } catch (error) {
      setDocumentActionMessage(
        error instanceof Error ? error.message : "清空待生成队列失败，请稍后重试。",
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
      await toggleDocumentLectureNotesPausedRequest(document.document_id, isPaused);

      setDocumentActionMessage(
        isPaused ? "逐页讲稿已继续生成，后台会消费已有待生成队列。" : "逐页讲稿已暂停，待生成队列会保留。",
      );
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
      await regeneratePageLectureNotesRequest(page.page_id);

      setDocumentActionMessage(`第 ${page.page_number} 页讲稿已加入待生成队列。`);
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

  async function loadDocumentExams(documentId: string) {
    setExamsLoadingByDocument((current) => ({ ...current, [documentId]: true }));
    try {
      const data = await listDocumentExams(documentId);
      setExamsByDocument((current) => ({ ...current, [documentId]: data }));
    } catch (error) {
      setDocumentActionMessage(
        error instanceof Error ? error.message : "试卷列表加载失败，请稍后重试。",
      );
    } finally {
      setExamsLoadingByDocument((current) => ({ ...current, [documentId]: false }));
    }
  }

  async function loadPhaseExams() {
    setPhaseExamsLoading(true);
    try {
      const data = await listPhaseExams();
      setPhaseExams(data);
    } catch (error) {
      setDocumentActionMessage(
        error instanceof Error ? error.message : "阶段考试列表加载失败，请稍后重试。",
      );
    } finally {
      setPhaseExamsLoading(false);
    }
  }

  async function loadExamForTaking(examId: string) {
    setExamTakeLoading(true);
    setCurrentExamResult(null);
    try {
      const [examMetadata, questionsWithoutAnswer] = await Promise.all([
        readExamMetadata(examId),
        readExamQuestions(examId, false),
      ]);
      setCurrentExam(examMetadata);
      setCurrentExamQuestionsWithoutAnswer(questionsWithoutAnswer as ExamQuestionForTaking[]);
      setDocumentActionMessage("");
    } catch (error) {
      setCurrentExam(null);
      setCurrentExamQuestionsWithoutAnswer([]);
      setDocumentActionMessage(
        error instanceof Error ? error.message : "试卷加载失败，请稍后重试。",
      );
    } finally {
      setExamTakeLoading(false);
    }
  }

  async function loadExamAttemptResult(examId: string, attemptId: string) {
    setExamTakeLoading(true);
    try {
      const [examMetadata, result] = await Promise.all([
        readExamMetadata(examId),
        readExamAttemptResult(examId, attemptId),
      ]);
      setCurrentExam(examMetadata);
      setCurrentExamResult(result);
      setCurrentExamQuestionsWithoutAnswer([]);
      setDocumentActionMessage("");
    } catch (error) {
      setCurrentExamResult(null);
      setDocumentActionMessage(
        error instanceof Error ? error.message : "考试结果加载失败，请稍后重试。",
      );
    } finally {
      setExamTakeLoading(false);
    }
  }

  async function handleGenerateExam(documentId: string, difficulty: string = "medium") {
    setDocumentActionState({ documentId, action: "regeneratingSummary" });
    try {
      await generateExamRequest(documentId, difficulty);
      setDocumentActionMessage("试卷已开始生成，稍后刷新查看。");
      await loadDocumentExams(documentId);
    } catch (error) {
      setDocumentActionMessage(
        error instanceof Error ? error.message : "试卷生成失败，请稍后重试。",
      );
    } finally {
      setDocumentActionState(null);
    }
  }

  async function handleDeleteExam(documentId: string, examId: string) {
    const confirmed = window.confirm("确定要删除这份试卷吗？相关答题记录和错题也会删除。");
    if (!confirmed) {
      return;
    }

    setDocumentActionMessage("");
    try {
      await deleteExamRequest(examId);
      setDocumentActionMessage("试卷已删除。");
      await loadDocumentExams(documentId);
      await loadWrongQuestions();
    } catch (error) {
      setDocumentActionMessage(
        error instanceof Error ? error.message : "试卷删除失败，请稍后重试。",
      );
    }
  }

  async function handleTakeExam(examId: string) {
    navigate(`/exams/${encodeURIComponent(examId)}/take`);
  }

  async function handleSubmitExam(answers: Record<string, string>) {
    if (!currentExam) {
      return;
    }

    try {
      const result = await submitExamAttempt(currentExam.id, answers);
      setCurrentExamResult(result);
      navigate(
        `/exams/${encodeURIComponent(currentExam.id)}/attempts/${encodeURIComponent(
          result.attempt.id,
        )}/result`,
      );
      await loadWrongQuestions();
    } catch (error) {
      setDocumentActionMessage(
        error instanceof Error ? error.message : "答题提交失败，请稍后重试。",
      );
      throw error;
    }
  }

  function handleRetryExam() {
    if (!currentExam) {
      return;
    }

    setCurrentExamResult(null);
    navigate(`/exams/${encodeURIComponent(currentExam.id)}/take`);
  }

  async function loadWrongQuestions() {
    setWrongQuestionsLoading(true);
    try {
      const data = await listWrongQuestions();
      setWrongQuestions(data);
    } catch (error) {
      setDocumentActionMessage(
        error instanceof Error ? error.message : "错题本加载失败，请稍后重试。",
      );
    } finally {
      setWrongQuestionsLoading(false);
    }
  }

  async function handleReviewWrongQuestion(wrongId: string) {
    try {
      await reviewWrongQuestion(wrongId);
      await loadWrongQuestions();
    } catch (error) {
      setDocumentActionMessage(
        error instanceof Error ? error.message : "标记复习失败，请稍后重试。",
      );
    }
  }

  async function handleDeleteWrongQuestion(wrongId: string) {
    try {
      await deleteWrongQuestion(wrongId);
      await loadWrongQuestions();
    } catch (error) {
      setDocumentActionMessage(
        error instanceof Error ? error.message : "删除错题失败，请稍后重试。",
      );
    }
  }

  async function handleCreatePhaseExam(
    documentIds: string[],
    name: string,
    difficulty: string,
  ) {
    setPhaseExamCreating(true);
    try {
      await generatePhaseExam(documentIds, name, difficulty);
      await loadPhaseExams();
      setDocumentActionMessage("阶段考试已开始生成，生成完成后可点击开始考试。");
      navigate(FILES_ROUTE);
    } catch (error) {
      setDocumentActionMessage(
        error instanceof Error ? error.message : "阶段考试生成失败，请稍后重试。",
      );
      throw error;
    } finally {
      setPhaseExamCreating(false);
    }
  }

  function formatCreatedAt(value: string) {
    const date = new Date(value);

    if (Number.isNaN(date.getTime())) {
      return value;
    }

    return date.toLocaleString();
  }

  function getStatusLabel(status: string) {
    const statusLabels: Record<string, string> = {
      uploaded: "已上传",
      processing: "解析中",
      ready: "解析完成",
      failed: "解析失败",
    };

    return statusLabels[status] ?? status;
  }

  function getCourseSummaryStatusLabel(status: string) {
    const statusLabels: Record<string, string> = {
      pending: "等待生成",
      processing: "生成中",
      ready: "已生成",
      failed: "生成失败",
    };

    return statusLabels[status] ?? status;
  }

  function getLectureNotesStatusLabel(status: string) {
    const statusLabels: Record<string, string> = {
      pending: "等待生成",
      processing: "生成中",
      ready: "已生成",
      failed: "生成失败",
    };

    return statusLabels[status] ?? status;
  }

  function buildLectureNotesProgressText(statusData: DocumentStatusResponse | undefined) {
    if (!statusData) {
      return "正在读取生成进度...";
    }

    if (statusData.total_pages === 0) {
      return "当前文档还没有页面记录。";
    }

    const pausedText = statusData.lecture_notes_paused ? "，已暂停" : "";
    return `讲稿进度：${statusData.lecture_notes_ready_count}/${statusData.total_pages} 页已有讲稿，${statusData.lecture_notes_processing_count} 页生成中，${statusData.lecture_notes_pending_count} 页在待生成队列，${statusData.lecture_notes_failed_count} 页失败${pausedText}。`;
  }

  function isDocumentBusy(documentId: string) {
    return documentActionState?.documentId === documentId;
  }

  function resolveLectureNotesPaused(document: DocumentItem) {
    return documentStatusById[document.document_id]?.lecture_notes_paused ?? document.lecture_notes_paused;
  }

  function toggleDocumentExpanded(documentId: string) {
    setExpandedDocumentIds((currentExpandedDocumentIds) => ({
      ...currentExpandedDocumentIds,
      [documentId]: !currentExpandedDocumentIds[documentId],
    }));
  }

  function isPageLectureNotesBusy(documentId: string, pageNumber: number) {
    return (
      documentActionState?.documentId === documentId &&
      documentActionState.action === "regeneratingLectureNotes" &&
      documentActionState.pageNumber === pageNumber
    );
  }

  if (!isKnownRoute) {
    return <Navigate to={FILES_ROUTE} replace />;
  }

  if (isReaderRoute && activeReaderDocument) {
    const readerDocument =
      documents.find((document) => document.document_id === activeReaderDocument.document_id) ??
      activeReaderDocument;
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
        ? Math.max(
            MIN_PDF_PAGE_STAGE_WIDTH,
            Math.min(readerWorkspaceSize.width, pdfPageWidthByHeight),
          )
        : readerViewportWidth > 0
          ? readerViewportWidth
          : undefined;
    const readerPages = pagesByDocument[readerDocument.document_id] ?? [];
    const currentReaderPage = readerPages.find((page) => page.page_number === currentPdfPage);
    const activeDocumentStatus = documentStatusById[readerDocument.document_id];
    const currentNoteBlock = currentReaderPage?.note_block ?? null;
    const readerNoteBlockLayoutKey = `reader-note-block:${readerDocument.document_id}`;
    const currentNoteBlockLayout = currentNoteBlock
      ? resolveNoteBlockLayout(currentNoteBlock, readerNoteBlockLayoutKey)
      : null;
    const isCurrentNoteBlockCollapsed =
      currentNoteBlock !== null &&
      (readerRightSidebar === "note" || isReaderNoteBlockCollapsed);
    const isSubmittingCurrentPageChat =
      currentReaderPage !== undefined && submittingPageChatId === currentReaderPage.page_id;
    const currentPageChatCount = currentReaderPage?.chat_messages.length ?? 0;
    const pageChatContent = (
      <PageChatContent
        currentReaderPage={currentReaderPage}
        currentPdfPage={currentPdfPage}
        pageQuestionInput={pageQuestionInput}
        isSubmittingCurrentPageChat={isSubmittingCurrentPageChat}
        pendingAttachments={pendingPageChatAttachments}
        formatCreatedAt={formatCreatedAt}
        onQuestionInputChange={setPageQuestionInput}
        onAddPendingAttachments={addPendingPageChatAttachments}
        onRemovePendingAttachment={removePendingPageChatAttachment}
        onSubmitPageQuestion={(page) => {
          void submitPageQuestion(page);
        }}
      />
    );
    const pageChatStatus = <PageChatStatus pageChatMessage={pageChatMessage} />;
    const noteSidebarContent = (
      <div className="reader-note-sidebar-content">
        {currentReaderPage?.lecture_notes ? (
          <MarkdownContent content={currentReaderPage.lecture_notes} />
        ) : currentReaderPage?.lecture_notes_status === "processing" ? (
          <p>本页讲稿正在生成，完成后会自动更新。</p>
        ) : currentReaderPage?.lecture_notes_status === "pending" ? (
          <p>本页讲稿还没有开始生成。</p>
        ) : currentReaderPage?.lecture_notes_status === "failed" ? (
          <p className="document-error">
            {currentReaderPage.lecture_notes_error ?? "本页讲稿生成失败。"}
          </p>
        ) : currentReaderPage ? (
          <p>本页暂时没有讲稿内容。</p>
        ) : (
          <p>正在加载当前页讲稿。</p>
        )}
      </div>
    );
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
    const noteBlockElement = currentNoteBlock ? (
      <NoteBlock
        readerDocument={readerDocument}
        noteBlock={currentNoteBlock}
        layout={
          currentNoteBlockLayout ?? {
            x: currentNoteBlock.x,
            y: currentNoteBlock.y,
            width: currentNoteBlock.width,
            height: currentNoteBlock.height,
          }
        }
        isCollapsed={isCurrentNoteBlockCollapsed}
        onStartDrag={(event, documentId, noteBlock) =>
          startNoteBlockDrag(event, documentId, noteBlock, readerNoteBlockLayoutKey)
        }
        onStartResize={(event, documentId, noteBlock, resizeDirection) =>
          startNoteBlockResize(
            event,
            documentId,
            noteBlock,
            resizeDirection,
            readerNoteBlockLayoutKey,
          )
        }
        onCollapse={() => setIsReaderNoteBlockCollapsed(true)}
        onExpand={expandCurrentNoteBlock}
        onOpenInSidebar={openCurrentNoteBlockInSidebar}
      />
    ) : null;

    return (
      <Suspense
        fallback={
          <main className="app-shell app-shell--files">
            <section className="status-panel app-page-panel">
              <p className="eyebrow">Slides Reader</p>
              <h1>正在加载阅读器...</h1>
              <p className="description">PDF 阅读模块正在初始化。</p>
            </section>
          </main>
        }
      >
        <ReaderView
        readerDocument={readerDocument}
        readerRightSidebar={readerRightSidebar}
        isReaderTopbarCollapsed={isReaderTopbarCollapsed}
        isReaderChatCollapsed={isReaderChatCollapsed}
        currentPdfPage={currentPdfPage}
        totalPdfPages={totalPdfPages}
        readerState={readerState}
        readerMessage={readerMessage}
        activeDocumentStatus={activeDocumentStatus}
        currentReaderPage={currentReaderPage}
        currentPageChatCount={currentPageChatCount}
        pageTurnControls={pageTurnControls}
        pageChatContent={pageChatContent}
        pageChatStatus={pageChatStatus}
        noteSidebarContent={noteSidebarContent}
        noteBlockElement={noteBlockElement}
        pdfPageWidth={pdfPageWidth}
        thumbnailRenderWidth={thumbnailRenderWidth}
        thumbnailSidebarWidth={thumbnailSidebarWidth}
        courseSummarySidebarWidth={courseSummarySidebarWidth}
        isResizingThumbnailSidebar={isResizingThumbnailSidebar}
        isResizingCourseSummarySidebar={isResizingCourseSummarySidebar}
        readerWorkspaceRef={readerWorkspaceRef}
        readerViewportRef={readerViewportRef}
        readerContentRef={readerContentRef}
        documentActionState={documentActionState}
        getStatusLabel={getStatusLabel}
        getCourseSummaryStatusLabel={getCourseSummaryStatusLabel}
        buildLectureNotesProgressText={buildLectureNotesProgressText}
        isDocumentBusy={isDocumentBusy}
        onCloseReader={closeReader}
        onOpenSettings={openSettings}
        onToggleCourseSummarySidebar={toggleCourseSummarySidebar}
        onClearActiveDocument={clearActiveDocument}
        onCollapseTopbar={() => {
          setIsCourseSummaryPanelOpen(false);
          setIsReaderChatCollapsed(true);
          setReaderRightSidebar((currentSidebar) =>
            currentSidebar === "summary" ? "none" : currentSidebar,
          );
          setIsReaderTopbarCollapsed(true);
        }}
        onExpandTopbar={() => setIsReaderTopbarCollapsed(false)}
        onCloseRightSidebar={closeRightSidebar}
        onToggleNoteSidebar={toggleNoteSidebar}
        onOpenChatSidebar={openChatSidebar}
        onSetReaderChatCollapsed={setIsReaderChatCollapsed}
        onGoToPdfPage={goToPdfPage}
        onPdfLoadSuccess={handlePdfLoadSuccess}
        onPdfLoadError={handlePdfLoadError}
        onPdfPageLoadSuccess={handlePdfPageLoadSuccess}
        onPdfPageRenderError={handlePdfPageRenderError}
        onStartResizingThumbnailSidebar={startResizingThumbnailSidebar}
        onStartResizingCourseSummarySidebar={startResizingCourseSummarySidebar}
        onRegenerateCourseSummary={(document) => {
          void regenerateCourseSummary(document);
        }}
        onRegeneratePageLectureNotes={(document, page) => {
          void regeneratePageLectureNotes(document, page);
        }}
        />
      </Suspense>
    );
  }

  if (isExamTakeRoute && routeExamId) {
    return (
      <ExamTakeView
        examId={routeExamId}
        title={currentExam?.title ?? "考试答题"}
        questions={currentExamQuestionsWithoutAnswer}
        isLoading={examTakeLoading}
        onSubmit={async (answers) => {
          await handleSubmitExam(answers);
        }}
        onBack={() => navigate(FILES_ROUTE)}
      />
    );
  }

  if (isExamResultRoute && routeExamId) {
    if (examTakeLoading && !currentExamResult) {
      return (
        <main className="app-shell app-shell--files">
          <section className="status-panel app-page-panel">
            <p className="eyebrow">Slides Reader</p>
            <h1>正在加载考试结果...</h1>
            <p className="description">正在读取本次答题记录和解析。</p>
          </section>
        </main>
      );
    }

    if (!currentExamResult) {
      return (
        <main className="app-shell app-shell--files">
          <section className="status-panel app-page-panel">
            <p className="eyebrow">Slides Reader</p>
            <h1>考试结果不可用</h1>
            <p className="description">
              {documentActionMessage || "没有找到对应的答题结果。"}
            </p>
            <button type="button" className="secondary-action-button" onClick={() => navigate(FILES_ROUTE)}>
              返回文件
            </button>
          </section>
        </main>
      );
    }

    return (
      <ExamResultView
        result={currentExamResult}
        questions={currentExamResult.questions}
        onBack={() => navigate(FILES_ROUTE)}
        onRetry={handleRetryExam}
      />
    );
  }

  if (isWrongBookRoute) {
    const wrongBookDocumentId = searchParams.get("document_id");
    const wrongBookDocument = wrongBookDocumentId
      ? documents.find((document) => document.document_id === wrongBookDocumentId)
      : undefined;

    return (
      <WrongBookView
        wrongQuestions={wrongQuestions}
        documentId={wrongBookDocumentId ?? undefined}
        documentTitle={wrongBookDocument?.title}
        onBack={() => navigate(FILES_ROUTE)}
        onReview={(wrongId) => handleReviewWrongQuestion(wrongId)}
        onDelete={(wrongId) => handleDeleteWrongQuestion(wrongId)}
      />
    );
  }

  if (isPhaseExamCreateRoute) {
    return (
      <PhaseExamCreateView
        documents={documents}
        onBack={() => navigate(FILES_ROUTE)}
        onCreate={(documentIds, name, difficulty) =>
          handleCreatePhaseExam(documentIds, name, difficulty)
        }
      />
    );
  }

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
                ? "配置 OpenAI-compatible LLM，用于课程简介、逐页讲稿和当前页问答。"
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
            <button
              type="button"
              className="topbar-button"
              onClick={() => {
                void loadWrongQuestions();
                navigate(WRONG_BOOK_ROUTE);
              }}
            >
              错题本
            </button>
            <button
              type="button"
              className="topbar-button"
              onClick={() => navigate(PHASE_EXAM_CREATE_ROUTE)}
            >
              阶段考试
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
          <FilesView
            selectedFile={selectedFile}
            uploadState={uploadState}
            uploadMessage={uploadMessage}
            uploadedDocumentId={uploadedDocumentId}
            currentOpenedDocument={currentOpenedDocument}
            documents={documents}
            documentsMessage={documentsMessage}
            documentStatusById={documentStatusById}
            documentStatusMessage={documentStatusMessage}
            activeReaderDocument={activeReaderDocument}
            editingDocumentId={editingDocumentId}
            editingTitle={editingTitle}
            documentActionState={documentActionState}
            documentActionMessage={documentActionMessage}
            expandedDocumentIds={expandedDocumentIds}
            expandedLectureNotesDocumentId={expandedLectureNotesDocumentId}
            pagesByDocument={pagesByDocument}
            pagesMessageByDocument={pagesMessageByDocument}
            examsByDocument={examsByDocument}
            examsLoadingByDocument={examsLoadingByDocument}
            phaseExams={phaseExams}
            phaseExamsLoading={phaseExamsLoading}
            onRefreshPhaseExams={() => {
              void loadPhaseExams();
            }}
            onTakePhaseExam={(phaseExam) => {
              if (phaseExam.exam_id) {
                void handleTakeExam(phaseExam.exam_id);
              }
            }}
            onReturnToReader={returnToReader}
            onFileChange={handleFileChange}
            onUploadSubmit={handleUploadSubmit}
            onEditingTitleChange={setEditingTitle}
            onSaveRename={(documentId) => {
              void saveRename(documentId);
            }}
            onCancelRename={cancelRename}
            onToggleDocumentLectureNotesPaused={(document) => {
              void toggleDocumentLectureNotesPaused(document);
            }}
            onOpenReader={openReader}
            onStartRename={startRename}
            onDeleteDocument={(document) => {
              void deleteDocument(document);
            }}
            onToggleDocumentExpanded={toggleDocumentExpanded}
            onRegenerateCourseSummary={(document) => {
              void regenerateCourseSummary(document);
            }}
            onToggleLectureNotesPanel={(document) => {
              void toggleLectureNotesPanel(document);
            }}
            onRegenerateDocumentLectureNotes={(document) => {
              void regenerateDocumentLectureNotes(document);
            }}
            onGenerateRemainingLectureNotes={(document) => {
              void generateRemainingLectureNotes(document);
            }}
            onClearLectureNotesQueue={(document) => {
              void clearDocumentLectureNotesQueue(document);
            }}
            onRegeneratePageLectureNotes={(document, page) => {
              void regeneratePageLectureNotes(document, page);
            }}
            onGenerateExam={(document) => {
              void handleGenerateExam(document.document_id);
            }}
            onTakeExam={(examId) => {
              void handleTakeExam(examId);
            }}
            onDeleteExam={(documentId, examId) => {
              void handleDeleteExam(documentId, examId);
            }}
            onViewWrongBook={(document) => {
              void loadWrongQuestions();
              navigate(`/wrong-book?document_id=${encodeURIComponent(document.document_id)}`);
            }}
            isDocumentBusy={isDocumentBusy}
            isPageLectureNotesBusy={isPageLectureNotesBusy}
            resolveLectureNotesPaused={resolveLectureNotesPaused}
            formatCreatedAt={formatCreatedAt}
            getStatusLabel={getStatusLabel}
            getCourseSummaryStatusLabel={getCourseSummaryStatusLabel}
            getLectureNotesStatusLabel={getLectureNotesStatusLabel}
            buildLectureNotesProgressText={buildLectureNotesProgressText}
          />
        ) : null}

        {visibleView === "settings" ? (
          <SettingsView
            llmConfigState={llmConfigState}
            llmBaseUrl={llmBaseUrl}
            llmApiKey={llmApiKey}
            llmApiKeyConfigured={llmApiKeyConfigured}
            llmApiKeyPreview={llmApiKeyPreview}
            shouldClearLlmApiKey={shouldClearLlmApiKey}
            llmModel={llmModel}
            llmTimeoutSeconds={llmTimeoutSeconds}
            courseSummaryPrompt={courseSummaryPrompt}
            lectureNotesPrompt={lectureNotesPrompt}
            pageChatPrompt={pageChatPrompt}
            examGenerationPrompt={examGenerationPrompt}
            isCourseSummaryPromptExpanded={isCourseSummaryPromptExpanded}
            isLectureNotesPromptExpanded={isLectureNotesPromptExpanded}
            isPageChatPromptExpanded={isPageChatPromptExpanded}
            isExamGenerationPromptExpanded={isExamGenerationPromptExpanded}
            llmTestPrompt={llmTestPrompt}
            llmConfigMessage={llmConfigMessage}
            llmTestAnswer={llmTestAnswer}
            courseSummaryPromptTextareaRef={courseSummaryPromptTextareaRef}
            lectureNotesPromptTextareaRef={lectureNotesPromptTextareaRef}
            pageChatPromptTextareaRef={pageChatPromptTextareaRef}
            examGenerationPromptTextareaRef={examGenerationPromptTextareaRef}
            onSubmit={saveLlmConfig}
            onBaseUrlChange={setLlmBaseUrl}
            onApiKeyChange={setLlmApiKey}
            onClearApiKeyChange={(shouldClear) => {
              setShouldClearLlmApiKey(shouldClear);
              if (shouldClear) {
                setLlmApiKey("");
              }
            }}
            onModelChange={setLlmModel}
            onTimeoutSecondsChange={setLlmTimeoutSeconds}
            onCourseSummaryPromptChange={setCourseSummaryPrompt}
            onLectureNotesPromptChange={setLectureNotesPrompt}
            onPageChatPromptChange={setPageChatPrompt}
            onExamGenerationPromptChange={setExamGenerationPrompt}
            onToggleCourseSummaryPrompt={() => setIsCourseSummaryPromptExpanded((value) => !value)}
            onToggleLectureNotesPrompt={() => setIsLectureNotesPromptExpanded((value) => !value)}
            onTogglePageChatPrompt={() => setIsPageChatPromptExpanded((value) => !value)}
            onToggleExamGenerationPrompt={() => setIsExamGenerationPromptExpanded((value) => !value)}
            onTestPromptChange={setLlmTestPrompt}
            onTestLlmConfig={() => {
              void testLlmConfig();
            }}
          />
        ) : null}
      </section>
    </main>
  );
}

export default App;
