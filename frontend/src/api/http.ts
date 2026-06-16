// 这个模块封装最基础的 fetch 错误处理。
// 具体业务接口放在 documents.ts 和 llm.ts 中，避免组件里散落 URL 和 JSON 解析。

type ErrorResponse = {
  detail?: string;
};

export async function readErrorMessage(response: Response, fallback: string): Promise<string> {
  // FastAPI 失败时通常返回 { detail: "错误原因" }，优先展示这个字段。
  const errorData = (await response.json().catch(() => null)) as ErrorResponse | null;
  return errorData?.detail ?? fallback;
}

export async function requestJson<T>(url: string, init?: RequestInit, errorPrefix = "请求失败"): Promise<T> {
  // 所有 JSON API 都走这里，统一处理非 2xx HTTP 状态码。
  const response = await fetch(url, init);

  if (!response.ok) {
    const message = await readErrorMessage(
      response,
      `${errorPrefix}，HTTP 状态码：${response.status}`,
    );
    throw new Error(message);
  }

  return (await response.json()) as T;
}

export async function requestNoContent(url: string, init?: RequestInit, errorPrefix = "请求失败"): Promise<void> {
  // 删除接口返回 204，没有 JSON 响应体，所以单独封装。
  const response = await fetch(url, init);

  if (!response.ok) {
    const message = await readErrorMessage(
      response,
      `${errorPrefix}，HTTP 状态码：${response.status}`,
    );
    throw new Error(message);
  }
}
