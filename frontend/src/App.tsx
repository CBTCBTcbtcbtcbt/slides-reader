import { useEffect, useState } from "react";

type HealthState = "checking" | "success" | "error";

type UploadState = "idle" | "uploading" | "success" | "error";

type HealthResponse = {
  status: string;
  service: string;
};

type UploadResponse = {
  document_id: string;
  title: string;
  filename: string;
  file_path: string;
  saved_filename: string;
  status: string;
  page_count: number;
  error_message: string | null;
  created_at: string;
};

type DocumentItem = {
  document_id: string;
  title: string;
  file_path: string;
  status: string;
  page_count: number;
  error_message: string | null;
  created_at: string;
};

type DocumentActionState = {
  documentId: string;
  action: "renaming" | "deleting";
} | null;

function App() {
  // connectionState 用来记录当前前端连接后端的状态。
  const [connectionState, setConnectionState] = useState<HealthState>("checking");

  // message 用来显示给用户看的连接结果说明。
  const [message, setMessage] = useState("正在检查后端连接...");

  // selectedFile 用来保存用户当前选择的 PDF 文件。
  const [selectedFile, setSelectedFile] = useState<File | null>(null);

  // uploadState 用来记录上传流程的当前状态。
  const [uploadState, setUploadState] = useState<UploadState>("idle");

  // uploadMessage 用来给用户展示上传成功或失败的说明。
  const [uploadMessage, setUploadMessage] = useState("请选择一个 PDF 文件。");

  // uploadedDocumentId 用来显示后端返回的 document_id。
  const [uploadedDocumentId, setUploadedDocumentId] = useState<string | null>(null);

  // documents 用来保存后端返回的已上传文档列表。
  const [documents, setDocuments] = useState<DocumentItem[]>([]);

  // documentsMessage 用来显示文档列表加载状态或错误信息。
  const [documentsMessage, setDocumentsMessage] = useState("正在加载已上传文档...");

  // editingDocumentId 用来记录当前正在编辑标题的文档。
  const [editingDocumentId, setEditingDocumentId] = useState<string | null>(null);

  // editingTitle 用来暂存用户输入的新标题。
  const [editingTitle, setEditingTitle] = useState("");

  // documentActionState 用来避免同一时间重复点击重命名或删除按钮。
  const [documentActionState, setDocumentActionState] = useState<DocumentActionState>(null);

  // documentActionMessage 用来展示重命名或删除操作的结果。
  const [documentActionMessage, setDocumentActionMessage] = useState("");

  useEffect(() => {
    // 使用 AbortController 可以在组件卸载时取消请求，避免无意义的状态更新。
    const controller = new AbortController();

    async function checkBackendHealth() {
      try {
        // 这里请求 Vite 代理下的 `/api/health`，实际会转发到 FastAPI 后端。
        const response = await fetch("/api/health", {
          signal: controller.signal,
        });

        // HTTP 状态码不是 2xx 时，说明后端虽然有响应，但接口结果不是正常成功。
        if (!response.ok) {
          throw new Error(`健康检查失败，HTTP 状态码：${response.status}`);
        }

        // 把后端返回的 JSON 解析成 TypeScript 对象。
        const data = (await response.json()) as HealthResponse;

        // 后端约定 status 为 ok 时，表示服务正常。
        if (data.status !== "ok") {
          throw new Error("后端返回了非正常状态。");
        }

        setConnectionState("success");
        setMessage(`后端连接成功：${data.service}`);
        await loadDocuments();
      } catch (error) {
        // 如果请求是因为组件卸载被取消，不需要向用户显示失败。
        if (error instanceof DOMException && error.name === "AbortError") {
          return;
        }

        setConnectionState("error");
        setMessage("后端连接失败，请确认 FastAPI 服务已经启动。");
      }
    }

    checkBackendHealth();

    // 组件卸载时取消仍在进行的健康检查请求。
    return () => {
      controller.abort();
    };
  }, []);

  async function loadDocuments() {
    try {
      // 文档列表接口从 SQLite 数据库读取记录，刷新页面后仍然应该返回历史上传记录。
      const response = await fetch("/api/documents");

      // HTTP 状态码不是 2xx 时，说明文档列表接口没有正常返回。
      if (!response.ok) {
        throw new Error(`文档列表加载失败，HTTP 状态码：${response.status}`);
      }

      const data = (await response.json()) as DocumentItem[];

      setDocuments(data);
      setDocumentsMessage(data.length > 0 ? "" : "还没有上传过 PDF slides。");
    } catch (error) {
      setDocuments([]);
      setDocumentsMessage(
        error instanceof Error ? error.message : "文档列表加载失败，请稍后重试。",
      );
    }
  }

  function formatCreatedAt(value: string) {
    // 后端使用 ISO 时间字符串保存创建时间，前端转换为本地时间展示。
    const date = new Date(value);

    // 如果时间字符串无法解析，就直接显示原始值，避免页面报错。
    if (Number.isNaN(date.getTime())) {
      return value;
    }

    return date.toLocaleString();
  }

  function getStatusLabel(status: string) {
    // 后端用英文状态值保存进数据库，前端把它转换成用户更容易理解的中文。
    const statusLabels: Record<string, string> = {
      uploaded: "已上传",
      processing: "解析中",
      ready: "解析完成",
      failed: "解析失败",
    };

    return statusLabels[status] ?? status;
  }

  function isDocumentBusy(documentId: string) {
    // 判断某个文档是否正在执行重命名或删除操作。
    return documentActionState?.documentId === documentId;
  }

  function handleFileChange(event: React.ChangeEvent<HTMLInputElement>) {
    // 浏览器文件选择控件会把用户选择的文件放在 files 列表中。
    const nextFile = event.target.files?.[0] ?? null;

    // 每次重新选择文件时，清空上一次上传结果。
    setUploadedDocumentId(null);

    if (!nextFile) {
      setSelectedFile(null);
      setUploadState("idle");
      setUploadMessage("请选择一个 PDF 文件。");
      return;
    }

    // 前端先做一次后缀和类型检查，给用户更快的反馈。
    // 后端仍然会再次校验，不能只依赖前端校验。
    if (!nextFile.name.toLowerCase().endsWith(".pdf") || nextFile.type !== "application/pdf") {
      setSelectedFile(null);
      setUploadState("error");
      setUploadMessage("请选择 .pdf 格式的 slides 文件。");
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
      setUploadMessage("上传前需要先选择一个 PDF 文件。");
      return;
    }

    // FormData 是浏览器上传文件时最常用的数据结构。
    const formData = new FormData();
    formData.append("file", selectedFile);

    setUploadState("uploading");
    setUploadMessage("正在上传 PDF...");
    setUploadedDocumentId(null);

    try {
      // 这里请求 Vite 代理下的 `/api/documents`，实际会转发到 FastAPI 后端。
      const response = await fetch("/api/documents", {
        method: "POST",
        body: formData,
      });

      // 如果后端拒绝上传，优先读取后端 detail 字段作为错误原因。
      if (!response.ok) {
        const errorData = (await response.json().catch(() => null)) as { detail?: string } | null;
        throw new Error(errorData?.detail ?? `上传失败，HTTP 状态码：${response.status}`);
      }

      const data = (await response.json()) as UploadResponse;

      setUploadState("success");
      setUploadedDocumentId(data.document_id);
      setUploadMessage(`上传成功：${data.title}`);
      await loadDocuments();
    } catch (error) {
      setUploadState("error");
      setUploadMessage(error instanceof Error ? error.message : "上传失败，请稍后重试。");
    }
  }

  function startRename(document: DocumentItem) {
    // 开始重命名时，把当前标题放进输入框，方便用户基于原标题修改。
    setEditingDocumentId(document.document_id);
    setEditingTitle(document.title);
    setDocumentActionMessage("");
  }

  function cancelRename() {
    // 取消编辑时清空编辑状态，不提交任何请求。
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
      const response = await fetch(`/api/documents/${documentId}`, {
        method: "PATCH",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({ title: nextTitle }),
      });

      if (!response.ok) {
        const errorData = (await response.json().catch(() => null)) as { detail?: string } | null;
        throw new Error(errorData?.detail ?? `重命名失败，HTTP 状态码：${response.status}`);
      }

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
    // 删除是不可恢复操作，所以先用浏览器确认框向用户确认。
    const confirmed = window.confirm(
      `确定要删除“${document.title}”吗？这会同时删除数据库记录、页面记录和本地 PDF 文件。`,
    );

    if (!confirmed) {
      return;
    }

    setDocumentActionState({ documentId: document.document_id, action: "deleting" });
    setDocumentActionMessage("");

    try {
      const response = await fetch(`/api/documents/${document.document_id}`, {
        method: "DELETE",
      });

      if (!response.ok) {
        const errorData = (await response.json().catch(() => null)) as { detail?: string } | null;
        throw new Error(errorData?.detail ?? `删除失败，HTTP 状态码：${response.status}`);
      }

      if (editingDocumentId === document.document_id) {
        cancelRename();
      }

      setDocumentActionMessage("文档已删除。");
      await loadDocuments();
    } catch (error) {
      setDocumentActionMessage(error instanceof Error ? error.message : "删除失败，请稍后重试。");
    } finally {
      setDocumentActionState(null);
    }
  }

  return (
    <main className="app-shell">
      <section className="status-panel">
        <p className="eyebrow">Slides Reader</p>
        <h1>AI slides 阅读与授课工具</h1>
        <p className="description">
          上传 PDF 格式的 slides，后端会保存文件并返回本次上传的 document_id。
        </p>

        <div className={`connection-card connection-card--${connectionState}`}>
          <span className="status-dot" />
          <div>
            <strong>{connectionState === "checking" ? "正在连接后端" : message}</strong>
            <p>
              {connectionState === "success"
                ? "现在可以上传 PDF slides。"
                : "请先启动后端，再刷新当前前端页面。"}
            </p>
          </div>
        </div>

        <form className="upload-panel" onSubmit={handleUploadSubmit}>
          <div>
            <h2>上传 PDF slides</h2>
            <p>请选择 `.pdf` 格式文件。上传成功后，页面会显示后端生成的 document_id。</p>
          </div>

          <label className="file-input-label">
            <span>选择 PDF 文件</span>
            <input type="file" accept="application/pdf,.pdf" onChange={handleFileChange} />
          </label>

          <button
            className="upload-button"
            type="submit"
            disabled={!selectedFile || uploadState === "uploading"}
          >
            {uploadState === "uploading" ? "上传中..." : "上传 PDF"}
          </button>

          <div className={`upload-message upload-message--${uploadState}`}>{uploadMessage}</div>

          {uploadedDocumentId ? (
            <div className="document-id-box">
              <span>document_id</span>
              <code>{uploadedDocumentId}</code>
            </div>
          ) : null}
        </form>

        <section className="documents-panel">
          <div>
            <h2>已上传文档</h2>
            <p>这些记录来自 SQLite 数据库，后端重启后仍然会保留。</p>
          </div>

          {documents.length > 0 ? (
            <ul className="document-list">
              {documents.map((document) => (
                <li className="document-list-item" key={document.document_id}>
                  <div className="document-header">
                    {editingDocumentId === document.document_id ? (
                      <div className="rename-form">
                        <label>
                          <span>新标题</span>
                          <input
                            value={editingTitle}
                            onChange={(event) => setEditingTitle(event.target.value)}
                            disabled={isDocumentBusy(document.document_id)}
                          />
                        </label>
                        <div className="document-actions">
                          <button
                            type="button"
                            onClick={() => saveRename(document.document_id)}
                            disabled={isDocumentBusy(document.document_id)}
                          >
                            {documentActionState?.documentId === document.document_id &&
                            documentActionState.action === "renaming"
                              ? "保存中..."
                              : "保存"}
                          </button>
                          <button
                            type="button"
                            className="secondary-button"
                            onClick={cancelRename}
                            disabled={isDocumentBusy(document.document_id)}
                          >
                            取消
                          </button>
                        </div>
                      </div>
                    ) : (
                      <div>
                        <strong>{document.title}</strong>
                        <span>{formatCreatedAt(document.created_at)}</span>
                      </div>
                    )}
                    <div className="document-actions">
                      <button
                        type="button"
                        className="secondary-button"
                        onClick={() => startRename(document)}
                        disabled={isDocumentBusy(document.document_id)}
                      >
                        重命名
                      </button>
                      <button
                        type="button"
                        className="danger-button"
                        onClick={() => deleteDocument(document)}
                        disabled={isDocumentBusy(document.document_id)}
                      >
                        {documentActionState?.documentId === document.document_id &&
                        documentActionState.action === "deleting"
                          ? "删除中..."
                          : "删除"}
                      </button>
                    </div>
                  </div>
                  <dl>
                    <div>
                      <dt>document_id</dt>
                      <dd>{document.document_id}</dd>
                    </div>
                    <div>
                      <dt>状态</dt>
                      <dd>
                        <span className={`document-status document-status--${document.status}`}>
                          {getStatusLabel(document.status)}
                        </span>
                      </dd>
                    </div>
                    <div>
                      <dt>总页数</dt>
                      <dd>{document.page_count}</dd>
                    </div>
                  </dl>
                  {document.error_message ? (
                    <p className="document-error">{document.error_message}</p>
                  ) : null}
                </li>
              ))}
            </ul>
          ) : (
            <p className="documents-empty">{documentsMessage}</p>
          )}

          {documentActionMessage ? (
            <p className="document-action-message">{documentActionMessage}</p>
          ) : null}
        </section>
      </section>
    </main>
  );
}

export default App;
