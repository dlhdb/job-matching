"""把舊版結構的資料庫改成最新版：先備份，在同一個交易裡改版，失敗時還原成改版前的內容。"""

import sqlite3
from contextlib import closing
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from job_db.schema import (
    JOB_DDL,
    JOB_SCORES_DDL,
    JOB_SCORES_INDEX_DDL,
    LATEST_VERSION,
    SETTINGS_DDL,
    db_version,
    is_empty,
)


@dataclass
class UpgradeResult:
    """一次改版的結果"""

    from_version: int
    to_version: int
    scores_moved: int
    skipped_manual: int
    skipped_orphan: int
    backup: Path


class UpgradeError(Exception):
    """改版失敗；資料庫已還原成改版前的內容"""


def _columns(conn: sqlite3.Connection, table: str) -> set[str]:
    """
    取出資料表的欄名

    :param conn: sqlite3.Connection, 開啟中的連線
    :param table: str, 資料表名稱
    :return: set[str], 欄名；資料表不存在時為空集合
    """
    return {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}


def _v0_to_v1(conn: sqlite3.Connection) -> tuple[int, int, int]:
    """
    第 0 版改成第 1 版：job_scores 拿掉評分來源、加上評分依據與外鍵，並建立設定的資料表

    第 0 版是開始記版本之前的各種舊版，依欄位判斷：
    - 最舊版以職缺代碼為主鍵，評分明細叫「評分結果」；只有自動評分寫入評分結果，沒有的是手動評分
    - 之後的版本有評分來源（auto／manual），可能還留著快取鍵欄位與限制手動評分的唯一索引

    新結構無法表示手動評分與沒有對應職缺的評分，這兩種略過並計數。建表語法要是第 1 版的樣子：
    之後再改版時，這一步仍要建出第 1 版的表，再由下一步改。

    :param conn: sqlite3.Connection, 開啟中的連線（呼叫端負責交易）
    :return: tuple (int, int, int), (搬移的評分筆數, 略過的手動評分筆數, 略過的沒有對應職缺的評分筆數)
    """
    for ddl in JOB_DDL:
        conn.execute(ddl)
    moved = skipped_manual = skipped_orphan = 0
    columns = _columns(conn, "job_scores")
    if columns:
        # 改名後舊表的索引名稱還在，要先刪掉才能建新表的同名索引
        conn.execute("DROP INDEX IF EXISTS job_scores_job")
        conn.execute("DROP INDEX IF EXISTS job_scores_manual")
        conn.execute("ALTER TABLE job_scores RENAME TO job_scores_old")
        if "評分來源" in columns:
            is_auto, details, score_id = "\"評分來源\" = 'auto'", '"評分明細"', '"評分編號"'
        elif "評分結果" in columns:
            is_auto, details, score_id = '"評分結果" IS NOT NULL', '"評分結果"', "NULL"
        else:
            # 不猜：SQLite 會把不存在的雙引號欄名當成字串，猜錯時整欄會被寫成欄名
            raise sqlite3.DatabaseError(f"看不出 job_scores 是哪一種舊版，欄位：{'、'.join(sorted(columns))}")
        has_job = 'EXISTS (SELECT 1 FROM jobs WHERE jobs."職缺代碼" = old."職缺代碼")'
        skipped_manual = conn.execute(f"SELECT COUNT(*) FROM job_scores_old WHERE NOT ({is_auto})").fetchone()[0]
        skipped_orphan = conn.execute(
            f"SELECT COUNT(*) FROM job_scores_old AS old WHERE {is_auto} AND NOT {has_job}"
        ).fetchone()[0]
        conn.execute(JOB_SCORES_DDL)
        # 保留原本的評分編號，同一秒內「後寫入的在前」的順序才不變；最舊版沒有評分編號，依寫入順序重新編
        cursor = conn.execute(
            'INSERT INTO job_scores ("評分編號", "職缺代碼", "評分時間", "淘汰", "總分", "評語", "評分明細", "供應商", "模型") '
            f'SELECT {score_id}, "職缺代碼", "評分時間", "淘汰", "總分", "評語", {details}, "供應商", "模型" '
            f"FROM job_scores_old AS old WHERE {is_auto} AND {has_job} ORDER BY rowid"
        )
        moved = cursor.rowcount
        conn.execute("DROP TABLE job_scores_old")
    conn.execute(JOB_SCORES_DDL)
    conn.execute(JOB_SCORES_INDEX_DDL)
    for ddl in SETTINGS_DDL:
        conn.execute(ddl)
    return moved, skipped_manual, skipped_orphan


def _backup_path(path: Path, version: int) -> Path:
    """
    找出還不存在的備份檔名：<檔名>.v<版本>-<時間>.bak，已存在時依序加上 _2、_3……

    :param path: Path, 資料庫檔
    :param version: int, 改版前的版本
    :return: Path, 備份檔的路徑，和資料庫在同一個目錄
    """
    stem = f"{path.name}.v{version}-{datetime.now():%Y%m%d_%H%M%S}"
    candidate, n = path.with_name(f"{stem}.bak"), 1
    while candidate.exists():
        n += 1
        candidate = path.with_name(f"{stem}_{n}.bak")
    return candidate


def _restore(conn: sqlite3.Connection, backup: Path) -> str:
    """
    改版失敗後 rollback，再用備份蓋回原檔；還原本身失敗時不拋例外，改在說明中請使用者手動還原

    :param conn: sqlite3.Connection, 改版中的連線
    :param backup: Path, 改版前的備份
    :return: str, 給人看的還原結果，含備份的路徑
    """
    try:
        if conn.in_transaction:
            conn.execute("ROLLBACK")
        with closing(sqlite3.connect(backup)) as source:
            source.backup(conn)
    except sqlite3.Error as e:
        return f"自動還原也失敗：{e}；請關掉其他開著資料庫的程式，再把備份 {backup} 複製回原本的位置"
    return f"改版前的備份：{backup}"


def upgrade_db(path: str | Path) -> UpgradeResult | None:
    """
    把舊版的資料庫改成最新版。

    改版前先用 SQLite 的 backup API 備份到同一個目錄，備份檔在改版成功後留著。
    所有步驟與外鍵檢查在同一個交易裡，任何一步失敗都 rollback，再用備份蓋回原檔。

    :param path: str or Path, 資料庫檔路徑
    :return: UpgradeResult or None, 改版的結果；檔案不存在、還沒有任何資料表、已是最新版或比程式新時為 None
    :raises UpgradeError: 無法備份（資料庫沒有改動），或改版失敗（資料庫已還原成改版前的內容）
    """
    path = Path(path)
    if not path.exists():
        return None
    with closing(sqlite3.connect(path, autocommit=True)) as conn:
        version = db_version(conn)
        # 比程式新的版本交給 open_db 報錯
        if version >= LATEST_VERSION or is_empty(conn):
            return None
        backup = _backup_path(path, version)
        try:
            with closing(sqlite3.connect(backup)) as target:
                conn.backup(target)
        except (sqlite3.Error, OSError) as e:
            # 還沒動到資料庫；備份不完整，留著反而會被誤當成可以還原的檔案
            backup.unlink(missing_ok=True)
            raise UpgradeError(f"無法備份，沒有改版：{e}") from e
        try:
            conn.execute("BEGIN IMMEDIATE")
        except sqlite3.Error as e:
            # 交易沒開始，資料庫沒有改動（例如被其他程式鎖住）
            raise UpgradeError(f"無法開始改版，資料庫沒有改動：{e}（改版前的備份：{backup}）") from e
        # 取得寫入鎖之前，另一個同時啟動的程式可能已經改好了；改好就不再改一次
        if db_version(conn) >= LATEST_VERSION:
            conn.execute("ROLLBACK")
            backup.unlink()
            return None
        try:
            moved, skipped_manual, skipped_orphan = _v0_to_v1(conn)
            violations = conn.execute("PRAGMA foreign_key_check").fetchall()
            if violations:
                tables = "、".join(sorted({row[0] for row in violations}))
                raise sqlite3.IntegrityError(f"改版後有 {len(violations)} 筆資料違反外鍵（{tables}）")
            conn.execute(f"PRAGMA user_version = {LATEST_VERSION}")
            conn.execute("COMMIT")
        except Exception as e:
            raise UpgradeError(f"{e}（{_restore(conn, backup)}）") from e
    return UpgradeResult(version, LATEST_VERSION, moved, skipped_manual, skipped_orphan, backup)
