import type { ExamAttemptResult, ExamQuestionItem } from "../../types/api";
import "./ExamResultView.css";

export type ExamResultViewProps = {
  result: ExamAttemptResult;
  questions: ExamQuestionItem[];
  onBack: () => void;
  onRetry: () => void;
};

export function ExamResultView({
  result,
  questions,
  onBack,
  onRetry,
}: ExamResultViewProps) {
  const percentage =
    result.max_score > 0
      ? Math.round((result.total_score / result.max_score) * 100)
      : 0;

  const questionMap = new Map(questions.map((q) => [q.id, q]));

  return (
    <div className="exam-result-view">
      <header className="exam-result-header">
        <button className="back-button" onClick={onBack}>
          ← 返回
        </button>
        <h2>考试结果</h2>
        <button className="retry-button" onClick={onRetry}>
          再考一次
        </button>
      </header>

      <main className="exam-result-main">
        <div className="score-card">
          <div className="score-value">{result.total_score}</div>
          <div className="score-max">/ {result.max_score}</div>
          <div className="score-percentage">{percentage}%</div>
        </div>

        <section className="result-details">
          <h3>答题详情</h3>
          {result.question_results.map((item, index) => {
            const question = questionMap.get(item.question_id);
            if (!question) return null;

            return (
              <div
                key={item.question_id}
                className={`result-question ${
                  item.is_correct ? "result-correct" : "result-wrong"
                }`}
              >
                <div className="result-question-header">
                  <span className="result-question-number">{index + 1}.</span>
                  <span className="result-question-status">
                    {item.is_correct ? "正确" : "错误"}
                  </span>
                  <span className="result-question-score">
                    {item.score} / {item.max_score} 分
                  </span>
                </div>

                <p className="result-question-content">{question.content}</p>

                <div className="result-answer-row">
                  <span>你的答案：{item.user_answer || "未作答"}</span>
                  <span>正确答案：{item.correct_answer}</span>
                </div>

                {question.source_page && (
                  <p className="result-source-page">
                    知识点来源：第 {question.source_page} 页
                  </p>
                )}

                <div className="result-explanation">
                  <strong>解析：</strong>
                  <p>{question.explanation}</p>
                </div>
              </div>
            );
          })}
        </section>
      </main>
    </div>
  );
}
