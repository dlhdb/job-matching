/**
 * 設定頁的編輯區：每份設定載入的是哪一版、改成什麼內容，以及主按鈕該做什麼。
 *
 * 編輯區的內容記在瀏覽器，直到套用、儲存或捨棄修改；和目前設定相同、也沒有修改時就不記。
 */
import { isRecord } from "../job-database/view";
import { KINDS, type Kind, type KindState, type SettingsState, type Version } from "./api";

export const DRAFTS_STORAGE_KEY = "settings.drafts.v1";

/** 一份設定的編輯區：以哪一版為底，以及目前的內容 */
export interface Draft {
  base: number;
  text: string;
}

export type Drafts = Partial<Record<Kind, Draft>>;

export interface EditorState {
  /** 編輯區載入的那一版 */
  base: Version;
  text: string;
  /** 和載入的那一版相比有沒有修改 */
  modified: boolean;
}

/** 主按鈕：有修改時儲存並套用、載入的不是目前設定時套用那一版，否則停用 */
export type PrimaryAction =
  { type: "save" } | { type: "apply"; version: number } | { type: "none" };

const findVersion = (state: KindState, version: number) =>
  state.versions.find((v) => v.version === version);

/** 目前設定的那一版 */
export function currentVersion(state: KindState): Version {
  const version = findVersion(state, state.current);
  if (version === undefined) throw new Error(`版本紀錄裡沒有目前設定的第 ${state.current} 版`);
  return version;
}

/** 算出編輯區的狀態；沒有編輯區的記錄時就是目前設定 */
export function editorState(state: KindState, draft: Draft | undefined): EditorState {
  const base = (draft && findVersion(state, draft.base)) ?? currentVersion(state);
  const text = draft && base.version === draft.base ? draft.text : base.content;
  return { base, text, modified: text !== base.content };
}

export function primaryAction(state: KindState, editor: EditorState): PrimaryAction {
  if (editor.modified) return { type: "save" };
  if (editor.base.version !== state.current) return { type: "apply", version: editor.base.version };
  return { type: "none" };
}

/** 編輯區和目前設定相同、也沒有修改時不必記住；載入的版本不存在時丟掉 */
export function pruneDraft(state: KindState, draft: Draft | undefined): Draft | undefined {
  if (draft === undefined || findVersion(state, draft.base) === undefined) return undefined;
  const editor = editorState(state, draft);
  return primaryAction(state, editor).type === "none" ? undefined : draft;
}

/** 逐份檢查記住的編輯區，格式不對或那一版不存在的丟掉，退回目前設定 */
export function parseDrafts(raw: unknown, settings: SettingsState): Drafts {
  const drafts: Drafts = {};
  if (!isRecord(raw)) return drafts;
  for (const kind of KINDS) {
    const item = raw[kind];
    if (!isRecord(item) || !Number.isInteger(item.base) || typeof item.text !== "string") continue;
    const draft = pruneDraft(settings[kind], { base: item.base as number, text: item.text });
    if (draft !== undefined) drafts[kind] = draft;
  }
  return drafts;
}
