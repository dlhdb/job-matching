import { useCallback, useEffect, useRef, useState } from "react";

import { ConfirmDialog } from "../app/ConfirmDialog";
import { readStore, writeStore } from "../lib/storage";
import {
  applyVersion,
  checkContent,
  fetchSettings,
  KIND_LABELS,
  KINDS,
  saveVersion,
  updateVersionMeta,
  type CheckResult,
  type Kind,
  type SettingsState,
  type Version,
} from "./api";
import {
  DRAFTS_STORAGE_KEY,
  currentVersion,
  editorState,
  parseDrafts,
  primaryAction,
  pruneDraft,
  type Draft,
  type Drafts,
} from "./drafts";
import { VersionDialog } from "./VersionDialog";
import { VersionList } from "./VersionList";

/** 停止輸入多久之後才檢查，避免每打一個字就送一次 */
const CHECK_DELAY_MS = 300;

/** 檢查失敗後多久重試 */
const CHECK_RETRY_MS = 2000;

const NO_RESCORE = "不會自動重評，之後開始的評分才用這一版。";

const messageOf = (error: unknown) => (error instanceof Error ? error.message : String(error));

const versionName = (v: Version) => `第 ${v.version} 版「${v.name}」`;

/** 檢查結果連同它檢查的內容，內容改了就知道結果過時 */
interface Checked {
  kind: Kind;
  text: string;
  result: CheckResult;
}

type Dialog = { mode: "save" } | { mode: "meta"; version: Version };

/**
 * 設定頁：編輯偏好、經歷與提示詞模板，每次儲存留下一個有名稱的版本，可以套用任何一版。
 *
 * 編輯區的內容只記在瀏覽器，儲存或套用前不動目前設定；儲存或套用都不會重評。
 */
export function SettingsPage() {
  const [settings, setSettings] = useState<SettingsState | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [kind, setKind] = useState<Kind>("preferences");
  const [drafts, setDrafts] = useState<Drafts>({});
  const [checked, setChecked] = useState<Checked | null>(null);
  const [checkError, setCheckError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [confirmLoad, setConfirmLoad] = useState<Version | null>(null);
  const [dialog, setDialog] = useState<Dialog | null>(null);
  const [dialogError, setDialogError] = useState<string | null>(null);

  // 最後一次送出的檢查；比它早送出的回應晚到時不採用
  const latestCheck = useRef(0);

  /** 重新取得設定；記住的編輯區跟著重新檢查，已經和目前設定相同的就不再記 */
  const reload = useCallback(async () => {
    const next = await fetchSettings();
    setSettings(next);
    setDrafts((previous) => {
      const pruned = parseDrafts(previous, next);
      writeStore(DRAFTS_STORAGE_KEY, pruned);
      return pruned;
    });
    return next;
  }, []);

  useEffect(() => {
    fetchSettings()
      .then((loaded) => {
        setSettings(loaded);
        setDrafts(parseDrafts(readStore(DRAFTS_STORAGE_KEY), loaded));
      })
      .catch((error: unknown) => setLoadError(messageOf(error)));
  }, []);

  const kindState = settings?.[kind] ?? null;
  const editor = kindState === null ? null : editorState(kindState, drafts[kind]);
  const text = editor?.text ?? null;

  // 檢查失敗時隔一段時間重試：內容沒變就不會再觸發檢查，主按鈕會一直停用
  const [checkAttempt, setCheckAttempt] = useState(0);

  useEffect(() => {
    if (text === null) return;
    const id = ++latestCheck.current;
    let retry: ReturnType<typeof setTimeout> | undefined;
    const timer = setTimeout(() => {
      checkContent(kind, text)
        .then((result) => {
          if (id !== latestCheck.current) return;
          setChecked({ kind, text, result });
          setCheckError(null);
        })
        .catch((error: unknown) => {
          if (id !== latestCheck.current) return;
          setCheckError(`無法檢查內容，稍後自動重試：${messageOf(error)}`);
          retry = setTimeout(() => setCheckAttempt((n) => n + 1), CHECK_RETRY_MS);
        });
    }, CHECK_DELAY_MS);
    return () => {
      clearTimeout(timer);
      clearTimeout(retry);
    };
  }, [kind, text, checkAttempt]);

  if (loadError !== null) return <p className="notice warn">{loadError}</p>;
  if (settings === null || kindState === null || editor === null) {
    return <p className="empty">讀取中…</p>;
  }

  const current = currentVersion(kindState);
  const action = primaryAction(kindState, editor);
  const result =
    checked !== null && checked.kind === kind && checked.text === editor.text
      ? checked.result
      : null;
  const hasErrors = result !== null && result.errors.length > 0;
  const label = KIND_LABELS[kind];
  const findLoaded = (version: number) =>
    kindState.versions.find((v) => v.version === version) ?? current;

  /**
   * 更新一份設定的編輯區並記在瀏覽器；以最新的狀態為準更新，
   * 等待請求時切到別的分頁打的字，不會被請求回來後的更新蓋掉
   */
  const updateDraft = (k: Kind, next: Draft | undefined) => {
    setDrafts((previous) => {
      const updated = { ...previous };
      const pruned = next === undefined ? undefined : pruneDraft(settings[k], next);
      if (pruned === undefined) delete updated[k];
      else updated[k] = pruned;
      writeStore(DRAFTS_STORAGE_KEY, updated);
      return updated;
    });
  };

  const setDraft = (next: Draft | undefined) => updateDraft(kind, next);

  /**
   * 儲存、套用或改名稱成功後重新取得設定；取不到時畫面上的版本紀錄與目前設定都已過時，整頁改成請使用者重新整理。
   *
   * sent 是儲存或套用送出的內容：編輯區仍是這個內容時就清掉，不論接下來取不取得到，
   * 否則重新打開時會把已存的內容當成修改再存一次；請求期間又改過的保留。只改名稱與描述時不動編輯區。
   */
  const afterChange = async (k: Kind, done: string, extra: string, sent: string | null) => {
    if (sent !== null) {
      setDrafts((previous) => {
        if (previous[k] === undefined || previous[k].text !== sent) return previous;
        const updated = { ...previous };
        delete updated[k];
        writeStore(DRAFTS_STORAGE_KEY, updated);
        return updated;
      });
    }
    try {
      await reload();
    } catch (error) {
      setLoadError(`${done}，但取不到最新的設定：${messageOf(error)}；請重新整理頁面`);
      return;
    }
    setNotice(`${done}；${extra}`);
  };

  const clearMessages = () => {
    setNotice(null);
    setActionError(null);
  };

  const load = (version: Version) => {
    clearMessages();
    setDraft({ base: version.version, text: version.content });
  };

  const requestLoad = (version: Version) => {
    if (version.version === editor.base.version && !editor.modified) return;
    // 有還沒儲存的修改時先確認才蓋掉
    if (editor.modified) {
      setConfirmLoad(version);
      return;
    }
    load(version);
  };

  const apply = async (version: number) => {
    const k = kind;
    clearMessages();
    setBusy(true);
    try {
      await applyVersion(k, version);
      const applied = findLoaded(version);
      await afterChange(
        k,
        `已套用${KIND_LABELS[k]}${versionName(applied)}`,
        NO_RESCORE,
        applied.content,
      );
    } catch (error) {
      setActionError(messageOf(error));
    }
    setBusy(false);
  };

  const onPrimary = () => {
    if (action.type === "save") {
      setDialogError(null);
      setDialog({ mode: "save" });
    }
    if (action.type === "apply") void apply(action.version);
  };

  const confirmDialog = async (name: string, description: string) => {
    if (dialog === null) return;
    const k = kind;
    setBusy(true);
    setDialogError(null);
    try {
      if (dialog.mode === "save") {
        const content = editor.text;
        const version = await saveVersion(k, { name, description, content });
        setDialog(null);
        await afterChange(
          k,
          `已把${KIND_LABELS[k]}存成第 ${version} 版並套用`,
          NO_RESCORE,
          content,
        );
      } else {
        await updateVersionMeta(k, dialog.version.version, { name, description });
        setDialog(null);
        await afterChange(
          k,
          `已修改第 ${dialog.version.version} 版的名稱與描述`,
          "內容不變。",
          null,
        );
      }
    } catch (error) {
      setDialogError(messageOf(error));
    }
    setBusy(false);
  };

  const primaryLabel =
    action.type === "save"
      ? "儲存並套用"
      : action.type === "apply"
        ? `套用第 ${action.version} 版`
        : "已是目前設定";
  const primaryDisabled = action.type === "none" || result === null || hasErrors || busy;
  const nextVersion = Math.max(...kindState.versions.map((v) => v.version)) + 1;

  return (
    <section className="card" aria-label="設定">
      <div className="kind-tabs" role="tablist" aria-label="設定的種類">
        {KINDS.map((k) => (
          <button
            key={k}
            type="button"
            role="tab"
            aria-selected={k === kind}
            onClick={() => {
              clearMessages();
              setKind(k);
            }}
          >
            {KIND_LABELS[k]}
          </button>
        ))}
      </div>
      <div className="settings-grid">
        <div>
          <div className="set-status" role="status">
            <span>目前設定：{versionName(current)}</span>
            {kind !== "template" && kindState.is_default && (
              <span className="tag default">預設範例</span>
            )}
            {editor.base.version !== kindState.current && (
              <span className="tag draft">編輯區載入{versionName(editor.base)}</span>
            )}
            {editor.modified && <span className="tag draft">有修改，還沒儲存</span>}
          </div>
          <textarea
            className="editor"
            aria-label={`${label}的編輯區`}
            spellCheck={false}
            value={editor.text}
            onChange={(event) => {
              clearMessages();
              setDraft({ base: editor.base.version, text: event.target.value });
            }}
          />
          {checkError !== null && <p className="notice warn">{checkError}</p>}
          {result !== null && result.errors.length + result.warnings.length > 0 && (
            <ul className="msgs" aria-label="檢查結果">
              {result.errors.map((e) => (
                <li key={e} className="error">
                  {e}
                </li>
              ))}
              {result.warnings.map((w) => (
                <li key={w} className="warning">
                  提醒：{w}
                </li>
              ))}
            </ul>
          )}
          <div className="set-actions">
            <button
              className="btn"
              type="button"
              disabled={editor.text === kindState.default_content || busy}
              onClick={() => {
                clearMessages();
                setDraft({ base: editor.base.version, text: kindState.default_content });
              }}
            >
              還原預設
            </button>
            <button
              className="btn"
              type="button"
              disabled={drafts[kind] === undefined || busy}
              onClick={() => {
                clearMessages();
                setDraft(undefined);
              }}
            >
              捨棄修改
            </button>
            <button
              className="btn primary"
              type="button"
              disabled={primaryDisabled}
              title={hasErrors ? "先修正上面的錯誤" : undefined}
              onClick={onPrimary}
            >
              {primaryLabel}
            </button>
          </div>
          {notice !== null && <p className="notice">{notice}</p>}
          {actionError !== null && <p className="notice error">{actionError}</p>}
        </div>
        <aside className="panel">
          <h3>版本紀錄</h3>
          <p className="hint">點一版載入編輯區，可以直接套用，或改過後儲存成新版本。</p>
          <VersionList
            versions={kindState.versions}
            current={kindState.current}
            loaded={editor.base.version}
            onLoad={requestLoad}
            onEditMeta={(version) => {
              clearMessages();
              setDialogError(null);
              setDialog({ mode: "meta", version });
            }}
          />
        </aside>
      </div>
      <ConfirmDialog
        open={confirmLoad !== null}
        message={
          confirmLoad === null
            ? ""
            : `編輯區的修改還沒儲存，載入第 ${confirmLoad.version} 版會蓋掉修改。`
        }
        confirmLabel={confirmLoad === null ? "" : `載入第 ${confirmLoad.version} 版`}
        onConfirm={() => {
          if (confirmLoad !== null) load(confirmLoad);
          setConfirmLoad(null);
        }}
        onCancel={() => setConfirmLoad(null)}
      />
      {dialog !== null && (
        <VersionDialog
          key={dialog.mode === "save" ? `save-${kind}` : `meta-${kind}-${dialog.version.version}`}
          title={
            dialog.mode === "save"
              ? `儲存並套用${label}`
              : `編輯${label}第 ${dialog.version.version} 版的名稱與描述`
          }
          note={
            dialog.mode === "save"
              ? `存成第 ${nextVersion} 版（以第 ${editor.base.version} 版為底修改），並改用這一版；${NO_RESCORE}`
              : "只改名稱與描述，這一版的內容不變。"
          }
          confirmLabel={dialog.mode === "save" ? "儲存並套用" : "儲存"}
          initialName={dialog.mode === "save" ? "" : dialog.version.name}
          initialDescription={dialog.mode === "save" ? "" : dialog.version.description}
          busy={busy}
          error={dialogError}
          onConfirm={(name, description) => void confirmDialog(name, description)}
          onCancel={() => setDialog(null)}
        />
      )}
    </section>
  );
}
