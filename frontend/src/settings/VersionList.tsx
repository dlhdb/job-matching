import type { Version } from "./api";

interface VersionListProps {
  /** 由新到舊 */
  versions: Version[];
  current: number;
  /** 編輯區載入的那一版 */
  loaded: number;
  onLoad: (version: Version) => void;
  onEditMeta: (version: Version) => void;
}

/** 儲存時間只顯示到分鐘 */
const showTime = (savedAt: string) => savedAt.slice(0, 16).replace("T", " ");

/** 版本紀錄：點一版載入編輯區，也可以修改名稱與描述；不提供刪除 */
export function VersionList({ versions, current, loaded, onLoad, onEditMeta }: VersionListProps) {
  return (
    <ol className="versions" aria-label="版本紀錄">
      {versions.map((v) => (
        <li key={v.version}>
          <button type="button" aria-pressed={v.version === loaded} onClick={() => onLoad(v)}>
            第 {v.version} 版 <span className="ver-name">{v.name}</span>
            {v.version === current && <span className="cur-mark"> 目前</span>}
            {v.version === loaded && v.version !== current && (
              <span className="cur-mark"> 編輯中</span>
            )}
            {v.description !== "" && <span className="ver-desc">{v.description}</span>}
            <span className="ver-desc">{showTime(v.saved_at)}</span>
          </button>
          <button
            type="button"
            className="linkbtn"
            aria-label={`編輯第 ${v.version} 版的名稱與描述`}
            onClick={() => onEditMeta(v)}
          >
            編輯名稱與描述
          </button>
        </li>
      ))}
    </ol>
  );
}
