"""104 職缺爬蟲的端對端測試：實際連到 104 抓取並輸出檔案（network 標記）。"""

import csv
import json

import pytest

import fetch_104_jobs as m

BOM = b"\xef\xbb\xbf"


def output_files(directory, suffix):
    return sorted(directory.glob(f"*{suffix}"))


@pytest.mark.network
def test_real_scraping(monkeypatch, tmp_path):
    monkeypatch.setattr(m, "OUTPUT_DIR", tmp_path)
    fetched = []
    real_fetch_jobs = m.fetch_jobs

    def counting_fetch_jobs(*args, **kwargs):
        jobs, pagination = real_fetch_jobs(*args, **kwargs)
        fetched.extend(job.get("jobNo") for job in jobs)
        return jobs, pagination

    monkeypatch.setattr(m, "fetch_jobs", counting_fetch_jobs)

    m.execute_scraping(["Python", "Python工程師"], 1, "6001001000", "台北市", 0)

    (json_file,) = output_files(tmp_path, ".json")
    (csv_file,) = output_files(tmp_path, ".csv")
    jobs = json.loads(json_file.read_text(encoding="utf-8"))
    ids = [job["職缺代碼"] for job in jobs]
    assert ids, "沒有抓到任何職缺"
    assert len(ids) == len(set(ids)) == len(set(fetched))
    assert len(ids) < len(fetched), "兩個關鍵字的結果沒有重疊，無法確認去重生效"
    assert csv_file.read_bytes().startswith(BOM)
    with open(csv_file, encoding="utf-8-sig", newline="") as f:
        assert next(csv.reader(f)) == m.CSV_FIELDNAMES
    assert any(job["工作內容"] for job in jobs), "沒有任何職缺取得完整工作內容"
