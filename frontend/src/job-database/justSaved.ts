/**
 * 只看剛存入的職缺：存入職缺的一方以 ?saved=代碼,代碼 打開職缺表。
 *
 * 這是暫時的篩選，只看網址，不寫進記在瀏覽器的檢視。
 */
import type { Job } from "../api/client";

/** 網址上帶剛存入的職缺代碼的參數名稱 */
export const SAVED_PARAM = "saved";

/** 取出網址帶來的職缺代碼（去掉空白與重複）；沒有帶、或只有逗號與空白時回傳 null */
export function parseSavedCodes(params: URLSearchParams): string[] | null {
  const raw = params.get(SAVED_PARAM);
  if (raw === null) return null;
  const codes = [
    ...new Set(
      raw
        .split(",")
        .map((c) => c.trim())
        .filter(Boolean),
    ),
  ];
  return codes.length > 0 ? codes : null;
}

/**
 * 只留下代碼在清單中的職缺，其他篩選不套用。
 *
 * 回傳的筆數就是標籤上的 N：資料庫裡沒有的代碼不算。
 */
export function pickJustSaved(jobs: Job[], codes: string[]): Job[] {
  const wanted = new Set(codes);
  return jobs.filter((job) => wanted.has(job.職缺代碼));
}
