import { useEffect, useId, useRef, useState } from "react";

interface VersionDialogProps {
  title: string;
  /** 說明按下確認後會發生的事 */
  note: string;
  confirmLabel: string;
  initialName: string;
  initialDescription: string;
  /** 送出中停用按鈕，避免重複送出 */
  busy: boolean;
  error: string | null;
  onConfirm: (name: string, description: string) => void;
  onCancel: () => void;
}

/**
 * 填寫版本的名稱與描述：儲存新版本、或修改既有版本的名稱與描述時用。名稱必填，描述可以空白。
 *
 * 由呼叫端決定要不要顯示（顯示時才掛上），每次打開都從 initialName、initialDescription 開始。
 */
export function VersionDialog({
  title,
  note,
  confirmLabel,
  initialName,
  initialDescription,
  busy,
  error,
  onConfirm,
  onCancel,
}: VersionDialogProps) {
  const ref = useRef<HTMLDialogElement>(null);
  const titleId = useId();
  const [name, setName] = useState(initialName);
  const [description, setDescription] = useState(initialDescription);

  useEffect(() => {
    const dialog = ref.current;
    if (dialog !== null && !dialog.open) dialog.showModal();
  }, []);

  const canConfirm = name.trim() !== "" && !busy;

  return (
    <dialog
      ref={ref}
      className="modal"
      aria-labelledby={titleId}
      onCancel={(event) => {
        event.preventDefault();
        onCancel();
      }}
    >
      <form
        method="dialog"
        onSubmit={(event) => {
          event.preventDefault();
          if (canConfirm) onConfirm(name.trim(), description.trim());
        }}
      >
        <h2 id={titleId}>{title}</h2>
        <p>{note}</p>
        <label className="field">
          <span className="label">名稱（必填）</span>
          <input
            className="wide"
            value={name}
            onChange={(event) => setName(event.target.value)}
            autoFocus
          />
        </label>
        <label className="field">
          <span className="label">描述</span>
          <textarea
            rows={3}
            value={description}
            onChange={(event) => setDescription(event.target.value)}
          />
        </label>
        {name.trim() === "" && <p className="hint">名稱必填，填了才能儲存。</p>}
        {error !== null && <p className="notice error">{error}</p>}
        <div className="actions">
          <button className="btn" type="button" onClick={onCancel}>
            取消
          </button>
          <button className="btn primary" type="submit" disabled={!canConfirm}>
            {confirmLabel}
          </button>
        </div>
      </form>
    </dialog>
  );
}
