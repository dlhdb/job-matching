import { describe, expect, it } from "vitest";

import { JOB_COLUMNS } from "./columns";
import { nextSort, sortRows } from "./sort";
import { makeJob } from "./testing";

const codes = (rows: { 職缺代碼: string }[]) => rows.map((row) => row.職缺代碼);

describe("sortRows", () => {
  const rows = [
    makeJob({ 職缺代碼: "low", 薪資下限: 40000 }),
    makeJob({ 職缺代碼: "none", 薪資下限: null }),
    makeJob({ 職缺代碼: "high", 薪資下限: 90000 }),
  ];

  it.each([
    { dir: "desc" as const, expected: ["high", "low", "none"] },
    { dir: "asc" as const, expected: ["low", "high", "none"] },
  ])("薪資下限 $dir：沒有值的排在最後 → $expected", ({ dir, expected }) => {
    expect(codes(sortRows(rows, JOB_COLUMNS, { key: "薪資下限", dir }))).toEqual(expected);
  });

  it("空字串和 null 一樣排在最後", () => {
    const withEmpty = [
      makeJob({ 職缺代碼: "empty", 電腦專長: "" }),
      makeJob({ 職缺代碼: "b", 電腦專長: "Rust" }),
      makeJob({ 職缺代碼: "a", 電腦專長: "Go" }),
    ];
    const sorted = sortRows(withEmpty, JOB_COLUMNS, { key: "電腦專長", dir: "desc" });
    expect(codes(sorted)).toEqual(["b", "a", "empty"]);
  });

  it("值相同時以職缺代碼由小到大排，不論升冪或降冪", () => {
    const same = [
      makeJob({ 職缺代碼: "c", 最後出現時間: "2026-09-02T00:00:00" }),
      makeJob({ 職缺代碼: "b", 最後出現時間: "2026-09-01T00:00:00" }),
      makeJob({ 職缺代碼: "a", 最後出現時間: "2026-09-02T00:00:00" }),
    ];
    expect(codes(sortRows(same, JOB_COLUMNS, { key: "最後出現時間", dir: "desc" }))).toEqual([
      "a",
      "c",
      "b",
    ]);
    expect(codes(sortRows(same, JOB_COLUMNS, { key: "最後出現時間", dir: "asc" }))).toEqual([
      "b",
      "a",
      "c",
    ]);
  });

  it("不改動傳入的陣列", () => {
    sortRows(rows, JOB_COLUMNS, { key: "薪資下限", dir: "desc" });
    expect(codes(rows)).toEqual(["low", "none", "high"]);
  });
});

describe("nextSort", () => {
  it.each([
    { note: "第一次點數字欄由大到小", key: "薪資下限", numeric: true, expected: "desc" },
    { note: "第一次點其他欄由小到大", key: "職缺名稱", numeric: false, expected: "asc" },
  ])("$note", ({ key, numeric, expected }) => {
    const current = { key: "最後出現時間", dir: "desc" as const };
    expect(nextSort(current, { key, numeric })).toEqual({ key, dir: expected });
  });

  it.each([
    { dir: "desc" as const, expected: "asc" },
    { dir: "asc" as const, expected: "desc" },
  ])("再點同一欄反向：$dir → $expected", ({ dir, expected }) => {
    expect(nextSort({ key: "薪資下限", dir }, { key: "薪資下限", numeric: true })).toEqual({
      key: "薪資下限",
      dir: expected,
    });
  });
});
