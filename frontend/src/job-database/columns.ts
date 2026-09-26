/**
 * 職缺表的欄位：可以選的欄位、預設顯示的欄位，以及勾選欄位的規則。
 */
import type { Job, JobFields } from "../api/client";

/** 表格的一個欄位，key 同時是標題 */
export interface Column<Row> {
  key: string;
  /** 數字欄：靠右對齊，第一次點標題時由大到小排序 */
  numeric?: boolean;
  /** clip：過長時截斷；nowrap：不換行 */
  className?: "clip" | "nowrap";
  /** 這一列在這一欄的值，排序與顯示都用它；null 或空字串代表沒有值 */
  value: (row: Row) => string | number | null;
  /** 顯示用的格式；沒有時數字加千分位，文字照原樣 */
  format?: (value: string | number) => string;
}

/** ISO 8601 的時間改用空白分開日期與時間，比較好讀 */
export const showTime = (value: string | number) => String(value).replace("T", " ");

type ColumnOptions = Pick<Column<unknown>, "numeric" | "className" | "format">;

function fieldColumn(key: keyof JobFields & string, options: ColumnOptions = {}) {
  return { key, value: (job: JobFields) => job[key], ...options } satisfies Column<JobFields>;
}

/** 職缺欄位契約的全部欄位，依契約的順序；抓取的預覽只能選這些 */
export const CONTRACT_COLUMNS: Column<JobFields>[] = [
  fieldColumn("職缺代碼", { className: "nowrap" }),
  fieldColumn("職缺名稱", { className: "clip" }),
  fieldColumn("公司名稱", { className: "clip" }),
  fieldColumn("產業類別", { className: "nowrap" }),
  fieldColumn("地區", { className: "clip" }),
  fieldColumn("薪資待遇", { className: "nowrap" }),
  fieldColumn("薪資下限", { numeric: true }),
  fieldColumn("薪資上限", { numeric: true }),
  fieldColumn("更新日期", { className: "nowrap" }),
  fieldColumn("應徵人數", { numeric: true }),
  fieldColumn("工作內容", { className: "clip" }),
  fieldColumn("電腦專長", { className: "clip" }),
  fieldColumn("科系要求", { className: "clip" }),
  fieldColumn("特色標籤", { className: "clip" }),
  fieldColumn("職缺連結", { className: "clip" }),
  fieldColumn("公司連結", { className: "clip" }),
];

function timeColumn(key: "首次出現時間" | "最後出現時間") {
  return {
    key,
    value: (job: Job) => job[key],
    className: "nowrap",
    format: showTime,
  } satisfies Column<Job>;
}

/** 職缺表可以選的欄位：職缺欄位契約的全部欄位，接著是首次、最後出現時間 */
export const JOB_COLUMNS: Column<Job>[] = [
  ...CONTRACT_COLUMNS,
  timeColumn("首次出現時間"),
  timeColumn("最後出現時間"),
];

/** 第一次打開職缺表時顯示的欄位 */
export const DEFAULT_COLUMNS = ["職缺名稱", "公司名稱", "地區", "薪資待遇", "最後出現時間"];

/**
 * 勾選或取消勾選一個欄位，回傳新的顯示欄位。
 *
 * 勾選時依可選欄位的順序插入；取消的是最後一欄時不變，表格至少留一欄。
 */
export function toggleColumn(
  order: string[],
  visible: string[],
  key: string,
  checked: boolean,
): string[] {
  if (checked) {
    return order.filter((k) => k === key || visible.includes(k));
  }
  if (visible.length === 1 && visible[0] === key) {
    return visible;
  }
  return visible.filter((k) => k !== key);
}
