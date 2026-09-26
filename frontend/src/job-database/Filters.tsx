import type { Filters as FilterValues } from "./filter";

interface FiltersProps {
  filters: FilterValues;
  onChange: (filters: FilterValues) => void;
  onClear: () => void;
  /** 只看剛存入的職缺時的筆數；null 代表沒有在看剛存入的職缺 */
  justSavedCount: number | null;
  onCloseJustSaved: () => void;
}

/** 職缺表的篩選列：關鍵字、地區、剛存入的標籤與清除篩選 */
export function Filters({
  filters,
  onChange,
  onClear,
  justSavedCount,
  onCloseJustSaved,
}: FiltersProps) {
  // 只看剛存入的職缺時，其他篩選暫停，不能調整
  const paused = justSavedCount !== null;
  return (
    <div className="card filters" role="search" aria-label="篩選">
      <div className="field">
        <label htmlFor="filter-keyword">關鍵字</label>
        <input
          type="search"
          id="filter-keyword"
          placeholder="職缺名稱、公司、工作內容、電腦專長"
          value={filters.keyword}
          disabled={paused}
          onChange={(event) => onChange({ ...filters, keyword: event.target.value })}
        />
        <span className="hint">多個關鍵字用逗號分隔，符合任一個就算</span>
      </div>
      <div className="field">
        <label htmlFor="filter-area">地區</label>
        <input
          type="search"
          id="filter-area"
          placeholder="例如 台北市, 內湖"
          value={filters.area}
          disabled={paused}
          onChange={(event) => onChange({ ...filters, area: event.target.value })}
        />
        <span className="hint">多個地名用逗號分隔，「臺」視為「台」</span>
      </div>
      {paused && (
        <div className="field">
          <span className="label">暫時篩選</span>
          <span className="filter-tag">
            <span>剛存入的 {justSavedCount} 筆</span>
            <button type="button" aria-label="關掉「剛存入」標籤" onClick={onCloseJustSaved}>
              ×
            </button>
          </span>
          <span className="hint">其他篩選暫停，關掉標籤後才能調整</span>
        </div>
      )}
      <div className="field">
        <span className="label">&nbsp;</span>
        <button className="btn" type="button" disabled={paused} onClick={onClear}>
          清除篩選
        </button>
        <span className="hint">&nbsp;</span>
      </div>
    </div>
  );
}
