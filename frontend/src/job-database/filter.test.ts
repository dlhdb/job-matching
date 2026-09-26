import { describe, expect, it } from "vitest";

import { anyTerm, EMPTY_FILTERS, matchesFilters, normalize, terms } from "./filter";
import { makeJob } from "./testing";

const A = makeJob({ 職缺代碼: "A", 職缺名稱: "Python 工程師", 地區: "台北市內湖區 瑞光路" });
const B = makeJob({ 職缺代碼: "B", 工作內容: "常駐台北辦公室", 地區: "新北市板橋區 文化路" });
const C = makeJob({ 職缺代碼: "C", 電腦專長: "Rust, Git", 地區: "台中市西屯區 市政路" });

describe("matchesFilters", () => {
  it.each([
    { keyword: "python", area: "", expected: ["A"], note: "不分大小寫" },
    { keyword: "Python，Rust", area: "", expected: ["A", "C"], note: "全形逗號、符合任一個" },
    { keyword: " , ", area: "", expected: ["A", "B", "C"], note: "只有空白與逗號等於沒有輸入" },
    { keyword: "", area: "臺北", expected: ["A"], note: "臺視為台" },
    { keyword: "", area: "台北", expected: ["A"], note: "地區不比對工作內容" },
    { keyword: "", area: "內湖, 台中", expected: ["A", "C"], note: "多個地名符合任一個" },
    { keyword: "Python", area: "台中", expected: [], note: "兩個條件都要符合" },
  ])("關鍵字 $keyword、地區 $area → $expected（$note）", ({ keyword, area, expected }) => {
    const listed = [A, B, C].filter((job) => matchesFilters(job, { keyword, area }));
    expect(listed.map((job) => job.職缺代碼)).toEqual(expected);
  });

  it("不篩選時全部符合", () => {
    expect([A, B, C].every((job) => matchesFilters(job, EMPTY_FILTERS))).toBe(true);
  });

  it("欄位是 null 時不出錯，只比對有值的欄位", () => {
    const job = makeJob({ 職缺代碼: "N", 工作內容: null, 地區: null });
    expect(matchesFilters(job, { keyword: "工程師", area: "" })).toBe(true);
    expect(matchesFilters(job, { keyword: "", area: "台北" })).toBe(false);
  });
});

describe("normalize", () => {
  it("去掉前後空白、轉小寫、臺換成台", () => {
    expect(normalize("  臺北 Python ")).toBe("台北 python");
  });
});

describe("terms", () => {
  it.each([
    { input: "a,b", expected: ["a", "b"] },
    { input: "a，b", expected: ["a", "b"] },
    { input: " , ，", expected: [] },
    { input: "", expected: [] },
  ])("$input → $expected", ({ input, expected }) => {
    expect(terms(input)).toEqual(expected);
  });
});

describe("anyTerm", () => {
  it("沒有輸入時一律符合，text 是 null 也一樣", () => {
    expect(anyTerm(null, "")).toBe(true);
  });
});
