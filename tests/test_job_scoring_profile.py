"""工作評分個人資料檔的測試：偏好檔驗證與版控設定。"""

import subprocess
from pathlib import Path

import pytest

import score_job
from job_scoring.profile import load_experience, load_preferences

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _drop_weights(data):
    del data["權重"]


def _add_unknown_weight(data):
    data["權重"]["通勤便利度"] = 0.1


def _minimum_above_expected(data):
    data["薪資"]["底線月薪"] = 80000


def _empty_title_keyword(data):
    data["淘汰條件"]["職稱關鍵字"] = ["業務", ""]


@pytest.mark.parametrize("mutate",
                         [_drop_weights, _add_unknown_weight, _minimum_above_expected, _empty_title_keyword],
                         ids=["缺少權重", "權重多出維度", "底線高於期望", "職稱關鍵字為空字串"])
def test_main_profile_invalid(mutate, preferences_data, write_profile, jobs_file, forbid_client, capsys):
    mutate(preferences_data)
    profile_dir = write_profile(preferences_data)

    code = score_job.main(["--jobs", str(jobs_file), "--profile-dir", str(profile_dir), "--job-no", "ok", "--dry-run"])

    assert code == 1
    assert "[-]" in capsys.readouterr().err


def test_main_profile_valid(profile_dir, jobs_file, forbid_client):
    """共用測試偏好本身必須合法"""
    assert score_job.main(["--jobs", str(jobs_file), "--profile-dir", str(profile_dir), "--job-no", "ok", "--dry-run"]) == 0


def test_load_preferences_template_valid():
    load_preferences(PROJECT_ROOT / "profile" / "preferences.example.yaml")


def test_load_experience_template_valid():
    assert load_experience(PROJECT_ROOT / "profile" / "experience.example.md")


def _is_ignored(path):
    result = subprocess.run(["git", "check-ignore", "-q", path], cwd=PROJECT_ROOT, check=False)
    return result.returncode == 0


@pytest.mark.parametrize("path", ["profile/preferences.yaml", "profile/experience.md", ".env"])
def test_profile_private_files_ignored(path):
    assert _is_ignored(path)


@pytest.mark.parametrize("path", ["profile/preferences.example.yaml", "profile/experience.example.md", ".env.example"])
def test_profile_templates_tracked(path):
    assert not _is_ignored(path)
    assert (PROJECT_ROOT / path).is_file()
