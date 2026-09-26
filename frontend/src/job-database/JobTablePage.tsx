import { useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";

import { fetchJobs, type Job } from "../api/client";
import { readStore, writeStore } from "../lib/storage";
import { JOB_COLUMNS, toggleColumn } from "./columns";
import { useNoExtension, type JobTableExtension, type UseJobTableExtension } from "./extension";
import { matchesFilters } from "./filter";
import { Filters } from "./Filters";
import { JobDetail } from "./JobDetail";
import { JobTable } from "./JobTable";
import { parseSavedCodes, pickJustSaved, SAVED_PARAM } from "./justSaved";
import { sortRows } from "./sort";
import {
  BASE_VIEW_CONFIG,
  DEFAULT_VIEW,
  parseView,
  resetView,
  VIEW_STORAGE_KEY,
  type View,
  type ViewConfig,
} from "./view";

type Loaded = { jobs: Job[] } | { error: string } | null;

/** 有擴充時，可以選的欄位多了擴充的欄位，預設檢視換成擴充的 */
function viewConfig(extension: JobTableExtension | null): ViewConfig {
  if (extension === null) return BASE_VIEW_CONFIG;
  return {
    known: new Set([...BASE_VIEW_CONFIG.known, ...extension.columns.map((c) => c.key)]),
    defaults: {
      columns: extension.defaultColumns,
      sort: extension.defaultSort,
      filters: { ...DEFAULT_VIEW.filters, ...extension.filterDefaults },
    },
  };
}

interface JobTablePageProps {
  /** 在職缺表上疊加欄位、篩選、展開內容與勾選的擴充 */
  useExtension?: UseJobTableExtension;
}

/** 職缺表：列出職缺資料庫的全部職缺，篩選、排序、選欄位都在瀏覽器處理 */
export function JobTablePage({ useExtension = useNoExtension }: JobTablePageProps) {
  const extension = useExtension();
  const config = viewConfig(extension);
  const [loaded, setLoaded] = useState<Loaded>(null);
  const [view, setView] = useState<View>(() => parseView(readStore(VIEW_STORAGE_KEY), config));
  const [searchParams, setSearchParams] = useSearchParams();
  const savedCodes = parseSavedCodes(searchParams);

  useEffect(() => {
    fetchJobs()
      .then((jobs) => setLoaded({ jobs }))
      .catch((error: unknown) =>
        setLoaded({ error: error instanceof Error ? error.message : String(error) }),
      );
  }, []);

  const updateView = (next: View) => {
    const filtersChanged = JSON.stringify(next.filters) !== JSON.stringify(view.filters);
    const sortChanged = JSON.stringify(next.sort) !== JSON.stringify(view.sort);
    if (filtersChanged || sortChanged) extension?.onViewChange({ filtersChanged });
    setView(next);
    writeStore(VIEW_STORAGE_KEY, next);
  };

  // 拿掉網址上的清單，重新整理後才不會又只看剛存入的職缺
  const closeJustSaved = () => {
    extension?.onViewChange({ filtersChanged: true });
    const next = new URLSearchParams(searchParams);
    next.delete(SAVED_PARAM);
    setSearchParams(next, { replace: true });
  };

  const status = extension?.status ?? "ready";
  if (loaded === null || status === "loading") return <p className="empty">讀取職缺中…</p>;
  if ("error" in loaded) return <p className="notice warn">{loaded.error}</p>;
  if (typeof status === "object") return <p className="notice warn">{status.error}</p>;

  const { jobs } = loaded;
  const columns = extension ? [...JOB_COLUMNS, ...extension.columns] : JOB_COLUMNS;
  const columnOrder = columns.map((c) => c.key);
  const matched = savedCodes
    ? pickJustSaved(jobs, savedCodes)
    : jobs.filter(
        (job) =>
          matchesFilters(job, view.filters) &&
          (extension?.matchesFilters(job, view.filters) ?? true),
      );

  // 只看剛存入的職缺時其他篩選暫停，檢視由剛存入的清單決定
  const viewKey = JSON.stringify(
    savedCodes
      ? { sort: view.sort, saved: savedCodes }
      : { sort: view.sort, filters: view.filters },
  );
  const frozen = extension?.frozenOrder(viewKey) ?? null;
  const byCode = new Map(jobs.map((job) => [job.職缺代碼, job]));
  // 列的順序固定時列出固定的那些列，分數改變後不再符合篩選的列也留著
  const rows = frozen
    ? frozen.map((code) => byCode.get(code)).filter((job): job is Job => job !== undefined)
    : sortRows(matched, columns, view.sort);

  return (
    <section aria-label="職缺表">
      <Filters
        filters={view.filters}
        onChange={(filters) => updateView({ ...view, filters })}
        extra={extension?.renderFilters(
          view.filters,
          (filters) => updateView({ ...view, filters }),
          savedCodes !== null,
        )}
        onClear={() => updateView({ ...view, filters: config.defaults.filters })}
        justSavedCount={savedCodes ? matched.length : null}
        onCloseJustSaved={closeJustSaved}
      />
      {extension?.renderBanner()}
      <JobTable
        rows={rows}
        presorted
        columns={columns}
        visible={view.columns}
        sort={view.sort}
        onToggleColumn={(key, checked) =>
          updateView({ ...view, columns: toggleColumn(columnOrder, view.columns, key, checked) })
        }
        onSortChange={(sort) => updateView({ ...view, sort })}
        countText={
          frozen
            ? `列出 ${rows.length} 筆／共 ${jobs.length} 筆・評分後列的順序固定，改篩選或排序時才重新排列`
            : `符合 ${rows.length} 筆／共 ${jobs.length} 筆`
        }
        emptyText={jobs.length === 0 ? "職缺資料庫還沒有職缺" : "沒有符合條件的職缺"}
        tools={
          <>
            {extension?.renderTools({ rows, viewKey })}
            <button
              className="btn"
              type="button"
              onClick={() => updateView(resetView(view, savedCodes !== null, config))}
            >
              還原預設檢視
            </button>
          </>
        }
        renderDetail={(job) => <JobDetail job={job}>{extension?.renderDetail(job)}</JobDetail>}
        rowBadge={extension?.rowBadge}
        selection={extension?.selection}
      />
    </section>
  );
}
