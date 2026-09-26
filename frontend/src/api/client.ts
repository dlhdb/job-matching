/**
 * 呼叫後端 API。型別來自 schema.d.ts，由 scripts/gen-api-types.sh 從 FastAPI 產生。
 */
import type { components } from "./schema";

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
