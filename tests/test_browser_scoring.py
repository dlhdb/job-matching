"""職缺表上的評分：前後端串起來，以 Playwright 操作真的 Chromium。LLM 換成 fake_llm，設定是 scoring_db 的測試設定。"""

import json
from contextlib import closing
from datetime import datetime, timedelta

import pytest
from playwright.sync_api import Page, expect
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError

from job_db import list_scores, open_db, save_auto_score, save_run
from job_scoring.llm import DEFAULT_MODEL
from job_scoring.prompt import snapshot

BASE_TIME = datetime(2026, 9, 1, 10, 0, 0)
DIMENSION_SCORES = {"職涯方向契合度": 4, "技能匹配度": None, "產業公司吸引力": 3, "薪資水準": 4}
ROW_CODES_JS = "() => [...document.querySelectorAll('tbody tr.row')].map(r => r.dataset.code)"


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
    寫入職缺：第 i 筆的最後出現時間是 BASE_TIME 加 i 天，職缺表預設（都沒有總分時）由新到舊列出

    :return: callable, seed(*overrides: dict) -> list[dict]，回傳寫入的職缺
    """
    def _seed(*overrides):
        jobs = [make_job(**fields) for fields in overrides]
        with closing(open_db(db)) as conn:
            for i, job in enumerate(jobs):
                save_run(conn, [job], BASE_TIME + timedelta(days=i), "爬蟲")
        return jobs
    return _seed


def write_score(db, job, total=60, at=BASE_TIME, eliminated=False, basis=True, model="舊模型"):
    """直接寫入一筆評分紀錄；basis 為 False 時是記錄依據之前的評分"""
    code = job["職缺代碼"]
    total = None if eliminated else total
    details = {
        "職缺代碼": code, "淘汰": eliminated, "淘汰原因": ["職稱含排除關鍵字：業務"] if eliminated else [],
        "維度": None if eliminated else {n: {"分數": s, "理由": f"{n}的理由"} for n, s in DIMENSION_SCORES.items()},
        "總分": total, "未知維度": [] if eliminated else ["技能匹配度"], "評語": f"{total} 分的評語",
    }
    with closing(open_db(db)) as conn:
        if basis:
            save_auto_score(
                conn, job_no=code, scored_at=at, eliminated=eliminated, total=total, comment=details["評語"],
                details=details, provider=None if eliminated else "gemini", model=None if eliminated else model,
                basis={"偏好版本": 2, "經歷版本": 2, "模板版本": 1, "職缺快照": snapshot(job)},
            )
        else:
            with conn:
                conn.execute(
                    'INSERT INTO job_scores ("職缺代碼", "評分時間", "淘汰", "總分", "評語", "評分明細") '
                    "VALUES (?, ?, 0, ?, ?, ?)",
                    (code, at.isoformat(), total, details["評語"], json.dumps(details, ensure_ascii=False)),
                )


def records(db, code):
    with closing(open_db(db)) as conn:
        return list_scores(conn, code)


def count(page: Page):
    return page.locator(".toolbar .count")


def open_table(page: Page, url: str) -> None:
    page.goto(url)
    expect(count(page)).to_contain_text("共")


def row_codes(page: Page) -> list[str]:
    return page.evaluate(ROW_CODES_JS)


def assert_rows(page: Page, expected: list[str]) -> None:
    """等表格列出的職缺代碼變成 expected（依顯示順序）"""
    try:
        page.wait_for_function(
            f"expected => JSON.stringify(({ROW_CODES_JS})()) === JSON.stringify(expected)",
            arg=expected, timeout=5000)
    except PlaywrightTimeoutError:
        pass
    assert row_codes(page) == expected


def row(page: Page, code: str):
    return page.locator(f'tbody tr.row[data-code="{code}"]')


def cell(page: Page, code: str, header: str):
    """某一列某一欄的格子；第一欄是勾選欄"""
    names = page.locator("thead th").evaluate_all(
        "ths => ths.map(th => th.firstChild ? th.firstChild.textContent : '')")
    return row(page, code).locator("td").nth(names.index(header))


def pick_column(page: Page, name: str) -> None:
    page.get_by_role("button", name="選擇欄位").click()
    page.get_by_role("group", name="選擇欄位").get_by_label(name, exact=True).set_checked(True)
    page.get_by_role("button", name="選擇欄位").click()


def check(page: Page, *codes: str) -> None:
    for code in codes:
        page.get_by_label(f"選取 {code}").check()


def selected_count(page: Page):
    return page.locator(".selcount")


def dialog(page: Page):
    return page.get_by_role("dialog", name="送去評分")


def open_dialog(page: Page):
    page.get_by_role("button", name="送去評分").click()
    expect(dialog(page)).to_be_visible()
    expect(dialog(page).get_by_role("list", name="這次評分")).to_be_visible()
    return dialog(page)


def start(page: Page) -> None:
    open_dialog(page).get_by_role("button", name="開始評分").click()
    expect(dialog(page)).to_be_hidden()


def detail(page: Page):
    return page.locator("tbody tr.detail")


# ---------------------------------------------------------------------------
# 評分的欄位、排序與篩選
# ---------------------------------------------------------------------------

def test_rank_columns_and_sort(page, live_server, db, seed):
    # AC-rank-columns、AC-rank-sort
    a, b, c, d = seed({"職缺代碼": "A"}, {"職缺代碼": "B"}, {"職缺代碼": "C"}, {"職缺代碼": "D"})
    write_score(db, a, total=60, at=datetime(2026, 9, 10, 9, 0, 0), model="舊的模型")
    write_score(db, a, total=80, at=datetime(2026, 9, 11, 9, 0, 0), model="新的模型")
    write_score(db, b, eliminated=True)
    write_score(db, d, total=90)
    open_table(page, live_server)

    headers = page.locator("thead th:not(.sel)").evaluate_all(
        "ths => ths.map(th => th.firstChild.textContent)")
    assert headers == ["職缺名稱", "公司名稱", "地區", "薪資待遇", "總分", "淘汰", "評語", "最後出現時間"]
    expect(page.locator("thead th", has_text="總分")).to_have_attribute("aria-sort", "descending")
    # 90、80，被淘汰與還沒評分的排在最後（都沒有總分，再依最後出現時間由新到舊）
    assert_rows(page, ["D", "A", "C", "B"])

    for name in ["職涯方向契合度", "技能匹配度", "產業公司吸引力", "薪資水準", "供應商", "模型"]:
        pick_column(page, name)
    expect(cell(page, "A", "總分")).to_have_text("80")
    expect(cell(page, "A", "淘汰")).to_have_text("否")
    expect(cell(page, "A", "職涯方向契合度")).to_have_text("4")
    expect(cell(page, "A", "技能匹配度")).to_have_text("—")
    expect(cell(page, "A", "模型")).to_have_text("新的模型")
    expect(cell(page, "B", "淘汰")).to_have_text("淘汰")
    for header in ["總分", "職涯方向契合度", "供應商", "模型"]:
        expect(cell(page, "B", header)).to_have_text("—")
    for header in ["總分", "淘汰", "評語", "薪資水準", "模型"]:
        expect(cell(page, "C", header)).to_have_text("—")


def test_rank_filter(page, live_server, db, seed):
    # AC-rank-filter
    jobs = seed(*({"職缺代碼": code} for code in ["s50", "s70", "s90", "out", "none"]))
    for job, total in zip(jobs[:3], [50, 70, 90]):
        write_score(db, job, total=total)
    write_score(db, jobs[3], eliminated=True)
    open_table(page, live_server)
    low, high = page.get_by_label("總分下限"), page.get_by_label("總分上限")
    status = page.get_by_label("評分狀態")

    low.fill("70")
    assert_rows(page, ["s90", "s70"])
    high.fill("80")
    assert_rows(page, ["s70"])
    low.fill("")
    high.fill("")
    for label, expected in [("未淘汰", ["s90", "s70", "s50"]), ("淘汰", ["out"]), ("未評分", ["none"])]:
        status.select_option(label=label)
        assert_rows(page, expected)
    status.select_option(label="全部")
    low.fill("0")
    assert_rows(page, ["s90", "s70", "s50"])

    # 清除篩選：五筆都列出，評分狀態回到全部
    status.select_option(label="淘汰")
    page.get_by_role("button", name="清除篩選").click()
    expect(count(page)).to_have_text("符合 5 筆／共 5 筆")
    expect(status).to_have_value("all")
    expect(low).to_have_value("")

    # 還原預設檢視也把評分的篩選還原
    high.fill("60")
    assert_rows(page, ["s50"])
    page.get_by_role("button", name="還原預設檢視").click()
    expect(high).to_have_value("")
    expect(count(page)).to_have_text("符合 5 筆／共 5 筆")


# ---------------------------------------------------------------------------
# 展開列：目前的評分、所有評分紀錄、評分依據
# ---------------------------------------------------------------------------

def test_detail_history_and_basis(page, live_server, db, seed, make_job):
    # AC-score-detail、AC-history-current、AC-history-all、AC-basis (b)(c)、AC-basis-legacy
    a, b, c, legacy = seed(
        {"職缺代碼": "A", "工作內容": "評分當時的工作內容"},
        {"職缺代碼": "B", "職缺名稱": "業務專員"},
        {"職缺代碼": "C"},
        {"職缺代碼": "L"},
    )
    write_score(db, a, total=60, at=datetime(2026, 9, 10, 9, 0, 0))
    write_score(db, a, total=80, at=datetime(2026, 9, 11, 9, 0, 0))
    write_score(db, b, total=50, at=datetime(2026, 9, 12, 9, 0, 0))
    write_score(db, b, at=datetime(2026, 9, 12, 9, 0, 0), eliminated=True)
    write_score(db, legacy, total=40, basis=False)
    # 評分之後職缺內容被更新
    with closing(open_db(db)) as conn:
        save_run(conn, [make_job(職缺代碼="A", 工作內容="更新後的工作內容")], BASE_TIME + timedelta(days=9), "爬蟲")
    open_table(page, live_server)

    # A：目前的評分是 80 那筆，明細有四個維度
    row(page, "A").click()
    current = detail(page).get_by_role("region", name="目前的評分")
    expect(current).to_contain_text("80")
    expect(current).to_contain_text("2026-09-11 09:00:00")
    dims = detail(page).get_by_role("region", name="評分明細")
    expect(dims.locator(".dims li")).to_have_count(4)
    expect(dims).to_contain_text("職涯方向契合度的理由")
    expect(dims).to_contain_text("未知維度：技能匹配度")
    history = detail(page).get_by_role("region", name="所有評分紀錄")
    expect(history).to_contain_text("所有評分紀錄（2 筆）")
    history_rows = history.locator("tbody tr")
    expect(history_rows.nth(0)).to_contain_text("80")
    expect(history_rows.nth(0)).to_contain_text("目前")
    expect(history_rows.nth(1)).to_contain_text("60")

    # 評分依據預設收合；偏好、經歷是第 2 版；提示詞含評分當時的工作內容
    basis = detail(page).get_by_role("region", name="評分依據")
    expect(basis.get_by_role("tab", name="偏好")).to_be_hidden()
    basis.locator("summary").click()
    expect(basis).to_contain_text("第 2 版「測試偏好」")
    expect(basis).to_contain_text("目標標記-AAA")
    basis.get_by_role("tab", name="經歷").click()
    expect(basis).to_contain_text("第 2 版「測試經歷」")
    expect(basis).to_contain_text("經歷標記-BBB")
    basis.get_by_role("tab", name="提示詞").click()
    expect(basis).to_contain_text("評分當時的工作內容")
    expect(basis).not_to_contain_text("更新後的工作內容")
    expect(basis).to_contain_text("提示詞模板第 1 版")

    # 檢視舊評分：評分與明細換成 60 那筆，職缺表那一列仍是 80
    history_rows.nth(1).click()
    viewing = detail(page).get_by_role("region", name="檢視中的評分")
    expect(viewing).to_contain_text("不是目前的評分")
    expect(viewing).to_contain_text("60")
    expect(cell(page, "A", "總分")).to_have_text("80")
    viewing.get_by_role("button", name="回到目前的評分").click()
    expect(detail(page).get_by_role("region", name="目前的評分")).to_contain_text("80")
    expect(detail(page)).not_to_contain_text("不是目前的評分")

    # B：時間相同時後寫入的淘汰那筆是目前的評分
    row(page, "B").click()
    expect(detail(page)).to_have_count(1)
    expect(cell(page, "B", "淘汰")).to_have_text("淘汰")
    history_rows = detail(page).get_by_role("region", name="所有評分紀錄").locator("tbody tr")
    expect(history_rows.nth(0)).to_contain_text("淘汰")
    expect(history_rows.nth(1)).to_contain_text("50")
    dims = detail(page).get_by_role("region", name="評分明細")
    expect(dims).to_contain_text("職稱含排除關鍵字：業務")
    expect(dims).to_contain_text("沒有呼叫 AI")
    basis = detail(page).get_by_role("region", name="評分依據")
    basis.locator("summary").click()
    basis.get_by_role("tab", name="提示詞").click()
    expect(basis).to_contain_text("沒有提示詞")
    expect(basis).to_contain_text("業務專員")
    expect(basis).to_contain_text("薪資上限")

    # C：還沒有評分
    row(page, "C").click()
    expect(detail(page).get_by_role("region", name="目前的評分")).to_contain_text("還沒有評分")

    # L：沒有記錄依據的舊評分
    row(page, "L").click()
    basis = detail(page).get_by_role("region", name="評分依據")
    basis.locator("summary").click()
    expect(basis).to_contain_text("這筆評分沒有記錄依據")


# ---------------------------------------------------------------------------
# 勾選與確認
# ---------------------------------------------------------------------------

def test_pick(page, live_server, db, seed, fake_llm):
    # AC-score-pick
    seed(*({"職缺代碼": code, "職缺名稱": name} for code, name in
           [("p1", "Python 甲"), ("p2", "Go 乙"), ("p3", "Python 丙"), ("p4", "Rust 丁"), ("p5", "Python 戊")]))
    open_table(page, live_server)

    # (a)
    check(page, "p1", "p2")
    expect(selected_count(page)).to_have_text("已選 2 筆")
    page.get_by_role("button", name="全選", exact=True).click()
    expect(selected_count(page)).to_have_text("已選 5 筆")
    page.get_by_role("button", name="取消全選").click()
    expect(selected_count(page)).to_have_text("已選 0 筆")

    # (b) 篩選改變後勾選清掉
    page.get_by_role("button", name="全選", exact=True).click()
    page.get_by_label("關鍵字").fill("Python")
    expect(count(page)).to_have_text("符合 3 筆／共 5 筆")
    expect(selected_count(page)).to_have_text("已選 0 筆")

    # (c) 全選只勾選篩選後的 3 筆；取消確認視窗時勾選不變，開始評分後清掉
    page.get_by_role("button", name="全選", exact=True).click()
    open_dialog(page).get_by_role("button", name="取消").click()
    expect(selected_count(page)).to_have_text("已選 3 筆")
    start(page)
    expect(selected_count(page)).to_have_text("已選 0 筆")
    expect(page.locator(".notice", has_text="評分完成")).to_contain_text("評分 3 筆")
    assert [code for code in ["p1", "p2", "p3", "p4", "p5"] if records(db, code)] == ["p1", "p3", "p5"]


@pytest.fixture
def four(db, seed):
    """a、b 已評過；c 沒評過；d 沒評過、會被淘汰"""
    jobs = seed({"職缺代碼": "a"}, {"職缺代碼": "b"}, {"職缺代碼": "c"}, {"職缺代碼": "d", "職缺名稱": "業務專員"})
    write_score(db, jobs[0])
    write_score(db, jobs[1])
    return jobs


def test_confirm(page, live_server, db, four):
    # AC-score-confirm (a)、AC-rescore 的確認視窗、AC-llm 的供應商與預設模型
    open_table(page, live_server)
    check(page, "a", "b", "c", "d")
    box = open_dialog(page)

    expect(box).to_contain_text("勾選 4 筆，其中 2 筆已評過")
    expect(box).to_contain_text("將評 2 筆")
    expect(box).to_contain_text("其中 1 筆符合淘汰條件")
    expect(box).to_contain_text("偏好第 2 版「測試偏好」、經歷第 2 版「測試經歷」、提示詞模板第 1 版「預設模板」")
    expect(box).to_contain_text("gemini")
    expect(box.get_by_label("模型")).to_have_value(DEFAULT_MODEL)
    rescore = box.get_by_label("包含已評過的職缺（重評）", exact=False)
    expect(rescore).not_to_be_checked()
    expect(box.get_by_role("button", name="開始評分")).to_be_enabled()

    rescore.check()
    expect(box).to_contain_text("將評 4 筆")
    rescore.uncheck()
    expect(box).to_contain_text("將評 2 筆")


@pytest.mark.parametrize("case", ["no_key", "zero", "default_experience"])
def test_confirm_errors(page, live_server, db, four, monkeypatch, case):
    # AC-score-confirm (c)、(e)、(f)：顯示原因、不能送出，沒有新增評分紀錄
    codes, reason = ["a", "b", "c", "d"], None
    if case == "no_key":
        monkeypatch.delenv("GEMINI_API_KEY")
        reason = "API key"
    elif case == "zero":
        codes, reason = ["a", "b"], "將評 0 筆"
    else:
        with closing(open_db(db)) as conn, conn:
            conn.execute("UPDATE current_settings SET \"版本\" = 1 WHERE \"種類\" = 'experience'")
        reason = "經歷還是預設範例"
    open_table(page, live_server)
    check(page, *codes)
    box = open_dialog(page)

    expect(box.get_by_role("alert", name="不能開始的原因")).to_contain_text(reason)
    expect(box.get_by_role("button", name="開始評分")).to_be_disabled()
    assert [len(records(db, code)) for code in "abcd"] == [1, 1, 0, 0]


# ---------------------------------------------------------------------------
# 評分中、停止、摘要與作業
# ---------------------------------------------------------------------------

@pytest.fixture
def five(seed, fake_llm):
    """五筆還沒評分的職缺，職缺表預設由新到舊列出 j5、j4、j3、j2、j1；j5 分數低、j4 分數高"""
    fake_llm.behaviors = {"戊職缺": {"career": 1, "industry": 1}, "丁職缺": {"career": 5, "industry": 5}}
    return seed(*({"職缺代碼": f"j{i}", "職缺名稱": f"{name}職缺"} for i, name in enumerate("甲乙丙丁戊", start=1)))


def indicator(page: Page):
    return page.locator("header .job-indicator")


def test_run_progress_stop_and_frozen_order(page, live_server, five, fake_llm):
    # AC-score-run (a)(b)、AC-score-order、AC-job (a)(b)
    fake_llm.hold("丙職缺")
    open_table(page, live_server)
    assert_rows(page, ["j5", "j4", "j3", "j2", "j1"])
    page.get_by_role("button", name="全選", exact=True).click()
    start(page)

    # (a) 評完的列有分數；評分中與排隊中；頁首的進度
    expect(indicator(page)).to_contain_text("評分中 2／5")
    expect(row(page, "j3").locator(".tag.scoring")).to_have_text("評分中")
    for code in ["j2", "j1"]:
        expect(row(page, code).locator(".tag.queued")).to_have_text("排隊中")
    expect(cell(page, "j4", "總分")).not_to_have_text("—")
    # j4 的總分比 j5 高，但評分中列的順序不變
    assert_rows(page, ["j5", "j4", "j3", "j2", "j1"])
    expect(count(page)).to_contain_text("評分後列的順序固定")

    # 切到別的分頁再回來、重新整理：仍在評分，列與順序不變
    page.get_by_role("link", name="設定").click()
    expect(indicator(page)).to_contain_text("評分中 2／5")
    page.get_by_role("link", name="職缺表").click()
    assert_rows(page, ["j5", "j4", "j3", "j2", "j1"])
    page.reload()
    expect(indicator(page)).to_contain_text("評分中 2／5")
    assert_rows(page, ["j5", "j4", "j3", "j2", "j1"])
    expect(row(page, "j3").locator(".tag.scoring")).to_be_visible()

    # 重新整理後第一次取狀態失敗，之後取到時仍沿用固定的順序
    failures = []

    def fail_first(route):
        if not failures:
            failures.append(route.request.url)
            route.fulfill(status=500, body="壞掉了")
        else:
            route.continue_()

    page.route("**/api/scoring", fail_first)
    page.reload()
    expect(indicator(page)).to_contain_text("評分中 2／5")
    assert_rows(page, ["j5", "j4", "j3", "j2", "j1"])
    assert len(failures) == 1
    page.unroute("**/api/scoring")

    # AC-job (b)：另開一個頁面也接得回進度
    other = page.context.new_page()
    open_table(other, live_server)
    expect(indicator(other)).to_contain_text("評分中 2／5")
    other.close()

    # (b) 評第 3 筆時停止：評完這筆就不再評
    page.get_by_role("button", name="停止評分").click()
    expect(page.get_by_role("button", name="停止中")).to_be_disabled()
    fake_llm.release("丙職缺")
    summary = page.locator(".notice", has_text="已停止")
    expect(summary).to_have_text("已停止：評分 3 筆、淘汰 0 筆、失敗 0 筆、沒評 2 筆。×")
    expect(indicator(page)).to_be_hidden()
    expect(page.locator(".tag.queued")).to_have_count(0)
    for code in ["j2", "j1"]:
        expect(cell(page, code, "總分")).to_have_text("—")

    # 評分結束後仍固定，改排序時才重新排列
    assert_rows(page, ["j5", "j4", "j3", "j2", "j1"])
    page.locator("thead th", has_text="總分").click()
    page.locator("thead th", has_text="總分").click()
    assert row_codes(page)[0] == "j4"
    expect(count(page)).not_to_contain_text("固定")


def test_run_summary_and_failure(page, live_server, five, fake_llm, db):
    # AC-score-run (c)、AC-score-failure 的畫面部分
    fake_llm.behaviors["乙職缺"] = "llm_error"
    with closing(open_db(db)) as conn:
        conn.execute("UPDATE jobs SET \"職缺名稱\" = '業務甲職缺' WHERE \"職缺代碼\" = 'j1'")
        conn.commit()
    open_table(page, live_server)
    page.get_by_role("button", name="全選", exact=True).click()
    start(page)

    summary = page.locator(".notice", has_text="評分完成")
    expect(summary).to_contain_text(
        "評分完成：評分 3 筆、淘汰 1 筆、失敗 1 筆。失敗的沒有寫入，列上看得到原因，可以再勾選重評。")
    failed = row(page, "j2").locator(".tag.failed")
    expect(failed).to_have_text("評分失敗：模擬的 API 錯誤")
    expect(cell(page, "j1", "淘汰")).to_have_text("淘汰")
    row(page, "j2").click()
    expect(detail(page)).to_contain_text("剛才評分失敗：模擬的 API 錯誤")
    assert records(db, "j2") == []

    # 關掉摘要
    summary.get_by_role("button", name="關閉評分的摘要").click()
    expect(summary).to_be_hidden()

    # 評分結束後重新整理：失敗標示消失，仍是還沒評分，可以再勾選
    page.reload()
    expect(count(page)).to_contain_text("共 5 筆")
    expect(page.locator(".tag.failed")).to_have_count(0)
    expect(cell(page, "j2", "總分")).to_have_text("—")
    expect(page.get_by_label("選取 j2")).to_be_enabled()


# ---------------------------------------------------------------------------
# 取不到資料時
# ---------------------------------------------------------------------------

def test_scores_retry_after_failure(page, live_server, db, seed):
    # 評分讀不到時顯示原因並自動重試，讀到後列出職缺
    seed({"職缺代碼": "a"})
    failures = []

    def fail_once(route):
        if not failures:
            failures.append(route.request.url)
            route.fulfill(status=500, body="壞掉了")
        else:
            route.continue_()

    page.route("**/api/scores", fail_once)
    page.goto(live_server)

    expect(page.get_by_text("讀不到評分")).to_be_visible()
    expect(count(page)).to_have_text("符合 1 筆／共 1 筆")
    assert len(failures) == 1


def test_scores_refetch_failure_keeps_table(page, live_server, db, seed):
    # 讀過一次之後再讀不到時，表格與上次的評分都還在，原因顯示在表格上方
    seed({"職缺代碼": "out", "職缺名稱": "業務專員"}, {"職缺代碼": "a"})
    open_table(page, live_server)
    row(page, "a").click()
    page.route("**/api/scores", lambda route: route.fulfill(status=500, body="壞掉了"))

    # 只評會被淘汰的那筆，不呼叫 AI；評完會重新取評分
    check(page, "out")
    start(page)

    expect(page.get_by_text("讀不到評分")).to_be_visible()
    expect(count(page)).to_have_text("列出 2 筆／共 2 筆・評分後列的順序固定，改篩選或排序時才重新排列")
    expect(detail(page)).to_have_count(1)
    page.unroute("**/api/scores")
    expect(cell(page, "out", "淘汰")).to_have_text("淘汰")
    expect(page.get_by_text("讀不到評分")).to_be_hidden()


def test_state_failure_still_lists_jobs(page, live_server, db, seed):
    # 評分作業的狀態取不到時，職缺表仍列得出來，並顯示原因
    seed({"職缺代碼": "a"})
    page.route("**/api/scoring", lambda route: route.fulfill(status=500, body="壞掉了"))
    page.goto(live_server)

    expect(count(page)).to_have_text("符合 1 筆／共 1 筆")
    expect(page.get_by_text("取不到評分的最新狀態")).to_be_visible()


def test_stop_failure_shown(page, live_server, five, fake_llm):
    # 停止失敗時，原因不會被下一次輪詢清掉
    fake_llm.hold("戊職缺")
    open_table(page, live_server)
    page.get_by_role("button", name="全選", exact=True).click()
    start(page)
    expect(indicator(page)).to_contain_text("評分中 0／5")
    page.route("**/api/scoring/stop", lambda route: route.fulfill(status=500, body="壞掉了"))

    page.get_by_role("button", name="停止評分").click()

    alert = page.locator("header").get_by_role("alert")
    expect(alert).to_contain_text("停止失敗")
    # 輪詢照常成功之後仍看得到
    page.wait_for_timeout(1500)
    expect(alert).to_contain_text("停止失敗")
    expect(indicator(page)).to_contain_text("評分中 0／5")
    fake_llm.release("戊職缺")
    expect(page.locator(".notice", has_text="評分完成")).to_be_visible()

    # 下一次評分不會帶著上一次停止失敗的原因
    fake_llm.hold("戊職缺")
    check(page, "j5")
    open_dialog(page).get_by_label("包含已評過的職缺（重評）", exact=False).check()
    expect(dialog(page)).to_contain_text("將評 1 筆")
    dialog(page).get_by_role("button", name="開始評分").click()
    expect(indicator(page)).to_contain_text("評分中 0／1")
    expect(alert).to_have_count(0)
    fake_llm.release("戊職缺")
