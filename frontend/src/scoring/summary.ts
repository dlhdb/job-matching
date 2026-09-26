/**
 * 評分作業的進度與摘要文字。
 */
import type { RunOut } from "./api";

/** 頁首的進度，例如「評分中 2／5」 */
export function progressText(run: RunOut): string {
  return `評分中 ${run.done}／${run.total}`;
}

export function progressPercent(run: RunOut): number {
  return run.total === 0 ? 0 : Math.round((run.done / run.total) * 100);
}

/**
 * 評完或停止後的摘要：成功、淘汰、失敗各幾筆；停止時加上沒評的筆數，有失敗時說明怎麼補評。
 */
export function summaryText(run: RunOut): string {
  const head = run.stopped ? "已停止" : "評分完成";
  const counts = `評分 ${run.ok} 筆、淘汰 ${run.eliminated} 筆、失敗 ${run.failed} 筆`;
  const skipped = run.stopped ? `、沒評 ${run.skipped} 筆` : "";
  const error = run.error ? `${run.error}。` : "";
  const failed = run.failed > 0 ? "失敗的沒有寫入，列上看得到原因，可以再勾選重評。" : "";
  return `${error}${head}：${counts}${skipped}。${failed}`;
}
