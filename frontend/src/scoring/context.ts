/**
 * 評分的共用狀態：各職缺代表的評分與評分作業的進度，職缺表與頁首都從這裡取。
 */
import { createContext, useContext } from "react";

import type { CurrentScore, RowStatus, RunOut, ScoringState } from "./api";
import type { Frozen } from "./frozen";

export interface ScoringContextValue {
  /** 各職缺代表的評分；還沒讀到時為 null */
  scores: Map<string, CurrentScore> | null;
  /** 讀不到評分時的原因 */
  scoresError: string | null;
  /** 評分作業的狀態；還沒讀到時為 null */
  state: ScoringState | null;
  /** 取不到最新狀態時的原因；下次取到時消失 */
  pollError: string | null;
  /** 列上要顯示的狀態：評分中的作業，或這次打開頁面時看過在跑、已經結束的作業 */
  statuses: Map<string, RowStatus>;
  /** 要顯示摘要的作業：這次打開頁面時看過在跑、已經結束、還沒關掉摘要的 */
  finished: RunOut | null;
  dismissSummary: () => void;
  /** 評分中固定的列順序 */
  frozen: Frozen | null;
  setFrozen: (frozen: Frozen | null) => void;
  /** 馬上重新取一次狀態 */
  refresh: () => Promise<void>;
  /** 這個頁面開始了一個評分作業：記下看過它，並取最新的狀態 */
  started: (runId: number) => Promise<void>;
  stop: () => Promise<void>;
  /** 評分中按停止卻失敗的原因 */
  stopError: string | null;
}

export const ScoringContext = createContext<ScoringContextValue | null>(null);

export function useScoring(): ScoringContextValue {
  const value = useContext(ScoringContext);
  if (value === null) throw new Error("useScoring 要在 ScoringProvider 裡使用");
  return value;
}
