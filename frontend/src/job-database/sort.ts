/**
 * 表格的排序：沒有值的排最後，值相同時再以職缺代碼排序。
 */
import type { Column } from "./columns";

export type SortDir = "asc" | "desc";

export interface Sort {
  key: string;
  dir: SortDir;
}

/** 表格的每一列都是職缺，以職缺代碼識別 */
export interface Identified {
  職缺代碼: string;
}

const isEmpty = (value: string | number | null) => value === null || value === "";

// 和資料庫的 ORDER BY 一樣逐字元比較，前後端排出來的順序才一致
const byCode = (a: Identified, b: Identified) =>
  a.職缺代碼 < b.職缺代碼 ? -1 : a.職缺代碼 > b.職缺代碼 ? 1 : 0;

/**
 * 產生依某一欄排序的比較函式。
 *
 * 沒有值（null 或空字串）的列一律排在最後，不論升冪或降冪；
 * 值相同時以職缺代碼由小到大排，同樣的資料每次排出來的順序才一致。
 */
export function makeCompare<Row extends Identified>(column: Column<Row>, dir: SortDir) {
  return (a: Row, b: Row): number => {
    const va = column.value(a);
    const vb = column.value(b);
    if (isEmpty(va)) return isEmpty(vb) ? byCode(a, b) : 1;
    if (isEmpty(vb)) return -1;
    let result =
      typeof va === "number" && typeof vb === "number"
        ? va - vb
        : String(va).localeCompare(String(vb), "zh-Hant");
    if (dir === "desc") result = -result;
    return result || byCode(a, b);
  };
}

/** 依排序設定排好的新陣列；找不到排序的欄位時維持原順序 */
export function sortRows<Row extends Identified>(
  rows: Row[],
  columns: Column<Row>[],
  sort: Sort,
): Row[] {
  const column = columns.find((c) => c.key === sort.key);
  return column ? [...rows].sort(makeCompare(column, sort.dir)) : rows;
}

/**
 * 點一個欄位標題後的排序：再點同一欄反向；換一欄時，數字欄由大到小，其他欄由小到大。
 */
export function nextSort(current: Sort, column: Pick<Column<never>, "key" | "numeric">): Sort {
  if (current.key === column.key) {
    return { key: column.key, dir: current.dir === "asc" ? "desc" : "asc" };
  }
  return { key: column.key, dir: column.numeric ? "desc" : "asc" };
}
