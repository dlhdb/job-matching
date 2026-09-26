/**
 * 職缺表的檢視：顯示的欄位、排序與篩選，記在瀏覽器，下次打開時沿用。
 */
import { DEFAULT_COLUMNS, JOB_COLUMNS } from "./columns";
import { EMPTY_FILTERS, type Filters } from "./filter";
import type { Sort } from "./sort";

export interface View {
  columns: string[];
  sort: Sort;
  filters: Filters;
}

/** 記在 localStorage 的鍵；結構改變時換版本號，舊的記錄就不會被誤讀 */
export const VIEW_STORAGE_KEY = "jobDatabase.view.v1";

export const DEFAULT_VIEW: View = {
  columns: DEFAULT_COLUMNS,
  sort: { key: "最後出現時間", dir: "desc" },
  filters: EMPTY_FILTERS,
};

const KNOWN_COLUMNS = new Set(JOB_COLUMNS.map((c) => c.key));

const isRecord = (value: unknown): value is Record<string, unknown> =>
  typeof value === "object" && value !== null && !Array.isArray(value);

/**
 * 從記住的內容還原檢視：逐項檢查，不合法的項目退回預設，其他項目照用。
 *
 * 記住的內容可能來自舊版或被手動改過，欄位不存在、方向不對都不應讓職缺表打不開。
 */
export function parseView(raw: unknown): View {
  if (!isRecord(raw)) return DEFAULT_VIEW;

  const columns = Array.isArray(raw.columns)
    ? [...new Set(raw.columns)].filter(
        (k): k is string => typeof k === "string" && KNOWN_COLUMNS.has(k),
      )
    : [];

  const sort = raw.sort;
  const validSort =
    isRecord(sort) &&
    typeof sort.key === "string" &&
    KNOWN_COLUMNS.has(sort.key) &&
    (sort.dir === "asc" || sort.dir === "desc");

  const filters = { ...EMPTY_FILTERS };
  if (isRecord(raw.filters)) {
    for (const key of Object.keys(filters) as (keyof Filters)[]) {
      const value = raw.filters[key];
      if (typeof value === "string") filters[key] = value;
    }
  }

  return {
    columns: columns.length > 0 ? columns : DEFAULT_VIEW.columns,
    sort: validSort ? { key: sort.key as string, dir: sort.dir as Sort["dir"] } : DEFAULT_VIEW.sort,
    filters,
  };
}

/**
 * 「還原預設檢視」後的檢視。只看剛存入的職缺時篩選暫停，只還原欄位與排序，篩選維持原樣。
 */
export function resetView(current: View, justSavedActive: boolean): View {
  return justSavedActive ? { ...DEFAULT_VIEW, filters: current.filters } : DEFAULT_VIEW;
}
