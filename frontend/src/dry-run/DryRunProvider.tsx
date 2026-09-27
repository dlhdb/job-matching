import { useCallback, useEffect, useRef, useState, type ReactNode } from "react";

import { fetchDryRunState, stopDryRun, type DryRunState } from "./api";
import { DryRunContext } from "./context";

const POLL_MS = 1000;

const messageOf = (error: unknown) => (error instanceof Error ? error.message : String(error));

/**
 * 試跑的共用狀態：打開頁面時取一次試跑作業的狀態，試跑中每秒更新。
 *
 * 試跑在伺服器上跑，切到別的分頁或重新整理都接得回進度與已完成的結果；
 * 結束後的結果要不要顯示，由設定頁決定。
 */
export function DryRunProvider({ children }: { children: ReactNode }) {
  const [state, setState] = useState<DryRunState | null>(null);
  const [pollError, setPollError] = useState<string | null>(null);
  // 停止失敗的原因與是哪一個試跑；只在那個試跑還在跑時顯示
  const [stopError, setStopError] = useState<{ runId: number; message: string } | null>(null);
  const runningId = useRef<number | null>(null);

  const applyState = useCallback((next: DryRunState) => {
    setState(next);
    setPollError(null);
    runningId.current = next.running?.id ?? null;
  }, []);

  // 最後一次送出的查詢；比它早送出的回應晚到時不採用
  const latestRefresh = useRef(0);
  const refresh = useCallback(async () => {
    const id = ++latestRefresh.current;
    try {
      const next = await fetchDryRunState();
      if (id === latestRefresh.current) applyState(next);
    } catch (error) {
      if (id !== latestRefresh.current) return;
      setPollError(`取不到試跑的最新狀態：${messageOf(error)}`);
    }
  }, [applyState]);

  useEffect(() => {
    const id = ++latestRefresh.current;
    fetchDryRunState()
      .then((next) => {
        if (id === latestRefresh.current) applyState(next);
      })
      .catch((error: unknown) => {
        if (id === latestRefresh.current) {
          setPollError(`取不到試跑的最新狀態：${messageOf(error)}`);
        }
      });
  }, [applyState]);

  // 試跑中持續取進度；取不到狀態時也持續重試。收到回應後才排下一次
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

  // 停止失敗的原因另外記：輪詢成功時會清掉 pollError，停止失敗的原因不能跟著消失
  const stop = useCallback(async () => {
    const runId = runningId.current;
    try {
      await stopDryRun();
      setStopError(null);
    } catch (error) {
      if (runId !== null) setStopError({ runId, message: `停止失敗：${messageOf(error)}` });
    }
    await refresh();
  }, [refresh]);

  const running = state?.running ?? null;
  return (
    <DryRunContext.Provider
      value={{
        state,
        pollError,
        refresh,
        stop,
        stopError: stopError !== null && stopError.runId === running?.id ? stopError.message : null,
      }}
    >
      {children}
    </DryRunContext.Provider>
  );
}
