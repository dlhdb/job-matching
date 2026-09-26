import { describe, expect, it } from "vitest";

import { DEFAULT_VIEW, parseView, resetView, type View } from "./view";

const CUSTOM: View = {
  columns: ["職缺代碼", "首次出現時間"],
  sort: { key: "薪資下限", dir: "asc" },
  filters: { keyword: "Python", area: "台北" },
};

describe("parseView", () => {
  it("合法的記錄照原樣還原", () => {
    expect(parseView(JSON.parse(JSON.stringify(CUSTOM)))).toEqual(CUSTOM);
  });

  it.each([
    { note: "沒有記錄", raw: null },
    { note: "不是物件", raw: "壞掉的內容" },
    { note: "是陣列", raw: [1, 2] },
  ])("$note → 全部用預設", ({ raw }) => {
    expect(parseView(raw)).toEqual(DEFAULT_VIEW);
  });

  it.each([
    {
      note: "欄位全部不存在",
      raw: { ...CUSTOM, columns: ["縣市", 3] },
      expected: { ...CUSTOM, columns: DEFAULT_VIEW.columns },
    },
    {
      note: "欄位部分不存在或重複",
      raw: { ...CUSTOM, columns: ["縣市", "職缺代碼", "職缺代碼"] },
      expected: { ...CUSTOM, columns: ["職缺代碼"] },
    },
    {
      note: "排序的欄位不存在",
      raw: { ...CUSTOM, sort: { key: "縣市", dir: "asc" } },
      expected: { ...CUSTOM, sort: DEFAULT_VIEW.sort },
    },
    {
      note: "排序的方向不對",
      raw: { ...CUSTOM, sort: { key: "薪資下限", dir: "up" } },
      expected: { ...CUSTOM, sort: DEFAULT_VIEW.sort },
    },
    {
      note: "篩選不是文字",
      raw: { ...CUSTOM, filters: { keyword: 1, area: "台北" } },
      expected: { ...CUSTOM, filters: { keyword: "", area: "台北" } },
    },
    {
      note: "缺少篩選",
      raw: { columns: CUSTOM.columns, sort: CUSTOM.sort },
      expected: { ...CUSTOM, filters: DEFAULT_VIEW.filters },
    },
  ])("$note → 只有那一項退回預設", ({ raw, expected }) => {
    expect(parseView(raw)).toEqual(expected);
  });
});

describe("resetView", () => {
  it("欄位、篩選與排序都回到預設", () => {
    expect(resetView(CUSTOM, false)).toEqual(DEFAULT_VIEW);
  });

  it("只看剛存入的職缺時，篩選維持原樣", () => {
    expect(resetView(CUSTOM, true)).toEqual({ ...DEFAULT_VIEW, filters: CUSTOM.filters });
  });
});
