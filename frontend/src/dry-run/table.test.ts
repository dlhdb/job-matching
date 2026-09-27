import { describe, expect, it } from "vitest";

import { makeJob } from "../job-database/testing";
import { sortRows } from "../job-database/sort";
import type { CurrentScore, ScoreDetails } from "../scoring/api";
import type { DryRunOut, DryRunRow } from "./api";
import {
  diff,
  draftLabel,
  ELIMINATED,
  LIST_COLUMNS,
  listRows,
  nextTriSort,
  settingsLabel,
  staleParts,
  statusText,
  trialTotal,
} from "./table";

const score = (code: string, total: number | null, eliminated = false): CurrentScore => ({
  職缺代碼: code,
  評分時間: "2026-09-01T10:00:00",
  淘汰: eliminated,
  總分: total,
  評語: "評語",
  供應商: null,
  模型: null,
  維度分數: null,
});

const result = (code: string, total: number | null, eliminated = false): ScoreDetails => ({
  職缺代碼: code,
  淘汰: eliminated,
  淘汰原因: eliminated ? ["職稱含排除關鍵字：業務"] : [],
  維度: null,
  總分: total,
  未知維度: [],
  評語: "試跑的評語",
});

const row = (code: string, status: DryRunRow["status"], details: ScoreDetails | null = null) => ({
  code,
  status,
  reason: status === "failed" ? "模擬的 API 錯誤" : null,
  result: details,
});

const SETTINGS = {
  preferences: { base: 2, name: "後端", modified: true, content: "偏好內容" },
  experience: { base: 1, name: "預設範例", modified: false, content: "經歷內容" },
  template: { base: 1, name: "預設模板", modified: false, content: "模板內容" },
};

const run = (rows: DryRunRow[]): DryRunOut => ({
  id: 1,
  total: rows.length,
  done: rows.length,
  model: "gemini-3.8-flash",
  settings: SETTINGS,
  stopping: false,
  stopped: false,
  error: null,
  rows,
});

// AC-dry-run-result 的清單：目前總分 70、60、還沒評分；試跑 75、淘汰、失敗
const JOBS = new Map(["a", "b", "c"].map((code) => [code, makeJob({ 職缺代碼: code })]));
const SCORES = new Map([
  ["a", score("a", 70)],
  ["b", score("b", 60)],
]);
const RUN = run([
  row("a", "done", result("a", 75)),
  row("b", "done", result("b", null, true)),
  row("c", "failed"),
]);

describe("listRows", () => {
  it("依清單的順序；職缺資料庫沒有的不列出", () => {
    const rows = listRows(["c", "gone", "a"], JOBS, SCORES, null);
    expect(rows.map((r) => [r.職缺代碼, r.order])).toEqual([
      ["c", 0],
      ["a", 2],
    ]);
  });

  it("目前總分用代表的評分，被淘汰時是 ELIMINATED", () => {
    // AC-history-current 的試跑清單部分
    const scores = new Map([["a", score("a", null, true)]]);
    const [a, b] = listRows(["a", "b"], JOBS, scores, null);
    expect([a?.current, b?.current]).toEqual([ELIMINATED, null]);
  });
});

describe("試跑總分與差距", () => {
  it("兩邊都是分數時才有差距", () => {
    // AC-dry-run-result (a)
    const [a, b, c] = listRows(["a", "b", "c"], JOBS, SCORES, RUN);
    expect([a, b, c].map((r) => r && trialTotal(r))).toEqual([75, ELIMINATED, null]);
    expect([a, b, c].map((r) => r && diff(r))).toEqual([5, null, null]);
  });

  it("目前被淘汰、試跑是分數時沒有差距", () => {
    const [a] = listRows(["a"], JOBS, new Map([["a", score("a", null, true)]]), RUN);
    expect(a && diff(a)).toBeNull();
  });

  it("狀態：失敗時連同原因，還沒試跑時沒有", () => {
    const [a, , c] = listRows(["a", "b", "c"], JOBS, SCORES, RUN);
    expect(a && statusText(a)).toBe("完成");
    expect(c && statusText(c)).toBe("失敗：模擬的 API 錯誤");
    const [none] = listRows(["a"], JOBS, SCORES, null);
    expect(none && statusText(none)).toBeNull();
  });
});

describe("排序", () => {
  const column = (key: string) => LIST_COLUMNS.find((c) => c.key === key)!;

  it("點三次：由大到小、由小到大、回到加入的順序", () => {
    const total = column("目前總分");
    const first = nextTriSort(null, total);
    expect(first).toEqual({ key: "目前總分", dir: "desc" });
    const second = nextTriSort(first, total);
    expect(second).toEqual({ key: "目前總分", dir: "asc" });
    expect(nextTriSort(second, total)).toBeNull();
  });

  it("文字欄先由小到大；換一欄時重新開始", () => {
    const name = column("職缺名稱");
    expect(nextTriSort(null, name)).toEqual({ key: "職缺名稱", dir: "asc" });
    expect(nextTriSort({ key: "目前總分", dir: "asc" }, name)).toEqual({
      key: "職缺名稱",
      dir: "asc",
    });
  });

  it("依目前總分由大到小：淘汰排在分數之後，沒評分的最後，相同時照加入的順序", () => {
    // AC-dry-run-list (d)
    const scores = new Map([
      ["a", score("a", 60)],
      ["b", score("b", null, true)],
      ["d", score("d", 60)],
      ["e", score("e", 80)],
    ]);
    const jobs = new Map(["a", "b", "c", "d", "e"].map((c) => [c, makeJob({ 職缺代碼: c })]));
    const rows = listRows(["d", "c", "b", "a", "e"], jobs, scores, null);
    const sorted = sortRows(rows, LIST_COLUMNS, { key: "目前總分", dir: "desc" });
    expect(sorted.map((r) => r.職缺代碼)).toEqual(["e", "d", "a", "b", "c"]);
  });
});

describe("用的設定", () => {
  it("沒修改寫版本與名稱，有修改寫以哪一版為底", () => {
    expect(draftLabel("experience", SETTINGS.experience)).toBe("經歷第 1 版「預設範例」");
    expect(settingsLabel(SETTINGS)).toBe(
      "偏好以第 2 版為底修改中、經歷第 1 版「預設範例」、提示詞模板第 1 版「預設模板」",
    );
  });
});

describe("staleParts", () => {
  const texts = { preferences: "偏好內容", experience: "經歷內容", template: "模板內容" };

  it("清單與內容都沒改：不過時；只改排序不算", () => {
    expect(staleParts(RUN, ["c", "b", "a"], texts)).toEqual([]);
  });

  it("改了清單或編輯區的內容", () => {
    // AC-dry-run-result (c)、(d)
    expect(staleParts(RUN, ["a", "b"], texts)).toEqual(["試跑清單"]);
    expect(staleParts(RUN, ["a", "b", "c"], { ...texts, preferences: "改過" })).toEqual([
      "編輯區的內容",
    ]);
    expect(staleParts(RUN, ["a", "b", "c", "d"], { ...texts, template: "改過" })).toEqual([
      "試跑清單",
      "編輯區的內容",
    ]);
  });
});
