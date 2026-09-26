/**
 * 抓取頁的 API。型別來自 schema.d.ts，由 scripts/gen-api-types.sh 從 FastAPI 產生。
 */
import { errorMessage } from "../api/client";
import type { components } from "../api/schema";

/** 抓取的狀態：抓取中的進度、沒存入的預覽，或最近一次沒有結果的原因 */
export type CrawlState = components["schemas"]["CrawlState"];
export type Running = components["schemas"]["Running"];
export type CrawlRequest = components["schemas"]["CrawlRequest"];

type AreaList = components["schemas"]["AreaList"];
type SavedCodes = components["schemas"]["SavedCodes"];

async function request(path: string, init?: RequestInit): Promise<Response> {
  const response = await fetch(path, init);
  if (!response.ok) throw new Error(await errorMessage(response));
  return response;
}

/** 可以選的縣市，依選單的順序 */
export async function fetchAreas(): Promise<string[]> {
  const body = (await (await request("/api/crawl/areas")).json()) as AreaList;
  return body.areas;
}

export async function fetchCrawlState(): Promise<CrawlState> {
  return (await (await request("/api/crawl")).json()) as CrawlState;
}

/** 開始抓取；已有作業在跑、條件不合法等情況丟出帶著原因的 Error */
export async function startCrawl(body: CrawlRequest): Promise<void> {
  await request("/api/crawl", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}

export async function stopCrawl(): Promise<void> {
  await request("/api/crawl/stop", { method: "POST" });
}

/** 把預覽整批存入職缺資料庫，回傳存入的職缺代碼；失敗時丟出帶著原因的 Error，預覽保留 */
export async function savePreview(): Promise<string[]> {
  const body = (await (await request("/api/crawl/save", { method: "POST" })).json()) as SavedCodes;
  return body.codes;
}

export async function discardPreview(): Promise<void> {
  await request("/api/crawl/preview", { method: "DELETE" });
}
