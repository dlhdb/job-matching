/**
 * 試跑的 API。型別來自 schema.d.ts，由 scripts/gen-api-types.sh 從 FastAPI 產生。
 */
import { errorMessage } from "../api/client";
import type { components } from "../api/schema";
import { ScoringRejected } from "../scoring/api";

export type DraftsIn = components["schemas"]["DraftsIn"];
export type DryRunPlan = components["schemas"]["DryRunPlan"];
export type DryRunState = components["schemas"]["DryRunState"];
export type DryRunOut = components["schemas"]["DryRunOut"];
export type DryRunRow = components["schemas"]["DryRunRow"];

type DryRunStarted = components["schemas"]["DryRunStarted"];

async function request(path: string, init?: RequestInit): Promise<Response> {
  const response = await fetch(path, init);
  if (!response.ok) throw new Error(await errorMessage(response));
  return response;
}

const post = (body: unknown): RequestInit => ({
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify(body),
});

/** 確認視窗的內容與開始前的錯誤；codes 依試跑清單的顯示順序 */
export async function planDryRun(codes: string[], settings: DraftsIn): Promise<DryRunPlan> {
  const response = await request("/api/dry-run/plan", post({ codes, settings }));
  return (await response.json()) as DryRunPlan;
}

/**
 * 開始試跑，回傳作業的編號。
 *
 * 開始時後端重做檢查，有錯時丟出 ScoringRejected；其他失敗（例如已有作業在跑）丟出 Error。
 */
export async function startDryRun(body: {
  codes: string[];
  settings: DraftsIn;
  model: string;
}): Promise<number> {
  const response = await fetch("/api/dry-run", post(body));
  if (response.status === 422) {
    const detail = ((await response.clone().json()) as { detail?: unknown }).detail;
    if (Array.isArray(detail) && detail.every((item) => typeof item === "string")) {
      throw new ScoringRejected(detail);
    }
  }
  if (!response.ok) throw new Error(await errorMessage(response));
  return ((await response.json()) as DryRunStarted).run_id;
}

export async function fetchDryRunState(): Promise<DryRunState> {
  return (await (await request("/api/dry-run")).json()) as DryRunState;
}

export async function stopDryRun(): Promise<void> {
  await request("/api/dry-run/stop", { method: "POST" });
}
