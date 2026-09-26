import { describe, expect, it } from "vitest";

import type { KindState, SettingsState, Version } from "./api";
import { editorState, parseDrafts, primaryAction, pruneDraft } from "./drafts";

const version = (n: number, content: string): Version => ({
  version: n,
  name: `第 ${n} 版`,
  description: "",
  saved_at: "2026-09-20T09:30:00",
  content,
});

/** 偏好有第 1、2、3 版，目前設定是第 3 版 */
const prefs: KindState = {
  current: 3,
  is_default: false,
  default_content: "一",
  versions: [version(3, "三"), version(2, "二"), version(1, "一")],
};

const settings: SettingsState = {
  preferences: prefs,
  experience: { ...prefs, current: 1, versions: [version(1, "經歷")] },
  template: { ...prefs, current: 1, versions: [version(1, "模板")] },
};

describe("editorState 與 primaryAction", () => {
  it("沒有編輯區的記錄時是目前設定，主按鈕停用", () => {
    const editor = editorState(prefs, undefined);
    expect(editor).toEqual({ base: prefs.versions[0], text: "三", modified: false });
    expect(primaryAction(prefs, editor)).toEqual({ type: "none" });
  });

  it("載入舊版本、沒有修改時是套用那一版", () => {
    const editor = editorState(prefs, { base: 1, text: "一" });
    expect(editor.base.version).toBe(1);
    expect(primaryAction(prefs, editor)).toEqual({ type: "apply", version: 1 });
  });

  it("有修改時是儲存並套用，即使改回和其他版本相同", () => {
    expect(primaryAction(prefs, editorState(prefs, { base: 3, text: "改過" }))).toEqual({
      type: "save",
    });
    expect(primaryAction(prefs, editorState(prefs, { base: 3, text: "二" }))).toEqual({
      type: "save",
    });
  });

  it("載入第 2 版後改回和第 2 版相同時是套用第 2 版", () => {
    const editor = editorState(prefs, { base: 2, text: "二" });
    expect(editor.modified).toBe(false);
    expect(primaryAction(prefs, editor)).toEqual({ type: "apply", version: 2 });
  });
});

describe("pruneDraft", () => {
  it("和目前設定相同、也沒有修改時不記", () => {
    expect(pruneDraft(prefs, { base: 3, text: "三" })).toBeUndefined();
  });

  it("有修改或載入別的版本時記住", () => {
    expect(pruneDraft(prefs, { base: 3, text: "改過" })).toEqual({ base: 3, text: "改過" });
    expect(pruneDraft(prefs, { base: 1, text: "一" })).toEqual({ base: 1, text: "一" });
  });

  it("載入的版本不存在時丟掉", () => {
    expect(pruneDraft(prefs, { base: 9, text: "改過" })).toBeUndefined();
  });
});

describe("parseDrafts", () => {
  it("逐份保留合法的編輯區", () => {
    const raw = {
      preferences: { base: 2, text: "改過" },
      experience: { base: 1, text: "經歷" },
      template: { base: 1, text: "新模板" },
    };
    expect(parseDrafts(raw, settings)).toEqual({
      preferences: { base: 2, text: "改過" },
      template: { base: 1, text: "新模板" },
    });
  });

  it.each([
    ["不是物件", "壞掉"],
    ["陣列", [1, 2]],
    ["null", null],
  ])("記住的值是%s時退回目前設定", (_, raw) => {
    expect(parseDrafts(raw, settings)).toEqual({});
  });

  it("單份格式不對或版本不存在時只丟掉那一份", () => {
    const raw = {
      preferences: { base: "2", text: "改過" },
      experience: { base: 7, text: "改過" },
      template: { base: 1.5, text: "改過" },
      unknown: { base: 1, text: "改過" },
    };
    expect(parseDrafts(raw, settings)).toEqual({});
    expect(parseDrafts({ preferences: { base: 1 } }, settings)).toEqual({});
  });
});
