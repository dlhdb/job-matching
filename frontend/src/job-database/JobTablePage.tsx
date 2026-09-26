import { useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";

import { fetchJobs, type Job } from "../api/client";
import { readStore, writeStore } from "../lib/storage";
import { JOB_COLUMNS, toggleColumn } from "./columns";
import { EMPTY_FILTERS, matchesFilters } from "./filter";
import { Filters } from "./Filters";
import { JobDetail } from "./JobDetail";
import { JobTable } from "./JobTable";
import { parseSavedCodes, pickJustSaved, SAVED_PARAM } from "./justSaved";
import { parseView, resetView, VIEW_STORAGE_KEY, type View } from "./view";

const COLUMN_ORDER = JOB_COLUMNS.map((c) => c.key);

type Loaded = { jobs: Job[] } | { error: string } | null;

/** 職缺表：列出職缺資料庫的全部職缺，篩選、排序、選欄位都在瀏覽器處理 */
export function JobTablePage() {
  const [loaded, setLoaded] = useState<Loaded>(null);
  const [view, setView] = useState<View>(() => parseView(readStore(VIEW_STORAGE_KEY)));
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
    setView(next);
    writeStore(VIEW_STORAGE_KEY, next);
  };

  // 拿掉網址上的清單，重新整理後才不會又只看剛存入的職缺
  const closeJustSaved = () => {
    const next = new URLSearchParams(searchParams);
    next.delete(SAVED_PARAM);
    setSearchParams(next, { replace: true });
  };

  if (loaded === null) return <p className="empty">讀取職缺中…</p>;
  if ("error" in loaded) return <p className="notice warn">{loaded.error}</p>;

  const { jobs } = loaded;
  const rows = savedCodes
    ? pickJustSaved(jobs, savedCodes)
    : jobs.filter((job) => matchesFilters(job, view.filters));

  return (
    <section aria-label="職缺表">
      <Filters
        filters={view.filters}
        onChange={(filters) => updateView({ ...view, filters })}
        onClear={() => updateView({ ...view, filters: EMPTY_FILTERS })}
        justSavedCount={savedCodes ? rows.length : null}
        onCloseJustSaved={closeJustSaved}
      />
      <JobTable
        rows={rows}
        columns={JOB_COLUMNS}
        visible={view.columns}
        sort={view.sort}
        onToggleColumn={(key, checked) =>
          updateView({ ...view, columns: toggleColumn(COLUMN_ORDER, view.columns, key, checked) })
        }
        onSortChange={(sort) => updateView({ ...view, sort })}
        countText={`符合 ${rows.length} 筆／共 ${jobs.length} 筆`}
        emptyText={jobs.length === 0 ? "職缺資料庫還沒有職缺" : "沒有符合條件的職缺"}
        tools={
          <button
            className="btn"
            type="button"
            onClick={() => updateView(resetView(view, savedCodes !== null))}
          >
            還原預設檢視
          </button>
        }
        renderDetail={(job) => <JobDetail job={job} />}
      />
    </section>
  );
}
