import { useEffect, useState } from "react";
import { Link } from "react-router-dom";

import { fetchJobs, type Job } from "../api/client";
import { ConfirmDialog } from "../app/ConfirmDialog";
import type { Column } from "../job-database/columns";
import { JobTable } from "../job-database/JobTable";
import { sortRows, type Sort } from "../job-database/sort";
import { readStore, writeStore } from "../lib/storage";
import { fetchScoreHistory, type ScoreDetails, type ScoreRecord } from "../scoring/api";
import { useScoring } from "../scoring/context";
import { Dimensions } from "../scoring/ScoreDetail";
import { KINDS, type Kind } from "../settings/api";
import type { DraftsIn } from "./api";
import { useDryRun } from "./context";
import { DryRunDialog } from "./DryRunDialog";
import { LIST_STORAGE_KEY, parseList, removeFromList } from "./list";
import {
  ELIMINATED,
  LIST_COLUMNS,
  listRows,
  nextTriSort,
  settingsLabel,
  STATUS_LABELS,
  staleParts,
  type ListRow,
} from "./table";

const messageOf = (error: unknown) => (error instanceof Error ? error.message : String(error));

const NO_SCORES = new Map();

function TotalCell({ value }: { value: string | number }) {
  return value === ELIMINATED ? (
    <span className="tag out">淘汰</span>
  ) : (
    <span className="score">{value}</span>
  );
}

function StatusCell({ value }: { value: string | number }) {
  const text = String(value);
  if (text === STATUS_LABELS.queued) return <span className="tag queued">{text}</span>;
  if (text === STATUS_LABELS.scoring) return <span className="tag scoring">{text}</span>;
  if (text.startsWith(STATUS_LABELS.failed)) {
    return (
      <span className="tag failed" title={text}>
        {text}
      </span>
    );
  }
  if (text === STATUS_LABELS.skipped) return <span className="null">{text}</span>;
  return <>{text}</>;
}

/** 表上的欄位加上顯示方式 */
const COLUMNS: Column<ListRow>[] = LIST_COLUMNS.map((column) => {
  if (column.key === "目前總分" || column.key === "試跑總分") {
    return { ...column, render: (value) => <TotalCell value={value} /> };
  }
  if (column.key === "差距") {
    return {
      ...column,
      render: (value) => {
        const n = Number(value);
        return (
          <span className={`score ${n > 0 ? "diff-up" : n < 0 ? "diff-down" : ""}`}>
            {n > 0 ? `+${n}` : n}
          </span>
        );
      },
    };
  }
  if (column.key === "狀態") return { ...column, render: (value) => <StatusCell value={value} /> };
  return column;
});

const VISIBLE = COLUMNS.map((column) => column.key);

/** 並排比較的一邊：總分、評語、各維度的分數與理由（被淘汰時是淘汰原因） */
function ScoreSide({ details }: { details: ScoreDetails }) {
  return (
    <>
      <p>
        總分：
        {details.淘汰 ? (
          <span className="tag out">淘汰</span>
        ) : details.總分 === null ? (
          <span className="null">—</span>
        ) : (
          <span className="score">{details.總分}</span>
        )}
      </p>
      <p>{details.評語}</p>
      <Dimensions details={details} />
    </>
  );
}

/** 目前的評分：代表的評分的評分明細，點開時才取 */
function CurrentSide({ code }: { code: string }) {
  const [loaded, setLoaded] = useState<ScoreRecord | { error: string } | null>(null);

  useEffect(() => {
    let cancelled = false;
    fetchScoreHistory(code)
      .then((records) => {
        if (!cancelled && records[0] !== undefined) setLoaded(records[0]);
      })
      .catch((error: unknown) => {
        if (!cancelled) setLoaded({ error: `讀不到目前的評分：${messageOf(error)}` });
      });
    return () => {
      cancelled = true;
    };
  }, [code]);

  if (loaded === null) return <p className="null">讀取中…</p>;
  if ("error" in loaded) return <p className="notice error">{loaded.error}</p>;
  return <ScoreSide details={loaded.評分明細} />;
}

/** 點一列：並排比較目前的評分與試跑的評分 */
function Compare({ row }: { row: ListRow }) {
  const trial = row.trial;
  return (
    <div className="compare">
      <section className="panel" aria-label="目前的評分">
        <h3>目前的評分</h3>
        {row.current === null ? (
          <p className="null">還沒評分</p>
        ) : (
          // 代表的評分改變時重新取
          <CurrentSide key={`${row.職缺代碼}|${row.currentKey}`} code={row.職缺代碼} />
        )}
      </section>
      <section className="panel" aria-label="試跑的評分">
        <h3>試跑</h3>
        {trial?.result ? (
          <ScoreSide details={trial.result} />
        ) : (
          <p className="null">
            {trial === undefined
              ? "還沒試跑這筆"
              : trial.status === "failed"
                ? `試跑失敗：${trial.reason ?? ""}`
                : STATUS_LABELS[trial.status]}
          </p>
        )}
      </section>
    </div>
  );
}

interface DryRunPanelProps {
  /** 三份設定編輯區的內容，試跑用它評 */
  drafts: DraftsIn;
}

/**
 * 設定頁的試跑清單：列出清單的職缺與目前總分，用編輯區的內容試跑，和目前的評分並排比較。
 *
 * 試跑的結果不存：結束後只留在打開的設定頁，離開或重新整理就不見。
 * 所以只顯示在跑的試跑，以及這次打開設定頁後看過它在跑、已結束、還沒清除的試跑。
 */
export function DryRunPanel({ drafts }: DryRunPanelProps) {
  const dryRun = useDryRun();
  const { scores } = useScoring();
  const [list, setList] = useState<string[]>(() => parseList(readStore(LIST_STORAGE_KEY)));
  const [jobs, setJobs] = useState<Map<string, Job> | { error: string } | null>(null);
  const [sort, setSort] = useState<Sort | null>(null);
  // 這次打開設定頁後看過在跑的試跑
  const [seen, setSeen] = useState<ReadonlySet<number>>(() => new Set());
  const [cleared, setCleared] = useState<number | null>(null);
  const [dialog, setDialog] = useState<{ codes: string[]; settings: DraftsIn } | null>(null);
  const [confirmClear, setConfirmClear] = useState(false);

  useEffect(() => {
    fetchJobs()
      .then((loaded) => setJobs(new Map(loaded.map((job) => [job.職缺代碼, job]))))
      .catch((error: unknown) => setJobs({ error: `讀不到職缺：${messageOf(error)}` }));
  }, []);

  const running = dryRun.state?.running ?? null;
  const last = dryRun.state?.last ?? null;
  // 看到在跑的試跑就記下來，結束後才知道要不要顯示它的結果
  if (running !== null && !seen.has(running.id)) setSeen(new Set(seen).add(running.id));
  const run =
    running ??
    (last !== null && seen.has(last.id) && last.id !== cleared && running === null ? last : null);

  if (jobs === null) return <section className="card dry-run">讀取試跑清單中…</section>;
  if ("error" in jobs) return <p className="notice warn">{jobs.error}</p>;

  const updateList = (next: string[]) => {
    setList(next);
    writeStore(LIST_STORAGE_KEY, next);
  };

  const rows = listRows(list, jobs, scores ?? NO_SCORES, run);
  const shown = sort === null ? rows : sortRows(rows, COLUMNS, sort);
  const codes = shown.map((row) => row.職缺代碼);
  const texts = Object.fromEntries(KINDS.map((kind) => [kind, drafts[kind].content])) as Record<
    Kind,
    string
  >;
  const stale = run === null ? [] : staleParts(run, codes, texts);
  const busy = running !== null;

  const onStarted = (runId: number) => {
    // 很快就試跑完時，下一次取狀態可能已經結束，先記下看過它
    setSeen((previous) => new Set(previous).add(runId));
    setDialog(null);
    void dryRun.refresh();
  };

  const runText =
    run === null
      ? null
      : `${busy ? "試跑中" : run.stopped ? "已停止" : "試跑完成"}・用 ${settingsLabel(run.settings)}・${run.model}・結果不存，離開或重新整理設定頁就不見`;

  return (
    <section className="card dry-run" aria-label="試跑清單">
      <div className="toolbar">
        <strong>試跑清單（{rows.length} 筆）</strong>
        <span className="spacer" />
        <button
          className="btn primary"
          type="button"
          disabled={rows.length === 0 || busy}
          title={busy ? "試跑中" : undefined}
          onClick={() => setDialog({ codes, settings: drafts })}
        >
          試跑清單的 {rows.length} 筆
        </button>
        {run !== null && !busy && (
          <button className="btn" type="button" onClick={() => setCleared(run.id)}>
            清除試跑結果
          </button>
        )}
        <button
          className="btn"
          type="button"
          disabled={rows.length === 0 || busy}
          title={busy ? "試跑中不能清空清單" : undefined}
          onClick={() => setConfirmClear(true)}
        >
          清空清單
        </button>
      </div>
      <p className="hint">
        用上面三份設定編輯區的內容評試跑清單的職缺，不影響正式分數；照表格目前的順序試跑。
      </p>
      {dryRun.pollError !== null && <p className="notice error">{dryRun.pollError}</p>}
      {runText !== null && <p className="run-info">{runText}</p>}
      {run?.error && <p className="notice error">{run.error}</p>}
      {stale.length > 0 && (
        <p className="viewing">
          {stale.join("與")}
          在試跑後改過，表上的試跑結果是改之前的。再按一次試跑會用現在的清單與內容。
        </p>
      )}
      {rows.length === 0 ? (
        <p className="null">
          清單是空的。到<Link to="/">職缺表</Link>
          勾選職缺後按「加入試跑清單」；清單記在瀏覽器，改篩選或評完分都不會消失。
        </p>
      ) : (
        <JobTable
          rows={shown}
          presorted
          columns={COLUMNS}
          visible={VISIBLE}
          sort={sort}
          onSortChange={(next) => {
            const column = COLUMNS.find((c) => c.key === next.key);
            if (column) setSort(nextTriSort(sort, column));
          }}
          countText="點欄位標題排序，再點一次反向，第三次回到加入的順序；點一列並排比較"
          emptyText="清單是空的"
          renderDetail={(row) => <Compare row={row} />}
          rowBadge={(row) => (
            <button
              type="button"
              className="linkbtn"
              aria-label={`移除 ${row.職缺代碼}`}
              disabled={busy}
              title={busy ? "試跑中不能移除" : undefined}
              onClick={() => updateList(removeFromList(list, row.職缺代碼))}
            >
              移除
            </button>
          )}
        />
      )}
      <ConfirmDialog
        open={confirmClear}
        message={`清空試跑清單的 ${rows.length} 筆職缺？`}
        confirmLabel="清空"
        onConfirm={() => {
          updateList([]);
          setConfirmClear(false);
        }}
        onCancel={() => setConfirmClear(false)}
      />
      {dialog !== null && (
        <DryRunDialog
          codes={dialog.codes}
          settings={dialog.settings}
          onStarted={onStarted}
          onCancel={() => setDialog(null)}
        />
      )}
    </section>
  );
}
