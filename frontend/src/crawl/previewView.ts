/**
 * 抓取預覽的檢視：顯示的欄位與排序，記在瀏覽器，和職缺表各記各的。
 */
import { CONTRACT_COLUMNS } from "../job-database/columns";
import type { Sort } from "../job-database/sort";
import { isRecord, parseColumns, parseSort } from "../job-database/view";

export interface PreviewView {
  columns: string[];
  sort: Sort;
}

/** 記在 localStorage 的鍵；結構改變時換版本號，舊的記錄就不會被誤讀 */
export const PREVIEW_VIEW_STORAGE_KEY = "crawl.previewView.v1";

export const DEFAULT_PREVIEW_VIEW: PreviewView = {
  columns: ["職缺名稱", "公司名稱", "地區", "薪資待遇", "更新日期"],
  sort: { key: "職缺名稱", dir: "asc" },
};

// 預覽的職缺還沒存入，只能選職缺欄位契約的欄位
const KNOWN_COLUMNS = new Set(CONTRACT_COLUMNS.map((c) => c.key));

/** 從記住的內容還原預覽的檢視：逐項檢查，不合法的項目退回預設 */
export function parsePreviewView(raw: unknown): PreviewView {
  if (!isRecord(raw)) return DEFAULT_PREVIEW_VIEW;
  return {
    columns: parseColumns(raw.columns, KNOWN_COLUMNS, DEFAULT_PREVIEW_VIEW.columns),
    sort: parseSort(raw.sort, KNOWN_COLUMNS, DEFAULT_PREVIEW_VIEW.sort),
  };
}
