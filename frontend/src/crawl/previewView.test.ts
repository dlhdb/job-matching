import { describe, expect, it } from "vitest";

import { DEFAULT_PREVIEW_VIEW, parsePreviewView, type PreviewView } from "./previewView";

const CUSTOM: PreviewView = {
  columns: ["職缺代碼", "工作內容"],
  sort: { key: "薪資下限", dir: "desc" },
};

describe("parsePreviewView", () => {
  it("合法的記錄照原樣還原", () => {
    expect(parsePreviewView(JSON.parse(JSON.stringify(CUSTOM)))).toEqual(CUSTOM);
  });

  it("預設依職缺名稱由小到大，顯示職缺名稱、公司名稱、地區、薪資待遇、更新日期", () => {
    expect(DEFAULT_PREVIEW_VIEW).toEqual({
      columns: ["職缺名稱", "公司名稱", "地區", "薪資待遇", "更新日期"],
      sort: { key: "職缺名稱", dir: "asc" },
    });
  });

  it.each([
    { note: "沒有記錄", raw: null },
    { note: "不是物件", raw: "壞掉的內容" },
  ])("$note → 全部用預設", ({ raw }) => {
    expect(parsePreviewView(raw)).toEqual(DEFAULT_PREVIEW_VIEW);
  });

  it.each([
    {
      note: "出現時間不是預覽能選的欄位",
      raw: { ...CUSTOM, columns: ["最後出現時間", "職缺代碼"] },
      expected: { ...CUSTOM, columns: ["職缺代碼"] },
    },
    {
      note: "只有出現時間",
      raw: { ...CUSTOM, columns: ["首次出現時間"] },
      expected: { ...CUSTOM, columns: DEFAULT_PREVIEW_VIEW.columns },
    },
    {
      note: "依出現時間排序",
      raw: { ...CUSTOM, sort: { key: "最後出現時間", dir: "desc" } },
      expected: { ...CUSTOM, sort: DEFAULT_PREVIEW_VIEW.sort },
    },
  ])("$note → 只有這一項用預設", ({ raw, expected }) => {
    expect(parsePreviewView(raw)).toEqual(expected);
  });
});
