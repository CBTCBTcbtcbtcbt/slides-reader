import type { ChatMessageItem, PageItem } from "../../types/api";
import { MarkdownContent } from "../MarkdownContent";

type PageChatContentProps = {
  // currentReaderPage 是当前页数据；为空时显示加载提示。
  currentReaderPage: PageItem | undefined;
  // currentPdfPage 用于当前页数据尚未加载时仍能显示用户所在页码。
  currentPdfPage: number;
  // pageQuestionInput 是用户正在输入的问题草稿。
  pageQuestionInput: string;
  // isSubmittingCurrentPageChat 表示当前页是否正在等待 LLM 回答。
  isSubmittingCurrentPageChat: boolean;
  // formatCreatedAt 把后端 ISO 时间转换为本地展示文本。
  formatCreatedAt: (value: string) => string;
  // onQuestionInputChange 更新问题草稿。
  onQuestionInputChange: (value: string) => void;
  // onSubmitPageQuestion 提交当前页问题。
  onSubmitPageQuestion: (page: PageItem) => void;
};

function getChatRoleLabel(role: ChatMessageItem["role"]) {
  // 后端只保存 user 和 assistant 两种角色；这里转换成中文称呼。
  return role === "user" ? "学生" : "AI 老师";
}

export function PageChatContent({
  currentReaderPage,
  pageQuestionInput,
  isSubmittingCurrentPageChat,
  formatCreatedAt,
  onQuestionInputChange,
  onSubmitPageQuestion,
}: PageChatContentProps) {
  return currentReaderPage ? (
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
              <MarkdownContent content={chatMessage.content} variant="chat" />
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
          onSubmitPageQuestion(currentReaderPage);
        }}
      >
        <label className="page-chat-input-label">
          <span>向 AI 老师提问</span>
          <textarea
            value={pageQuestionInput}
            onChange={(event) => onQuestionInputChange(event.target.value)}
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
}

type PageChatStatusProps = {
  // pageChatMessage 是当前页问答的状态或错误提示。
  pageChatMessage: string;
};

export function PageChatStatus({ pageChatMessage }: PageChatStatusProps) {
  return pageChatMessage ? (
    <p
      className={`page-chat-status${
        pageChatMessage.includes("失败") ||
        pageChatMessage.includes("不能为空") ||
        pageChatMessage.includes("错误") ||
        pageChatMessage.includes("无法") ||
        pageChatMessage.includes("超时")
          ? " page-chat-status--error"
          : ""
      }`}
    >
      {pageChatMessage}
    </p>
  ) : null;
}
