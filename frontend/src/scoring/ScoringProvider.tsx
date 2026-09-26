import { useCallback, useEffect, useRef, useState, type ReactNode } from "react";

import { readStore, writeStore } from "../lib/storage";
import {
  fetchScores,
  fetchScoringState,
  stopScoring,
  type CurrentScore,
  type ScoringState,
} from "./api";
import { ScoringContext } from "./context";
import { FROZEN_STORAGE_KEY, parseFrozen, type Frozen } from "./frozen";

const POLL_MS = 1000;
const RETRY_MS = 2000;

const messageOf = (error: unknown) => (error instanceof Error ? error.message : String(error));

/**
 * 評分的共用狀態：打開頁面時取一次評分作業的狀態與各職缺代表的評分，評分中每秒更新。
 *
 * 評分作業在伺服器上跑，切到別的分頁或重新整理都接得回進度。結束後的摘要與失敗標示
 * 只給這次打開頁面時看過它在跑的作業，所以評分結束後重新整理，失敗標示就消失。
 */
export function ScoringProvider({ children }: { children: ReactNode }) {
  const [scores, setScores] = useState<Map<string, CurrentScore> | null>(null);
  const [scoresError, setScoresError] = useState<string | null>(null);
  const [state, setState] = useState<ScoringState | null>(null);
  const [pollError, setPollError] = useState<string | null>(null);
  // 這次打開頁面後看過在跑的作業
  const [seen, setSeen] = useState<ReadonlySet<number>>(() => new Set());
  const [dismissed, setDismissed] = useState<number | null>(null);
  const [frozen, setFrozenState] = useState<Frozen | null>(null);
  // 停止失敗的原因與是哪一個作業；只在那個作業還在跑時顯示
  const [stopError, setStopError] = useState<{ runId: number; message: string } | null>(null);
  const runningId = useRef<number | null>(null);

  const markSeen = useCallback((runId: number) => {
    setSeen((prev) => (prev.has(runId) ? prev : new Set(prev).add(runId)));
  }, []);

  // 評分中重新整理時，同一個作業還在跑就沿用固定的列順序；在第一次取到狀態時決定，不論是哪一次查詢
  const restored = useRef(false);
  const applyState = useCallback(
    (next: ScoringState) => {
      setState(next);
      setPollError(null);
      runningId.current = next.running?.id ?? null;
      if (next.running) markSeen(next.running.id);
      if (!restored.current) {
        restored.current = true;
        const stored = parseFrozen(readStore(FROZEN_STORAGE_KEY));
        if (stored !== null && stored.runId === next.running?.id) setFrozenState(stored);
      }
    },
    [markSeen],
  );

  // 最後一次送出的查詢；比它早送出的回應晚到時不採用
  const latestRefresh = useRef(0);
  const refresh = useCallback(async () => {
    const id = ++latestRefresh.current;
    try {
      const next = await fetchScoringState();
      if (id === latestRefresh.current) applyState(next);
    } catch (error) {
      if (id !== latestRefresh.current) return;
      setPollError(`取不到評分的最新狀態：${messageOf(error)}`);
    }
  }, [applyState]);

  useEffect(() => {
    const id = ++latestRefresh.current;
    fetchScoringState()
      .then((next) => {
        if (id === latestRefresh.current) applyState(next);
      })
      .catch((error: unknown) => {
        if (id === latestRefresh.current) {
          setPollError(`取不到評分的最新狀態：${messageOf(error)}`);
        }
      });
  }, [applyState]);

  // 評分中持續取進度；取不到狀態時也持續重試。收到回應後才排下一次
  const shouldPoll = state?.running != null || pollError !== null;
  useEffect(() => {
    if (!shouldPoll) return;
    let cancelled = false;
    let timer: ReturnType<typeof setTimeout>;
    const tick = async () => {
      await refresh();
      if (!cancelled) timer = setTimeout(() => void tick(), POLL_MS);
    };
    timer = setTimeout(() => void tick(), POLL_MS);
    return () => {
      cancelled = true;
      clearTimeout(timer);
    };
  }, [shouldPoll, refresh]);

  // 打開頁面、評完一筆、作業結束時重新取各職缺的評分；取不到時每隔一段時間自動重試。
  // 不等評分作業的狀態：狀態取不到時，職缺表仍列得出來
  const running = state?.running ?? null;
  const last = state?.last ?? null;
  const scoresKey = `${running?.id}:${running?.done}:${last?.id}`;
  const [scoresRetry, setScoresRetry] = useState(0);
  useEffect(() => {
    let cancelled = false;
    let timer: ReturnType<typeof setTimeout> | undefined;
    fetchScores()
      .then((next) => {
        if (cancelled) return;
        setScores(next);
        setScoresError(null);
      })
      .catch((error: unknown) => {
        if (cancelled) return;
        setScoresError(`讀不到評分：${messageOf(error)}，稍後自動重試`);
        timer = setTimeout(() => setScoresRetry((n) => n + 1), RETRY_MS);
      });
    return () => {
      cancelled = true;
      clearTimeout(timer);
    };
  }, [scoresKey, scoresRetry]);

  const setFrozen = useCallback((next: Frozen | null) => {
    setFrozenState(next);
    writeStore(FROZEN_STORAGE_KEY, next);
  }, []);

  const started = useCallback(
    async (runId: number) => {
      // 很快就評完時，下一次取狀態可能已經結束，先記下看過它
      markSeen(runId);
      await refresh();
    },
    [markSeen, refresh],
  );

  // 停止失敗的原因另外記：輪詢成功時會清掉 pollError，停止失敗的原因不能跟著消失
  const stop = useCallback(async () => {
    const runId = runningId.current;
    try {
      await stopScoring();
      setStopError(null);
    } catch (error) {
      if (runId !== null) setStopError({ runId, message: `停止失敗：${messageOf(error)}` });
    }
    await refresh();
  }, [refresh]);

  const seenLast = running === null && last !== null && seen.has(last.id) ? last : null;
  const shown = running ?? seenLast;
  const statuses = new Map((shown?.statuses ?? []).map((status) => [status.code, status]));

  return (
    <ScoringContext.Provider
      value={{
        scores,
        scoresError,
        state,
        pollError,
        statuses,
        finished: seenLast !== null && seenLast.id !== dismissed ? seenLast : null,
        dismissSummary: () => setDismissed(seenLast?.id ?? null),
        frozen,
        setFrozen,
        refresh,
        started,
        stop,
        stopError: stopError !== null && stopError.runId === running?.id ? stopError.message : null,
      }}
    >
      {children}
    </ScoringContext.Provider>
  );
}
