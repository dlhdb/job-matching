/**
 * 職缺表的擴充點：其他功能在職缺表上疊加欄位、篩選、展開的內容、勾選與工具列。
 *
 * 職缺表不知道誰在擴充它；由外殼把擴充的 hook 交給 JobTablePage。
 */
import type { ReactNode } from "react";

import type { Job } from "../api/client";
import type { Column } from "./columns";
import type { Sort } from "./sort";
import type { FilterValues } from "./view";

/** 工具列與勾選看得到的職缺表狀態 */
export interface TableContext {
  /** 目前列出的職缺，依顯示的順序 */
  rows: Job[];
  /** 目前的排序與篩選（含只看剛存入的職缺）；相同時列的順序也相同 */
  viewKey: string;
}

export interface JobTableExtension {
  /** 擴充的資料是否讀好；讀好之前職缺表不列出職缺，預設排序才不會在資料到了之後跳動 */
  status: "loading" | "ready" | { error: string };
  /** 接在職缺欄位之後的欄位 */
  columns: Column<Job>[];
  /** 取代職缺表預設的欄位與排序 */
  defaultColumns: string[];
  defaultSort: Sort;
  /** 擴充的篩選的鍵與預設值，和關鍵字、地區一起記在瀏覽器 */
  filterDefaults: Record<string, string>;
  /** 擴充的篩選是否符合；和關鍵字、地區同時生效 */
  matchesFilters: (job: Job, filters: FilterValues) => boolean;
  /** 篩選列中擴充的欄位；只看剛存入的職缺時 disabled */
  renderFilters: (
    filters: FilterValues,
    onChange: (filters: FilterValues) => void,
    disabled: boolean,
  ) => ReactNode;
  /** 展開列在職缺內容之後多加的區塊 */
  renderDetail: (job: Job) => ReactNode;
  /** 每列最前面的標記 */
  rowBadge: (job: Job) => ReactNode;
  /** 勾選的職缺代碼 */
  selection: { selected: ReadonlySet<string>; onChange: (selected: Set<string>) => void };
  /** 工具列的按鈕 */
  renderTools: (context: TableContext) => ReactNode;
  /** 表格上方的訊息 */
  renderBanner: () => ReactNode;
  /** 這個檢視下固定的列順序（職缺代碼）；沒有固定時為 null，照排序與篩選列出 */
  frozenOrder: (viewKey: string) => string[] | null;
  /** 使用者改了排序或篩選（含關掉剛存入的標籤）；只改顯示的欄位不算 */
  onViewChange: (change: { filtersChanged: boolean }) => void;
}

/** 在 JobTablePage 裡呼叫的 hook，回傳擴充；沒有擴充時回傳 null */
export type UseJobTableExtension = () => JobTableExtension | null;

export const useNoExtension: UseJobTableExtension = () => null;
