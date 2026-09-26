import { describe, expect, it } from "vitest";

import type { Running } from "./api";
import { progressPercent, progressText } from "./progress";

const search: Running = {
  progress: { stage: "search", keyword: "Python", page: 1, pages: 2, found: 30 },
  stopping: false,
};
const detail: Running = { progress: { stage: "detail", index: 5, total: 40 }, stopping: false };

describe("progressText", () => {
  it.each([
    {
      note: "搜尋時",
      running: search,
      expected: "搜尋中：「Python」第 1／2 頁，已找到 30 筆不重複的職缺",
    },
    {
      note: "取內容時",
      running: detail,
      expected: "取職缺內容：第 5／40 筆（抓完或停止後一次列出）",
    },
    {
      note: "還沒送出請求",
      running: { progress: null, stopping: false },
      expected: "準備開始抓取…",
    },
    {
      note: "停止中",
      running: { ...detail, stopping: true },
      expected: "停止中：不再發出新的請求",
    },
  ])("$note", ({ running, expected }) => {
    expect(progressText(running)).toBe(expected);
  });
});

describe("progressPercent", () => {
  it.each([
    { note: "搜尋時不知道總數", running: search, expected: null },
    { note: "取第 5 筆時已取完 4 筆", running: detail, expected: 10 },
    { note: "還沒送出請求", running: { progress: null, stopping: false }, expected: null },
  ])("$note", ({ running, expected }) => {
    expect(progressPercent(running)).toBe(expected);
  });
});
