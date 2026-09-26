/**
 * 職缺表上評分的欄位：值都取自代表的評分，沒評過的職缺沒有值。
 */
import type { Job } from "../api/client";
import { showTime, type Column } from "../job-database/columns";
import type { Sort } from "../job-database/sort";
import type { CurrentScore } from "./api";
import { EliminatedTag } from "./ScoreTags";

/** 四個評分維度，依評分結果的順序 */
export const DIMENSIONS = ["職涯方向契合度", "技能匹配度", "產業公司吸引力", "薪資水準"];

/** 有評分時，第一次打開職缺表顯示的欄位 */
export const SCORE_DEFAULT_COLUMNS = [
  "職缺名稱",
  "公司名稱",
  "地區",
  "薪資待遇",
  "總分",
  "淘汰",
  "評語",
  "最後出現時間",
];

export const SCORE_DEFAULT_SORT: Sort = { key: "總分", dir: "desc" };

/** 最後出現時間由新到舊；依總分排序時，總分相同或都沒有總分的再依它排 */
export const byLastSeenDesc = (a: Job, b: Job): number =>
  a.最後出現時間 < b.最後出現時間 ? 1 : a.最後出現時間 > b.最後出現時間 ? -1 : 0;

const ELIMINATED = "淘汰";
const KEPT = "否";

/**
 * 評分的欄位，依 總分、淘汰、評語、評分時間、四個維度、供應商、模型 的順序
 *
 * @param scores 各職缺代表的評分，以職缺代碼查詢
 */
export function scoreColumns(scores: Map<string, CurrentScore>): Column<Job>[] {
  const of = (job: Job) => scores.get(job.職缺代碼);
  return [
    {
      key: "總分",
      numeric: true,
      value: (job) => of(job)?.總分 ?? null,
      render: (value) => <span className="score">{value}</span>,
      tieBreak: byLastSeenDesc,
    },
    {
      key: "淘汰",
      value: (job) => {
        const score = of(job);
        return score === undefined ? null : score.淘汰 ? ELIMINATED : KEPT;
      },
      render: (value) => <EliminatedTag eliminated={value === ELIMINATED} />,
    },
    { key: "評語", className: "clip", value: (job) => of(job)?.評語 ?? null },
    {
      key: "評分時間",
      className: "nowrap",
      value: (job) => of(job)?.評分時間 ?? null,
      format: showTime,
    },
    ...DIMENSIONS.map((name): Column<Job> => ({
      key: name,
      numeric: true,
      value: (job) => of(job)?.維度分數?.[name] ?? null,
    })),
    { key: "供應商", value: (job) => of(job)?.供應商 ?? null },
    { key: "模型", className: "nowrap", value: (job) => of(job)?.模型 ?? null },
  ];
}
