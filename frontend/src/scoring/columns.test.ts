import { describe, expect, it } from "vitest";

import { sortRows } from "../job-database/sort";
import { makeJob } from "../job-database/testing";
import type { CurrentScore } from "./api";
import { scoreColumns, SCORE_DEFAULT_SORT } from "./columns";

function score(code: string, 總分: number | null, 淘汰 = false): [string, CurrentScore] {
  return [
    code,
    {
      職缺代碼: code,
      評分時間: "2026-09-01T10:00:00",
      淘汰,
      總分,
      評語: `${code} 的評語`,
      供應商: 淘汰 ? null : "gemini",
      模型: 淘汰 ? null : "gemini-3.8-flash",
      維度分數: 淘汰
        ? null
        : { 職涯方向契合度: 4, 技能匹配度: null, 產業公司吸引力: 3, 薪資水準: 5 },
    },
  ];
}

const SCORES = new Map([score("s70", 70), score("s90", 90), score("out", null, true)]);
const COLUMNS = scoreColumns(SCORES);
const value = (key: string, code: string) =>
  COLUMNS.find((c) => c.key === key)!.value(makeJob({ 職缺代碼: code }));

describe("scoreColumns", () => {
  it("欄位依總分、淘汰、評語、評分時間、四個維度、供應商、模型的順序", () => {
    expect(COLUMNS.map((c) => c.key)).toEqual([
      "總分",
      "淘汰",
      "評語",
      "評分時間",
      "職涯方向契合度",
      "技能匹配度",
      "產業公司吸引力",
      "薪資水準",
      "供應商",
      "模型",
    ]);
  });

  it("值取自代表的評分；被淘汰的沒有總分與維度；沒評過的都沒有值", () => {
    expect([value("總分", "s70"), value("淘汰", "s70"), value("職涯方向契合度", "s70")]).toEqual([
      70,
      "否",
      4,
    ]);
    expect([
      value("總分", "out"),
      value("淘汰", "out"),
      value("薪資水準", "out"),
      value("模型", "out"),
    ]).toEqual([null, "淘汰", null, null]);
    expect(COLUMNS.map((c) => c.value(makeJob({ 職缺代碼: "none" })))).toEqual(
      Array(10).fill(null),
    );
  });

  it("預設依總分由高到低；沒有總分的排最後，再依最後出現時間由新到舊", () => {
    // AC-rank-sort
    const rows = [
      makeJob({ 職缺代碼: "none", 最後出現時間: "2026-09-01T10:00:00" }),
      makeJob({ 職缺代碼: "s70" }),
      makeJob({ 職缺代碼: "out", 最後出現時間: "2026-09-02T10:00:00" }),
      makeJob({ 職缺代碼: "s90" }),
    ];
    expect(sortRows(rows, COLUMNS, SCORE_DEFAULT_SORT).map((r) => r.職缺代碼)).toEqual([
      "s90",
      "s70",
      "out",
      "none",
    ]);
  });
});
