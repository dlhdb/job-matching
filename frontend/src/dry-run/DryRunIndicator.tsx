import { useNavigate } from "react-router-dom";

import { useDryRun } from "./context";

/** 頁首的試跑進度與停止按鈕；試跑中切到任何分頁都看得到，點進度回到設定頁 */
export function DryRunIndicator() {
  const navigate = useNavigate();
  const { state, stop, stopError } = useDryRun();
  const running = state?.running ?? null;
  if (running === null) return null;

  const text = `試跑中 ${running.done}／${running.total}`;
  const percent = running.total === 0 ? 0 : Math.round((running.done / running.total) * 100);
  return (
    <>
      <button
        type="button"
        className="job-indicator"
        aria-label={`${text}，回到設定頁`}
        onClick={() => navigate("/settings")}
      >
        <span role="status">{text}</span>
        <span className="bar">
          <span style={{ width: `${percent}%` }} />
        </span>
      </button>
      <button
        type="button"
        className="btn danger"
        disabled={running.stopping}
        onClick={() => void stop()}
      >
        {running.stopping ? "停止中" : "停止試跑"}
      </button>
      {stopError !== null && (
        <span className="header-error" role="alert">
          {stopError}
        </span>
      )}
    </>
  );
}
