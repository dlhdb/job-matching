import { useEffect, useId, useRef, useState } from "react";

import { planScoring, ScoringRejected, startScoring, type Plan } from "./api";

const KIND_LABELS: Record<string, string> = {
  preferences: "偏好",
  experience: "經歷",
  template: "提示詞模板",
};

const messageOf = (error: unknown) => (error instanceof Error ? error.message : String(error));

interface ScoreDialogProps {
  /** 勾選的職缺代碼，依職缺表的顯示順序 */
  codes: string[];
  /** 開始了評分作業 */
  onStarted: (runId: number) => void;
  onCancel: () => void;
}

/**
 * 送去評分前的確認：將評幾筆、其中幾筆淘汰、用哪一版設定與哪個模型，以及開始前的錯誤。
 *
 * 由呼叫端決定要不要顯示（顯示時才掛上）。開始時後端會重讀設定、重做檢查，被擋下時顯示新的原因。
 */
export function ScoreDialog({ codes, onStarted, onCancel }: ScoreDialogProps) {
  const ref = useRef<HTMLDialogElement>(null);
  const titleId = useId();
  const [rescore, setRescore] = useState(false);
  const [plan, setPlan] = useState<Plan | null>(null);
  const [planError, setPlanError] = useState<string | null>(null);
  const [model, setModel] = useState<string | null>(null);
  const [starting, setStarting] = useState(false);
  // 勾選框改變後，新的確認內容回來之前不能開始，才不會用舊的筆數開始
  const [pending, setPending] = useState(true);
  // 最後一次送出的確認；勾選框切換得快時，較早送出的回應晚到不採用
  const latest = useRef(0);

  useEffect(() => {
    const dialog = ref.current;
    if (dialog !== null && !dialog.open) dialog.showModal();
  }, []);

  useEffect(() => {
    const id = ++latest.current;
    planScoring(codes, rescore)
      .then((next) => {
        if (id !== latest.current) return;
        setPlan(next);
        setPlanError(null);
        setPending(false);
        setModel((current) => current ?? next.models[0] ?? null);
      })
      .catch((error: unknown) => {
        if (id !== latest.current) return;
        setPlanError(`取不到確認的內容：${messageOf(error)}`);
        setPending(false);
      });
  }, [codes, rescore]);

  const current = plan;
  const canStart =
    current !== null &&
    current.errors.length === 0 &&
    model !== null &&
    !starting &&
    !pending &&
    planError === null;

  const start = async () => {
    if (!canStart || model === null) return;
    setStarting(true);
    try {
      onStarted(await startScoring({ codes, rescore, model }));
    } catch (error) {
      if (error instanceof ScoringRejected && current !== null) {
        setPlan({ ...current, errors: error.errors });
      } else {
        setPlanError(`無法開始評分：${messageOf(error)}`);
      }
      setStarting(false);
    }
  };

  return (
    <dialog
      ref={ref}
      className="modal"
      aria-labelledby={titleId}
      onCancel={(event) => {
        event.preventDefault();
        onCancel();
      }}
    >
      <h2 id={titleId}>送去評分</h2>
      {current === null ? (
        planError === null && <p className="null">讀取中…</p>
      ) : (
        <>
          <ul aria-label="這次評分">
            <li>
              勾選 <strong>{current.selected}</strong> 筆，其中 {current.scored} 筆已評過
            </li>
            <li>
              將評 <strong>{current.targets}</strong> 筆，照職缺表目前的順序逐筆評
            </li>
            {current.eliminated !== null && current.eliminated > 0 && (
              <li>其中 {current.eliminated} 筆符合淘汰條件，直接淘汰、不呼叫 AI</li>
            )}
            <li>
              用目前的設定：
              {Object.entries(current.versions)
                .map(([kind, v]) => `${KIND_LABELS[kind] ?? kind}第 ${v.version} 版「${v.name}」`)
                .join("、")}
            </li>
          </ul>
          <label className="check">
            <input
              type="checkbox"
              checked={rescore}
              onChange={(event) => {
                setPending(true);
                setRescore(event.target.checked);
              }}
            />
            <span>包含已評過的職缺（重評）：已評過的也評，各新增一筆評分紀錄</span>
          </label>
          {current.errors.length > 0 && (
            <ul className="errors" role="alert" aria-label="不能開始的原因">
              {current.errors.map((error) => (
                <li key={error}>{error}</li>
              ))}
            </ul>
          )}
          <div className="field">
            <span className="label">供應商</span>
            <span>{current.provider}</span>
          </div>
          <label className="field">
            <span className="label">模型</span>
            <select value={model ?? ""} onChange={(event) => setModel(event.target.value)}>
              {current.models.map((name) => (
                <option key={name} value={name}>
                  {name}
                </option>
              ))}
            </select>
          </label>
        </>
      )}
      {planError !== null && <p className="notice error">{planError}</p>}
      <div className="actions">
        <button className="btn" type="button" onClick={onCancel}>
          取消
        </button>
        <button
          className="btn primary"
          type="button"
          disabled={!canStart}
          onClick={() => void start()}
        >
          開始評分
        </button>
      </div>
    </dialog>
  );
}
