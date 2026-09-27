import { describe, expect, it } from "vitest";

import { addToList, parseList, removeFromList } from "./list";

describe("parseList", () => {
  it("照原樣還原，重複的只留第一個", () => {
    expect(parseList(["b", "a", "b"])).toEqual(["b", "a"]);
  });

  it.each([
    { note: "沒有記錄", raw: null },
    { note: "不是陣列", raw: { a: 1 } },
  ])("$note → 空的清單", ({ raw }) => {
    expect(parseList(raw)).toEqual([]);
  });

  it("丟掉不是文字的項目", () => {
    expect(parseList(["a", 1, null, "b"])).toEqual(["a", "b"]);
  });
});

describe("addToList", () => {
  it("新加入的接在最後", () => {
    expect(addToList([], ["a", "b"])).toEqual({ list: ["a", "b"], added: 2, existing: 0 });
  });

  it("已在清單裡的不重複加入，並算出原本就在的筆數", () => {
    // AC-dry-run-list (b)
    expect(addToList(["a", "b"], ["b", "c"])).toEqual({
      list: ["a", "b", "c"],
      added: 1,
      existing: 1,
    });
  });
});

describe("removeFromList", () => {
  it("只移除那一筆，其他的順序不變", () => {
    expect(removeFromList(["a", "b", "c"], "b")).toEqual(["a", "c"]);
  });
});
