/**
 * 呼叫後端 API。型別來自 schema.d.ts，由 scripts/gen-api-types.sh 從 FastAPI 產生。
 */
import type { components } from "./schema";

/** 職缺欄位契約的欄位；抓取的預覽還沒存入，只有這些欄位 */
export type JobFields = components["schemas"]["JobFields"];

/** 職缺資料庫的一筆職缺：職缺欄位契約的欄位，接著是首次、最後出現時間 */
export type Job = components["schemas"]["Job"];

type JobList = components["schemas"]["JobList"];

/** 取出職缺資料庫的全部職缺，排序為最後出現時間由新到舊 */
export async function fetchJobs(): Promise<Job[]> {
  const response = await fetch("/api/jobs");
  if (!response.ok) {
    throw new Error(`讀取職缺失敗（HTTP ${response.status}）`);
  }
  const body = (await response.json()) as JobList;
  return body.jobs;
}

/**
 * 從失敗的回應取出給人看的原因。
 *
 * 端點自己擋下的錯誤 detail 是一句話；FastAPI 驗證失敗時是一串錯誤，逐條取出 msg。
 */
export async function errorMessage(response: Response): Promise<string> {
  try {
    const body = (await response.json()) as { detail?: unknown };
    if (typeof body.detail === "string") return body.detail;
    if (Array.isArray(body.detail)) {
      const messages = body.detail
        .map((item: unknown) =>
          typeof item === "object" && item !== null && "msg" in item ? String(item.msg) : null,
        )
        .filter((msg): msg is string => msg !== null);
      if (messages.length > 0) return messages.join("；");
    }
  } catch {
    // 回應不是 JSON 時改用狀態碼
  }
  return `HTTP ${response.status}`;
}
