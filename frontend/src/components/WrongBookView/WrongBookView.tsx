import { useMemo } from "react";
import { AppIcon } from "../AppIcon";
import type { WrongQuestionItem } from "../../types/api";
import "./WrongBookView.css";

export type WrongBookViewProps = {
  wrongQuestions: WrongQuestionItem[];
  documentId?: string;
  documentTitle?: string;
  onBack: () => void;
  onReview: (wrongId: string) => Promise<void>;
  onDelete: (wrongId: string) => Promise<void>;
};

export function WrongBookView({
  wrongQuestions,
  documentId,
  documentTitle,
  onBack,
  onReview,
  onDelete,
}: WrongBookViewProps) {
  const filteredQuestions = useMemo(() => {
    if (!documentId) return wrongQuestions;
    return wrongQuestions.filter((item) => item.document_id === documentId);
  }, [wrongQuestions, documentId]);

  const grouped = useMemo(() => {
    const map = new Map<string, WrongQuestionItem[]>();
    for (const item of filteredQuestions) {
      const key = item.document_id;
      if (!map.has(key)) {
        map.set(key, []);
      }
      map.get(key)!.push(item);
    }
    return map;
  }, [filteredQuestions]);

  return (
    <div className="wrong-book-view">
      <header className="wrong-book-header">
        <button type="button" className="page-back-button" onClick={onBack}>
          <AppIcon name="chevronLeft" />
          返回
        </button>
        <h2>{documentTitle ? `${documentTitle} 的错题本` : "错题本"}</h2>
        <span className="wrong-count">共 {filteredQuestions.length} 题</span>
      </header>

      <main className="wrong-book-main">
        {filteredQuestions.length === 0 ? (
          <div className="wrong-book-empty">
            <p>暂无错题，快去生成试卷答题吧。</p>
          </div>
        ) : (
          Array.from(grouped.entries()).map(([documentId, items]) => (
            <section key={documentId} className="wrong-group">
              <h3 className="wrong-group-title">
                {items[0]?.document_title || "未知课件"}
              </h3>
              <ul className="wrong-list">
                {items.map((item) => (
                  <li key={item.id} className="wrong-card">
                    <div className="wrong-card-header">
                      <span className="wrong-type">
                        {item.question_type === "choice" ? "单选题" : "填空题"}
                      </span>
                      {item.knowledge_tag && (
                        <span className="wrong-tag">{item.knowledge_tag}</span>
                      )}
                      {item.source_page && (
                        <span className="wrong-page">第 {item.source_page} 页</span>
                      )}
                    </div>

                    <p className="wrong-content">{item.question_content}</p>

                    {item.question_options && (
                      <ul className="wrong-options">
                        {item.question_options.map((option) => (
                          <li key={option}>{option}</li>
                        ))}
                      </ul>
                    )}

                    <div className="wrong-answer-row">
                      <span className="wrong-user-answer">
                        你的答案：{item.user_answer || "未作答"}
                      </span>
                      <span className="wrong-correct-answer">
                        正确答案：{item.correct_answer}
                      </span>
                    </div>

                    <div className="wrong-explanation">
                      <strong>解析：</strong>
                      <p>{item.explanation}</p>
                    </div>

                    <div className="wrong-actions">
                      <button
                        className="wrong-review-button"
                        onClick={() => onReview(item.id)}
                        disabled={item.reviewed > 0}
                      >
                        {item.reviewed > 0 ? "已复习" : "标记已复习"}
                      </button>
                      <button
                        className="wrong-delete-button"
                        onClick={() => onDelete(item.id)}
                      >
                        移除
                      </button>
                    </div>
                  </li>
                ))}
              </ul>
            </section>
          ))
        )}
      </main>
    </div>
  );
}
