/**
 * 職缺表的欄位：可以選的欄位、預設顯示的欄位，以及勾選欄位的規則。
 */
import type { Job } from "../api/client";

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

type JobKey = keyof Job & string;

function jobColumn(
  key: JobKey,
  options: Pick<Column<Job>, "numeric" | "className" | "format"> = {},
) {
  return { key, value: (job: Job) => job[key], ...options } satisfies Column<Job>;
}

/** 可以選的欄位：職缺欄位契約的全部欄位，接著是首次、最後出現時間 */
export const JOB_COLUMNS: Column<Job>[] = [
  jobColumn("職缺代碼", { className: "nowrap" }),
  jobColumn("職缺名稱", { className: "clip" }),
  jobColumn("公司名稱", { className: "clip" }),
  jobColumn("產業類別", { className: "nowrap" }),
  jobColumn("地區", { className: "clip" }),
  jobColumn("薪資待遇", { className: "nowrap" }),
  jobColumn("薪資下限", { numeric: true }),
  jobColumn("薪資上限", { numeric: true }),
  jobColumn("更新日期", { className: "nowrap" }),
  jobColumn("應徵人數", { numeric: true }),
  jobColumn("工作內容", { className: "clip" }),
  jobColumn("電腦專長", { className: "clip" }),
  jobColumn("科系要求", { className: "clip" }),
  jobColumn("特色標籤", { className: "clip" }),
  jobColumn("職缺連結", { className: "clip" }),
  jobColumn("公司連結", { className: "clip" }),
  jobColumn("首次出現時間", { className: "nowrap", format: showTime }),
  jobColumn("最後出現時間", { className: "nowrap", format: showTime }),
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
