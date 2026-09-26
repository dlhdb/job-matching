/**
 * 讀寫瀏覽器的 localStorage。
 *
 * 瀏覽器不允許保存（例如封鎖網站資料）時 localStorage 會丟出例外，這裡一律吞掉：
 * 讀不到當成沒有記錄，寫不進去就只在這次開著的頁面有效，都不是錯誤。
 */

/** 讀出記住的值；沒有記錄、讀不到或內容不是 JSON 時回傳 null */
export function readStore(key: string): unknown {
  try {
    const raw = localStorage.getItem(key);
    return raw === null ? null : JSON.parse(raw);
  } catch {
    return null;
  }
}

/** 記住一個值；寫不進去時不理會 */
export function writeStore(key: string, value: unknown): void {
  try {
    localStorage.setItem(key, JSON.stringify(value));
  } catch {
    // 記不住時沿用這次的設定
  }
}
