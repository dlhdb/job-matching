"""試跑：前後端串起來，以 Playwright 操作真的 Chromium。LLM 換成 fake_llm，設定是 scoring_db 的測試設定。"""

import json
from contextlib import closing
from datetime import datetime, timedelta

import pytest
import yaml
from playwright.sync_api import Page, expect
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError

from job_db import current_versions, list_scores, open_db, save_auto_score, save_run
from job_scoring.llm import DEFAULT_MODEL
from job_scoring.prompt import snapshot

BASE_TIME = datetime(2026, 9, 1, 10, 0, 0)
LIST_KEY = "jobAutoScoring.dryRunList.v1"


@pytest.fixture
def db(scoring_db, fake_llm, live_server):
    """
    伺服器啟動後的資料庫路徑；每次存取都另開連線再關掉，伺服器寫入時才拿得到鎖

    :return: Path
    """
    return scoring_db


@pytest.fixture
def seed(db, make_job):
    """
    寫入職缺：第 i 筆的最後出現時間是 BASE_TIME 加 i 天

    :return: callable, seed(*overrides: dict) -> list[dict]，回傳寫入的職缺
    """
    def _seed(*overrides):
        jobs = [make_job(**fields) for fields in overrides]
        with closing(open_db(db)) as conn:
            for i, job in enumerate(jobs):
                save_run(conn, [job], BASE_TIME + timedelta(days=i), "爬蟲")
        return jobs
    return _seed


def write_score(db, job, total=60, at=BASE_TIME, eliminated=False):
    """直接寫入一筆評分紀錄"""
    code = job["職缺代碼"]
    total = None if eliminated else total
    details = {
        "職缺代碼": code, "淘汰": eliminated, "淘汰原因": ["職稱含排除關鍵字：業務"] if eliminated else [],
        "維度": None if eliminated else {
            n: {"分數": 3, "理由": f"目前的{n}理由"} for n in ("職涯方向契合度", "技能匹配度", "產業公司吸引力", "薪資水準")
        },
        "總分": total, "未知維度": [], "評語": f"{total} 分的評語",
    }
    with closing(open_db(db)) as conn:
        save_auto_score(
            conn, job_no=code, scored_at=at, eliminated=eliminated, total=total, comment=details["評語"],
            details=details, provider=None if eliminated else "gemini", model=None if eliminated else "舊模型",
            basis={"偏好版本": 2, "經歷版本": 2, "模板版本": 1, "職缺快照": snapshot(job)},
        )


def all_records(db, codes):
    with closing(open_db(db)) as conn:
        return {code: list_scores(conn, code) for code in codes}


def set_list(page: Page, url: str, codes: list[str]) -> None:
    """直接把試跑清單寫進瀏覽器"""
    page.goto(f"{url}/crawl")
    page.evaluate("([key, codes]) => localStorage.setItem(key, JSON.stringify(codes))", [LIST_KEY, codes])


def panel(page: Page):
    return page.get_by_role("region", name="試跑清單")


def open_settings(page: Page, url: str) -> None:
    page.goto(f"{url}/settings")
    expect(panel(page).get_by_text("試跑清單（")).to_be_visible()


def editor(page: Page, label: str = "偏好"):
    return page.get_by_label(f"{label}的編輯區")


def list_codes(page: Page) -> list[str]:
    return panel(page).locator("tbody tr.row").evaluate_all("rows => rows.map(r => r.dataset.code)")


def assert_list(page: Page, expected: list[str]) -> None:
    """等清單的表列出的職缺代碼變成 expected（依顯示順序）"""
    try:
        panel(page).locator("tbody tr.row").nth(len(expected) - 1).wait_for(timeout=5000)
        page.wait_for_function(
            "expected => JSON.stringify([...document.querySelectorAll('section[aria-label=\"試跑清單\"] tbody tr.row')]"
            ".map(r => r.dataset.code)) === JSON.stringify(expected)",
            arg=expected, timeout=5000)
    except PlaywrightTimeoutError:
        pass
    assert list_codes(page) == expected


def cell(page: Page, code: str, header: str):
    """清單的表中某一列某一欄的格子；第一欄是移除按鈕"""
    panel(page).locator("thead").wait_for()
    names = panel(page).locator("thead th").evaluate_all(
        "ths => ths.map(th => th.firstChild ? th.firstChild.textContent : '')")
    return panel(page).locator(f'tbody tr.row[data-code="{code}"] td').nth(names.index(header))


def dialog(page: Page):
    return page.get_by_role("dialog", name="試跑")


def open_dialog(page: Page, count: int):
    panel(page).get_by_role("button", name=f"試跑清單的 {count} 筆").click()
    expect(dialog(page)).to_be_visible()
    expect(dialog(page).get_by_role("list", name="這次試跑")).to_be_visible()
    return dialog(page)


def start(page: Page, count: int) -> None:
    open_dialog(page, count).get_by_role("button", name="開始試跑").click()
    expect(dialog(page)).to_be_hidden()


def run_info(page: Page):
    return panel(page).locator(".run-info")


def indicator(page: Page):
    return page.locator("header .job-indicator")


# ---------------------------------------------------------------------------
# 試跑清單
# ---------------------------------------------------------------------------

def test_dry_run_list(page, live_server, db, seed, browser):
    # AC-dry-run-list
    jobs = seed(*({"職缺代碼": c, "職缺名稱": f"{n}職缺", "公司名稱": f"{n}公司"} for c, n in zip("abcde", "甲乙丙丁戊")))
    write_score(db, jobs[0], total=70)
    write_score(db, jobs[1], total=60)
    page.goto(live_server)
    expect(page.locator(".toolbar .count")).to_contain_text("共 5 筆")

    # (a) 勾選 2 筆加入
    page.get_by_label("選取 a").check()
    page.get_by_label("選取 b").check()
    page.get_by_role("button", name="加入試跑清單", exact=True).click()
    expect(page.get_by_role("status").filter(has_text="已加入試跑清單")).to_have_text(
        "已加入試跑清單 2 筆；清單共 2 筆，到設定頁試跑×")

    # (b) 勾選其中 1 筆與另 1 筆，再加入一次
    page.get_by_label("選取 b").uncheck()
    page.get_by_label("選取 c").check()
    page.get_by_role("button", name="加入試跑清單", exact=True).click()
    expect(page.get_by_role("status").filter(has_text="已加入試跑清單")).to_have_text(
        "已加入試跑清單 1 筆（1 筆原本就在清單裡）；清單共 3 筆，到設定頁試跑×")

    # (c) 改篩選：勾選清掉；關掉分頁後重新打開設定頁，清單仍在
    page.get_by_label("關鍵字").fill("職缺")
    expect(page.locator(".selcount")).to_have_text("已選 0 筆")
    context = page.context
    page.close()
    page = context.new_page()
    open_settings(page, live_server)
    assert_list(page, ["a", "b", "c"])
    expect(panel(page).get_by_text("試跑清單（3 筆）")).to_be_visible()
    # (a) 列出職缺名稱、公司名稱、目前總分
    expect(cell(page, "a", "職缺名稱")).to_have_text("甲職缺")
    expect(cell(page, "a", "公司名稱")).to_have_text("甲公司")
    expect(cell(page, "a", "目前總分")).to_have_text("70")
    expect(cell(page, "c", "目前總分")).to_have_text("—")

    # (d) 依目前總分排序：由大到小、由小到大、回到加入的順序
    header = panel(page).locator("thead th", has_text="目前總分")
    header.click()
    assert_list(page, ["a", "b", "c"])
    header.click()
    assert_list(page, ["b", "a", "c"])
    header.click()
    assert_list(page, ["a", "b", "c"])
    header.click()
    header.click()
    assert_list(page, ["b", "a", "c"])

    # 移除 1 筆
    panel(page).get_by_role("button", name="移除 b").click()
    assert_list(page, ["a", "c"])

    # 清空前先確認；取消時不變
    panel(page).get_by_role("button", name="清空清單").click()
    confirm = page.get_by_role("dialog", name="清空試跑清單的 2 筆職缺？")
    expect(confirm).to_be_visible()
    confirm.get_by_role("button", name="取消").click()
    assert_list(page, ["a", "c"])
    panel(page).get_by_role("button", name="清空清單").click()
    confirm.get_by_role("button", name="清空").click()
    expect(panel(page)).to_contain_text("清單是空的")
    expect(panel(page).get_by_role("button", name="試跑清單的 0 筆")).to_be_disabled()
    page.reload()
    expect(panel(page)).to_contain_text("清單是空的")


def test_list_current_total(page, live_server, db, seed):
    # AC-history-current 的試跑清單部分：A 用較新的 80，B 用後寫入的淘汰
    a, b = seed({"職缺代碼": "A", "職缺名稱": "甲職缺"}, {"職缺代碼": "B", "職缺名稱": "乙職缺"})
    write_score(db, a, total=80, at=BASE_TIME + timedelta(days=1))
    write_score(db, a, total=60, at=BASE_TIME)
    write_score(db, b, total=70, at=BASE_TIME)
    write_score(db, b, eliminated=True, at=BASE_TIME)
    set_list(page, live_server, ["A", "B"])

    open_settings(page, live_server)

    expect(cell(page, "A", "目前總分")).to_have_text("80")
    expect(cell(page, "B", "目前總分").locator(".tag.out")).to_have_text("淘汰")


# ---------------------------------------------------------------------------
# 試跑
# ---------------------------------------------------------------------------

def test_dry_run_does_not_store(page, live_server, db, seed, fake_llm, preferences_data):
    # AC-dry-run：偏好改了權重還沒儲存、經歷是預設範例
    jobs = seed(
        {"職缺代碼": "a", "職缺名稱": "甲職缺"},
        {"職缺代碼": "b", "職缺名稱": "乙職缺"},
        {"職缺代碼": "c", "職缺名稱": "業務專員"},
    )
    write_score(db, jobs[0], total=70)
    response = page.request.put(f"{live_server}/api/settings/experience/current", data={"version": 1})
    assert response.ok
    before = all_records(db, "abc")
    set_list(page, live_server, ["a", "b", "c"])
    open_settings(page, live_server)
    preferences_data["權重"]["職涯方向契合度"] = 0.9
    preferences_data["目標方向"] = ["目標標記-試跑"]
    editor(page).fill(yaml.safe_dump(preferences_data, allow_unicode=True))

    confirm = open_dialog(page, 3)
    summary = confirm.get_by_role("list", name="這次試跑")
    expect(summary).to_contain_text("試跑清單 3 筆")
    expect(summary).to_contain_text("其中 1 筆符合淘汰條件")
    expect(summary).to_contain_text("偏好以第 2 版為底修改中、經歷第 1 版「預設範例」、提示詞模板第 1 版「預設模板」")
    expect(confirm.get_by_role("alert")).to_have_count(0)
    expect(confirm.get_by_label("模型")).to_have_value(DEFAULT_MODEL)
    confirm.get_by_role("button", name="開始試跑").click()
    expect(run_info(page)).to_contain_text("試跑完成")

    assert fake_llm.calls("甲職缺", "乙職缺", "業務專員") == ["甲職缺", "乙職缺"]
    assert all("目標標記-試跑" in prompt for prompt in fake_llm.prompts)
    assert all_records(db, "abc") == before
    with closing(open_db(db)) as conn:
        current = current_versions(conn)
    assert (current["preferences"]["版本"], current["experience"]["版本"]) == (2, 1)
    # 職缺表上的分數不變
    page.get_by_role("link", name="職缺表").click()
    expect(page.locator('tbody tr.row[data-code="a"]')).to_contain_text("70")
    expect(page.locator('tbody tr.row[data-code="b"]')).not_to_contain_text("75")
    expect(page.locator('tbody tr.row[data-code="c"]')).not_to_contain_text("淘汰")


def test_dry_run_result(page, live_server, db, seed, fake_llm):
    # AC-dry-run-result：目前總分 70、60、還沒評分；試跑 75、淘汰、失敗
    jobs = seed(
        {"職缺代碼": "a", "職缺名稱": "甲職缺"},
        {"職缺代碼": "b", "職缺名稱": "業務專員"},
        {"職缺代碼": "c", "職缺名稱": "丙職缺"},
    )
    write_score(db, jobs[0], total=70)
    write_score(db, jobs[1], total=60)
    fake_llm.behaviors = {"丙職缺": "llm_error"}
    set_list(page, live_server, ["a", "b", "c"])
    open_settings(page, live_server)

    # (a) 試跑完成
    start(page, 3)
    expect(run_info(page)).to_have_text(
        f"試跑完成・用 偏好第 2 版「測試偏好」、經歷第 2 版「測試經歷」、提示詞模板第 1 版「預設模板」・{DEFAULT_MODEL}"
        "・結果不存，離開或重新整理設定頁就不見")
    expect(cell(page, "a", "試跑總分")).to_have_text("75")
    expect(cell(page, "a", "差距")).to_have_text("+5")
    expect(cell(page, "b", "試跑總分").locator(".tag.out")).to_have_text("淘汰")
    expect(cell(page, "b", "差距")).to_have_text("—")
    expect(cell(page, "c", "試跑總分")).to_have_text("—")
    expect(cell(page, "c", "狀態")).to_have_text("失敗：模擬的 API 錯誤")
    expect(panel(page).locator(".viewing")).to_have_count(0)

    # (b) 點第 1 筆：並排比較
    panel(page).locator('tbody tr.row[data-code="a"]').click()
    current = panel(page).get_by_role("region", name="目前的評分")
    trial = panel(page).get_by_role("region", name="試跑的評分")
    expect(current).to_contain_text("70 分的評語")
    expect(current).to_contain_text("目前的職涯方向契合度理由")
    expect(trial).to_contain_text("總分：75")
    expect(trial).to_contain_text("職涯方向契合度")
    panel(page).locator('tbody tr.row[data-code="c"]').click()
    expect(panel(page).get_by_role("region", name="試跑的評分")).to_contain_text("試跑失敗：模擬的 API 錯誤")
    expect(panel(page).get_by_role("region", name="目前的評分")).to_contain_text("還沒評分")

    # (c) 修改偏好的編輯區：標示過時
    editor(page).fill(editor(page).input_value() + "\n# 改過")
    expect(panel(page).locator(".viewing")).to_contain_text("編輯區的內容在試跑後改過，表上的試跑結果是改之前的")
    page.get_by_role("button", name="捨棄修改").click()
    expect(panel(page).locator(".viewing")).to_have_count(0)

    # (d) 移除 1 筆：標示過時
    panel(page).get_by_role("button", name="移除 c").click()
    expect(panel(page).locator(".viewing")).to_contain_text("試跑清單在試跑後改過")

    # (e) 重新整理：結果不見，清單仍在
    page.reload()
    assert_list(page, ["a", "b"])
    expect(cell(page, "a", "試跑總分")).to_have_text("—")
    expect(run_info(page)).to_have_count(0)


def test_dry_run_progress_reload_and_stop(page, live_server, db, seed, fake_llm):
    # 試跑中重新整理或切換分頁，接回進度與已完成的結果；頁首的停止
    seed(*({"職缺代碼": f"j{i}", "職缺名稱": f"{n}職缺"} for i, n in enumerate("甲乙丙丁戊", start=1)))
    fake_llm.hold("丙職缺")
    set_list(page, live_server, [f"j{i}" for i in range(1, 6)])
    open_settings(page, live_server)
    start(page, 5)

    expect(indicator(page)).to_contain_text("試跑中 2／5")
    expect(cell(page, "j3", "狀態")).to_have_text("試跑中")
    expect(cell(page, "j4", "狀態")).to_have_text("排隊中")
    expect(cell(page, "j1", "試跑總分")).to_have_text("75")
    expect(panel(page).get_by_role("button", name="試跑清單的 5 筆")).to_be_disabled()
    expect(panel(page).get_by_role("button", name="清空清單")).to_be_disabled()
    expect(panel(page).get_by_role("button", name="移除 j1")).to_be_disabled()

    page.reload()
    expect(indicator(page)).to_contain_text("試跑中 2／5")
    expect(cell(page, "j1", "試跑總分")).to_have_text("75")
    expect(run_info(page)).to_contain_text("試跑中")

    # 切到職缺表：頁首仍看得到，點它回到設定頁
    page.get_by_role("link", name="職缺表").click()
    expect(indicator(page)).to_contain_text("試跑中 2／5")
    indicator(page).click()
    expect(cell(page, "j1", "試跑總分")).to_have_text("75")

    page.get_by_role("button", name="停止試跑").click()
    expect(page.get_by_role("button", name="停止中")).to_be_disabled()
    fake_llm.release("丙職缺")
    expect(run_info(page)).to_contain_text("已停止")
    expect(indicator(page)).to_be_hidden()
    for code in ["j4", "j5"]:
        expect(cell(page, code, "狀態")).to_have_text("停止，沒試跑")
    expect(cell(page, "j3", "試跑總分")).to_have_text("75")


def test_result_not_kept_when_finished_elsewhere(page, live_server, db, seed, fake_llm):
    # 試跑結束時沒有打開設定頁，結果也不留；在設定頁看到的結果可以清除
    seed({"職缺代碼": "a", "職缺名稱": "甲職缺"})
    fake_llm.hold("甲職缺")
    set_list(page, live_server, ["a"])
    open_settings(page, live_server)
    start(page, 1)
    expect(indicator(page)).to_contain_text("試跑中 0／1")

    page.get_by_role("link", name="職缺表").click()
    fake_llm.release("甲職缺")
    expect(indicator(page)).to_be_hidden()
    page.get_by_role("link", name="設定").click()
    assert_list(page, ["a"])
    expect(cell(page, "a", "試跑總分")).to_have_text("—")
    expect(run_info(page)).to_have_count(0)

    start(page, 1)
    expect(cell(page, "a", "試跑總分")).to_have_text("75")
    panel(page).get_by_role("button", name="清除試跑結果").click()
    expect(cell(page, "a", "試跑總分")).to_have_text("—")
    expect(run_info(page)).to_have_count(0)


@pytest.mark.parametrize("kind", ["偏好", "提示詞模板"])
def test_invalid_editor_blocks(page, live_server, db, seed, preferences_data, kind):
    # AC-settings-check：偏好或模板有錯時不能試跑
    seed({"職缺代碼": "a", "職缺名稱": "甲職缺"})
    set_list(page, live_server, ["a"])
    open_settings(page, live_server)
    if kind == "偏好":
        del preferences_data["權重"]
        editor(page).fill(yaml.safe_dump(preferences_data, allow_unicode=True))
        expected = "偏好：權重：缺少這個欄位"
    else:
        page.get_by_role("tab", name="提示詞模板").click()
        editor(page, "提示詞模板").fill(editor(page, "提示詞模板").input_value().replace("<!-- USER -->", ""))
        expected = "提示詞模板：缺少 <!-- SYSTEM --> 或 <!-- USER --> 標記"

    confirm = open_dialog(page, 1)

    expect(confirm.get_by_role("alert")).to_contain_text(expected)
    expect(confirm.get_by_role("button", name="開始試跑")).to_be_disabled()
    confirm.get_by_role("button", name="取消").click()
    expect(dialog(page)).to_be_hidden()


def test_one_job_at_a_time(page, live_server, db, seed, fake_llm):
    # AC-job (c)：評分中在設定頁按試跑，不能開始，說明同一時間只能跑一個作業
    seed({"職缺代碼": "a", "職缺名稱": "甲職缺"}, {"職缺代碼": "b", "職缺名稱": "乙職缺"})
    fake_llm.hold("乙職缺")
    response = page.request.post(
        f"{live_server}/api/scoring",
        data=json.dumps({"codes": ["b"], "rescore": False, "model": DEFAULT_MODEL}),
        headers={"Content-Type": "application/json"},
    )
    assert response.status == 202
    set_list(page, live_server, ["a"])
    open_settings(page, live_server)
    expect(indicator(page)).to_contain_text("評分中 0／1")

    confirm = open_dialog(page, 1)

    expect(confirm.get_by_role("alert")).to_contain_text("同一時間只能跑一個作業，目前正在評分")
    expect(confirm.get_by_role("button", name="開始試跑")).to_be_disabled()
    fake_llm.release("乙職缺")
