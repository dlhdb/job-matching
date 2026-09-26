/**
 * 評分的篩選：總分範圍與評分狀態，和職缺表的關鍵字、地區篩選同時生效。
 */
import type { CurrentScore } from "./api";

export type ScoreStatus = "all" | "kept" | "eliminated" | "unscored";

export const SCORE_STATUS_LABELS: Record<ScoreStatus, string> = {
  all: "全部",
  kept: "未淘汰",
  eliminated: "淘汰",
  unscored: "未評分",
};

/** 篩選的鍵與預設值；總分的上下限是輸入框的文字 */
export const SCORE_FILTER_DEFAULTS = { scoreMin: "", scoreMax: "", scoreStatus: "all" };

/** 輸入框的總分；空白或不是數字時為 null，當作沒有設 */
export function parseBound(text: string | undefined): number | null {
  const trimmed = (text ?? "").trim();
  if (trimmed === "") return null;
  const value = Number(trimmed);
  return Number.isFinite(value) ? value : null;
}

const isStatus = (value: string | undefined): value is ScoreStatus =>
  value !== undefined && value in SCORE_STATUS_LABELS;

/**
 * 職缺是否符合評分的篩選。
 *
 * - 總分範圍包含邊界；設了任一邊時，排除沒有總分的職缺（被淘汰與還沒評分）。
 * - 評分狀態依代表的評分：未淘汰是評過且沒被淘汰，淘汰是代表的評分被淘汰，未評分是沒有任何評分紀錄。
 *   記住的值不認得時當作全部。
 */
export function matchesScoreFilters(
  score: CurrentScore | undefined,
  filters: Record<string, string>,
): boolean {
  const min = parseBound(filters.scoreMin);
  const max = parseBound(filters.scoreMax);
  if (min !== null || max !== null) {
    const total = score?.總分 ?? null;
    if (total === null) return false;
    if (min !== null && total < min) return false;
    if (max !== null && total > max) return false;
  }
  const status = isStatus(filters.scoreStatus) ? filters.scoreStatus : "all";
  if (status === "kept") return score !== undefined && !score.淘汰;
  if (status === "eliminated") return score !== undefined && score.淘汰;
  if (status === "unscored") return score === undefined;
  return true;
}
