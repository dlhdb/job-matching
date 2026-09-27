/**
 * 試跑的共用狀態：試跑作業的進度與結果，頁首與設定頁都從這裡取。
 */
import { createContext, useContext } from "react";

import type { DryRunState } from "./api";

export interface DryRunContextValue {
  /** 試跑作業的狀態；還沒讀到時為 null */
  state: DryRunState | null;
  /** 取不到最新狀態時的原因；下次取到時消失 */
  pollError: string | null;
  /** 馬上重新取一次狀態 */
  refresh: () => Promise<void>;
  stop: () => Promise<void>;
  /** 試跑中按停止卻失敗的原因 */
  stopError: string | null;
}

export const DryRunContext = createContext<DryRunContextValue | null>(null);

export function useDryRun(): DryRunContextValue {
  const value = useContext(DryRunContext);
  if (value === null) throw new Error("useDryRun 要在 DryRunProvider 裡使用");
  return value;
}
