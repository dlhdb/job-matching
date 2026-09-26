"""評分用設定的測試：偏好與提示詞模板的檢查、預設內容、第 1 版，以及讀出目前設定。"""

from datetime import datetime

import pytest
import yaml

from job_db import add_version, current_versions, list_versions
from job_scoring.prompt import VARIABLES
from job_scoring.settings import (
    DEFAULTS,
    EXPERIENCE,
    KINDS,
    PREFERENCES,
    TEMPLATE,
    SettingsError,
    check,
    ensure_defaults,
    is_default,
    load_current,
    parse_preferences,
)

T = datetime(2026, 9, 20, 9, 30, 0)


def _dump(data):
    return yaml.safe_dump(data, allow_unicode=True)


def _drop_weights(data):
    del data["權重"]


def _add_unknown_weight(data):
    data["權重"]["通勤便利度"] = 0.1


def _minimum_above_expected(data):
    data["薪資"]["底線月薪"] = 80000


def _empty_title_keyword(data):
    data["淘汰條件"]["職稱關鍵字"] = ["業務", ""]


# AC-settings-check (d) 的四種錯誤，以及錯誤訊息要提到的欄位與原因
@pytest.mark.parametrize("mutate, expected", [
    (_drop_weights, "權重：缺少這個欄位"),
    (_add_unknown_weight, "權重的鍵必須剛好是"),
    (_minimum_above_expected, "薪資：底線月薪 80000 不可大於期望月薪 70000"),
    (_empty_title_keyword, "淘汰條件：職稱關鍵字不可為空字串"),
], ids=["缺少權重", "權重多出維度", "底線高於期望", "職稱關鍵字為空字串"])
def test_check_preferences_invalid(mutate, expected, preferences_data):
    mutate(preferences_data)

    result = check(PREFERENCES, _dump(preferences_data))

    assert any(expected in error for error in result.errors), result.errors
    assert result.warnings == []


@pytest.mark.parametrize("text, expected", [
    ("目標方向: [\n", "YAML 格式錯誤"),
    ("- 只是清單", "（最上層）：要是鍵與值的對應"),
])
def test_check_preferences_not_a_mapping(text, expected):
    assert expected in check(PREFERENCES, text).errors[0]


def test_check_preferences_type_error_in_chinese(preferences_data):
    preferences_data["薪資"]["期望月薪"] = "七萬"

    assert "薪資.期望月薪：要是整數" in check(PREFERENCES, _dump(preferences_data)).errors


def test_check_preferences_valid(preferences_data):
    assert check(PREFERENCES, _dump(preferences_data)).errors == []


def test_parse_preferences_raises_with_messages(preferences_data):
    _drop_weights(preferences_data)

    with pytest.raises(SettingsError) as info:
        parse_preferences(_dump(preferences_data))

    assert info.value.messages == ["權重：缺少這個欄位"]


def test_check_template_missing_user_marker():
    # AC-settings-check (a)
    text = DEFAULTS[TEMPLATE].replace("<!-- USER -->", "")

    assert "缺少 <!-- SYSTEM --> 或 <!-- USER --> 標記" in check(TEMPLATE, text).errors


def test_check_template_markers_reversed():
    text = "<!-- USER -->\n$職缺名稱\n<!-- SYSTEM -->\n指示"

    assert "<!-- SYSTEM --> 要在 <!-- USER --> 前面" in check(TEMPLATE, text).errors


def test_check_template_unknown_variable_lists_known():
    # AC-settings-check (b)
    text = DEFAULTS[TEMPLATE] + "\n- 年資：$年資"

    [error] = check(TEMPLATE, text).errors

    assert error.startswith("不認得的變數：$年資（可以用的變數：")
    assert all(f"${name}" in error for name in VARIABLES)


def test_check_template_unused_variable_warns():
    # AC-settings-check (c)
    text = DEFAULTS[TEMPLATE].replace("$工作經歷", "")

    result = check(TEMPLATE, text)

    assert result.errors == []
    assert result.warnings == ["沒有用到 $工作經歷：AI 收不到這項資料"]


def test_check_template_ignores_text_before_system_marker():
    text = "<!-- $不是變數 -->\n" + DEFAULTS[TEMPLATE]

    assert check(TEMPLATE, text).errors == []


def test_check_experience_not_checked():
    # AC-settings-check (e)
    assert check(EXPERIENCE, "只有一行文字") == check(EXPERIENCE, "") == check(EXPERIENCE, "$年資")
    assert check(EXPERIENCE, "只有一行文字").errors == []
    assert check(EXPERIENCE, "只有一行文字").warnings == []


@pytest.mark.parametrize("kind", KINDS)
def test_defaults_pass_check(kind):
    result = check(kind, DEFAULTS[kind])

    assert result.errors == []
    assert result.warnings == []


def test_is_default():
    assert is_default(PREFERENCES, DEFAULTS[PREFERENCES])
    assert not is_default(PREFERENCES, DEFAULTS[PREFERENCES] + "\n")
    assert not is_default(EXPERIENCE, DEFAULTS[PREFERENCES])


def test_ensure_defaults_writes_first_versions(db_conn):
    assert ensure_defaults(db_conn) == list(KINDS)

    current = current_versions(db_conn)
    for kind in KINDS:
        assert current[kind]["版本"] == 1
        assert current[kind]["內容"] == DEFAULTS[kind]
    assert current[PREFERENCES]["名稱"] == current[EXPERIENCE]["名稱"] == "預設範例"
    assert current[TEMPLATE]["名稱"] == "預設模板"
    # 已經有版本時不再寫入
    assert ensure_defaults(db_conn) == []
    assert all(len(list_versions(db_conn, kind)) == 1 for kind in KINDS)


def test_load_current(db_conn, preferences_data):
    ensure_defaults(db_conn)
    add_version(db_conn, PREFERENCES, name="我的偏好", description="", content=_dump(preferences_data), saved_at=T)
    add_version(db_conn, EXPERIENCE, name="我的經歷", description="", content="經歷", saved_at=T)
    add_version(db_conn, EXPERIENCE, name="我的經歷 2", description="", content="經歷 2", saved_at=T)

    settings = load_current(db_conn)

    assert settings.preferences == parse_preferences(_dump(preferences_data))
    assert settings.experience == "經歷 2"
    assert settings.template == DEFAULTS[TEMPLATE]
    assert settings.versions == {PREFERENCES: 2, EXPERIENCE: 3, TEMPLATE: 1}


def test_load_current_rejects_invalid(db_conn, preferences_data):
    ensure_defaults(db_conn)
    _drop_weights(preferences_data)
    add_version(db_conn, PREFERENCES, name="壞掉的", description="", content=_dump(preferences_data), saved_at=T)

    with pytest.raises(SettingsError, match="權重：缺少這個欄位"):
        load_current(db_conn)


def test_load_current_without_settings(db_conn):
    with pytest.raises(SettingsError, match="還沒有目前設定"):
        load_current(db_conn)
