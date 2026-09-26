/**
 * 職缺表的關鍵字與地區篩選。
 */
import type { Job } from "../api/client";

export interface Filters {
  keyword: string;
  area: string;
}

/** 不篩選 */
export const EMPTY_FILTERS: Filters = { keyword: "", area: "" };

/** 比對前的整理：去掉前後空白、不分大小寫、「臺」換成「台」 */
export function normalize(text: string): string {
  return text.trim().toLowerCase().replace(/臺/g, "台");
}

/** 以半形或全形逗號拆開輸入；只有空白或逗號時是空陣列 */
export function terms(input: string): string[] {
  return input.split(/[,，]/).map(normalize).filter(Boolean);
}

/** text 含任一個詞就算符合；沒有輸入時一律符合 */
export function anyTerm(text: string | null, input: string): boolean {
  const wanted = terms(input);
  if (wanted.length === 0) return true;
  const haystack = normalize(text ?? "");
  return wanted.some((term) => haystack.includes(term));
}

/**
 * 職缺是否符合篩選：關鍵字比對職缺名稱、公司名稱、工作內容、電腦專長，地區只比對地區，
 * 兩個都有輸入時都要符合。
 */
export function matchesFilters(job: Job, filters: Filters): boolean {
  // 以換行接起來，一個詞不會橫跨兩個欄位
  const keywordText = [job.職缺名稱, job.公司名稱, job.工作內容, job.電腦專長]
    .filter((v) => v !== null)
    .join("\n");
  return anyTerm(keywordText, filters.keyword) && anyTerm(job.地區, filters.area);
}
