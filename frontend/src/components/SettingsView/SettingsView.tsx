import type { LLMConfigState } from "../../types/ui";
import { MarkdownContent } from "../MarkdownContent";

type SettingsViewProps = {
  llmConfigState: LLMConfigState;
  llmBaseUrl: string;
  llmApiKey: string;
  llmApiKeyConfigured: boolean;
  llmApiKeyPreview: string;
  shouldClearLlmApiKey: boolean;
  llmModel: string;
  llmTimeoutSeconds: string;
  courseSummaryPrompt: string;
  lectureNotesPrompt: string;
  pageChatPrompt: string;
  examGenerationPrompt: string;
  isCourseSummaryPromptExpanded: boolean;
  isLectureNotesPromptExpanded: boolean;
  isPageChatPromptExpanded: boolean;
  isExamGenerationPromptExpanded: boolean;
  llmTestPrompt: string;
  llmConfigMessage: string;
  llmTestAnswer: string;
  courseSummaryPromptTextareaRef: React.RefObject<HTMLTextAreaElement | null>;
  lectureNotesPromptTextareaRef: React.RefObject<HTMLTextAreaElement | null>;
  pageChatPromptTextareaRef: React.RefObject<HTMLTextAreaElement | null>;
  examGenerationPromptTextareaRef: React.RefObject<HTMLTextAreaElement | null>;
  onSubmit: (event: React.FormEvent<HTMLFormElement>) => void;
  onBaseUrlChange: (value: string) => void;
  onApiKeyChange: (value: string) => void;
  onClearApiKeyChange: (shouldClear: boolean) => void;
  onModelChange: (value: string) => void;
  onTimeoutSecondsChange: (value: string) => void;
  onCourseSummaryPromptChange: (value: string) => void;
  onLectureNotesPromptChange: (value: string) => void;
  onPageChatPromptChange: (value: string) => void;
  onExamGenerationPromptChange: (value: string) => void;
  onToggleCourseSummaryPrompt: () => void;
  onToggleLectureNotesPrompt: () => void;
  onTogglePageChatPrompt: () => void;
  onToggleExamGenerationPrompt: () => void;
  onTestPromptChange: (value: string) => void;
  onTestLlmConfig: () => void;
};

export function SettingsView({
  llmConfigState,
  llmBaseUrl,
  llmApiKey,
  llmApiKeyConfigured,
  llmApiKeyPreview,
  shouldClearLlmApiKey,
  llmModel,
  llmTimeoutSeconds,
  courseSummaryPrompt,
  lectureNotesPrompt,
  pageChatPrompt,
  examGenerationPrompt,
  isCourseSummaryPromptExpanded,
  isLectureNotesPromptExpanded,
  isPageChatPromptExpanded,
  isExamGenerationPromptExpanded,
  llmTestPrompt,
  llmConfigMessage,
  llmTestAnswer,
  courseSummaryPromptTextareaRef,
  lectureNotesPromptTextareaRef,
  pageChatPromptTextareaRef,
  examGenerationPromptTextareaRef,
  onSubmit,
  onBaseUrlChange,
  onApiKeyChange,
  onClearApiKeyChange,
  onModelChange,
  onTimeoutSecondsChange,
  onCourseSummaryPromptChange,
  onLectureNotesPromptChange,
  onPageChatPromptChange,
  onExamGenerationPromptChange,
  onToggleCourseSummaryPrompt,
  onToggleLectureNotesPrompt,
  onTogglePageChatPrompt,
  onToggleExamGenerationPrompt,
  onTestPromptChange,
  onTestLlmConfig,
}: SettingsViewProps) {
  const isBusy = llmConfigState === "saving" || llmConfigState === "testing";

  return (
    <form className="llm-config-panel" onSubmit={onSubmit}>
      <div>
        <h2>LLM 配置</h2>
        <p>
          LLM 是 Large Language Model，也就是“大语言模型”。这里配置
          OpenAI-compatible API，用于后续生成课程简介、逐页讲稿、回答问题和生成试卷。
        </p>
      </div>

      <label className="config-field">
        <span>LLM_BASE_URL</span>
        <input
          value={llmBaseUrl}
          onChange={(event) => onBaseUrlChange(event.target.value)}
          placeholder="https://api.openai.com/v1"
          disabled={isBusy}
        />
      </label>

      <label className="config-field">
        <span>LLM_API_KEY</span>
        <input
          value={llmApiKey}
          onChange={(event) => onApiKeyChange(event.target.value)}
          type="password"
          placeholder={
            llmApiKeyConfigured
              ? `已保存：${llmApiKeyPreview}，留空表示不修改`
              : "请输入 API Key"
          }
          disabled={shouldClearLlmApiKey || isBusy}
        />
      </label>

      <label className="config-checkbox">
        <input
          type="checkbox"
          checked={shouldClearLlmApiKey}
          onChange={(event) => onClearApiKeyChange(event.target.checked)}
          disabled={isBusy}
        />
        <span>清空已保存的 LLM_API_KEY</span>
      </label>

      <label className="config-field">
        <span>LLM_MODEL</span>
        <input
          value={llmModel}
          onChange={(event) => onModelChange(event.target.value)}
          placeholder="gpt-4.1-mini"
          disabled={isBusy}
        />
      </label>

      <label className="config-field">
        <span>请求超时时间（秒）</span>
        <input
          value={llmTimeoutSeconds}
          onChange={(event) => onTimeoutSecondsChange(event.target.value)}
          inputMode="numeric"
          disabled={isBusy}
        />
      </label>

      <div className="prompt-setting">
        <div className="prompt-setting-header">
          <span>课程简介 prompt</span>
          <button type="button" className="prompt-toggle-button" onClick={onToggleCourseSummaryPrompt} disabled={isBusy}>
            {isCourseSummaryPromptExpanded ? "折叠" : "展开"}
          </button>
        </div>
        {isCourseSummaryPromptExpanded ? (
          <label className="config-field">
            <textarea
              ref={courseSummaryPromptTextareaRef}
              className="prompt-textarea"
              value={courseSummaryPrompt}
              onChange={(event) => onCourseSummaryPromptChange(event.target.value)}
              disabled={isBusy}
            />
          </label>
        ) : null}
      </div>

      <div className="prompt-setting">
        <div className="prompt-setting-header">
          <span>逐页讲稿 prompt</span>
          <button type="button" className="prompt-toggle-button" onClick={onToggleLectureNotesPrompt} disabled={isBusy}>
            {isLectureNotesPromptExpanded ? "折叠" : "展开"}
          </button>
        </div>
        {isLectureNotesPromptExpanded ? (
          <label className="config-field">
            <textarea
              ref={lectureNotesPromptTextareaRef}
              className="prompt-textarea"
              value={lectureNotesPrompt}
              onChange={(event) => onLectureNotesPromptChange(event.target.value)}
              disabled={isBusy}
            />
          </label>
        ) : null}
      </div>

      <div className="prompt-setting">
        <div className="prompt-setting-header">
          <span>当前页问答 prompt</span>
          <button type="button" className="prompt-toggle-button" onClick={onTogglePageChatPrompt} disabled={isBusy}>
            {isPageChatPromptExpanded ? "折叠" : "展开"}
          </button>
        </div>
        {isPageChatPromptExpanded ? (
          <label className="config-field">
            <textarea
              ref={pageChatPromptTextareaRef}
              className="prompt-textarea"
              value={pageChatPrompt}
              onChange={(event) => onPageChatPromptChange(event.target.value)}
              disabled={isBusy}
            />
          </label>
        ) : null}
      </div>

      <div className="prompt-setting">
        <div className="prompt-setting-header">
          <span>试卷生成 prompt</span>
          <button type="button" className="prompt-toggle-button" onClick={onToggleExamGenerationPrompt} disabled={isBusy}>
            {isExamGenerationPromptExpanded ? "折叠" : "展开"}
          </button>
        </div>
        {isExamGenerationPromptExpanded ? (
          <label className="config-field">
            <textarea
              ref={examGenerationPromptTextareaRef}
              className="prompt-textarea"
              value={examGenerationPrompt}
              onChange={(event) => onExamGenerationPromptChange(event.target.value)}
              disabled={isBusy}
            />
          </label>
        ) : null}
      </div>

      <label className="config-field">
        <span>测试提示词</span>
        <textarea
          value={llmTestPrompt}
          onChange={(event) => onTestPromptChange(event.target.value)}
          disabled={isBusy}
        />
      </label>

      <div className="llm-config-actions">
        <button className="upload-button" type="submit" disabled={isBusy}>
          {llmConfigState === "saving" ? "保存中..." : "保存配置"}
        </button>
        <button
          type="button"
          className="secondary-action-button"
          onClick={onTestLlmConfig}
          disabled={isBusy}
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
          <MarkdownContent content={llmTestAnswer} variant="compact" />
        </div>
      ) : null}
    </form>
  );
}
