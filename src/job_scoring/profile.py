"""讀取並驗證個人資料檔（job-scoring.md §2）。"""

from pathlib import Path

import yaml
from pydantic import ValidationError

from job_scoring.models import Preferences


class ProfileError(ValueError):
    """個人資料檔缺少或格式錯誤"""


def load_preferences(path: str | Path) -> Preferences:
    """
    讀取 preferences.yaml 並依欄位字典驗證，不補任何預設值。

    :param path: str or Path, preferences.yaml 的路徑
    :return: Preferences, 驗證後的偏好設定
    :raises ProfileError: 檔案不存在、YAML 語法錯誤，或欄位缺少、型別錯誤、值不合法
    """
    path = Path(path)
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise ProfileError(f"找不到偏好檔：{path}（可複製 preferences.example.yaml 修改）") from None
    except yaml.YAMLError as e:
        raise ProfileError(f"偏好檔 YAML 格式錯誤：{path}\n{e}") from None

    try:
        return Preferences.model_validate(data)
    except ValidationError as e:
        details = "\n".join(
            f"    - {'.'.join(str(p) for p in err['loc']) or '（根層級）'}：{err['msg']}"
            for err in e.errors()
        )
        raise ProfileError(f"偏好檔內容不合法：{path}\n{details}") from None


def load_experience(path: str | Path) -> str:
    """
    讀取 experience.md 全文。

    :param path: str or Path, experience.md 的路徑
    :return: str, 去除頭尾空白的經歷全文
    :raises ProfileError: 檔案不存在或內容為空
    """
    path = Path(path)
    try:
        text = path.read_text(encoding="utf-8").strip()
    except FileNotFoundError:
        raise ProfileError(f"找不到經歷檔：{path}（可複製 experience.example.md 修改）") from None
    if not text:
        raise ProfileError(f"經歷檔是空的：{path}")
    return text
