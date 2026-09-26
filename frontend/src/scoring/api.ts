/**
 * 評分的 API。型別來自 schema.d.ts，由 scripts/gen-api-types.sh 從 FastAPI 產生。
 */
import { errorMessage } from "../api/client";
import type { components } from "../api/schema";

/** 一筆職缺代表的評分：職缺表的評分欄位、排序與篩選都用它 */
export type CurrentScore = components["schemas"]["CurrentScore"];
export type ScoreRecord = components["schemas"]["ScoreRecord"];
export type Basis = components["schemas"]["Basis"];
export type Plan = components["schemas"]["Plan"];
export type ScoringState = components["schemas"]["ScoringState"];
export type RunOut = components["schemas"]["RunOut"];
export type RowStatus = components["schemas"]["RowStatus"];

type ScoreList = components["schemas"]["ScoreList"];
type ScoreHistory = components["schemas"]["ScoreHistory"];
type Started = components["schemas"]["Started"];

/** 開始評分被擋下：開始前的檢查有錯，errors 是要顯示在確認視窗的原因 */
export class ScoringRejected extends Error {
  readonly errors: string[];

  constructor(errors: string[]) {
    super(errors.join("；"));
    this.errors = errors;
  }
}

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

/** 各職缺代表的評分，以職缺代碼查詢；沒評過的職缺不在其中 */
export async function fetchScores(): Promise<Map<string, CurrentScore>> {
  const body = (await (await request("/api/scores")).json()) as ScoreList;
  return new Map(body.scores.map((score) => [score.職缺代碼, score]));
}

/** 一筆職缺的所有評分紀錄，由新到舊，第一筆是代表的評分 */
export async function fetchScoreHistory(code: string): Promise<ScoreRecord[]> {
  const response = await request(`/api/scores/${encodeURIComponent(code)}`);
  return ((await response.json()) as ScoreHistory).records;
}

/** 確認視窗的內容與開始前的錯誤；codes 依職缺表的顯示順序 */
export async function planScoring(codes: string[], rescore: boolean): Promise<Plan> {
  return (await (await request("/api/scoring/plan", post({ codes, rescore }))).json()) as Plan;
}

/**
 * 開始評分，回傳作業的編號。
 *
 * 開始時後端重讀目前設定、重做檢查，有錯時丟出 ScoringRejected；其他失敗（例如已有作業在跑）丟出 Error。
 */
export async function startScoring(body: {
  codes: string[];
  rescore: boolean;
  model: string;
}): Promise<number> {
  const response = await fetch("/api/scoring", post(body));
  if (response.status === 422) {
    const detail = ((await response.clone().json()) as { detail?: unknown }).detail;
    if (Array.isArray(detail) && detail.every((item) => typeof item === "string")) {
      throw new ScoringRejected(detail);
    }
  }
  if (!response.ok) throw new Error(await errorMessage(response));
  return ((await response.json()) as Started).run_id;
}

export async function fetchScoringState(): Promise<ScoringState> {
  return (await (await request("/api/scoring")).json()) as ScoringState;
}

export async function stopScoring(): Promise<void> {
  await request("/api/scoring/stop", { method: "POST" });
}
