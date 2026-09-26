import { describe, expect, it } from "vitest";

import type { CurrentScore } from "./api";
import { matchesScoreFilters, parseBound, SCORE_FILTER_DEFAULTS } from "./filters";

function score(總分: number | null, 淘汰 = false): CurrentScore {
  return {
    職缺代碼: "x",
    評分時間: "2026-09-01T10:00:00",
    淘汰,
    總分,
    評語: "評語",
    供應商: null,
    模型: null,
    維度分數: null,
  };
}

// AC-rank-filter：總分 50、70、90 各一筆，一筆被淘汰，一筆還沒評分
const JOBS: [string, CurrentScore | undefined][] = [
  ["50", score(50)],
  ["70", score(70)],
  ["90", score(90)],
  ["淘汰", score(null, true)],
  ["未評分", undefined],
];

const pick = (filters: Record<string, string>) =>
  JOBS.filter(([, s]) => matchesScoreFilters(s, { ...SCORE_FILTER_DEFAULTS, ...filters })).map(
    ([name]) => name,
  );

describe("matchesScoreFilters", () => {
  it.each([
    { note: "預設", filters: {}, expected: ["50", "70", "90", "淘汰", "未評分"] },
    { note: "總分下限 70", filters: { scoreMin: "70" }, expected: ["70", "90"] },
    { note: "總分 60～80", filters: { scoreMin: "60", scoreMax: "80" }, expected: ["70"] },
    { note: "只填上限", filters: { scoreMax: "50" }, expected: ["50"] },
    { note: "未淘汰", filters: { scoreStatus: "kept" }, expected: ["50", "70", "90"] },
    { note: "淘汰", filters: { scoreStatus: "eliminated" }, expected: ["淘汰"] },
    { note: "未評分", filters: { scoreStatus: "unscored" }, expected: ["未評分"] },
    {
      note: "總分下限 0、全部：排除沒有總分的",
      filters: { scoreMin: "0", scoreStatus: "all" },
      expected: ["50", "70", "90"],
    },
    {
      note: "記住的狀態不認得時當作全部",
      filters: { scoreStatus: "壞掉" },
      expected: ["50", "70", "90", "淘汰", "未評分"],
    },
    {
      note: "下限不是數字時當作沒設",
      filters: { scoreMin: "abc" },
      expected: ["50", "70", "90", "淘汰", "未評分"],
    },
  ])("$note → $expected", ({ filters, expected }) => {
    expect(pick(filters)).toEqual(expected);
  });
});

describe("parseBound", () => {
  it.each([
    { text: "", expected: null },
    { text: "  ", expected: null },
    { text: " 70 ", expected: 70 },
    { text: "abc", expected: null },
    { text: undefined, expected: null },
  ])("$text → $expected", ({ text, expected }) => {
    expect(parseBound(text)).toBe(expected);
  });
});
