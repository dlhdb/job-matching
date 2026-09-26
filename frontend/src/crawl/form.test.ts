import { describe, expect, it } from "vitest";

import {
  DEFAULT_FORM,
  formError,
  hasKeyword,
  parseForm,
  toRequest,
  type CrawlFormValues,
} from "./form";

const AREAS = ["台北市", "台中市", "新竹縣"];

const CUSTOM: CrawlFormValues = {
  keyword: "Python, 資料工程師",
  area: "台中市",
  pages: "2",
  jobType: "1",
};

describe("parseForm", () => {
  it("合法的記錄照原樣還原", () => {
    expect(parseForm(JSON.parse(JSON.stringify(CUSTOM)), AREAS)).toEqual(CUSTOM);
  });

  it.each([
    { note: "沒有記錄（包括瀏覽器不允許保存）", raw: null },
    { note: "不是物件", raw: "壞掉的內容" },
    { note: "是陣列", raw: [1, 2] },
  ])("$note → 全部用預設", ({ raw }) => {
    expect(parseForm(raw, AREAS)).toEqual(DEFAULT_FORM);
  });

  it("預設是沒有關鍵字、全台灣、3 頁、全部", () => {
    expect(DEFAULT_FORM).toEqual({ keyword: "", area: "", pages: "3", jobType: "0" });
  });

  it.each([
    {
      note: "關鍵字不是文字",
      raw: { ...CUSTOM, keyword: 3 },
      expected: { ...CUSTOM, keyword: "" },
    },
    {
      note: "縣市不在清單",
      raw: { ...CUSTOM, area: "火星" },
      expected: { ...CUSTOM, area: "" },
    },
    { note: "全台灣", raw: { ...CUSTOM, area: "" }, expected: { ...CUSTOM, area: "" } },
    {
      note: "頁數是 0",
      raw: { ...CUSTOM, pages: "0" },
      expected: { ...CUSTOM, pages: "3" },
    },
    {
      note: "頁數不是整數",
      raw: { ...CUSTOM, pages: "1.5" },
      expected: { ...CUSTOM, pages: "3" },
    },
    {
      note: "頁數是數字而不是文字",
      raw: { ...CUSTOM, pages: 2 },
      expected: { ...CUSTOM, pages: "3" },
    },
    {
      note: "職缺性質不是 0／1／2",
      raw: { ...CUSTOM, jobType: "3" },
      expected: { ...CUSTOM, jobType: "0" },
    },
  ])("$note → 只有這一欄用預設", ({ raw, expected }) => {
    expect(parseForm(raw, AREAS)).toEqual(expected);
  });
});

describe("hasKeyword", () => {
  it.each([
    { keyword: "", expected: false },
    { keyword: " , ，  ", expected: false },
    { keyword: "Python", expected: true },
    { keyword: " ，Python,", expected: true },
  ])("「$keyword」→ $expected", ({ keyword, expected }) => {
    expect(hasKeyword(keyword)).toBe(expected);
  });
});

describe("formError", () => {
  it.each([
    { note: "可以開始", form: CUSTOM, expected: null },
    {
      note: "只有逗號與空白",
      form: { ...CUSTOM, keyword: " ,， " },
      expected: "至少要有一個關鍵字",
    },
    { note: "頁數是 0", form: { ...CUSTOM, pages: "0" }, expected: "頁數要是正整數" },
    { note: "頁數空白", form: { ...CUSTOM, pages: "" }, expected: "頁數要是正整數" },
  ])("$note", ({ form, expected }) => {
    expect(formError(form)).toBe(expected);
  });
});

describe("toRequest", () => {
  it("轉成開始抓取的請求", () => {
    expect(toRequest(CUSTOM, false)).toEqual({
      keyword: "Python, 資料工程師",
      area: "台中市",
      pages: 2,
      job_type: 1,
      discard_preview: false,
    });
  });

  it("全台灣的縣市是 null", () => {
    expect(toRequest({ ...CUSTOM, area: "" }, true)).toMatchObject({
      area: null,
      discard_preview: true,
    });
  });
});
