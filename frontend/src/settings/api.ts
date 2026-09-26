/**
 * 設定頁的 API。型別來自 schema.d.ts，由 scripts/gen-api-types.sh 從 FastAPI 產生。
 */
import { errorMessage } from "../api/client";
import type { components } from "../api/schema";

export type SettingsState = components["schemas"]["SettingsState"];
export type KindState = components["schemas"]["KindState"];
export type Version = components["schemas"]["Version"];
export type CheckResult = components["schemas"]["CheckResult"];
export type Kind = components["schemas"]["CheckRequest"]["kind"];

type SavedVersion = components["schemas"]["SavedVersion"];

/** 三份設定，依分頁的順序 */
export const KINDS: Kind[] = ["preferences", "experience", "template"];

export const KIND_LABELS: Record<Kind, string> = {
  preferences: "偏好",
  experience: "經歷",
  template: "提示詞模板",
};

async function request(path: string, init?: RequestInit): Promise<Response> {
  const response = await fetch(path, init);
  if (!response.ok) throw new Error(await errorMessage(response));
  return response;
}

const json = (method: string, body: unknown): RequestInit => ({
  method,
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify(body),
});

export async function fetchSettings(): Promise<SettingsState> {
  return (await (await request("/api/settings")).json()) as SettingsState;
}

/** 檢查編輯區的內容：有錯誤時不能儲存或套用，提醒不擋 */
export async function checkContent(kind: Kind, content: string): Promise<CheckResult> {
  const response = await request("/api/settings/check", json("POST", { kind, content }));
  return (await response.json()) as CheckResult;
}

/** 存成新版本並改成目前設定，回傳新版本的編號 */
export async function saveVersion(
  kind: Kind,
  body: { name: string; description: string; content: string },
): Promise<number> {
  const response = await request(`/api/settings/${kind}/versions`, json("POST", body));
  return ((await response.json()) as SavedVersion).version;
}

/** 把某一版改成目前設定，不新增版本 */
export async function applyVersion(kind: Kind, version: number): Promise<void> {
  await request(`/api/settings/${kind}/current`, json("PUT", { version }));
}

/** 只改某一版的名稱與描述 */
export async function updateVersionMeta(
  kind: Kind,
  version: number,
  body: { name: string; description: string },
): Promise<void> {
  await request(`/api/settings/${kind}/versions/${version}`, json("PATCH", body));
}
