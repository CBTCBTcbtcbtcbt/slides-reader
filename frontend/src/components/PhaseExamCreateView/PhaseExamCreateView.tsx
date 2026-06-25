import { useState } from "react";
import type { DocumentItem } from "../../types/api";
import "./PhaseExamCreateView.css";

export type PhaseExamCreateViewProps = {
  documents: DocumentItem[];
  onBack: () => void;
  onCreate: (documentIds: string[], name: string, difficulty: string) => Promise<void>;
};

export function PhaseExamCreateView({
  documents,
  onBack,
  onCreate,
}: PhaseExamCreateViewProps) {
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
  const [name, setName] = useState("");
  const [difficulty, setDifficulty] = useState("medium");
  const [isCreating, setIsCreating] = useState(false);
  const [message, setMessage] = useState("");
  const [messageType, setMessageType] = useState<"success" | "error">("success");

  function setDocumentSelected(documentId: string, shouldSelect: boolean) {
    setSelectedIds((prev) => {
      const next = new Set(prev);
      if (shouldSelect) {
        next.add(documentId);
      } else {
        next.delete(documentId);
      }
      return next;
    });
  }

  async function handleSubmit(event: React.FormEvent) {
    event.preventDefault();

    if (selectedIds.size === 0) {
      setMessageType("error");
      setMessage("请至少选择一个课件。");
      return;
    }
    if (!name.trim()) {
      setMessageType("error");
      setMessage("请输入阶段考试名称。");
      return;
    }

    setIsCreating(true);
    setMessage("");
    try {
      await onCreate(Array.from(selectedIds), name.trim(), difficulty);
      setMessageType("success");
      setMessage("阶段考试已开始生成。");
    } catch (error) {
      setMessageType("error");
      setMessage(error instanceof Error ? error.message : "生成失败");
    } finally {
      setIsCreating(false);
    }
  }

  return (
    <div className="phase-exam-create-view">
      <header className="phase-exam-header">
        <button className="back-button" onClick={onBack}>
          ← 返回
        </button>
        <h2>创建阶段考试</h2>
      </header>

      <main className="phase-exam-main">
        <form onSubmit={handleSubmit}>
          <section className="phase-exam-section">
            <h3>选择课件</h3>
            {documents.length === 0 ? (
              <p className="phase-exam-empty">暂无课件，请先上传课件。</p>
            ) : (
              <ul className="phase-exam-document-list">
                {documents.map((doc) => (
                  <li
                    key={doc.document_id}
                    className={`phase-exam-document-item ${
                      selectedIds.has(doc.document_id) ? "selected" : ""
                    }`}
                  >
                    <label className="phase-exam-document-label">
                      <input
                        type="checkbox"
                        checked={selectedIds.has(doc.document_id)}
                        onChange={(event) => {
                          setDocumentSelected(doc.document_id, event.currentTarget.checked);
                        }}
                      />
                      <span className="phase-exam-document-title">
                        {doc.title}
                      </span>
                      <span className="phase-exam-document-pages">
                        {doc.page_count} 页
                      </span>
                    </label>
                  </li>
                ))}
              </ul>
            )}
          </section>

          <section className="phase-exam-section">
            <h3>考试设置</h3>
            <div className="phase-exam-field">
              <label htmlFor="phase-name">阶段考试名称</label>
              <input
                id="phase-name"
                type="text"
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder="例如：期中复习卷"
                required
              />
            </div>

            <div className="phase-exam-field">
              <label htmlFor="phase-difficulty">难度</label>
              <select
                id="phase-difficulty"
                value={difficulty}
                onChange={(e) => setDifficulty(e.target.value)}
              >
                <option value="easy">简单</option>
                <option value="medium">中等</option>
                <option value="hard">困难</option>
              </select>
            </div>
          </section>

          {message && (
            <div
              className={`phase-exam-message ${
                messageType === "success"
                  ? "phase-exam-message-success"
                  : "phase-exam-message-error"
              }`}
            >
              {message}
            </div>
          )}

          <div className="phase-exam-actions">
            <button
              type="submit"
              className="phase-exam-submit"
              disabled={isCreating || documents.length === 0}
            >
              {isCreating ? "生成中..." : "生成阶段考试"}
            </button>
          </div>
        </form>
      </main>
    </div>
  );
}
