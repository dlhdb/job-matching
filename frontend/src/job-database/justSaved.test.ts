import { describe, expect, it } from "vitest";

import { parseSavedCodes, pickJustSaved } from "./justSaved";
import { makeJob } from "./testing";

describe("parseSavedCodes", () => {
  it.each([
    { search: "", expected: null },
    { search: "?saved=", expected: null },
    { search: "?saved=,%20,", expected: null },
    { search: "?saved=a,b", expected: ["a", "b"] },
    { search: "?saved=a,%20b%20,a", expected: ["a", "b"] },
  ])("$search → $expected", ({ search, expected }) => {
    expect(parseSavedCodes(new URLSearchParams(search))).toEqual(expected);
  });
});

describe("pickJustSaved", () => {
  const jobs = ["j1", "j2", "j3", "j4", "j5"].map((code) =>
    makeJob({ 職缺代碼: code, 職缺名稱: code === "j2" ? "Python 工程師" : "Go 工程師" }),
  );

  it("只列出清單中的職缺，資料庫沒有的代碼不算進筆數", () => {
    const picked = pickJustSaved(jobs, ["j1", "j2", "不存在"]);
    expect(picked.map((job) => job.職缺代碼)).toEqual(["j1", "j2"]);
  });

  it("不套用其他篩選：不符合關鍵字的職缺也列出", () => {
    // j1 不含 Python，只看剛存入的職缺時仍要列出
    expect(pickJustSaved(jobs, ["j1"]).map((job) => job.職缺代碼)).toEqual(["j1"]);
  });
});
