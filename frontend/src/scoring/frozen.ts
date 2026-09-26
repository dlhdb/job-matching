/**
 * 評分中固定的列順序：開始評分時記下職缺表列出的職缺與檢視，改篩選或排序時才重新排列。
 *
 * 記在瀏覽器，評分中重新整理後，同一個作業還在跑時沿用。
 */
import { isRecord } from "../job-database/view";

export const FROZEN_STORAGE_KEY = "jobAutoScoring.frozen.v1";

export interface Frozen {
  /** 開始的評分作業 */
  runId: number;
  /** 開始時職缺表的檢視，見 TableContext.viewKey */
  viewKey: string;
  /** 開始時列出的職缺代碼，依顯示的順序 */
  codes: string[];
}

/** 從記住的內容還原；格式不對時為 null */
export function parseFrozen(raw: unknown): Frozen | null {
  if (
    isRecord(raw) &&
    typeof raw.runId === "number" &&
    typeof raw.viewKey === "string" &&
    Array.isArray(raw.codes) &&
    raw.codes.every((code) => typeof code === "string")
  ) {
    return { runId: raw.runId, viewKey: raw.viewKey, codes: raw.codes as string[] };
  }
  return null;
}

/** 這個檢視下固定的列順序；檢視和開始時不同時不固定 */
export function frozenOrder(frozen: Frozen | null, viewKey: string): string[] | null {
  return frozen !== null && frozen.viewKey === viewKey ? frozen.codes : null;
}
