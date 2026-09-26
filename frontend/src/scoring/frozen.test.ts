import { describe, expect, it } from "vitest";

import { frozenOrder, parseFrozen } from "./frozen";

const FROZEN = { runId: 3, viewKey: "檢視", codes: ["b", "a"] };

describe("parseFrozen", () => {
  it("合法的記錄照原樣還原", () => {
    expect(parseFrozen(JSON.parse(JSON.stringify(FROZEN)))).toEqual(FROZEN);
  });

  it.each([
    { note: "沒有記錄", raw: null },
    { note: "作業編號不是數字", raw: { ...FROZEN, runId: "3" } },
    { note: "職缺代碼不是文字", raw: { ...FROZEN, codes: ["a", 1] } },
    { note: "缺少檢視", raw: { runId: 3, codes: [] } },
  ])("$note → null", ({ raw }) => {
    expect(parseFrozen(raw)).toBeNull();
  });
});

describe("frozenOrder", () => {
  it("檢視相同時用固定的順序，不同時不固定", () => {
    expect(frozenOrder(FROZEN, "檢視")).toEqual(["b", "a"]);
    expect(frozenOrder(FROZEN, "改過的檢視")).toBeNull();
    expect(frozenOrder(null, "檢視")).toBeNull();
  });
});
