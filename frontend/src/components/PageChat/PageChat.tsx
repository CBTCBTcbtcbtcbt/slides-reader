import { useEffect, useRef, useState } from "react";
import type { ChatAttachmentItem, ChatMessageItem, PageItem } from "../../types/api";
import type { PendingChatAttachment } from "../../types/ui";
import { MarkdownContent } from "../MarkdownContent";

const PAGE_CHAT_MAX_ATTACHMENTS = 4;
const PAGE_CHAT_SUPPORTED_IMAGE_TYPES = new Set(["image/png", "image/jpeg", "image/webp"]);

type PageChatContentProps = {
  // currentReaderPage 是当前页数据；为空时显示加载提示。
  currentReaderPage: PageItem | undefined;
  // currentPdfPage 用于当前页数据尚未加载时仍能显示用户所在页码。
  currentPdfPage: number;
  // pageQuestionInput 是用户正在输入的问题草稿。
  pageQuestionInput: string;
  // isSubmittingCurrentPageChat 表示当前页是否正在等待 LLM 回答。
  isSubmittingCurrentPageChat: boolean;
  // pendingAttachments 是当前输入框上方等待随问题发送的图片。
  pendingAttachments: PendingChatAttachment[];
  // formatCreatedAt 把后端 ISO 时间转换为本地展示文本。
  formatCreatedAt: (value: string) => string;
  // onQuestionInputChange 更新问题草稿。
  onQuestionInputChange: (value: string) => void;
  // onAddPendingAttachments 把选择或粘贴的图片加入待发送列表。
  onAddPendingAttachments: (files: File[]) => void;
  // onRemovePendingAttachment 从待发送列表移除单张图片。
  onRemovePendingAttachment: (attachmentId: string) => void;
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
  pendingAttachments,
  formatCreatedAt,
  onQuestionInputChange,
  onAddPendingAttachments,
  onRemovePendingAttachment,
  onSubmitPageQuestion,
}: PageChatContentProps) {
  const [previewAttachment, setPreviewAttachment] = useState<{
    url: string;
    filename: string;
  } | null>(null);
  const chatHistoryRef = useRef<HTMLDivElement | null>(null);
  const latestMessageFingerprint =
    currentReaderPage?.chat_messages
      .map(
        (message) =>
          // 这里把消息 ID、内容长度和附件数量合成滚动依赖，避免整段 Markdown 文本进入依赖数组。
          `${message.chat_message_id}:${message.content.length}:${message.attachments.length}`,
      )
      .join("|") ?? "";

  useEffect(() => {
    // 当前页会话历史第一次渲染、发送新消息、流式回答追加文本时，都让用户看到最新一条消息。
    const chatHistoryElement = chatHistoryRef.current;
    if (chatHistoryElement === null) {
      return;
    }

    // requestAnimationFrame 会等本轮 DOM 更新完成后再滚动，避免读到旧的 scrollHeight。
    const animationFrameId = window.requestAnimationFrame(() => {
      chatHistoryElement.scrollTop = chatHistoryElement.scrollHeight;
    });

    return () => {
      window.cancelAnimationFrame(animationFrameId);
    };
  }, [currentReaderPage?.page_id, latestMessageFingerprint, pendingAttachments.length]);

  useEffect(() => {
    // 图片预览打开后支持 Escape 关闭，符合常见会话产品的键盘习惯。
    if (previewAttachment === null) {
      return;
    }

    function handleKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") {
        setPreviewAttachment(null);
      }
    }

    window.addEventListener("keydown", handleKeyDown);
    return () => {
      window.removeEventListener("keydown", handleKeyDown);
    };
  }, [previewAttachment]);

  function collectSupportedImageFiles(fileList: FileList | File[]) {
    // 浏览器粘贴和文件选择都会给 File 对象，这里统一过滤出第一版支持的图片类型。
    return Array.from(fileList).filter((file) => PAGE_CHAT_SUPPORTED_IMAGE_TYPES.has(file.type));
  }

  function openAttachmentPreview(attachment: ChatAttachmentItem) {
    // 预览层使用后端文件接口作为原图地址，保证刷新后历史图片仍可查看。
    setPreviewAttachment({
      url: attachment.file_url,
      filename: attachment.filename,
    });
  }

  function handleFileInputChange(event: React.ChangeEvent<HTMLInputElement>) {
    const files = event.target.files ? collectSupportedImageFiles(event.target.files) : [];
    onAddPendingAttachments(files);
    event.target.value = "";
  }

  function handleTextareaPaste(event: React.ClipboardEvent<HTMLTextAreaElement>) {
    const files = collectSupportedImageFiles(Array.from(event.clipboardData.files));
    if (files.length === 0) {
      return;
    }

    event.preventDefault();
    onAddPendingAttachments(files);
  }

  return currentReaderPage ? (
    <div className="page-chat-content">
      <div className="page-chat-history" ref={chatHistoryRef}>
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
              {chatMessage.attachments.length > 0 ? (
                <div className="page-chat-attachments" aria-label="消息图片附件">
                  {chatMessage.attachments.map((attachment) => (
                    <button
                      type="button"
                      className="page-chat-attachment"
                      key={attachment.attachment_id}
                      onClick={() => openAttachmentPreview(attachment)}
                      title={attachment.filename}
                    >
                      <img src={attachment.file_url} alt={attachment.filename} />
                    </button>
                  ))}
                </div>
              ) : null}
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
        <div className="page-chat-composer" aria-label="当前页问答输入区">
          {pendingAttachments.length > 0 ? (
            <div className="page-chat-pending-attachments" aria-label="待发送图片">
              {pendingAttachments.map((attachment) => (
                <div className="page-chat-pending-attachment" key={attachment.id}>
                  <img src={attachment.previewUrl} alt={attachment.file.name} />
                  <button
                    type="button"
                    onClick={() => onRemovePendingAttachment(attachment.id)}
                    disabled={isSubmittingCurrentPageChat}
                    aria-label={`移除 ${attachment.file.name}`}
                    title="移除图片"
                  >
                    ×
                  </button>
                </div>
              ))}
            </div>
          ) : null}
          <div className="page-chat-composer-row">
            <label
              className={`page-chat-attach-button${
                isSubmittingCurrentPageChat ||
                pendingAttachments.length >= PAGE_CHAT_MAX_ATTACHMENTS
                  ? " page-chat-attach-button--disabled"
                  : ""
              }`}
              title="添加图片"
            >
              <span aria-hidden="true">+</span>
              <input
                type="file"
                accept="image/png,image/jpeg,image/webp"
                multiple
                onChange={handleFileInputChange}
                disabled={
                  isSubmittingCurrentPageChat ||
                  pendingAttachments.length >= PAGE_CHAT_MAX_ATTACHMENTS
                }
              />
            </label>
            <label className="page-chat-input-label">
              <span className="sr-only">向 AI 老师提问</span>
              <textarea
                value={pageQuestionInput}
                onChange={(event) => onQuestionInputChange(event.target.value)}
                onPaste={handleTextareaPaste}
                disabled={isSubmittingCurrentPageChat}
                placeholder="Ask anything"
                rows={1}
              />
            </label>
            <button
              type="submit"
              className={`page-chat-send-button${
                isSubmittingCurrentPageChat ? " page-chat-send-button--stop" : ""
              }`}
              aria-label={isSubmittingCurrentPageChat ? "中断回答" : "发送问题"}
              title={isSubmittingCurrentPageChat ? "中断回答" : "发送问题"}
            >
              <span
                className={
                  isSubmittingCurrentPageChat
                    ? "page-chat-send-button__stop-icon"
                    : "page-chat-send-button__send-icon"
                }
                aria-hidden="true"
              >
                {isSubmittingCurrentPageChat ? "" : "↑"}
              </span>
            </button>
          </div>
        </div>
      </form>

      {previewAttachment ? (
        <div
          className="page-chat-image-lightbox"
          role="dialog"
          aria-modal="true"
          aria-label={`预览图片 ${previewAttachment.filename}`}
          onClick={() => setPreviewAttachment(null)}
        >
          <button
            type="button"
            className="page-chat-image-lightbox__close"
            onClick={() => setPreviewAttachment(null)}
            aria-label="关闭图片预览"
            title="关闭"
          >
            ×
          </button>
          <img
            src={previewAttachment.url}
            alt={previewAttachment.filename}
            onClick={(event) => event.stopPropagation()}
          />
        </div>
      ) : null}
    </div>
  ) : (
    <div className="page-chat-content page-chat-content--loading">
      <p className="page-chat-empty">正在加载当前页数据，稍后即可提问。</p>
    </div>
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
