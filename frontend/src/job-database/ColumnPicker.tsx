import { useEffect, useRef, useState } from "react";

interface ColumnPickerProps {
  /** 可以選的欄位，依顯示的順序 */
  options: string[];
  visible: string[];
  onToggle: (key: string, checked: boolean) => void;
}

/** 「選擇欄位」按鈕與勾選欄位的浮動視窗；點視窗外面時關閉 */
export function ColumnPicker({ options, visible, onToggle }: ColumnPickerProps) {
  const [open, setOpen] = useState(false);
  const wrapRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const closeOnOutside = (event: MouseEvent) => {
      if (!wrapRef.current?.contains(event.target as Node)) setOpen(false);
    };
    document.addEventListener("click", closeOnOutside);
    return () => document.removeEventListener("click", closeOnOutside);
  }, [open]);

  return (
    <div className="popover-wrap" ref={wrapRef}>
      <button className="btn" type="button" aria-expanded={open} onClick={() => setOpen((v) => !v)}>
        選擇欄位
      </button>
      {open && (
        <div className="popover" role="group" aria-label="選擇欄位">
          <div className="col-group">
            <h3>職缺</h3>
            <div className="col-list">
              {options.map((key) => {
                const checked = visible.includes(key);
                // 至少要留一欄：只剩一欄時不能取消
                const last = checked && visible.length === 1;
                return (
                  <label key={key} title={last ? "至少要留一欄" : undefined}>
                    <input
                      type="checkbox"
                      checked={checked}
                      disabled={last}
                      onChange={(event) => onToggle(key, event.target.checked)}
                    />{" "}
                    {key}
                  </label>
                );
              })}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
