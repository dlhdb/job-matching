import { useCallback, useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";

import type { JobFields } from "../api/client";
import { ConfirmDialog } from "../app/ConfirmDialog";
import { readStore, writeStore } from "../lib/storage";
import { CONTRACT_COLUMNS, toggleColumn } from "../job-database/columns";
import { JobDetail } from "../job-database/JobDetail";
import { JobTable } from "../job-database/JobTable";
import { SAVED_PARAM } from "../job-database/justSaved";
import {
  discardPreview,
  fetchAreas,
  fetchCrawlState,
  savePreview,
  startCrawl,
  stopCrawl,
  type CrawlState,
} from "./api";
import { CrawlForm } from "./CrawlForm";
import { formError, FORM_STORAGE_KEY, parseForm, toRequest, type CrawlFormValues } from "./form";
import { parsePreviewView, PREVIEW_VIEW_STORAGE_KEY, type PreviewView } from "./previewView";
import { progressPercent, progressText } from "./progress";

const COLUMN_ORDER = CONTRACT_COLUMNS.map((c) => c.key);
const POLL_MS = 1000;

const messageOf = (error: unknown) => (error instanceof Error ? error.message : String(error));

/**
 * 抓取頁：填條件後在伺服器上抓取，抓完或停止後預覽，再整批存入職缺資料庫或捨棄。
 *
 * 抓取與沒存入的結果都在伺服器上，打開頁面時取回目前的狀態，抓取中每秒更新進度。
 */
export function CrawlPage() {
  const navigate = useNavigate();
  const [areas, setAreas] = useState<string[] | null>(null);
  const [form, setForm] = useState<CrawlFormValues | null>(null);
  const [state, setState] = useState<CrawlState | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [refreshError, setRefreshError] = useState<string | null>(null);
  const [startError, setStartError] = useState<string | null>(null);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [confirming, setConfirming] = useState(false);
  const [busy, setBusy] = useState(false);
  // 開始抓取的請求送出後，到取回狀態、畫面換成抓取中之前，不能再按一次
  const [starting, setStarting] = useState(false);
  const [view, setView] = useState<PreviewView>(() =>
    parsePreviewView(readStore(PREVIEW_VIEW_STORAGE_KEY)),
  );

  // 最後一次送出的查詢；比它早送出的回應晚到時不採用，輪詢的舊狀態才不會蓋掉按鈕操作後的新狀態
  const latestRefresh = useRef(0);

  // 取不到最新狀態時保留畫面上的狀態，只顯示原因；下次取到時自動消失
  const refresh = useCallback(async () => {
    const id = ++latestRefresh.current;
    try {
      const next = await fetchCrawlState();
      if (id !== latestRefresh.current) return;
      setState(next);
      setRefreshError(null);
    } catch (error) {
      if (id !== latestRefresh.current) return;
      setRefreshError(`取不到抓取的最新狀態：${messageOf(error)}`);
    }
  }, []);

  useEffect(() => {
    Promise.all([fetchAreas(), fetchCrawlState()])
      .then(([loadedAreas, loadedState]) => {
        setAreas(loadedAreas);
        setForm(parseForm(readStore(FORM_STORAGE_KEY), loadedAreas));
        setState(loadedState);
      })
      .catch((error: unknown) => setLoadError(messageOf(error)));
  }, []);

  const running = state?.running ?? null;
  // 抓取中持續取進度，抓完或停止後停下來；取不到狀態時也持續重試，
  // 否則剛開始抓取就取不到的話，畫面會一直停在沒有抓取的樣子。
  // 收到回應後才排下一次：同時只有一個輪詢，回應再慢也會被採用
  const shouldPoll = running !== null || refreshError !== null;
  useEffect(() => {
    if (!shouldPoll) return;
    let cancelled = false;
    let timer: ReturnType<typeof setTimeout>;
    const tick = async () => {
      await refresh();
      if (!cancelled) timer = setTimeout(() => void tick(), POLL_MS);
    };
    timer = setTimeout(() => void tick(), POLL_MS);
    return () => {
      cancelled = true;
      clearTimeout(timer);
    };
  }, [shouldPoll, refresh]);

  if (loadError !== null) return <p className="notice warn">{loadError}</p>;
  if (areas === null || form === null || state === null) {
    return <p className="empty">讀取中…</p>;
  }

  const preview = state.preview;

  const start = async (discard: boolean) => {
    if (starting) return;
    setStarting(true);
    setConfirming(false);
    setStartError(null);
    setSaveError(null);
    setNotice(null);
    try {
      await startCrawl(toRequest(form, discard));
      writeStore(FORM_STORAGE_KEY, form);
    } catch (error) {
      setStartError(messageOf(error));
    }
    await refresh();
    setStarting(false);
  };

  const submit = () => {
    if (starting) return;
    const error = formError(form);
    setStartError(error);
    if (error !== null) return;
    // 還有沒存入的結果時先確認，確認後才捨棄
    if (preview !== null) {
      setConfirming(true);
      return;
    }
    void start(false);
  };

  const stop = async () => {
    try {
      await stopCrawl();
    } catch (error) {
      setStartError(messageOf(error));
    }
    await refresh();
  };

  const save = async () => {
    setBusy(true);
    setSaveError(null);
    try {
      const codes = await savePreview();
      navigate(`/?${SAVED_PARAM}=${codes.map(encodeURIComponent).join(",")}`);
    } catch (error) {
      setSaveError(messageOf(error));
      setBusy(false);
    }
  };

  const discard = async () => {
    setBusy(true);
    try {
      await discardPreview();
      setNotice("已捨棄這次的抓取結果，沒有寫入職缺資料庫。");
    } catch (error) {
      setSaveError(messageOf(error));
    }
    setBusy(false);
    await refresh();
  };

  const updateView = (next: PreviewView) => {
    setView(next);
    writeStore(PREVIEW_VIEW_STORAGE_KEY, next);
  };

  const percent = running ? progressPercent(running) : null;
  const newCodes = new Set(preview?.new_codes ?? []);

  return (
    <section aria-label="抓取">
      <CrawlForm
        values={form}
        areas={areas}
        onChange={setForm}
        onSubmit={submit}
        onStop={() => void stop()}
        running={running !== null}
        stopping={running?.stopping ?? false}
        starting={starting}
        error={startError}
      />
      {refreshError && <p className="notice error">{refreshError}</p>}
      {running && (
        <div className="progress" role="status" aria-label="抓取進度">
          {percent !== null && (
            <div className="bar">
              <span style={{ width: `${percent}%` }} />
            </div>
          )}
          <div className="msg">{progressText(running)}</div>
        </div>
      )}
      {!running && preview === null && (
        <p className="notice" role="status">
          {notice ?? state.outcome ?? "輸入條件後按「開始抓取」，抓完會在這裡預覽。"}
        </p>
      )}
      {preview && (
        <>
          <p className="notice warn">
            {preview.stopped && "已停止，只列出取完內容的職缺。"}
            預覽的職缺還沒寫進職缺資料庫，要整批存入或整批捨棄。
          </p>
          {saveError && (
            <p className="notice error" role="alert">
              {saveError}
            </p>
          )}
          <JobTable<JobFields>
            rows={preview.jobs}
            columns={CONTRACT_COLUMNS}
            visible={view.columns}
            sort={view.sort}
            onToggleColumn={(key, checked) =>
              updateView({
                ...view,
                columns: toggleColumn(COLUMN_ORDER, view.columns, key, checked),
              })
            }
            onSortChange={(sort) => updateView({ ...view, sort })}
            countText={`這次抓到 ${preview.jobs.length} 筆，其中 ${newCodes.size} 筆資料庫裡還沒有`}
            emptyText="沒有職缺"
            tools={
              <>
                <button
                  className="btn"
                  type="button"
                  disabled={busy}
                  onClick={() => void discard()}
                >
                  捨棄
                </button>
                <button
                  className="btn primary"
                  type="button"
                  disabled={busy}
                  onClick={() => void save()}
                >
                  存入職缺資料庫
                </button>
              </>
            }
            renderDetail={(job) => <JobDetail job={job} />}
            rowBadge={(job) =>
              newCodes.has(job.職缺代碼) ? <span className="tag new">新</span> : null
            }
          />
        </>
      )}
      <ConfirmDialog
        open={confirming}
        message="這次的抓取結果還沒存入，重新抓取會捨棄它。"
        confirmLabel="捨棄並重新抓取"
        onConfirm={() => void start(true)}
        onCancel={() => setConfirming(false)}
      />
    </section>
  );
}
