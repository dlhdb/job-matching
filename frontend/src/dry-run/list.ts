/**
 * 試跑清單：從職缺表加入的職缺代碼，依加入的順序。
 *
 * 和職缺表的勾選分開，記在瀏覽器：改篩選、送去評分都不會清掉，調整設定時可以反覆拿同一批職缺比較。
 */

export const LIST_STORAGE_KEY = "jobAutoScoring.dryRunList.v1";

/** 從記住的內容還原；格式不對或記不住時是空的清單，重複的只留第一個 */
export function parseList(raw: unknown): string[] {
  if (!Array.isArray(raw)) return [];
  return [...new Set(raw.filter((code): code is string => typeof code === "string"))];
}

/** 加入職缺：已在清單裡的不重複加入，新加入的接在最後 */
export function addToList(
  list: string[],
  codes: string[],
): { list: string[]; added: number; existing: number } {
  const next = [...new Set([...list, ...codes])];
  const added = next.length - list.length;
  return { list: next, added, existing: new Set(codes).size - added };
}

export function removeFromList(list: string[], code: string): string[] {
  return list.filter((c) => c !== code);
}
