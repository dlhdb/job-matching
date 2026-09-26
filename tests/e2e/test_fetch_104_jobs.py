"""104 職缺爬蟲的整合檢查：實際連到 104 抓取，確認 API 與欄位整理仍然可用（network 標記）。"""

import threading

import pytest

import fetch_104_jobs as m
from job_db import JOB_COLUMNS


@pytest.mark.network
def test_real_scrape():
    fetched = []
    real_fetch_jobs = m.fetch_jobs

    def counting_fetch_jobs(*args, **kwargs):
        jobs, pagination = real_fetch_jobs(*args, **kwargs)
        fetched.extend(job.get("jobNo") for job in jobs)
        return jobs, pagination

    progress = []
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(m, "fetch_jobs", counting_fetch_jobs)
        result = m.scrape(["Python", "Python工程師"], 1, m.AREAS["台北市"], 0,
                          stop=threading.Event(), on_progress=progress.append)

    ids = [job["職缺代碼"] for job in result.jobs]
    assert ids, "沒有抓到任何職缺"
    assert len(ids) == len(set(ids)) == len(set(fetched)) == result.found
    assert len(ids) < len(fetched), "兩個關鍵字的結果沒有重疊，無法確認去重生效"
    assert all(list(job) == [name for name, _ in JOB_COLUMNS] for job in result.jobs)
    assert any(job["工作內容"] for job in result.jobs), "沒有任何職缺取得完整工作內容"
    assert isinstance(progress[-1], m.DetailProgress) and progress[-1].index == len(ids)
    assert result.stopped is False
