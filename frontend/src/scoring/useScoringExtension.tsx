import { useState } from "react";

import type { JobTableExtension, TableContext } from "../job-database/extension";
import { useScoring } from "./context";
import { scoreColumns, SCORE_DEFAULT_COLUMNS, SCORE_DEFAULT_SORT } from "./columns";
import { matchesScoreFilters, SCORE_FILTER_DEFAULTS, SCORE_STATUS_LABELS } from "./filters";
import { ScoreDetail } from "./ScoreDetail";
import { ScoreDialog } from "./ScoreDialog";
import { frozenOrder } from "./frozen";
import { summaryText } from "./summary";
import { StatusTag } from "./ScoreTags";

const NO_SCORES = new Map();

/**
 * 在職缺表上疊加評分：評分的欄位、預設依總分排序、總分範圍與評分狀態的篩選、勾選與送去評分、
 * 評分中列上的狀態，以及展開列的評分。
 */
export function useScoringExtension(): JobTableExtension {
  const scoring = useScoring();
  const [selected, setSelected] = useState<ReadonlySet<string>>(() => new Set());
  // 打開確認視窗時的職缺與檢視：開始評分時以它們固定列的順序
  const [dialog, setDialog] = useState<{ codes: string[]; context: TableContext } | null>(null);

  const scores = scoring.scores ?? NO_SCORES;
  const running = scoring.state?.running ?? null;
  // 讀過一次之後再讀不到時，沿用上次的評分，原因只顯示在表格上方
  const status: JobTableExtension["status"] =
    scoring.scores !== null
      ? "ready"
      : scoring.scoresError !== null
        ? { error: scoring.scoresError }
        : "loading";

  const started = (runId: number, context: TableContext) => {
    scoring.setFrozen({
      runId,
      viewKey: context.viewKey,
      codes: context.rows.map((j) => j.職缺代碼),
    });
    setSelected(new Set());
    setDialog(null);
    void scoring.started(runId);
  };

  const renderTools = (context: TableContext) => {
    const shown = context.rows.map((job) => job.職缺代碼);
    const picked = shown.filter((code) => selected.has(code));
    return (
      <span className="selbar">
        <span className="selcount">已選 {picked.length} 筆</span>
        <button
          className="btn"
          type="button"
          disabled={shown.length === 0}
          onClick={() => setSelected(new Set(shown))}
        >
          全選
        </button>
        <button
          className="btn"
          type="button"
          disabled={selected.size === 0}
          onClick={() => setSelected(new Set())}
        >
          取消全選
        </button>
        <button
          className="btn primary"
          type="button"
          disabled={picked.length === 0 || running !== null}
          title={running !== null ? "同一時間只能跑一個作業" : undefined}
          onClick={() => setDialog({ codes: picked, context })}
        >
          送去評分
        </button>
        {dialog !== null && (
          <ScoreDialog
            codes={dialog.codes}
            onStarted={(runId) => started(runId, dialog.context)}
            onCancel={() => setDialog(null)}
          />
        )}
      </span>
    );
  };

  const renderBanner = () => (
    <>
      {scoring.pollError !== null && <p className="notice error">{scoring.pollError}</p>}
      {scoring.scores !== null && scoring.scoresError !== null && (
        <p className="notice error">{scoring.scoresError}</p>
      )}
      {scoring.finished !== null && (
        <div
          className={
            scoring.finished.failed > 0 || scoring.finished.stopped ? "notice warn" : "notice"
          }
          role="status"
        >
          <span>{summaryText(scoring.finished)}</span>
          <button
            type="button"
            className="close"
            aria-label="關閉評分的摘要"
            onClick={scoring.dismissSummary}
          >
            ×
          </button>
        </div>
      )}
    </>
  );

  return {
    status,
    columns: scoreColumns(scores),
    defaultColumns: SCORE_DEFAULT_COLUMNS,
    defaultSort: SCORE_DEFAULT_SORT,
    filterDefaults: SCORE_FILTER_DEFAULTS,
    matchesFilters: (job, filters) => matchesScoreFilters(scores.get(job.職缺代碼), filters),
    renderFilters: (filters, onChange, disabled) => (
      <>
        <div className="field">
          <span className="label">總分範圍</span>
          <span className="range">
            <input
              className="narrow"
              type="number"
              aria-label="總分下限"
              placeholder="下限"
              value={filters.scoreMin ?? ""}
              disabled={disabled}
              onChange={(event) => onChange({ ...filters, scoreMin: event.target.value })}
            />
            ～
            <input
              className="narrow"
              type="number"
              aria-label="總分上限"
              placeholder="上限"
              value={filters.scoreMax ?? ""}
              disabled={disabled}
              onChange={(event) => onChange({ ...filters, scoreMax: event.target.value })}
            />
          </span>
          <span className="hint">包含邊界；設了範圍時不列沒有總分的職缺</span>
        </div>
        <label className="field">
          <span className="label">評分狀態</span>
          <select
            value={filters.scoreStatus ?? "all"}
            disabled={disabled}
            onChange={(event) => onChange({ ...filters, scoreStatus: event.target.value })}
          >
            {Object.entries(SCORE_STATUS_LABELS).map(([value, label]) => (
              <option key={value} value={value}>
                {label}
              </option>
            ))}
          </select>
          <span className="hint">&nbsp;</span>
        </label>
      </>
    ),
    renderDetail: (job) => {
      const score = scores.get(job.職缺代碼);
      return (
        <ScoreDetail
          code={job.職缺代碼}
          currentKey={JSON.stringify(score ?? null)}
          status={scoring.statuses.get(job.職缺代碼)}
        />
      );
    },
    rowBadge: (job) => {
      const rowStatus = scoring.statuses.get(job.職缺代碼);
      return rowStatus ? <StatusTag status={rowStatus} /> : null;
    },
    selection: { selected, onChange: setSelected },
    renderTools,
    renderBanner,
    frozenOrder: (viewKey) => frozenOrder(scoring.frozen, viewKey),
    onViewChange: ({ filtersChanged }) => {
      if (scoring.frozen !== null) scoring.setFrozen(null);
      if (filtersChanged) setSelected(new Set());
    },
  };
}
