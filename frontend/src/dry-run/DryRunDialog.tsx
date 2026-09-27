import { useEffect, useId, useRef, useState } from "react";

import { ScoringRejected } from "../scoring/api";
import { planDryRun, startDryRun, type DraftsIn, type DryRunPlan } from "./api";
import { settingsLabel } from "./table";

const messageOf = (error: unknown) => (error instanceof Error ? error.message : String(error));

interface DryRunDialogProps {
  /** 試跑清單的職缺代碼，依清單的顯示順序 */
  codes: string[];
  /** 三份設定編輯區的內容 */
  settings: DraftsIn;
  /** 開始了試跑 */
  onStarted: (runId: number) => void;
  onCancel: () => void;
}

/**
 * 試跑前的確認：清單幾筆、其中幾筆淘汰、用編輯區的什麼內容與哪個模型，以及開始前的錯誤。
 *
 * 由呼叫端決定要不要顯示（顯示時才掛上）。開始時後端會重做檢查，被擋下時顯示新的原因。
 */
export function DryRunDialog({ codes, settings, onStarted, onCancel }: DryRunDialogProps) {
  const ref = useRef<HTMLDialogElement>(null);
  const titleId = useId();
  const [plan, setPlan] = useState<DryRunPlan | null>(null);
  const [planError, setPlanError] = useState<string | null>(null);
  const [model, setModel] = useState<string | null>(null);
  const [starting, setStarting] = useState(false);

  useEffect(() => {
    const dialog = ref.current;
    if (dialog !== null && !dialog.open) dialog.showModal();
  }, []);

  useEffect(() => {
    let cancelled = false;
    planDryRun(codes, settings)
      .then((next) => {
        if (cancelled) return;
        setPlan(next);
        setModel(next.models[0] ?? null);
      })
      .catch((error: unknown) => {
        if (!cancelled) setPlanError(`取不到確認的內容：${messageOf(error)}`);
      });
    return () => {
      cancelled = true;
    };
  }, [codes, settings]);

  const canStart =
    plan !== null && plan.errors.length === 0 && model !== null && !starting && planError === null;

  const start = async () => {
    if (!canStart || model === null) return;
    setStarting(true);
    try {
      onStarted(await startDryRun({ codes, settings, model }));
    } catch (error) {
      if (error instanceof ScoringRejected) {
        setPlan({ ...plan, errors: error.errors });
      } else {
        setPlanError(`無法開始試跑：${messageOf(error)}`);
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
      <h2 id={titleId}>試跑</h2>
      {plan === null ? (
        planError === null && <p className="null">讀取中…</p>
      ) : (
        <>
          <ul aria-label="這次試跑">
            <li>
              試跑清單 <strong>{plan.count}</strong> 筆，照清單目前的順序逐筆評
            </li>
            {plan.eliminated !== null && plan.eliminated > 0 && (
              <li>其中 {plan.eliminated} 筆符合淘汰條件，直接淘汰、不呼叫 AI</li>
            )}
            <li>用設定頁編輯區的內容：{settingsLabel(plan.settings)}</li>
            <li>結果不存：不寫入評分紀錄，和目前的評分並排比較</li>
          </ul>
          {plan.errors.length > 0 && (
            <ul className="errors" role="alert" aria-label="不能開始的原因">
              {plan.errors.map((error) => (
                <li key={error}>{error}</li>
              ))}
            </ul>
          )}
          <div className="field">
            <span className="label">供應商</span>
            <span>{plan.provider}</span>
          </div>
          <label className="field">
            <span className="label">模型</span>
            <select value={model ?? ""} onChange={(event) => setModel(event.target.value)}>
              {plan.models.map((name) => (
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
          開始試跑
        </button>
      </div>
    </dialog>
  );
}
