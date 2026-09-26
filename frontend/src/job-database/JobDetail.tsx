import { Fragment, type ReactNode } from "react";

import type { Job, JobFields } from "../api/client";
import { showTime } from "./columns";

const NULL = <span className="null">—</span>;

function text(value: string | number | null): ReactNode {
  if (value === null || value === "") return NULL;
  return typeof value === "number" ? value.toLocaleString("en-US") : value;
}

function link(href: string | null, label: string): ReactNode {
  return href ? (
    <a href={href} target="_blank" rel="noopener noreferrer">
      {label}
    </a>
  ) : (
    NULL
  );
}

function times(job: Partial<Pick<Job, "首次出現時間" | "最後出現時間">>): [string, ReactNode][] {
  const pairs: [string, ReactNode][] = [];
  if (job.首次出現時間) pairs.push(["首次出現時間", showTime(job.首次出現時間)]);
  if (job.最後出現時間) pairs.push(["最後出現時間", showTime(job.最後出現時間)]);
  return pairs;
}

interface JobDetailProps {
  /** 抓取的預覽還沒存入，沒有出現時間 */
  job: JobFields & Partial<Pick<Job, "首次出現時間" | "最後出現時間">>;
}

/** 展開一列時顯示的職缺完整內容；出現時間有值才顯示 */
export function JobDetail({ job }: JobDetailProps) {
  const pairs: [string, ReactNode][] = [
    ["職缺代碼", text(job.職缺代碼)],
    ["職缺名稱", text(job.職缺名稱)],
    ["公司名稱", text(job.公司名稱)],
    ["產業類別", text(job.產業類別)],
    ["地區", text(job.地區)],
    ["薪資待遇", text(job.薪資待遇)],
    [
      "薪資下限／上限",
      <>
        {text(job.薪資下限)}／{text(job.薪資上限)}
      </>,
    ],
    ["更新日期", text(job.更新日期)],
    ["應徵人數", text(job.應徵人數)],
    ["電腦專長", text(job.電腦專長)],
    ["科系要求", text(job.科系要求)],
    ["特色標籤", text(job.特色標籤)],
    ...times(job),
    [
      "連結",
      <>
        {link(job.職缺連結, "職缺頁")} {link(job.公司連結, "公司頁")}
      </>,
    ],
  ];

  return (
    <div className="detail-grid">
      <section className="panel wide" aria-label="職缺內容">
        <h3>職缺內容</h3>
        <dl className="kv">
          {pairs.map(([label, value]) => (
            <Fragment key={label}>
              <dt>{label}</dt>
              <dd>{value}</dd>
            </Fragment>
          ))}
        </dl>
        {job.工作內容 === null ? (
          <p className="null">沒有工作內容（來源取不到職缺的詳細內容）</p>
        ) : (
          <pre className="content">{job.工作內容}</pre>
        )}
      </section>
    </div>
  );
}
