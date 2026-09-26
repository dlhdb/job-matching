import type { RowStatus } from "./api";

/** 淘汰欄的標籤 */
export function EliminatedTag({ eliminated }: { eliminated: boolean }) {
  return eliminated ? <span className="tag out">淘汰</span> : <span className="tag in">否</span>;
}

/** 評分中列上的狀態：排隊中、評分中、評分失敗與原因 */
export function StatusTag({ status }: { status: RowStatus }) {
  if (status.status === "queued") return <span className="tag queued">排隊中</span>;
  if (status.status === "scoring") return <span className="tag scoring">評分中</span>;
  return (
    <span className="tag failed" title={status.reason ?? undefined}>
      評分失敗：{status.reason}
    </span>
  );
}
