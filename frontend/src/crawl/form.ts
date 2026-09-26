/**
 * 抓取的條件：表單的值、記在瀏覽器的上次條件，以及開始前的檢查。
 */
import type { CrawlRequest } from "./api";
import { isRecord } from "../job-database/view";

/** 表單的值，和表單元件一樣都是字串；area 是空字串代表全台灣 */
export interface CrawlFormValues {
  keyword: string;
  area: string;
  pages: string;
  jobType: "0" | "1" | "2";
}

/** 記在 localStorage 的鍵；結構改變時換版本號，舊的記錄就不會被誤讀 */
export const FORM_STORAGE_KEY = "crawl.form.v1";

export const DEFAULT_FORM: CrawlFormValues = { keyword: "", area: "", pages: "3", jobType: "0" };

const JOB_TYPES = ["0", "1", "2"] as const;

const isPositiveInteger = (value: string) => /^[1-9]\d*$/.test(value.trim());

const isJobType = (value: unknown): value is CrawlFormValues["jobType"] =>
  JOB_TYPES.some((t) => t === value);

/** 至少有一個關鍵字：只有空白與逗號時不算 */
export function hasKeyword(keyword: string): boolean {
  return keyword.split(/[,，]/).some((k) => k.trim() !== "");
}

/**
 * 從記住的內容還原表單：逐欄檢查，不合法的欄位退回預設，其他欄位照用。
 *
 * 縣市清單可能改過，記著的縣市不在 areas 裡時也退回全台灣。
 */
export function parseForm(raw: unknown, areas: string[]): CrawlFormValues {
  if (!isRecord(raw)) return DEFAULT_FORM;
  return {
    keyword: typeof raw.keyword === "string" ? raw.keyword : DEFAULT_FORM.keyword,
    area:
      typeof raw.area === "string" && (raw.area === "" || areas.includes(raw.area))
        ? raw.area
        : DEFAULT_FORM.area,
    pages:
      typeof raw.pages === "string" && isPositiveInteger(raw.pages)
        ? raw.pages.trim()
        : DEFAULT_FORM.pages,
    jobType: isJobType(raw.jobType) ? raw.jobType : DEFAULT_FORM.jobType,
  };
}

/** 開始抓取前的檢查；可以開始時回傳 null，否則回傳說明 */
export function formError(form: CrawlFormValues): string | null {
  if (!hasKeyword(form.keyword)) return "至少要有一個關鍵字";
  if (!isPositiveInteger(form.pages)) return "頁數要是正整數";
  return null;
}

/** 轉成開始抓取的請求；先以 formError 確認可以開始 */
export function toRequest(form: CrawlFormValues, discardPreview: boolean): CrawlRequest {
  return {
    keyword: form.keyword,
    area: form.area === "" ? null : form.area,
    pages: Number(form.pages.trim()),
    job_type: Number(form.jobType) as CrawlRequest["job_type"],
    discard_preview: discardPreview,
  };
}
