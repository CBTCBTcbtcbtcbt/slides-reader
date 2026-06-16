// LLM 配置和测试相关 API。

import type { HealthResponse, LLMConfigResponse, LLMConfigUpdatePayload, LLMTestResponse } from "../types/api";
import { requestJson } from "./http";

export function checkHealth(): Promise<HealthResponse> {
  return requestJson<HealthResponse>("/api/health", undefined, "健康检查失败");
}

export function readLlmConfig(): Promise<LLMConfigResponse> {
  return requestJson<LLMConfigResponse>("/api/llm/config", undefined, "LLM 配置加载失败");
}

export function saveLlmConfig(payload: LLMConfigUpdatePayload): Promise<LLMConfigResponse> {
  return requestJson<LLMConfigResponse>(
    "/api/llm/config",
    {
      method: "PATCH",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify(payload),
    },
    "保存失败",
  );
}

export function testLlmConfig(prompt: string): Promise<LLMTestResponse> {
  return requestJson<LLMTestResponse>(
    "/api/llm/test",
    {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ prompt }),
    },
    "测试失败",
  );
}
