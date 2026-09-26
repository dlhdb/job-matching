"""評分用的設定：偏好、經歷、提示詞模板的預設內容、檢查，以及從資料庫讀出目前設定。

設定只存在職缺資料庫（讀寫見 job_db/settings.py），不讀 profile/ 等檔案；預設內容放在 defaults/，是每份設定的第 1 版。
"""

import sqlite3
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

import yaml
from pydantic import ValidationError

from job_db import current_versions, init_defaults
from job_scoring.models import Preferences
from job_scoring.prompt import SYSTEM_MARKER, VARIABLES, split_template, unknown_variables, used_variables

PREFERENCES = "preferences"
EXPERIENCE = "experience"
TEMPLATE = "template"
KINDS = (PREFERENCES, EXPERIENCE, TEMPLATE)

_DEFAULTS_DIR = Path(__file__).parent / "defaults"
DEFAULTS = {
    PREFERENCES: (_DEFAULTS_DIR / "preferences.yaml").read_text(encoding="utf-8"),
    EXPERIENCE: (_DEFAULTS_DIR / "experience.md").read_text(encoding="utf-8"),
    TEMPLATE: (_DEFAULTS_DIR / "template.md").read_text(encoding="utf-8"),
}

# 第 1 版的名稱與描述
_DEFAULT_META = {
    PREFERENCES: ("預設範例", "專案附的範例"),
    EXPERIENCE: ("預設範例", "專案附的範例"),
    TEMPLATE: ("預設模板", "專案附的提示詞模板"),
}

# pydantic 常見的錯誤改寫成中文；其他的沿用 pydantic 的訊息
_ERROR_MESSAGES = {
    "missing": "缺少這個欄位",
    "extra_forbidden": "不認得這個欄位",
    "int_type": "要是整數",
    "float_type": "要是數字",
    "string_type": "要是文字",
    "list_type": "要是清單",
    "dict_type": "要是鍵與值的對應",
    "model_type": "要是鍵與值的對應",
}


class SettingsError(ValueError):
    """設定的內容不合法"""

    def __init__(self, messages: list[str]):
        super().__init__("；".join(messages))
        self.messages = messages


@dataclass
class Check:
    """一份設定的檢查結果：有錯誤時不能儲存、套用、試跑或送去評分；提醒不擋"""

    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class ScoringSettings:
    """評分用的一組設定，以及它們各是哪一版（評分依據要記下）"""

    preferences: Preferences
    experience: str
    template: str
    versions: dict[str, int]


def _error_message(error: Any) -> str:
    """
    把一筆 pydantic 的驗證錯誤寫成「欄位路徑：原因」

    :param error: pydantic 的 ErrorDetails
    :return: str, 給人看的錯誤訊息
    """
    path = ".".join(str(p) for p in error["loc"]) or "（最上層）"
    kind = error["type"]
    if kind in _ERROR_MESSAGES:
        reason = _ERROR_MESSAGES[kind]
    elif kind == "greater_than":
        reason = f"要大於 {error['ctx']['gt']}"
    elif kind == "value_error":
        reason = str(error["ctx"]["error"])
    else:
        reason = error["msg"]
    return f"{path}：{reason}"


def parse_preferences(text: str) -> Preferences:
    """
    讀取 YAML 格式的偏好並依欄位字典驗證，不補任何預設值。

    :param text: str, 偏好的內容
    :return: Preferences, 驗證後的偏好
    :raises SettingsError: YAML 語法錯誤，或欄位缺少、型別錯誤、值不合法
    """
    try:
        data = yaml.safe_load(text)
    except yaml.YAMLError as e:
        raise SettingsError([f"YAML 格式錯誤：{e}"]) from None
    try:
        return Preferences.model_validate(data)
    except ValidationError as e:
        raise SettingsError([_error_message(error) for error in e.errors()]) from None


def _check_template(text: str) -> Check:
    """
    檢查提示詞模板：標記與不認得的變數是錯誤，沒用到的變數是提醒

    只檢查會送給 AI 的部分，也就是 SYSTEM 標記之後；沒有 SYSTEM 標記時檢查全文。

    :param text: str, 提示詞模板
    :return: Check
    """
    result = Check()
    try:
        split_template(text)
    except ValueError as e:
        result.errors.append(str(e))
    _, marker, body = text.partition(SYSTEM_MARKER)
    body = body if marker else text
    unknown = unknown_variables(body)
    if unknown:
        known = "、".join(f"${name}" for name in VARIABLES)
        result.errors.append(
            f"不認得的變數：{'、'.join(f'${name}' for name in unknown)}（可以用的變數：{known}）"
        )
    used = used_variables(body)
    result.warnings += [f"沒有用到 ${name}：AI 收不到這項資料" for name in VARIABLES if name not in used]
    return result


def check(kind: str, text: str) -> Check:
    """
    檢查一份設定的內容。經歷是自由格式，不檢查。

    :param kind: str, 設定的種類
    :param text: str, 內容
    :return: Check
    :raises ValueError: 不認得的種類
    """
    if kind == PREFERENCES:
        try:
            parse_preferences(text)
        except SettingsError as e:
            return Check(errors=e.messages)
        return Check()
    if kind == TEMPLATE:
        return _check_template(text)
    if kind == EXPERIENCE:
        return Check()
    raise ValueError(f"不認得的設定種類：{kind}")


def is_default(kind: str, text: str) -> bool:
    """
    內容是否和專案附的預設內容相同

    :param kind: str, 設定的種類
    :param text: str, 內容
    :return: bool
    """
    return text == DEFAULTS[kind]


def ensure_defaults(conn: sqlite3.Connection) -> list[str]:
    """
    替還沒有任何版本的設定寫入第 1 版（預設內容）並設成目前設定

    :param conn: sqlite3.Connection, open_db 開啟的連線
    :return: list[str], 這次寫入第 1 版的種類
    """
    defaults = {kind: (*_DEFAULT_META[kind], DEFAULTS[kind]) for kind in KINDS}
    return init_defaults(conn, defaults, datetime.now())


def load_current(conn: sqlite3.Connection) -> ScoringSettings:
    """
    讀出目前設定，並檢查偏好與提示詞模板

    :param conn: sqlite3.Connection, open_db 開啟的連線
    :return: ScoringSettings
    :raises SettingsError: 還沒有目前設定，或偏好、提示詞模板有錯
    """
    current = current_versions(conn)
    missing = [kind for kind in KINDS if kind not in current]
    if missing:
        raise SettingsError([f"還沒有目前設定：{'、'.join(missing)}"])
    errors = [
        message
        for kind in (PREFERENCES, TEMPLATE)
        for message in check(kind, current[kind]["內容"]).errors
    ]
    if errors:
        raise SettingsError(errors)
    return ScoringSettings(
        preferences=parse_preferences(current[PREFERENCES]["內容"]),
        experience=current[EXPERIENCE]["內容"],
        template=current[TEMPLATE]["內容"],
        versions={kind: current[kind]["版本"] for kind in KINDS},
    )

