import type { FormEvent } from "react";

import type { CrawlFormValues } from "./form";

interface CrawlFormProps {
  values: CrawlFormValues;
  areas: string[];
  onChange: (values: CrawlFormValues) => void;
  onSubmit: () => void;
  onStop: () => void;
  /** 抓取中：不能改條件，按鈕換成「停止」 */
  running: boolean;
  stopping: boolean;
  /** 開始抓取的請求還沒有結果：不能再按一次 */
  starting: boolean;
  /** 不能開始抓取的原因 */
  error: string | null;
}

/** 抓取的條件：關鍵字、縣市、頁數、職缺性質 */
export function CrawlForm({
  values,
  areas,
  onChange,
  onSubmit,
  onStop,
  running,
  stopping,
  starting,
  error,
}: CrawlFormProps) {
  const submit = (event: FormEvent) => {
    event.preventDefault();
    onSubmit();
  };

  return (
    <form className="card crawl-form" aria-label="抓取條件" noValidate onSubmit={submit}>
      <div className="field">
        <label htmlFor="crawl-keyword">關鍵字</label>
        <input
          type="text"
          id="crawl-keyword"
          className="wide"
          placeholder="例如 Python, 資料工程師"
          value={values.keyword}
          disabled={running}
          onChange={(event) => onChange({ ...values, keyword: event.target.value })}
        />
        <span className="hint">多個關鍵字用逗號分隔</span>
      </div>
      <div className="field">
        <label htmlFor="crawl-area">縣市</label>
        <select
          id="crawl-area"
          value={values.area}
          disabled={running}
          onChange={(event) => onChange({ ...values, area: event.target.value })}
        >
          <option value="">全台灣</option>
          {areas.map((area) => (
            <option key={area} value={area}>
              {area}
            </option>
          ))}
        </select>
        <span className="hint">不選代表全台灣</span>
      </div>
      <div className="field">
        <label htmlFor="crawl-pages">每個關鍵字抓幾頁</label>
        <input
          type="number"
          id="crawl-pages"
          className="narrow"
          min={1}
          value={values.pages}
          disabled={running}
          onChange={(event) => onChange({ ...values, pages: event.target.value })}
        />
        <span className="hint">每頁 30 筆</span>
      </div>
      <div className="field">
        <label htmlFor="crawl-job-type">職缺性質</label>
        <select
          id="crawl-job-type"
          value={values.jobType}
          disabled={running}
          onChange={(event) =>
            onChange({ ...values, jobType: event.target.value as CrawlFormValues["jobType"] })
          }
        >
          <option value="0">全部</option>
          <option value="1">全職</option>
          <option value="2">兼職／工讀</option>
        </select>
        <span className="hint">&nbsp;</span>
      </div>
      <div className="field">
        <span className="label">&nbsp;</span>
        {running ? (
          <button className="btn danger" type="button" disabled={stopping} onClick={onStop}>
            停止
          </button>
        ) : (
          <button className="btn primary" type="submit" disabled={starting}>
            開始抓取
          </button>
        )}
        <span className="hint">&nbsp;</span>
      </div>
      {error && (
        <p className="err" role="alert">
          {error}
        </p>
      )}
    </form>
  );
}
