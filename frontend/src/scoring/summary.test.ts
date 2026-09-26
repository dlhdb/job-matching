import { describe, expect, it } from "vitest";

import type { RunOut } from "./api";
import { progressPercent, progressText, summaryText } from "./summary";

function run(overrides: Partial<RunOut>): RunOut {
  return {
    id: 1,
    total: 5,
    done: 5,
    ok: 3,
    eliminated: 1,
    failed: 1,
    skipped: 0,
    stopping: false,
    stopped: false,
    error: null,
    statuses: [],
    ...overrides,
  };
}

describe("summaryText", () => {
  it("評完且有失敗時說明失敗的沒有寫入", () => {
    // AC-score-run (c)
    expect(summaryText(run({}))).toBe(
      "評分完成：評分 3 筆、淘汰 1 筆、失敗 1 筆。失敗的沒有寫入，列上看得到原因，可以再勾選重評。",
    );
  });

  it("停止時寫出沒評的筆數", () => {
    // AC-score-run (b)
    expect(summaryText(run({ done: 3, ok: 2, failed: 0, skipped: 2, stopped: true }))).toBe(
      "已停止：評分 2 筆、淘汰 1 筆、失敗 0 筆、沒評 2 筆。",
    );
  });

  it("因錯誤停止時先寫出錯誤", () => {
    expect(
      summaryText(
        run({
          done: 0,
          ok: 0,
          eliminated: 0,
          failed: 0,
          skipped: 5,
          stopped: true,
          error: "無法開始評分：連不上",
        }),
      ),
    ).toBe("無法開始評分：連不上。已停止：評分 0 筆、淘汰 0 筆、失敗 0 筆、沒評 5 筆。");
  });
});

describe("progress", () => {
  it("評完幾筆／共幾筆", () => {
    expect(progressText(run({ done: 2 }))).toBe("評分中 2／5");
    expect(progressPercent(run({ done: 2 }))).toBe(40);
    expect(progressPercent(run({ total: 0, done: 0 }))).toBe(0);
  });
});
