import { useEffect, useId, useRef } from "react";

interface ConfirmDialogProps {
  open: boolean;
  message: string;
  /** 確認按鈕的文字，寫出確認後會發生的事，例如「捨棄並重新抓取」 */
  confirmLabel: string;
  onConfirm: () => void;
  onCancel: () => void;
}

/** 要使用者確認才繼續的對話框；按 Esc 等同取消 */
export function ConfirmDialog({
  open,
  message,
  confirmLabel,
  onConfirm,
  onCancel,
}: ConfirmDialogProps) {
  const ref = useRef<HTMLDialogElement>(null);
  const messageId = useId();

  useEffect(() => {
    const dialog = ref.current;
    if (dialog === null) return;
    if (open && !dialog.open) dialog.showModal();
    if (!open && dialog.open) dialog.close();
  }, [open]);

  return (
    <dialog
      ref={ref}
      className="modal"
      aria-labelledby={messageId}
      onCancel={(event) => {
        // 由 open 決定開關，Esc 只通知呼叫端
        event.preventDefault();
        onCancel();
      }}
    >
      <p id={messageId}>{message}</p>
      <div className="actions">
        <button className="btn" type="button" onClick={onCancel}>
          取消
        </button>
        <button className="btn primary" type="button" onClick={onConfirm}>
          {confirmLabel}
        </button>
      </div>
    </dialog>
  );
}
