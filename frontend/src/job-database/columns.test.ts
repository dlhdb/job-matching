import { describe, expect, it } from "vitest";

import { DEFAULT_COLUMNS, JOB_COLUMNS, toggleColumn } from "./columns";

const ORDER = JOB_COLUMNS.map((c) => c.key);

describe("JOB_COLUMNS", () => {
  it("可以選職缺欄位契約的全部欄位，接著是首次、最後出現時間", () => {
    expect(ORDER).toEqual([
      "職缺代碼",
      "職缺名稱",
      "公司名稱",
      "產業類別",
      "地區",
      "薪資待遇",
      "薪資下限",
      "薪資上限",
      "更新日期",
      "應徵人數",
      "工作內容",
      "電腦專長",
      "科系要求",
      "特色標籤",
      "職缺連結",
      "公司連結",
      "首次出現時間",
      "最後出現時間",
    ]);
  });

  it("預設欄位都是可以選的欄位", () => {
    expect(DEFAULT_COLUMNS.every((key) => ORDER.includes(key))).toBe(true);
  });
});

describe("toggleColumn", () => {
  it("勾選時依可選欄位的順序插入", () => {
    expect(toggleColumn(ORDER, ["職缺名稱", "最後出現時間"], "首次出現時間", true)).toEqual([
      "職缺名稱",
      "首次出現時間",
      "最後出現時間",
    ]);
  });

  it("取消勾選時拿掉該欄", () => {
    expect(toggleColumn(ORDER, ["職缺名稱", "薪資待遇"], "薪資待遇", false)).toEqual(["職缺名稱"]);
  });

  it("只剩一欄時取消不掉", () => {
    expect(toggleColumn(ORDER, ["職缺名稱"], "職缺名稱", false)).toEqual(["職缺名稱"]);
  });
});
