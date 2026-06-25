import { useEffect, useState } from "react";
import type { NavigateFunction } from "react-router-dom";
import {
  deleteExam as deleteExamRequest,
  generateExam as generateExamRequest,
  listDocumentExams,
  readExamAttemptResult,
  readExamMetadata,
  readExamQuestions,
  submitExamAttempt,
} from "../api/exams";
import {
  deletePhaseExam as deletePhaseExamRequest,
  generatePhaseExam,
  listPhaseExams,
} from "../api/phaseExams";
import {
  deleteWrongQuestion,
  listWrongQuestions,
  reviewWrongQuestion,
} from "../api/wrongQuestions";
import type {
  DocumentItem,
  ExamAttemptResult,
  ExamItem,
  ExamQuestionForTaking,
  PhaseExamItem,
  WrongQuestionItem,
} from "../types/api";
import type { DocumentActionState } from "../types/ui";

type UseExamWorkflowsOptions = {
  // documents 是文件页已经加载出的文档列表，hook 会按文档加载普通试卷列表。
  documents: DocumentItem[];
  // hasLoadedDocuments 用来避免文档列表还没加载完时就请求考试接口。
  hasLoadedDocuments: boolean;
  // visibleView 表示当前主页面区域，只有文件页可见时才刷新列表。
  visibleView: "files" | "settings";
  // 下面这些 route 标志来自 App 的 React Router 匹配结果，用来支持刷新页面后恢复答题页、结果页和错题本。
  isWrongBookRoute: boolean;
  isExamTakeRoute: boolean;
  isExamResultRoute: boolean;
  routeExamId: string | null;
  routeAttemptId: string | null;
  // pollIntervalMs 是生成中考试的刷新间隔，单位是毫秒。
  pollIntervalMs: number;
  // filesRoute 是文件页路径，创建阶段考试后会回到文件页。
  filesRoute: string;
  // navigate 是 React Router 的跳转函数，由 App 注入，避免 hook 自己理解路由配置。
  navigate: NavigateFunction;
  // 复用 App 原有的文档操作状态，避免文件页按钮状态和消息展示逻辑被拆散。
  setDocumentActionState: React.Dispatch<React.SetStateAction<DocumentActionState>>;
  setDocumentActionMessage: (message: string) => void;
};

export function isAsyncExamStatus(status: string) {
  // pending 和 processing 都表示后端后台任务还可能继续推进，需要前端继续轮询。
  return status === "pending" || status === "processing";
}

export function pruneRecordToDocumentIds<T>(
  record: Record<string, T>,
  allowedDocumentIds: Set<string>,
) {
  // 这个工具用于清理按 document_id 做 key 的缓存，避免文档删除后 UI 继续保留旧数据。
  return Object.fromEntries(
    Object.entries(record).filter(([documentId]) => allowedDocumentIds.has(documentId)),
  ) as Record<string, T>;
}

export function useExamWorkflows({
  documents,
  hasLoadedDocuments,
  visibleView,
  isWrongBookRoute,
  isExamTakeRoute,
  isExamResultRoute,
  routeExamId,
  routeAttemptId,
  pollIntervalMs,
  filesRoute,
  navigate,
  setDocumentActionState,
  setDocumentActionMessage,
}: UseExamWorkflowsOptions) {
  // examsByDocument 按 document_id 保存普通试卷列表，方便 FilesView 逐个文档展示。
  const [examsByDocument, setExamsByDocument] = useState<Record<string, ExamItem[]>>({});
  // examsLoadingByDocument 按 document_id 保存加载状态，避免一个文档加载中影响其他文档。
  const [examsLoadingByDocument, setExamsLoadingByDocument] = useState<Record<string, boolean>>({});
  // currentExam 保存当前答题页或结果页正在查看的试卷元数据。
  const [currentExam, setCurrentExam] = useState<ExamItem | null>(null);
  // currentExamQuestionsWithoutAnswer 保存答题页题目，刻意不包含 answer 和 explanation。
  const [currentExamQuestionsWithoutAnswer, setCurrentExamQuestionsWithoutAnswer] = useState<
    ExamQuestionForTaking[]
  >([]);
  // currentExamResult 保存一次答题提交或结果页重新加载得到的判分结果。
  const [currentExamResult, setCurrentExamResult] = useState<ExamAttemptResult | null>(null);
  // examTakeLoading 同时覆盖答题页题目加载和结果页结果加载。
  const [examTakeLoading, setExamTakeLoading] = useState(false);
  // wrongQuestions 是错题本列表，由错题本页面和删除试卷后刷新使用。
  const [wrongQuestions, setWrongQuestions] = useState<WrongQuestionItem[]>([]);
  // wrongQuestionsLoading 暂时主要用于后续 UI 扩展，当前保留给调用方消费。
  const [wrongQuestionsLoading, setWrongQuestionsLoading] = useState(false);
  // phaseExams 保存阶段考试列表，文件页会单独展示它们。
  const [phaseExams, setPhaseExams] = useState<PhaseExamItem[]>([]);
  // phaseExamsLoading 控制阶段考试列表刷新、删除时的加载状态。
  const [phaseExamsLoading, setPhaseExamsLoading] = useState(false);

  useEffect(() => {
    // 文档删除后，App 不再直接知道考试缓存内部结构；hook 根据最新文档列表清掉失效缓存。
    const activeDocumentIds = new Set(documents.map((document) => document.document_id));
    setExamsByDocument((current) => pruneRecordToDocumentIds(current, activeDocumentIds));
    setExamsLoadingByDocument((current) => pruneRecordToDocumentIds(current, activeDocumentIds));
  }, [documents]);

  async function loadDocumentExams(documentId: string) {
    // 每次只标记当前文档的考试列表加载中，不阻塞其他文档操作。
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
    // 阶段考试列表是全局列表，因此只需要一个加载状态。
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
    // 答题页需要试卷元数据和不含答案的题目，两者可以并行请求。
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
    // 结果页刷新后不能依赖内存状态，所以要通过 examId 和 attemptId 重新读取结果。
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
    // 生成试卷是后台异步任务，提交后立即刷新一次列表，用 pending/processing 状态反馈给用户。
    setDocumentActionState({ documentId, action: "generatingExam" });
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
    // 删除试卷会级联影响答题记录和错题，因此保留二次确认。
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
    // 答题页自身会根据 URL 重新加载题目，因此这里负责跳转即可。
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
    // 错题本是跨试卷的全局列表，删除试卷或阶段考试后也需要刷新。
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
    try {
      await generatePhaseExam(documentIds, name, difficulty);
      await loadPhaseExams();
      setDocumentActionMessage("阶段考试已开始生成，生成完成后可点击开始考试。");
      navigate(filesRoute);
    } catch (error) {
      setDocumentActionMessage(
        error instanceof Error ? error.message : "阶段考试生成失败，请稍后重试。",
      );
      throw error;
    }
  }

  async function handleDeletePhaseExam(phaseExam: PhaseExamItem) {
    // 阶段考试可能关联普通试卷、答题记录和错题，删除前需要明确提示影响范围。
    const confirmed = window.confirm(
      `确定要删除阶段考试“${phaseExam.name}”吗？关联试卷、答题记录和错题也会一起删除。`,
    );
    if (!confirmed) {
      return;
    }

    setDocumentActionMessage("");
    setPhaseExamsLoading(true);
    try {
      await deletePhaseExamRequest(phaseExam.id);
      setDocumentActionMessage("阶段考试已删除。");
      await loadPhaseExams();
      await loadWrongQuestions();
    } catch (error) {
      setDocumentActionMessage(
        error instanceof Error ? error.message : "阶段考试删除失败，请稍后重试。",
      );
    } finally {
      setPhaseExamsLoading(false);
    }
  }

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
    // 文件页存在生成中的普通试卷或阶段考试时，定时刷新列表，避免用户必须手动点刷新。
    if (visibleView !== "files" || !hasLoadedDocuments) {
      return;
    }

    const documentIdsWithRunningExams = documents
      .map((document) => document.document_id)
      .filter((documentId) =>
        (examsByDocument[documentId] ?? []).some((exam) => isAsyncExamStatus(exam.status)),
      );
    const shouldRefreshPhaseExams = phaseExams.some((phaseExam) =>
      isAsyncExamStatus(phaseExam.status),
    );

    if (documentIdsWithRunningExams.length === 0 && !shouldRefreshPhaseExams) {
      return;
    }

    const intervalId = window.setInterval(() => {
      documentIdsWithRunningExams.forEach((documentId) => {
        void loadDocumentExams(documentId);
      });
      if (shouldRefreshPhaseExams) {
        void loadPhaseExams();
      }
    }, pollIntervalMs);

    return () => window.clearInterval(intervalId);
  }, [documents, examsByDocument, hasLoadedDocuments, phaseExams, pollIntervalMs, visibleView]);

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

  return {
    examsByDocument,
    examsLoadingByDocument,
    currentExam,
    currentExamQuestionsWithoutAnswer,
    currentExamResult,
    examTakeLoading,
    wrongQuestions,
    wrongQuestionsLoading,
    phaseExams,
    phaseExamsLoading,
    loadDocumentExams,
    loadPhaseExams,
    loadExamForTaking,
    loadExamAttemptResult,
    handleGenerateExam,
    handleDeleteExam,
    handleTakeExam,
    handleSubmitExam,
    handleRetryExam,
    loadWrongQuestions,
    handleReviewWrongQuestion,
    handleDeleteWrongQuestion,
    handleCreatePhaseExam,
    handleDeletePhaseExam,
  };
}
