"""抓取頁的瀏覽器行為：前後端串起來，以 Playwright 操作真的 Chromium；104 以 fake_104 取代。"""

import threading
from contextlib import closing
from datetime import datetime

import pytest
from playwright.sync_api import Page, expect

import fetch_104_jobs
from job_db import list_jobs, list_runs, open_db, save_run

PREVIEW_HEADERS = ["職缺名稱", "公司名稱", "地區", "薪資待遇", "更新日期"]
JOB_TABLE_HEADERS = ["職缺名稱", "公司名稱", "地區", "薪資待遇", "最後出現時間"]
T = datetime(2026, 9, 20, 9, 30, 0)
EARLIER = datetime(2026, 9, 1, 10, 0, 0)


class FixedDatetime(datetime):
    """抓完或停止的時間固定為 T"""

    @classmethod
    def now(cls, tz=None):
        return cls(T.year, T.month, T.day, T.hour, T.minute, T.second)


@pytest.fixture
def fixed_time(monkeypatch):
    """讓抓完或停止的時間固定為 T"""
    monkeypatch.setattr(fetch_104_jobs, "datetime", FixedDatetime)


@pytest.fixture
def seed(isolate_db, make_job):
    """
    在抓取前寫入職缺資料庫已有的職缺，最後出現時間是 EARLIER

    :return: callable, seed(*codes) -> None
    """
    def _seed(*codes):
        with closing(open_db(isolate_db)) as conn:
            save_run(conn, [make_job(職缺代碼=code) for code in codes], EARLIER, "爬蟲")
    return _seed


def db_jobs(db_path):
    with closing(open_db(db_path)) as conn:
        return {job["職缺代碼"]: job for job in list_jobs(conn)}


def db_runs(db_path):
    with closing(open_db(db_path)) as conn:
        return list_runs(conn)


def row_codes(page: Page) -> list[str]:
    """預覽目前列出的職缺代碼，依顯示順序"""
    return page.evaluate("() => [...document.querySelectorAll('tbody tr.row')].map(r => r.dataset.code)")


def headers(page: Page) -> list[str]:
    """表格目前的欄位標題（不含排序箭頭與「新」那一欄）"""
    return page.locator("thead th:not(.sel)").evaluate_all(
        "ths => ths.map(th => th.firstChild ? th.firstChild.textContent : '')")


def open_crawl(page: Page, url: str) -> None:
    """打開抓取頁，等表單讀完"""
    page.goto(f"{url}/crawl")
    expect(page.get_by_label("關鍵字", exact=True)).to_be_visible()


def progress(page: Page):
    return page.locator(".progress .msg")


def count(page: Page):
    """預覽工具列的計數文字"""
    return page.locator(".toolbar .count")


def rows(page: Page):
    return page.locator("tbody tr.row")


def start(page: Page, keyword: str) -> None:
    page.get_by_label("關鍵字", exact=True).fill(keyword)
    page.get_by_role("button", name="開始抓取").click()


def stop(page: Page) -> None:
    """按停止，等伺服器收到"""
    page.get_by_role("button", name="停止").click()
    expect(progress(page)).to_have_text("停止中：不再發出新的請求")


def two_keywords(fake_104) -> list[str]:
    """
    AC 的 Given：2 個關鍵字、每個關鍵字 2 頁，共 10 筆不重複的職缺

    :return: list[str], 去重後的職缺代碼，依取內容的順序
    """
    fake_104.add("A", 1, ["a1", "a2", "a3"], 2)
    fake_104.add("A", 2, ["a4", "a5", "a6"], 2)
    fake_104.add("B", 1, ["b1", "b2", "a1"], 2)
    fake_104.add("B", 2, ["b3", "b4", "a2"], 2)
    return ["a1", "a2", "a3", "a4", "a5", "a6", "b1", "b2", "b3", "b4"]


# ---------------------------------------------------------------------------
# 搜尋條件
# ---------------------------------------------------------------------------

def test_crawl_form(page, live_server, fake_104):
    fake_104.add("Python", 1, ["p1"], 1)
    open_crawl(page, live_server)

    # (a) 只有逗號與空白：不開始抓取，說明原因
    start(page, " , ， ")
    expect(page.get_by_role("alert")).to_have_text("至少要有一個關鍵字")
    assert fake_104.searches == []

    # (b) 以這組條件搜尋；重新打開時表單是上次的條件
    page.get_by_label("縣市").select_option("台中市")
    page.get_by_label("每個關鍵字抓幾頁").fill("2")
    page.get_by_label("職缺性質").select_option(label="全職")
    start(page, "Python, 資料工程師")
    expect(count(page)).to_have_text("這次抓到 1 筆，其中 1 筆資料庫裡還沒有")
    assert fake_104.searches == [("Python", 1, "6001005000", 1), ("資料工程師", 1, "6001005000", 1)]

    open_crawl(page, live_server)
    expect(page.get_by_label("關鍵字", exact=True)).to_have_value("Python, 資料工程師")
    expect(page.get_by_label("縣市")).to_have_value("台中市")
    expect(page.get_by_label("每個關鍵字抓幾頁")).to_have_value("2")
    expect(page.get_by_label("職缺性質")).to_have_value("1")


def test_crawl_form_storage_blocked(page, live_server):
    # (c) 不允許保存的瀏覽器：讀取 localStorage 就丟出例外
    page.add_init_script("""
        Object.defineProperty(window, "localStorage", {
          get() { throw new DOMException("blocked", "SecurityError"); },
        });
    """)
    errors = []
    page.on("pageerror", lambda error: errors.append(error))
    open_crawl(page, live_server)

    expect(page.get_by_label("關鍵字", exact=True)).to_have_value("")
    expect(page.get_by_label("縣市")).to_have_value("")
    expect(page.get_by_label("縣市").locator("option:checked")).to_have_text("全台灣")
    expect(page.get_by_label("每個關鍵字抓幾頁")).to_have_value("3")
    expect(page.get_by_label("職缺性質").locator("option:checked")).to_have_text("全部")
    assert errors == []


def test_crawl_area(page, live_server, fake_104):
    open_crawl(page, live_server)
    area = page.get_by_label("縣市")

    # 清單列出全台灣與 22 個縣市
    expect(area.locator("option")).to_have_count(23)

    # (a) 選新竹縣：以新竹縣的地區代碼搜尋
    area.select_option("新竹縣")
    start(page, "Python")
    expect(page.get_by_text("沒有抓到職缺。")).to_be_visible()
    assert fake_104.searches == [("Python", 1, "6001007000", 0)]

    # (b) 不選縣市：搜尋全台灣
    area.select_option("")
    start(page, "Go")
    expect(page.get_by_text("沒有抓到職缺。")).to_be_visible()
    expect(page.get_by_label("關鍵字", exact=True)).to_be_enabled()
    assert fake_104.searches[-1] == ("Go", 1, None, 0)


# ---------------------------------------------------------------------------
# 抓取中與停止
# ---------------------------------------------------------------------------

def test_crawl_run_progress(page, live_server, fake_104):
    codes = two_keywords(fake_104)
    search_gate = fake_104.hold("search", 1)
    detail_gate = fake_104.hold("detail", 1)
    open_crawl(page, live_server)
    page.get_by_label("每個關鍵字抓幾頁").fill("2")

    # (a) 搜尋時：關鍵字、第幾頁、已找到幾筆；預覽還沒有列出職缺
    start(page, "A, B")
    expect(progress(page)).to_have_text("搜尋中：「A」第 1／2 頁，已找到 0 筆不重複的職缺")
    expect(rows(page)).to_have_count(0)
    search_gate.release()

    # 取內容時：第幾筆、共幾筆；預覽仍然沒有列出職缺
    expect(progress(page)).to_contain_text("取職缺內容：第 1／10 筆")
    expect(rows(page)).to_have_count(0)
    detail_gate.release()

    expect(count(page)).to_have_text("這次抓到 10 筆，其中 10 筆資料庫裡還沒有")
    assert sorted(row_codes(page)) == sorted(codes)


def test_crawl_run_stop_during_detail(page, live_server, fake_104):
    codes = two_keywords(fake_104)
    gate = fake_104.hold("detail", 5)
    open_crawl(page, live_server)
    page.get_by_label("每個關鍵字抓幾頁").fill("2")

    # (b) 取第 5 筆時停止：第 5 筆取完後不再發出請求，預覽只列出取完的 5 筆
    start(page, "A, B")
    expect(progress(page)).to_contain_text("取職缺內容：第 5／10 筆")
    stop(page)
    gate.release()

    expect(count(page)).to_have_text("這次抓到 5 筆，其中 5 筆資料庫裡還沒有")
    expect(page.get_by_text("已停止，只列出取完內容的職缺。")).to_be_visible()
    assert sorted(row_codes(page)) == sorted(codes[:5])
    assert fake_104.details == codes[:5]


def test_crawl_run_stop_during_search(page, live_server, fake_104):
    two_keywords(fake_104)
    gate = fake_104.hold("search", 1)
    open_crawl(page, live_server)
    page.get_by_label("每個關鍵字抓幾頁").fill("2")

    # (c) 搜尋第 1 頁時停止：沒有預覽，說明還沒有取完內容的職缺
    start(page, "A, B")
    expect(progress(page)).to_contain_text("搜尋中：「A」第 1／2 頁")
    stop(page)
    gate.release()

    expect(page.get_by_text("已停止，還沒有取完內容的職缺。")).to_be_visible()
    expect(rows(page)).to_have_count(0)
    assert len(fake_104.searches) == 1
    assert fake_104.details == []


def test_crawl_run_no_jobs(page, live_server, fake_104):
    open_crawl(page, live_server)
    page.get_by_label("每個關鍵字抓幾頁").fill("2")

    # (d) 兩個關鍵字都搜不到：沒有預覽，說明沒有抓到職缺
    start(page, "A, B")

    expect(page.get_by_text("沒有抓到職缺。")).to_be_visible()
    expect(rows(page)).to_have_count(0)
    assert [s[0] for s in fake_104.searches] == ["A", "B"]


# ---------------------------------------------------------------------------
# 預覽與存入
# ---------------------------------------------------------------------------

def test_crawl_store_preview(page, live_server, fake_104, seed, isolate_db):
    seed("A")
    fake_104.add("Python", 1, ["A", "B", "C"], 1)
    open_crawl(page, live_server)
    start(page, "Python")

    # (a) 列出 A、B、C，B、C 標「新」；預設欄位與排序；可以選的只有職缺欄位契約的欄位
    expect(count(page)).to_have_text("這次抓到 3 筆，其中 2 筆資料庫裡還沒有")
    assert row_codes(page) == ["A", "B", "C"]
    for code, new in [("A", 0), ("B", 1), ("C", 1)]:
        expect(page.locator(f'tr.row[data-code="{code}"] .tag.new')).to_have_count(new)
    assert headers(page) == PREVIEW_HEADERS
    expect(page.locator("thead th", has_text="職缺名稱")).to_have_attribute("aria-sort", "ascending")
    page.get_by_role("button", name="選擇欄位").click()
    options = page.get_by_role("group", name="選擇欄位").get_by_role("checkbox")
    expect(options).to_have_count(16)
    expect(page.get_by_role("group", name="選擇欄位").get_by_label("最後出現時間")).to_have_count(0)
    page.get_by_role("button", name="選擇欄位").click()
    assert sorted(db_jobs(isolate_db)) == ["A"]

    # (b) 改選欄位與排序，展開 B：完整的欄位、工作內容與連結，沒有出現時間
    page.get_by_role("button", name="選擇欄位").click()
    page.get_by_role("group", name="選擇欄位").get_by_label("職缺代碼", exact=True).check()
    page.get_by_role("button", name="選擇欄位").click()
    page.locator("thead th", has_text="職缺名稱").click()
    expect(rows(page).first).to_have_attribute("data-code", "C")
    page.locator('tr.row[data-code="B"]').click()
    detail = page.locator("tbody tr.detail")
    expect(detail.locator("pre.content")).to_have_text(fake_104.description("B"))
    expect(detail.get_by_role("link", name="職缺頁")).to_have_attribute("href", "https://www.104.com.tw/job/B")
    expect(detail.get_by_role("link", name="公司頁")).to_have_attribute(
        "href", "https://www.104.com.tw/company/cB")
    expect(detail).not_to_contain_text("出現時間")

    # (c) 職缺表的欄位與排序沒有跟著改；回到抓取頁時沿用 (b) 的欄位與排序
    page.get_by_role("link", name="職缺表").click()
    expect(page.get_by_role("status")).to_contain_text("共 1 筆")
    assert headers(page) == JOB_TABLE_HEADERS
    page.get_by_role("link", name="抓取").click()
    expect(count(page)).to_have_text("這次抓到 3 筆，其中 2 筆資料庫裡還沒有")
    assert headers(page) == ["職缺代碼", *PREVIEW_HEADERS]
    assert row_codes(page) == ["C", "B", "A"]


def given_saved_crawl(page, live_server, fake_104, seed):
    """
    AC-store-save 的 Given：資料庫已有 A，以 Python、台北市、3 頁、全職抓到 A、B，抓完的時間是 T
    """
    seed("A")
    fake_104.add("Python", 1, ["A", "B"], 1)
    open_crawl(page, live_server)
    page.get_by_label("縣市").select_option("台北市")
    page.get_by_label("職缺性質").select_option(label="全職")
    start(page, "Python")
    expect(count(page)).to_have_text("這次抓到 2 筆，其中 1 筆資料庫裡還沒有")


def test_crawl_store_save(page, live_server, fake_104, seed, isolate_db, fixed_time):
    given_saved_crawl(page, live_server, fake_104, seed)

    # (a) 存入：寫入 A、B 與執行紀錄，跳到職缺表只列出剛存入的 2 筆
    page.get_by_role("button", name="存入職缺資料庫").click()

    expect(page.get_by_text("剛存入的 2 筆")).to_be_visible()
    assert page.url.endswith("/?saved=A,B")
    assert sorted(row_codes(page)) == ["A", "B"]
    jobs = db_jobs(isolate_db)
    t = T.isoformat()
    assert jobs["A"]["最後出現時間"] == jobs["B"]["最後出現時間"] == t
    assert jobs["B"]["首次出現時間"] == t
    latest = db_runs(isolate_db)[0]
    assert {k: latest[k] for k in ("執行時間", "來源", "關鍵字", "地區", "職缺性質", "頁數")} == {
        "執行時間": t, "來源": "爬蟲", "關鍵字": "Python", "地區": "台北市", "職缺性質": 1, "頁數": 3,
    }

    # 抓取頁的預覽清空
    page.get_by_role("link", name="抓取").click()
    expect(page.get_by_text("輸入條件後按「開始抓取」，抓完會在這裡預覽。")).to_be_visible()
    expect(rows(page)).to_have_count(0)


def test_crawl_store_discard(page, live_server, fake_104, seed, isolate_db):
    given_saved_crawl(page, live_server, fake_104, seed)
    before = (db_jobs(isolate_db), db_runs(isolate_db))

    # (b) 捨棄：資料庫不變，預覽清空
    page.get_by_role("button", name="捨棄").click()

    expect(page.get_by_text("已捨棄這次的抓取結果，沒有寫入職缺資料庫。")).to_be_visible()
    expect(rows(page)).to_have_count(0)
    assert (db_jobs(isolate_db), db_runs(isolate_db)) == before
    page.reload()
    expect(page.get_by_text("輸入條件後按「開始抓取」，抓完會在這裡預覽。")).to_be_visible()


def test_crawl_store_stopped(page, live_server, fake_104, isolate_db, fixed_time):
    fake_104.add("Python", 1, [f"p{i}" for i in range(1, 9)], 1)
    gate = fake_104.hold("detail", 3)
    open_crawl(page, live_server)

    # 取職缺內容時在時間 T 停止，預覽列出取完內容的職缺
    start(page, "Python")
    expect(progress(page)).to_contain_text("取職缺內容：第 3／8 筆")
    stop(page)
    gate.release()
    expect(count(page)).to_have_text("這次抓到 3 筆，其中 3 筆資料庫裡還沒有")
    previewed = sorted(row_codes(page))

    page.get_by_role("button", name="存入職缺資料庫").click()

    expect(page.get_by_text("剛存入的 3 筆")).to_be_visible()
    assert sorted(db_jobs(isolate_db)) == previewed == ["p1", "p2", "p3"]
    latest = db_runs(isolate_db)[0]
    assert (latest["執行時間"], latest["頁數"]) == (T.isoformat(), 3)


def test_crawl_store_failure(page, live_server, fake_104, seed, isolate_db):
    seed("A")
    fake_104.add("Python", 1, ["A", "B"], 1)
    open_crawl(page, live_server)
    start(page, "Python")
    expect(count(page)).to_have_text("這次抓到 2 筆，其中 1 筆資料庫裡還沒有")
    with closing(open_db(isolate_db)) as conn, conn:
        conn.execute("CREATE TRIGGER fail_run BEFORE INSERT ON scrape_runs BEGIN SELECT RAISE(ABORT, '模擬寫入失敗'); END")

    # 存入失敗：顯示原因，資料庫不變，預覽照舊
    page.get_by_role("button", name="存入職缺資料庫").click()
    expect(page.get_by_role("alert")).to_have_text("存入失敗：模擬寫入失敗")
    assert sorted(db_jobs(isolate_db)) == ["A"]
    assert row_codes(page) == ["A", "B"]
    assert "/crawl" in page.url

    # 可以再存入一次
    with closing(open_db(isolate_db)) as conn, conn:
        conn.execute("DROP TRIGGER fail_run")
    page.get_by_role("button", name="存入職缺資料庫").click()
    expect(page.get_by_text("剛存入的 2 筆")).to_be_visible()
    assert sorted(db_jobs(isolate_db)) == ["A", "B"]


def test_crawl_store_keep(page, live_server, fake_104, isolate_db):
    fake_104.add("Python", 1, ["p1", "p2"], 1)
    fake_104.add("Go", 1, ["g1"], 1)
    open_crawl(page, live_server)
    start(page, "Python")
    expect(count(page)).to_have_text("這次抓到 2 筆，其中 2 筆資料庫裡還沒有")

    # (a) 重新整理、關掉瀏覽器後重新打開：仍看得到同一份預覽
    page.reload()
    expect(count(page)).to_have_text("這次抓到 2 筆，其中 2 筆資料庫裡還沒有")
    other = page.context.browser.new_context()
    page.context.close()
    page = other.new_page()
    open_crawl(page, live_server)
    expect(count(page)).to_have_text("這次抓到 2 筆，其中 2 筆資料庫裡還沒有")
    assert row_codes(page) == ["p1", "p2"]

    # (b) 開始抓取時取消：不抓取，預覽照舊
    searches = len(fake_104.searches)
    start(page, "Go")
    dialog = page.get_by_role("dialog")
    expect(dialog).to_contain_text("這次的抓取結果還沒存入，重新抓取會捨棄它。")
    dialog.get_by_role("button", name="取消").click()
    expect(dialog).to_be_hidden()
    assert row_codes(page) == ["p1", "p2"]
    assert len(fake_104.searches) == searches

    # (c) 確認：原本的預覽捨棄、沒有寫入資料庫，開始新的抓取
    page.get_by_role("button", name="開始抓取").click()
    dialog.get_by_role("button", name="捨棄並重新抓取").click()
    expect(count(page)).to_have_text("這次抓到 1 筆，其中 1 筆資料庫裡還沒有")
    assert row_codes(page) == ["g1"]
    assert db_jobs(isolate_db) == {}
    other.close()


# ---------------------------------------------------------------------------
# 作業
# ---------------------------------------------------------------------------

def test_crawl_job(page, live_server, fake_104):
    codes = two_keywords(fake_104)
    gate = fake_104.hold("detail", 2)
    open_crawl(page, live_server)
    page.get_by_label("每個關鍵字抓幾頁").fill("2")
    start(page, "A, B")
    expect(progress(page)).to_contain_text("取職缺內容：第 2／10 筆")

    # (a) 重新整理：接回目前的進度
    page.reload()
    expect(progress(page)).to_contain_text("取職缺內容：第 2／10 筆")
    expect(page.get_by_role("button", name="停止")).to_be_visible()

    # (b) 關掉瀏覽器後重新打開：抓取沒有中斷，接回進度，抓完後照常預覽
    other = page.context.browser.new_context()
    page.context.close()
    page = other.new_page()
    open_crawl(page, live_server)
    expect(progress(page)).to_contain_text("取職缺內容：第 2／10 筆")
    gate.release()
    expect(count(page)).to_have_text("這次抓到 10 筆，其中 10 筆資料庫裡還沒有")
    assert sorted(row_codes(page)) == sorted(codes)
    other.close()


def test_crawl_job_busy(page, live_server, web_app, fake_104):
    release = threading.Event()
    web_app.state.runner.start("評分", lambda job: release.wait(30))
    try:
        open_crawl(page, live_server)

        # 有其他作業在跑：不開始抓取，說明同一時間只能跑一個作業
        start(page, "Python")
        expect(page.get_by_role("alert")).to_have_text("同一時間只能跑一個作業，目前正在評分")
        assert fake_104.searches == []
    finally:
        release.set()


def fail_next_state(page: Page) -> None:
    """讓下一次取得抓取狀態的請求回 500，之後照常"""
    failed = []

    def fail_once(route):
        if route.request.method == "GET" and not failed:
            failed.append(route.request.url)
            route.fulfill(status=500, body="伺服器錯誤")
        else:
            route.continue_()

    page.route("**/api/crawl", fail_once)


def test_crawl_refresh_failure_keeps_page(page, live_server, fake_104):
    fake_104.add("Python", 1, ["p1", "p2"], 1)
    gate = fake_104.hold("detail", 1)
    open_crawl(page, live_server)
    start(page, "Python")
    expect(progress(page)).to_contain_text("取職缺內容：第 1／2 筆")

    # 抓取中有一次取不到狀態：畫面留著，可以繼續停止或等抓完，下次取到時訊息消失
    fail_next_state(page)
    expect(page.get_by_text("取不到抓取的最新狀態")).to_be_visible()
    expect(progress(page)).to_contain_text("取職缺內容：第 1／2 筆")
    expect(page.get_by_role("button", name="停止")).to_be_visible()
    gate.release()
    expect(count(page)).to_have_text("這次抓到 2 筆，其中 2 筆資料庫裡還沒有")
    expect(page.get_by_text("取不到抓取的最新狀態")).to_have_count(0)


def test_crawl_refresh_failure_after_start_recovers(page, live_server, fake_104):
    fake_104.add("Python", 1, ["p1", "p2"], 1)
    gate = fake_104.hold("detail", 1)
    open_crawl(page, live_server)

    # 開始抓取後第一次就取不到狀態：持續重試，取到後接上進度
    fail_next_state(page)
    start(page, "Python")
    expect(progress(page)).to_contain_text("取職缺內容：第 1／2 筆")
    expect(page.get_by_role("button", name="停止")).to_be_visible()
    expect(page.get_by_text("取不到抓取的最新狀態")).to_have_count(0)
    gate.release()
    expect(count(page)).to_have_text("這次抓到 2 筆，其中 2 筆資料庫裡還沒有")


def test_crawl_slow_state_still_updates(page, live_server, fake_104):
    fake_104.add("Python", 1, ["p1", "p2"], 1)
    gate = fake_104.hold("detail", 1)
    open_crawl(page, live_server)
    # 每個請求都要 1.5 秒才回應，比輪詢的間隔長：回應再慢也要採用，進度才會更新
    cdp = page.context.new_cdp_session(page)
    cdp.send("Network.emulateNetworkConditions", {
        "offline": False, "latency": 1500, "downloadThroughput": -1, "uploadThroughput": -1,
    })

    start(page, "Python")
    expect(progress(page)).to_contain_text("取職缺內容：第 1／2 筆", timeout=15000)
    gate.release()
    expect(count(page)).to_have_text("這次抓到 2 筆，其中 2 筆資料庫裡還沒有", timeout=15000)


def test_crawl_double_click_starts_once(page, live_server, fake_104):
    fake_104.add("Python", 1, ["p1"], 1)
    fake_104.add("Go", 1, ["g1"], 1)
    open_crawl(page, live_server)
    # 請求要 0.5 秒才回應，第二下一定落在第一個請求還沒有結果的時候
    cdp = page.context.new_cdp_session(page)
    cdp.send("Network.emulateNetworkConditions", {
        "offline": False, "latency": 500, "downloadThroughput": -1, "uploadThroughput": -1,
    })

    # 連按兩下「開始抓取」：只開始一次，不會出現「同一時間只能跑一個作業」
    page.get_by_label("關鍵字", exact=True).fill("Python")
    page.get_by_role("button", name="開始抓取").dblclick()
    expect(count(page)).to_have_text("這次抓到 1 筆，其中 1 筆資料庫裡還沒有", timeout=10000)
    expect(page.get_by_role("alert")).to_have_count(0)
    assert len(fake_104.searches) == 1

    # 確認視窗的「捨棄並重新抓取」連按兩下也一樣
    start(page, "Go")
    page.get_by_role("dialog").get_by_role("button", name="捨棄並重新抓取").dblclick()
    expect(count(page)).to_have_text("這次抓到 1 筆，其中 1 筆資料庫裡還沒有", timeout=10000)
    expect(rows(page).first).to_have_attribute("data-code", "g1")
    expect(page.get_by_role("alert")).to_have_count(0)
    assert len(fake_104.searches) == 2
