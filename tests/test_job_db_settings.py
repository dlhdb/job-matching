"""設定版本的讀寫測試：新增並套用、套用舊版本、修改名稱與描述、第 1 版，以及不能刪除版本。"""

from datetime import datetime

import pytest

import job_db
import job_db.settings
from job_db import (
    add_version, apply_version, current_versions, get_version, init_defaults, list_versions, update_version_meta,
)

T1 = datetime(2026, 9, 1, 10, 0, 0)
T2 = datetime(2026, 9, 5, 20, 12, 40)


def _add(conn, kind, content, name="名稱", saved_at=T2):
    return add_version(conn, kind, name=name, description="", content=content, saved_at=saved_at)


def test_add_version_numbers_and_applies(db_conn):
    assert _add(db_conn, "preferences", "第一版") == 1
    assert _add(db_conn, "preferences", "第二版", name="後端與 LLM") == 2
    # 其他種類的版本號各自從 1 開始
    assert _add(db_conn, "experience", "經歷") == 1

    current = current_versions(db_conn)
    assert current["preferences"] == {
        "版本": 2, "名稱": "後端與 LLM", "描述": "", "儲存時間": "2026-09-05T20:12:40", "內容": "第二版",
    }
    assert current["experience"]["版本"] == 1
    assert "template" not in current


def test_add_version_same_content_still_adds(db_conn):
    _add(db_conn, "template", "內容")
    _add(db_conn, "template", "內容")

    assert [v["版本"] for v in list_versions(db_conn, "template")] == [2, 1]


@pytest.mark.parametrize("name", ["", "   "])
def test_add_version_requires_name(db_conn, name):
    with pytest.raises(ValueError, match="名稱必填"):
        _add(db_conn, "preferences", "內容", name=name)

    assert list_versions(db_conn, "preferences") == []
    assert current_versions(db_conn) == {}


def test_list_versions_newest_first(db_conn):
    for content in ("一", "二", "三"):
        _add(db_conn, "experience", content)

    assert [(v["版本"], v["內容"]) for v in list_versions(db_conn, "experience")] == [(3, "三"), (2, "二"), (1, "一")]


def test_apply_version_does_not_add(db_conn):
    for content in ("一", "二", "三"):
        _add(db_conn, "preferences", content)

    apply_version(db_conn, "preferences", 1)

    assert current_versions(db_conn)["preferences"]["版本"] == 1
    assert len(list_versions(db_conn, "preferences")) == 3
    with pytest.raises(LookupError):
        apply_version(db_conn, "preferences", 9)
    assert current_versions(db_conn)["preferences"]["版本"] == 1


def test_update_version_meta_keeps_content(db_conn):
    _add(db_conn, "preferences", "一")
    _add(db_conn, "preferences", "二", name="後端與 LLM")

    update_version_meta(db_conn, "preferences", 2, name="後端", description="第一次填")

    assert get_version(db_conn, "preferences", 2) == {
        "版本": 2, "名稱": "後端", "描述": "第一次填", "儲存時間": "2026-09-05T20:12:40", "內容": "二",
    }
    with pytest.raises(ValueError):
        update_version_meta(db_conn, "preferences", 2, name=" ", description="")
    with pytest.raises(LookupError):
        update_version_meta(db_conn, "preferences", 9, name="名稱", description="")
    assert get_version(db_conn, "preferences", 2)["名稱"] == "後端"


def test_get_version_missing_is_none(db_conn):
    assert get_version(db_conn, "preferences", 1) is None


def test_init_defaults_only_fills_missing_kinds(db_conn):
    _add(db_conn, "preferences", "自己的偏好")
    defaults = {kind: ("預設範例", "專案附的範例", f"{kind} 預設") for kind in ("preferences", "experience")}

    assert init_defaults(db_conn, defaults, T1) == ["experience"]

    current = current_versions(db_conn)
    assert current["preferences"]["內容"] == "自己的偏好"
    assert current["experience"] == {
        "版本": 1, "名稱": "預設範例", "描述": "專案附的範例", "儲存時間": "2026-09-01T10:00:00", "內容": "experience 預設",
    }


def test_unknown_kind_rejected(db_conn):
    with pytest.raises(Exception, match="CHECK"):
        _add(db_conn, "profile", "內容")


def test_no_way_to_delete_versions():
    names = set(dir(job_db)) | set(dir(job_db.settings))

    assert not [name for name in names if "delete" in name or "remove" in name]
