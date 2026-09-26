/**
 * 抓取中的進度文字與進度條。
 */
import type { Running } from "./api";

export function progressText(running: Running): string {
  if (running.stopping) return "停止中：不再發出新的請求";
  const progress = running.progress;
  if (progress === null) return "準備開始抓取…";
  if (progress.stage === "search") {
    return `搜尋中：「${progress.keyword}」第 ${progress.page}／${progress.pages} 頁，已找到 ${progress.found} 筆不重複的職缺`;
  }
  return `取職缺內容：第 ${progress.index}／${progress.total} 筆（抓完或停止後一次列出）`;
}

/**
 * 進度條的百分比：取職缺內容時依取到第幾筆；搜尋時不知道總共幾頁有結果，回傳 null。
 */
export function progressPercent(running: Running): number | null {
  const progress = running.progress;
  if (progress === null || progress.stage === "search") return null;
  return Math.round(((progress.index - 1) / progress.total) * 100);
}
