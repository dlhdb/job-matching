import { useNavigate } from "react-router-dom";

import { useScoring } from "./context";
import { progressPercent, progressText } from "./summary";

/** 頁首的評分進度與停止按鈕；評分中切到任何分頁都看得到，點進度回到職缺表 */
export function ScoringIndicator() {
  const navigate = useNavigate();
  const { state, stop, stopError } = useScoring();
  const running = state?.running ?? null;
  if (running === null) return null;

  return (
    <>
      <button
        type="button"
        className="job-indicator"
        aria-label={`${progressText(running)}，回到職缺表`}
        onClick={() => navigate("/")}
      >
        <span role="status">{progressText(running)}</span>
        <span className="bar">
          <span style={{ width: `${progressPercent(running)}%` }} />
        </span>
      </button>
      <button
        type="button"
        className="btn danger"
        disabled={running.stopping}
        onClick={() => void stop()}
      >
        {running.stopping ? "停止中" : "停止評分"}
      </button>
      {stopError !== null && (
        <span className="header-error" role="alert">
          {stopError}
        </span>
      )}
    </>
  );
}
