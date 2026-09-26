/**
 * 職缺表的檢視：顯示的欄位、排序與篩選，記在瀏覽器，下次打開時沿用。
 */
import { DEFAULT_COLUMNS, JOB_COLUMNS } from "./columns";
import { EMPTY_FILTERS, type Filters } from "./filter";
import type { Sort } from "./sort";

/** 篩選：關鍵字、地區，加上擴充的篩選，值都是輸入框或選單的文字 */
export type FilterValues = Filters & Record<string, string>;

export interface View {
  columns: string[];
  sort: Sort;
  filters: FilterValues;
}

/** 記在 localStorage 的鍵；結構或預設改變時換版本號，舊的記錄就不會被誤讀 */
export const VIEW_STORAGE_KEY = "jobDatabase.view.v2";

export const DEFAULT_VIEW: View = {
  columns: DEFAULT_COLUMNS,
  sort: { key: "最後出現時間", dir: "desc" },
  filters: EMPTY_FILTERS,
};

/** 檢視的規則：可以選的欄位與預設檢視；有擴充時兩者都由擴充補上 */
export interface ViewConfig {
  known: Set<string>;
  defaults: View;
}

export const BASE_VIEW_CONFIG: ViewConfig = {
  known: new Set(JOB_COLUMNS.map((c) => c.key)),
  defaults: DEFAULT_VIEW,
};

export const isRecord = (value: unknown): value is Record<string, unknown> =>
  typeof value === "object" && value !== null && !Array.isArray(value);

/**
 * 從記住的內容還原顯示的欄位：去掉重複與不認得的欄位；一欄都不剩時用 fallback。
 */
export function parseColumns(raw: unknown, known: Set<string>, fallback: string[]): string[] {
  const columns = Array.isArray(raw)
    ? [...new Set(raw)].filter((k): k is string => typeof k === "string" && known.has(k))
    : [];
  return columns.length > 0 ? columns : fallback;
}

/** 從記住的內容還原排序：欄位不認得或方向不對時用 fallback */
export function parseSort(raw: unknown, known: Set<string>, fallback: Sort): Sort {
  if (
    isRecord(raw) &&
    typeof raw.key === "string" &&
    known.has(raw.key) &&
    (raw.dir === "asc" || raw.dir === "desc")
  ) {
    return { key: raw.key, dir: raw.dir };
  }
  return fallback;
}

/**
 * 從記住的內容還原檢視：逐項檢查，不合法的項目退回預設，其他項目照用。
 *
 * 記住的內容可能來自舊版或被手動改過，欄位不存在、方向不對都不應讓職缺表打不開。
 * 篩選只認得預設檢視裡有的鍵。
 */
export function parseView(raw: unknown, config: ViewConfig = BASE_VIEW_CONFIG): View {
  const { known, defaults } = config;
  if (!isRecord(raw)) return defaults;

  const filters: FilterValues = { ...defaults.filters };
  if (isRecord(raw.filters)) {
    for (const key of Object.keys(filters)) {
      const value = raw.filters[key];
      if (typeof value === "string") filters[key] = value;
    }
  }

  return {
    columns: parseColumns(raw.columns, known, defaults.columns),
    sort: parseSort(raw.sort, known, defaults.sort),
    filters,
  };
}

/**
 * 「還原預設檢視」後的檢視。只看剛存入的職缺時篩選暫停，只還原欄位與排序，篩選維持原樣。
 */
export function resetView(
  current: View,
  justSavedActive: boolean,
  config: ViewConfig = BASE_VIEW_CONFIG,
): View {
  return justSavedActive ? { ...config.defaults, filters: current.filters } : config.defaults;
}
