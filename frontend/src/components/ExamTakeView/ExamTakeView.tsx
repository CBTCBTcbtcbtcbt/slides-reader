import { useState } from "react";
import type { ExamQuestionForTaking } from "../../types/api";
import "./ExamTakeView.css";

export type ExamTakeViewProps = {
  examId: string;
  title: string;
  questions: ExamQuestionForTaking[];
  isLoading: boolean;
  onSubmit: (answers: Record<string, string>) => Promise<void>;
  onBack: () => void;
};

export function ExamTakeView({
  title,
  questions,
  isLoading,
  onSubmit,
  onBack,
}: ExamTakeViewProps) {
  const [answers, setAnswers] = useState<Record<string, string>>({});
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [message, setMessage] = useState("");

  function handleChoiceChange(questionId: string, option: string) {
    setAnswers((prev) => ({ ...prev, [questionId]: option }));
  }

  function handleFillChange(questionId: string, value: string) {
    setAnswers((prev) => ({ ...prev, [questionId]: value }));
  }

  async function handleSubmit(event: React.FormEvent) {
    event.preventDefault();

    const unanswered = questions.filter((q) => !answers[q.id]);
    if (unanswered.length > 0) {
      setMessage(`还有 ${unanswered.length} 道题未作答。`);
      return;
    }

    setIsSubmitting(true);
    setMessage("");
    try {
      await onSubmit(answers);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "提交失败");
    } finally {
      setIsSubmitting(false);
    }
  }

  if (isLoading) {
    return (
      <div className="exam-take-view">
        <p className="exam-take-loading">试卷加载中...</p>
      </div>
    );
  }

  return (
    <div className="exam-take-view">
      <header className="exam-take-header">
        <button className="back-button" onClick={onBack}>
          ← 返回
        </button>
        <h2>{title}</h2>
        <span className="exam-progress">
          已答 {Object.keys(answers).length} / {questions.length}
        </span>
      </header>

      <form className="exam-form" onSubmit={handleSubmit}>
        {questions.map((question, index) => (
          <div key={question.id} className="question-card">
            <div className="question-header">
              <span className="question-number">{index + 1}.</span>
              <span className="question-type">
                {question.question_type === "choice" ? "单选题" : "填空题"}
              </span>
              <span className="question-score">{question.score} 分</span>
            </div>

            <p className="question-content">{question.content}</p>

            {question.question_type === "choice" && question.options && (
              <div className="choice-options">
                {question.options.map((option, optionIndex) => {
                  const letter = String.fromCharCode(65 + optionIndex);
                  return (
                    <label key={optionIndex} className="choice-option">
                      <input
                        type="radio"
                        name={`question-${question.id}`}
                        value={letter}
                        checked={answers[question.id] === letter}
                        onChange={() => handleChoiceChange(question.id, letter)}
                      />
                      <span>
                        <strong className="choice-letter">{letter}.</strong> {option}
                      </span>
                    </label>
                  );
                })}
              </div>
            )}

            {question.question_type === "fill_in" && (
              <input
                type="text"
                className="fill-input"
                placeholder="请输入答案"
                value={answers[question.id] || ""}
                onChange={(e) => handleFillChange(question.id, e.target.value)}
              />
            )}
          </div>
        ))}

        {message && <div className="exam-take-message">{message}</div>}

        <div className="exam-submit-area">
          <button
            type="submit"
            className="exam-submit-button"
            disabled={isSubmitting}
          >
            {isSubmitting ? "提交中..." : "提交试卷"}
          </button>
        </div>
      </form>
    </div>
  );
}
