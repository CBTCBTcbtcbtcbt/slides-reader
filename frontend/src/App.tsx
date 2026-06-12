import { useEffect, useState } from "react";

type HealthState = "checking" | "success" | "error";

type UploadState = "idle" | "uploading" | "success" | "error";

type HealthResponse = {
  status: string;
  service: string;
};

type UploadResponse = {
  document_id: string;
  filename: string;
  saved_filename: string;
};

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
      setUploadMessage(`上传成功：${data.filename}`);
    } catch (error) {
      setUploadState("error");
      setUploadMessage(error instanceof Error ? error.message : "上传失败，请稍后重试。");
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
      </section>
    </main>
  );
}

export default App;
