// 这里集中保存后端 API 返回的数据类型。
// TypeScript 类型只在开发和构建时做检查，不会改变浏览器运行时行为。

export type HealthResponse = {
  status: string;
  service: string;
};

export type UploadResponse = {
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

export type DocumentItem = {
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

export type NoteBlockItem = {
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

export type ChatAttachmentItem = {
  attachment_id: string;
  chat_message_id: string;
  page_id: string;
  kind: "image";
  filename: string;
  mime_type: string;
  file_size: number;
  file_url: string;
  created_at: string;
};

export type ChatMessageItem = {
  chat_message_id: string;
  page_id: string;
  role: "user" | "assistant";
  content: string;
  attachments: ChatAttachmentItem[];
  created_at: string;
};

export type PageItem = {
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

export type LLMConfigResponse = {
  base_url: string;
  model: string;
  timeout_seconds: number;
  course_summary_prompt: string;
  lecture_notes_prompt: string;
  page_chat_prompt: string;
  exam_generation_prompt: string;
  api_key_configured: boolean;
  api_key_preview: string;
};

export type LLMConfigUpdatePayload = {
  base_url: string;
  model: string;
  timeout_seconds: number;
  course_summary_prompt: string;
  lecture_notes_prompt: string;
  page_chat_prompt: string;
  exam_generation_prompt: string;
  api_key?: string;
};

export type LLMTestResponse = {
  status: string;
  answer: string;
};

export type PageChatResponse = {
  status: string;
  page_id: string;
  user_message: ChatMessageItem;
  assistant_message: ChatMessageItem;
  messages: ChatMessageItem[];
};

export type PageChatStreamEvent =
  | {
      type: "user_message";
      message: ChatMessageItem;
    }
  | {
      type: "delta";
      content: string;
    }
  | {
      type: "done";
      assistant_message: ChatMessageItem;
      messages: ChatMessageItem[];
    }
  | {
      type: "error";
      message: string;
    };

export type DocumentStatusPageItem = {
  page_id: string;
  page_number: number;
  status: string;
  error_message: string | null;
  lecture_notes_status: string;
  lecture_notes_error: string | null;
};

export type DocumentStatusResponse = {
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

export type ExamItem = {
  id: string;
  document_id: string;
  title: string;
  description: string | null;
  status: string;
  error_message: string | null;
  total_score: number;
  latest_attempt_score: number | null;
  created_at: string;
};

export type ExamQuestionItem = {
  id: string;
  exam_id: string;
  question_number: number;
  section: string;
  question_type: "choice" | "fill_in";
  score: number;
  content: string;
  options: string[] | null;
  answer: string;
  explanation: string;
  source_page: number | null;
  expected_type: string | null;
  difficulty: string | null;
  knowledge_tag: string | null;
  created_at: string;
};

export type ExamQuestionForTaking = Omit<ExamQuestionItem, "answer" | "explanation">;

export type ExamWithQuestions = ExamItem & {
  questions: ExamQuestionItem[];
};

export type ExamAttemptItem = {
  id: string;
  exam_id: string;
  started_at: string;
  finished_at: string | null;
  score: number | null;
  answers: Record<string, string>;
};

export type ExamAttemptResult = {
  status: string;
  attempt: ExamAttemptItem;
  total_score: number;
  max_score: number;
  questions: ExamQuestionItem[];
  question_results: {
    question_id: string;
    user_answer: string;
    correct_answer: string;
    is_correct: boolean;
    score: number;
    max_score: number;
  }[];
};

export type WrongQuestionItem = {
  id: string;
  question_id: string;
  exam_id: string;
  attempt_id: string;
  user_answer: string;
  created_at: string;
  reviewed: number;
  question_content: string;
  question_options: string[] | null;
  correct_answer: string;
  explanation: string;
  question_type: string;
  score: number;
  source_page: number | null;
  knowledge_tag: string | null;
  document_id: string;
  document_title: string;
};

export type PhaseExamItem = {
  id: string;
  name: string;
  document_ids: string[];
  difficulty: string;
  exam_id: string | null;
  status: string;
  error_message: string | null;
  created_at: string;
};
