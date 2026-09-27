import { Fragment, useState, type KeyboardEvent, type ReactNode } from "react";

import { ColumnPicker } from "./ColumnPicker";
import type { Column } from "./columns";
import { nextSort, sortRows, type Identified, type Sort } from "./sort";

interface JobTableProps<Row extends Identified> {
  /** 要列出的職缺，已經篩選好；排序由表格處理 */
  rows: Row[];
  /** 可以選的欄位 */
  columns: Column<Row>[];
  /** 目前顯示的欄位 */
  visible: string[];
  /** 目前的排序；null 時照 rows 的順序，標題不標箭頭 */
  sort: Sort | null;
  /** 勾選或取消勾選欄位；沒有時不能選欄位 */
  onToggleColumn?: (key: string, checked: boolean) => void;
  onSortChange: (sort: Sort) => void;
  /** 工具列左邊的計數文字，例如「符合 3 筆／共 5 筆」 */
  countText: string;
  /** 沒有任何列時顯示的文字 */
  emptyText: string;
  /** 工具列右邊的其他按鈕 */
  tools?: ReactNode;
  /** 展開一列時顯示的內容 */
  renderDetail: (row: Row) => ReactNode;
  /** 每列最前面的標記，例如「新」 */
  rowBadge?: (row: Row) => ReactNode;
  /** 每列最前面的勾選框；沒有時不能勾選 */
  selection?: { selected: ReadonlySet<string>; onChange: (selected: Set<string>) => void };
  /** rows 已經依顯示的順序排好，表格不再排序 */
  presorted?: boolean;
}

const isEmpty = (value: string | number | null) => value === null || value === "";

function Cell<Row>({ column, row }: { column: Column<Row>; row: Row }) {
  const value = column.value(row);
  if (value === null || isEmpty(value)) return <span className="null">—</span>;
  if (column.render) return <>{column.render(value)}</>;
  if (column.format) return <>{column.format(value)}</>;
  return <>{typeof value === "number" ? value.toLocaleString("en-US") : value}</>;
}

/**
 * 職缺的表格：點標題排序、點一列展開、選擇欄位。
 *
 * 不綁定哪一份資料，職缺表、抓取的預覽都用它，資料、欄位、勾選與每列的標記由呼叫端傳入。
 */
export function JobTable<Row extends Identified>({
  rows,
  columns,
  visible,
  sort,
  onToggleColumn,
  onSortChange,
  countText,
  emptyText,
  tools,
  renderDetail,
  rowBadge,
  selection,
  presorted = false,
}: JobTableProps<Row>) {
  const [openCode, setOpenCode] = useState<string | null>(null);

  const shown = visible
    .map((key) => columns.find((c) => c.key === key))
    .filter((c): c is Column<Row> => c !== undefined);
  const sorted = presorted || sort === null ? rows : sortRows(rows, columns, sort);
  const lead = rowBadge !== undefined || selection !== undefined;
  const colSpan = shown.length + (lead ? 1 : 0);

  const toggleSelected = (code: string, checked: boolean) => {
    if (!selection) return;
    const next = new Set(selection.selected);
    if (checked) next.add(code);
    else next.delete(code);
    selection.onChange(next);
  };

  const toggleRow = (code: string) => setOpenCode((current) => (current === code ? null : code));
  const onEnterOrSpace = (action: () => void) => (event: KeyboardEvent) => {
    if (event.key === "Enter" || event.key === " ") {
      event.preventDefault();
      action();
    }
  };

  return (
    <div>
      <div className="toolbar">
        <span className="count" role="status">
          {countText}
        </span>
        <span className="spacer" />
        {tools}
        {onToggleColumn && (
          <ColumnPicker
            options={columns.map((c) => c.key)}
            visible={visible}
            onToggle={onToggleColumn}
          />
        )}
      </div>
      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              {lead && <th className="sel" />}
              {shown.map((column) => {
                const active = sort !== null && sort.key === column.key;
                const ariaSort = active
                  ? sort?.dir === "asc"
                    ? "ascending"
                    : "descending"
                  : "none";
                const changeSort = () => onSortChange(nextSort(sort, column));
                return (
                  <th
                    key={column.key}
                    className={column.numeric ? "num" : undefined}
                    aria-sort={ariaSort}
                    tabIndex={0}
                    onClick={changeSort}
                    onKeyDown={onEnterOrSpace(changeSort)}
                  >
                    {column.key}
                    {active && <span className="arrow">{sort?.dir === "asc" ? "▲" : "▼"}</span>}
                  </th>
                );
              })}
            </tr>
          </thead>
          <tbody>
            {sorted.length === 0 && (
              <tr>
                <td className="empty" colSpan={colSpan}>
                  {emptyText}
                </td>
              </tr>
            )}
            {sorted.map((row) => {
              const code = row.職缺代碼;
              const open = code === openCode;
              return (
                <Fragment key={code}>
                  <tr
                    className={open ? "row open" : "row"}
                    data-code={code}
                    tabIndex={0}
                    aria-expanded={open}
                    onClick={() => toggleRow(code)}
                    onKeyDown={(event) => {
                      // 勾選框上按空白鍵是勾選，不是展開
                      if (event.target === event.currentTarget)
                        onEnterOrSpace(() => toggleRow(code))(event);
                    }}
                  >
                    {lead && (
                      // 勾選與標記不展開這一列
                      <td className="sel" onClick={(event) => event.stopPropagation()}>
                        {selection && (
                          <input
                            type="checkbox"
                            aria-label={`選取 ${code}`}
                            checked={selection.selected.has(code)}
                            onChange={(event) => toggleSelected(code, event.target.checked)}
                          />
                        )}{" "}
                        {rowBadge?.(row)}
                      </td>
                    )}
                    {shown.map((column) => {
                      const value = column.value(row);
                      const className = [column.numeric ? "num" : "", column.className ?? ""]
                        .join(" ")
                        .trim();
                      return (
                        <td
                          key={column.key}
                          className={className || undefined}
                          // 截斷的欄位滑過時看得到完整內容
                          title={
                            column.className === "clip" && value !== null
                              ? String(value)
                              : undefined
                          }
                        >
                          <Cell column={column} row={row} />
                        </td>
                      );
                    })}
                  </tr>
                  {open && (
                    <tr className="detail">
                      <td colSpan={colSpan}>{renderDetail(row)}</td>
                    </tr>
                  )}
                </Fragment>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}
