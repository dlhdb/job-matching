/**
 * 試跑清單的表：每列的目前總分、試跑總分、差距與狀態，排序，以及試跑結果是否過時。
 */
import type { Job } from "../api/client";
import type { Column } from "../job-database/columns";
import { nextSort, type Sort } from "../job-database/sort";
import type { CurrentScore } from "../scoring/api";
import { KIND_LABELS, KINDS, type Kind } from "../settings/api";
import type { DryRunOut, DryRunRow } from "./api";

/**
 * 總分欄中代表「被淘汰」的值：比所有分數（0–100）都小，依總分排序時當作最低分，
 * 沒有總分的列仍排最後；顯示成淘汰標籤
 */
export const ELIMINATED = -1;

/** 試跑清單的一列 */
export interface ListRow {
  職缺代碼: string;
  職缺名稱: string | null;
  公司名稱: string | null;
  /** 加入清單的順序，從 0 起算 */
  order: number;
  /** 代表的評分的總分；被淘汰時是 ELIMINATED，還沒評分時是 null */
  current: number | null;
  /** 代表的評分的識別；改變時（例如剛重評）並排比較重新取目前的評分 */
  currentKey: string;
  /** 這一列的試跑結果；還沒試跑時是 undefined */
  trial: DryRunRow | undefined;
}

/** 列上的試跑狀態 */
export const STATUS_LABELS: Record<DryRunRow["status"], string> = {
  queued: "排隊中",
  scoring: "試跑中",
  done: "完成",
  failed: "失敗",
  skipped: "停止，沒試跑",
};

const totalOf = (eliminated: boolean, total: number | null) => (eliminated ? ELIMINATED : total);

/** 試跑總分；還沒試跑完或失敗時是 null */
export function trialTotal(row: ListRow): number | null {
  const result = row.trial?.result;
  return result ? totalOf(result.淘汰, result.總分) : null;
}

/** 試跑總分減目前總分；兩邊都是分數時才有，任一邊被淘汰、還沒評分或失敗時是 null */
export function diff(row: ListRow): number | null {
  const trial = trialTotal(row);
  const current = row.current;
  if (trial === null || current === null || trial === ELIMINATED || current === ELIMINATED) {
    return null;
  }
  return trial - current;
}

/** 依清單的順序組出表上的列；職缺資料庫沒有的職缺不列出 */
export function listRows(
  list: string[],
  jobs: Map<string, Job>,
  scores: Map<string, CurrentScore>,
  run: DryRunOut | null,
): ListRow[] {
  const trials = new Map((run?.rows ?? []).map((row) => [row.code, row]));
  return list.flatMap((code, order) => {
    const job = jobs.get(code);
    if (job === undefined) return [];
    const score = scores.get(code);
    return [
      {
        職缺代碼: code,
        職缺名稱: job.職缺名稱,
        公司名稱: job.公司名稱,
        order,
        current: score === undefined ? null : totalOf(score.淘汰, score.總分),
        currentKey: JSON.stringify(score ?? null),
        trial: trials.get(code),
      },
    ];
  });
}

/** 列上的試跑狀態，失敗時連同原因；還沒試跑時是 null */
export function statusText(row: ListRow): string | null {
  const trial = row.trial;
  if (trial === undefined) return null;
  if (trial.status === "failed") return `${STATUS_LABELS.failed}：${trial.reason ?? ""}`;
  return STATUS_LABELS[trial.status];
}

/** 值相同或都沒有值時，照加入清單的順序 */
const byOrder = (a: ListRow, b: ListRow) => a.order - b.order;

/** 表上的欄位；顯示方式由試跑清單的元件加上 */
export const LIST_COLUMNS: Column<ListRow>[] = [
  { key: "職缺名稱", className: "clip", value: (row) => row.職缺名稱, tieBreak: byOrder },
  { key: "公司名稱", className: "clip", value: (row) => row.公司名稱, tieBreak: byOrder },
  { key: "目前總分", numeric: true, value: (row) => row.current, tieBreak: byOrder },
  { key: "試跑總分", numeric: true, value: trialTotal, tieBreak: byOrder },
  { key: "差距", numeric: true, value: diff, tieBreak: byOrder },
  { key: "狀態", value: statusText, tieBreak: byOrder },
];

/** 點欄位標題後的排序：第一次、第二次同職缺表，第三次回到加入的順序（null） */
export function nextTriSort(
  current: Sort | null,
  column: Pick<Column<never>, "key" | "numeric">,
): Sort | null {
  const next = nextSort(current, column);
  const first = column.numeric ? "desc" : "asc";
  return current !== null && current.key === column.key && next.dir === first ? null : next;
}

/** 一份設定用的是什麼內容，例如「偏好第 2 版「後端」」或「經歷以第 2 版為底修改中」 */
export function draftLabel(
  kind: Kind,
  ref: { base: number; name: string; modified: boolean },
): string {
  return ref.modified
    ? `${KIND_LABELS[kind]}以第 ${ref.base} 版為底修改中`
    : `${KIND_LABELS[kind]}第 ${ref.base} 版「${ref.name}」`;
}

/** 三份設定用的內容，依偏好、經歷、提示詞模板的順序 */
export function settingsLabel(
  settings: Record<string, { base: number; name: string; modified: boolean }>,
): string {
  return KINDS.flatMap((kind) => (settings[kind] ? [draftLabel(kind, settings[kind])] : [])).join(
    "、",
  );
}

/**
 * 試跑後改過的部分：試跑清單（加入或移除職缺，只改排序不算）、編輯區的內容。
 *
 * @param texts 三份設定編輯區目前的內容
 */
export function staleParts(run: DryRunOut, list: string[], texts: Record<Kind, string>): string[] {
  const sameList =
    new Set(list).size === run.rows.length && run.rows.every((row) => list.includes(row.code));
  const sameTexts = KINDS.every((kind) => run.settings[kind]?.content === texts[kind]);
  return [...(sameList ? [] : ["試跑清單"]), ...(sameTexts ? [] : ["編輯區的內容"])];
}
