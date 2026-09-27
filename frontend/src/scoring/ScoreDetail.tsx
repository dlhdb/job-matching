import { Fragment, useEffect, useState, type ReactNode } from "react";

import { showTime } from "../job-database/columns";
import {
  fetchScoreHistory,
  type Basis,
  type RowStatus,
  type ScoreDetails,
  type ScoreRecord,
} from "./api";
import { DIMENSIONS } from "./columns";
import { EliminatedTag } from "./ScoreTags";

const NULL = <span className="null">—</span>;

type BasisTab = "preferences" | "experience" | "prompt";

const BASIS_TABS: [BasisTab, string][] = [
  ["preferences", "偏好"],
  ["experience", "經歷"],
  ["prompt", "提示詞"],
];

/** 被淘汰時列出的快照欄位：淘汰依據的欄位 */
const ELIMINATION_FIELDS = ["職缺名稱", "公司名稱", "薪資待遇", "薪資下限", "薪資上限"];

const messageOf = (error: unknown) => (error instanceof Error ? error.message : String(error));

function Pairs({ pairs }: { pairs: [string, ReactNode][] }) {
  return (
    <dl className="kv">
      {pairs.map(([label, value]) => (
        <Fragment key={label}>
          <dt>{label}</dt>
          <dd>{value}</dd>
        </Fragment>
      ))}
    </dl>
  );
}

interface DimensionsProps {
  details: ScoreDetails;
  /** 產生 AI 維度的供應商與模型；沒有傳入時不列出 */
  source?: { provider: string | null; model: string | null };
}

/** 評分明細：四個維度的分數與理由；被淘汰時改列淘汰原因 */
export function Dimensions({ details, source }: DimensionsProps) {
  if (details.淘汰 || details.維度 === null) {
    return (
      <>
        <p>淘汰原因：</p>
        <ul>
          {details.淘汰原因.map((reason) => (
            <li key={reason}>{reason}</li>
          ))}
        </ul>
        <p className="null">被淘汰的職缺沒有呼叫 AI，沒有維度分數</p>
      </>
    );
  }
  const dimensions = details.維度;
  return (
    <>
      <ul className="dims">
        {DIMENSIONS.map((name) => {
          const dimension = dimensions[name];
          return (
            <li key={name}>
              <span>{name}</span>
              <span className="score">
                {dimension?.分數 == null ? NULL : `${dimension.分數}/5`}
              </span>
              <span className="reason">{dimension?.理由}</span>
            </li>
          );
        })}
      </ul>
      {details.未知維度.length > 0 && (
        <p>未知維度：{details.未知維度.join("、")}（總分以 3 分代入）</p>
      )}
      {source && (
        <Pairs
          pairs={[
            ["供應商", source.provider ?? NULL],
            ["模型", source.model ?? NULL],
          ]}
        />
      )}
    </>
  );
}

const versionLabel = (v: Basis["preferences"]) =>
  `第 ${v.version} 版「${v.name}」（${showTime(v.saved_at)} 儲存）`;

/** 評分依據：評分當時用的偏好、經歷，以及組回的提示詞 */
function BasisBody({ record, tab }: { record: ScoreRecord; tab: BasisTab }) {
  const basis = record.basis;
  if (basis === null) return <p className="null">這筆評分沒有記錄依據</p>;
  if (tab === "preferences" || tab === "experience") {
    const version = basis[tab];
    return (
      <>
        <p className="hint">
          評分時用的{tab === "preferences" ? "偏好" : "經歷"}：{versionLabel(version)}
        </p>
        <pre className="basis-body">{version.content}</pre>
      </>
    );
  }
  if (record.淘汰) {
    return (
      <>
        <p>被淘汰的職缺沒有呼叫 AI，沒有提示詞。淘汰依據的送評時職缺內容：</p>
        <Pairs
          pairs={ELIMINATION_FIELDS.map((name) => [name, basis.snapshot[name] ?? "（無資料）"])}
        />
        <p className="hint">淘汰條件來自偏好{versionLabel(basis.preferences)}</p>
      </>
    );
  }
  if (basis.prompt === null) return <p className="notice warn">{basis.prompt_error}</p>;
  return (
    <>
      <p className="hint">
        由送評時的職缺內容快照，加上偏好第 {basis.preferences.version} 版、經歷第{" "}
        {basis.experience.version} 版、提示詞模板第 {basis.template.version} 版組回
      </p>
      <h4>system</h4>
      <pre className="basis-body">{basis.prompt.system}</pre>
      <h4>user</h4>
      <pre className="basis-body">{basis.prompt.user}</pre>
    </>
  );
}

interface ScoreDetailProps {
  code: string;
  /** 代表的評分的識別；改變時（例如剛評完）重新取評分紀錄 */
  currentKey: string;
  /** 評分中列上的狀態；評分失敗時顯示原因 */
  status: RowStatus | undefined;
}

/**
 * 展開列的評分：目前的評分、評分明細、所有評分紀錄與評分依據。
 *
 * 點所有評分紀錄中的一筆時，評分、評分明細與評分依據換成那一筆；職缺表那一列仍是代表的評分。
 */
export function ScoreDetail({ code, currentKey, status }: ScoreDetailProps) {
  const [loaded, setLoaded] = useState<
    { key: string; records: ScoreRecord[] } | { key: string; error: string } | null
  >(null);
  // 檢視中的舊評分：記下是哪一次取回的紀錄中的第幾筆，紀錄換過（例如剛評完）就回到目前的評分
  const [viewing, setViewing] = useState<{ key: string; index: number } | null>(null);
  const [basisOpen, setBasisOpen] = useState(false);
  const [basisTab, setBasisTab] = useState<BasisTab>("preferences");
  const key = `${code}|${currentKey}`;

  useEffect(() => {
    let cancelled = false;
    fetchScoreHistory(code)
      .then((records) => {
        if (!cancelled) setLoaded({ key, records });
      })
      .catch((error: unknown) => {
        if (!cancelled) setLoaded({ key, error: `讀不到評分紀錄：${messageOf(error)}` });
      });
    return () => {
      cancelled = true;
    };
  }, [code, key]);

  const failed =
    status?.status === "failed" ? (
      <p className="viewing">
        剛才評分失敗：{status.reason}。失敗沒有寫入，可以再勾選重評；重新整理後這個標示就消失。
      </p>
    ) : null;

  if (loaded === null) {
    return (
      <section className="panel" aria-label="目前的評分">
        {failed}
        <p className="null">讀取評分紀錄中…</p>
      </section>
    );
  }
  if ("error" in loaded) {
    return (
      <section className="panel" aria-label="目前的評分">
        <p className="notice error">{loaded.error}</p>
      </section>
    );
  }

  const { records } = loaded;
  const shownIndex =
    viewing !== null && viewing.key === loaded.key && viewing.index < records.length
      ? viewing.index
      : 0;
  const view = (index: number) => setViewing(index === 0 ? null : { key: loaded.key, index });
  const shown = records[shownIndex] as ScoreRecord | undefined;
  const isOld = shownIndex !== 0;

  return (
    <>
      <section className="panel" aria-label={isOld ? "檢視中的評分" : "目前的評分"}>
        <h3>{isOld ? "檢視中的評分" : "目前的評分"}</h3>
        {failed}
        {isOld && shown && (
          <div className="viewing">
            檢視中：{showTime(shown.評分時間)} 的評分，不是目前的評分
            <button type="button" className="linkbtn" onClick={() => setViewing(null)}>
              回到目前的評分
            </button>
          </div>
        )}
        {shown ? (
          <Pairs
            pairs={[
              ["總分", shown.總分 === null ? NULL : <span className="score">{shown.總分}</span>],
              ["淘汰", <EliminatedTag eliminated={shown.淘汰} />],
              ["評語", shown.評語],
              ["評分時間", showTime(shown.評分時間)],
            ]}
          />
        ) : (
          <p className="null">還沒有評分，勾選後按「送去評分」</p>
        )}
      </section>
      <section className="panel" aria-label="評分明細">
        <h3>評分明細</h3>
        {shown ? (
          <Dimensions
            details={shown.評分明細}
            source={{ provider: shown.供應商, model: shown.模型 }}
          />
        ) : (
          <p className="null">還沒有評分</p>
        )}
      </section>
      <section className="panel" aria-label="所有評分紀錄">
        <h3>所有評分紀錄（{records.length} 筆）</h3>
        {records.length === 0 ? (
          <p className="null">還沒有評分</p>
        ) : (
          <>
            <p className="hint">點一筆切換上面顯示的評分</p>
            <div className="table-wrap">
              <table className="history">
                <thead>
                  <tr>
                    <th>評分時間</th>
                    <th>模型</th>
                    <th className="num">總分</th>
                    <th>淘汰</th>
                  </tr>
                </thead>
                <tbody>
                  {records.map((record, index) => (
                    <tr
                      key={index}
                      className={index === shownIndex ? "shown" : undefined}
                      aria-selected={index === shownIndex}
                      tabIndex={0}
                      onClick={() => view(index)}
                      onKeyDown={(event) => {
                        if (event.key === "Enter" || event.key === " ") {
                          event.preventDefault();
                          view(index);
                        }
                      }}
                    >
                      <td className="nowrap">
                        {showTime(record.評分時間)}{" "}
                        {index === 0 && <span className="cur-mark">目前</span>}
                      </td>
                      <td className="nowrap">{record.模型 ?? NULL}</td>
                      <td className="num">{record.總分 ?? NULL}</td>
                      <td>
                        <EliminatedTag eliminated={record.淘汰} />
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </>
        )}
      </section>
      {shown && (
        <section className="panel wide" aria-label="評分依據">
          <details
            className="basis"
            open={basisOpen}
            onToggle={(event) => setBasisOpen(event.currentTarget.open)}
          >
            <summary>評分依據</summary>
            {shown.basis !== null && (
              <div className="basis-tabs" role="tablist">
                {BASIS_TABS.map(([tab, label]) => (
                  <button
                    key={tab}
                    type="button"
                    role="tab"
                    aria-selected={tab === basisTab}
                    onClick={() => setBasisTab(tab)}
                  >
                    {label}
                  </button>
                ))}
              </div>
            )}
            <BasisBody record={shown} tab={basisTab} />
          </details>
        </section>
      )}
    </>
  );
}
