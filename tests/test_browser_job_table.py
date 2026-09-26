"""職缺表的瀏覽器行為：前後端串起來，以 Playwright 操作真的 Chromium。"""

from contextlib import closing
from datetime import datetime, timedelta

import pytest
from playwright.sync_api import Page, expect
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError

from job_db import open_db, save_run

DEFAULT_HEADERS = ["職缺名稱", "公司名稱", "地區", "薪資待遇", "最後出現時間"]
BASE_TIME = datetime(2026, 9, 1, 10, 0, 0)


@pytest.fixture
def seed(isolate_db, make_job):
    """
    寫入職缺：每筆各自一次寫入，第 i 筆的最後出現時間是 BASE_TIME 加 i 天

    :return: callable, seed(*overrides: dict) -> None，每個 dict 覆寫一筆職缺的欄位
    """
    def _seed(*overrides):
        with closing(open_db(isolate_db)) as conn:
            for i, fields in enumerate(overrides):
                save_run(conn, [make_job(**fields)], BASE_TIME + timedelta(days=i), "爬蟲")
    return _seed


ROW_CODES_JS = "() => [...document.querySelectorAll('tbody tr.row')].map(r => r.dataset.code)"


def row_codes(page: Page) -> list[str]:
    """表格目前列出的職缺代碼，依顯示順序"""
    return page.evaluate(ROW_CODES_JS)


def assert_rows(page: Page, expected: list[str]) -> None:
    """
    等表格列出的職缺代碼變成 expected（依顯示順序），逾時仍不同時以實際的代碼失敗

    操作後畫面是非同步更新的，計數文字不變時（例如篩選前後都是 2 筆）沒有其他東西可以等。
    """
    try:
        page.wait_for_function(
            f"expected => JSON.stringify(({ROW_CODES_JS})()) === JSON.stringify(expected)",
            arg=expected, timeout=5000)
    except PlaywrightTimeoutError:
        pass
    assert row_codes(page) == expected


def headers(page: Page) -> list[str]:
    """表格目前的欄位標題（不含排序箭頭）"""
    return page.locator("thead th").evaluate_all(
        "ths => ths.map(th => th.firstChild ? th.firstChild.textContent : '')")


def count(page: Page):
    """工具列的計數文字"""
    return page.get_by_role("status")


def open_table(page: Page, url: str) -> None:
    """打開職缺表，等職缺讀完"""
    page.goto(url)
    expect(count(page)).to_contain_text("共")


def pick_column(page: Page, name: str, checked: bool) -> None:
    """在「選擇欄位」勾選或取消一個欄位，再關掉選單"""
    page.get_by_role("button", name="選擇欄位").click()
    box = page.get_by_role("group", name="選擇欄位").get_by_label(name, exact=True)
    box.set_checked(checked)
    page.get_by_role("button", name="選擇欄位").click()


def test_job_table_lists_all_jobs(page, live_server, seed):
    seed({"職缺代碼": "old", "職缺名稱": "Go 工程師"},
         {"職缺代碼": "mid", "職缺名稱": "Rust 工程師"},
         {"職缺代碼": "new", "職缺名稱": "Python 工程師"})
    open_table(page, live_server)

    # (a) 全部列出，沒有分頁，最後出現時間由新到舊
    expect(count(page)).to_have_text("符合 3 筆／共 3 筆")
    assert_rows(page, ["new", "mid", "old"])

    # (b) 只有 1 筆符合的關鍵字
    page.get_by_label("關鍵字").fill("Python")
    expect(count(page)).to_have_text("符合 1 筆／共 3 筆")
    assert_rows(page, ["new"])

    # (c) 沒有職缺符合：表格是空的，沒有錯誤訊息
    page.get_by_label("關鍵字").fill("COBOL")
    expect(count(page)).to_have_text("符合 0 筆／共 3 筆")
    assert_rows(page, [])
    expect(page.get_by_text("沒有符合條件的職缺")).to_be_visible()
    expect(page.locator(".notice.warn")).to_have_count(0)


def test_job_table_columns(page, live_server, seed):
    seed({"職缺代碼": "a"})
    open_table(page, live_server)

    # (a) 預設欄位；可以選的欄位是職缺欄位契約的全部欄位與兩個出現時間
    assert headers(page) == DEFAULT_HEADERS
    page.get_by_role("button", name="選擇欄位").click()
    options = page.get_by_role("group", name="選擇欄位").get_by_role("checkbox")
    expect(options).to_have_count(18)
    page.get_by_role("button", name="選擇欄位").click()

    # (b) 勾選首次出現時間、取消薪資待遇
    pick_column(page, "首次出現時間", True)
    pick_column(page, "薪資待遇", False)
    assert headers(page) == ["職缺名稱", "公司名稱", "地區", "首次出現時間", "最後出現時間"]

    # (c) 取消到只剩一欄，最後一欄取消不掉
    for name in ["職缺名稱", "公司名稱", "地區", "首次出現時間"]:
        pick_column(page, name, False)
    assert headers(page) == ["最後出現時間"]
    page.get_by_role("button", name="選擇欄位").click()
    expect(page.get_by_role("group", name="選擇欄位").get_by_label("最後出現時間")).to_be_disabled()
    assert headers(page) == ["最後出現時間"]


def test_job_table_sort(page, live_server, seed):
    seed({"職缺代碼": "none", "薪資下限": None},
         {"職缺代碼": "low", "薪資下限": 40000},
         {"職缺代碼": "high", "薪資下限": 90000})
    open_table(page, live_server)
    pick_column(page, "薪資下限", True)
    header = page.locator("thead th", has_text="薪資下限")

    # (a) 由大到小，null 排在最後
    header.click()
    expect(header).to_have_attribute("aria-sort", "descending")
    assert_rows(page, ["high", "low", "none"])

    # (b) 反向，null 仍在最後
    header.click()
    expect(header).to_have_attribute("aria-sort", "ascending")
    assert_rows(page, ["low", "high", "none"])


def test_job_table_expand(page, live_server, seed):
    seed({"職缺代碼": "a", "工作內容": "第一行\n第二行：完整的工作內容"},
         {"職缺代碼": "b"})
    open_table(page, live_server)
    row_a = page.locator('tbody tr.row[data-code="a"]')
    row_b = page.locator('tbody tr.row[data-code="b"]')
    detail = page.locator("tbody tr.detail")

    # (a) 展開：完整工作內容、兩個出現時間、在新分頁開啟的連結
    row_a.click()
    expect(detail).to_have_count(1)
    expect(detail.locator("pre.content")).to_have_text("第一行\n第二行：完整的工作內容")
    expect(detail).to_contain_text("首次出現時間")
    expect(detail).to_contain_text("2026-09-01 10:00:00")
    job_link = detail.get_by_role("link", name="職缺頁")
    expect(job_link).to_have_attribute("href", "https://www.104.com.tw/job/ok")
    expect(detail.get_by_role("link", name="公司頁")).to_have_attribute(
        "href", "https://www.104.com.tw/company/abc")
    # 不真的連到 104：攔下新分頁的請求，只確認它開在新分頁
    page.context.route("https://www.104.com.tw/**", lambda route: route.fulfill(body="104"))
    with page.expect_popup() as popup:
        job_link.click()
    assert popup.value.url == "https://www.104.com.tw/job/ok"
    popup.value.close()

    # (b) 點另一列：前一列收合，改展開這一列
    row_b.click()
    expect(detail).to_have_count(1)
    expect(row_a).to_have_attribute("aria-expanded", "false")
    expect(row_b).to_have_attribute("aria-expanded", "true")

    # (c) 再點同一列：收合
    row_b.click()
    expect(detail).to_have_count(0)


FILTER_JOBS = (
    {"職缺代碼": "A", "職缺名稱": "Python 工程師", "地區": "台北市內湖區 瑞光路"},
    {"職缺代碼": "B", "職缺名稱": "工程師", "工作內容": "常駐台北辦公室", "地區": "新北市板橋區 文化路"},
    {"職缺代碼": "C", "職缺名稱": "工程師", "電腦專長": "Rust", "地區": "台中市西屯區 市政路"},
)


@pytest.mark.parametrize("keyword, area, expected", [
    ("python", "", ["A"]),
    ("Python，Rust", "", ["A", "C"]),
    (" , ", "", ["A", "B", "C"]),
    ("", "臺北", ["A"]),
    ("", "台北", ["A"]),
    ("", "內湖, 台中", ["A", "C"]),
    ("Python", "台中", []),
], ids=["不分大小寫", "全形逗號", "只有逗號", "臺視為台", "不比對工作內容", "多個地名", "兩個都要符合"])
def test_job_table_filter(page, live_server, seed, keyword, area, expected):
    seed(*FILTER_JOBS)
    open_table(page, live_server)

    page.get_by_label("關鍵字").fill(keyword)
    page.get_by_label("地區").fill(area)
    expect(count(page)).to_have_text(f"符合 {len(expected)} 筆／共 3 筆")
    assert sorted(row_codes(page)) == expected

    page.get_by_role("button", name="清除篩選").click()
    expect(count(page)).to_have_text("符合 3 筆／共 3 筆")
    expect(page.get_by_label("關鍵字")).to_have_value("")
    expect(page.get_by_label("地區")).to_have_value("")


def customize(page: Page) -> None:
    """改掉欄位、關鍵字、地區與排序"""
    pick_column(page, "職缺代碼", True)
    page.get_by_label("關鍵字").fill("工程師")
    page.get_by_label("地區").fill("台北")
    page.locator("thead th", has_text="職缺代碼").click()


def assert_customized(page: Page) -> None:
    assert headers(page) == ["職缺代碼", *DEFAULT_HEADERS]
    expect(page.get_by_label("關鍵字")).to_have_value("工程師")
    expect(page.get_by_label("地區")).to_have_value("台北")
    expect(page.locator("thead th", has_text="職缺代碼")).to_have_attribute("aria-sort", "ascending")


def assert_default(page: Page) -> None:
    assert headers(page) == DEFAULT_HEADERS
    expect(page.get_by_label("關鍵字")).to_have_value("")
    expect(page.get_by_label("地區")).to_have_value("")
    expect(page.locator("thead th", has_text="最後出現時間")).to_have_attribute(
        "aria-sort", "descending")


def test_job_table_remembers_view(page, live_server, seed):
    seed({"職缺代碼": "a"}, {"職缺代碼": "b"})
    open_table(page, live_server)
    customize(page)

    # (a) 關掉分頁後重新打開
    reopened = page.context.new_page()
    page.close()
    open_table(reopened, live_server)
    assert_customized(reopened)


def test_job_table_storage_blocked(page, live_server, seed):
    seed({"職缺代碼": "a"}, {"職缺代碼": "b"})
    # (b) 不允許保存的瀏覽器：讀取 localStorage 就丟出例外
    page.add_init_script("""
        Object.defineProperty(window, "localStorage", {
          get() { throw new DOMException("blocked", "SecurityError"); },
        });
    """)
    errors = []
    page.on("pageerror", lambda error: errors.append(error))
    open_table(page, live_server)
    blocked = page.evaluate("() => { try { localStorage; return false } catch { return true } }")
    assert blocked

    expect(count(page)).to_have_text("符合 2 筆／共 2 筆")
    assert_default(page)
    # 改了也不出錯，只是記不住：重新整理後回到預設
    customize(page)
    page.reload()
    expect(count(page)).to_contain_text("共")
    assert_default(page)
    assert errors == []


def test_job_table_reset_view(page, live_server, seed):
    seed({"職缺代碼": "a"}, {"職缺代碼": "b"})
    open_table(page, live_server)
    customize(page)

    page.get_by_role("button", name="還原預設檢視").click()
    assert_default(page)

    page.reload()
    expect(count(page)).to_contain_text("共")
    assert_default(page)


def test_job_table_just_saved(page, live_server, seed):
    # 5 筆職缺，j4、j5 是剛存入的；記著的關鍵字 Python 只有 j1、j5 符合
    seed({"職缺代碼": "j1", "職缺名稱": "Python 工程師"},
         {"職缺代碼": "j2", "職缺名稱": "Go 工程師"},
         {"職缺代碼": "j3", "職缺名稱": "Rust 工程師"},
         {"職缺代碼": "j4", "職缺名稱": "Java 工程師"},
         {"職缺代碼": "j5", "職缺名稱": "Python 資深工程師"})
    open_table(page, live_server)
    page.get_by_label("關鍵字").fill("Python")
    expect(count(page)).to_have_text("符合 2 筆／共 5 筆")
    saved_url = f"{live_server}/?saved=j4,j5,not-in-db"
    keyword = page.get_by_label("關鍵字")
    area = page.get_by_label("地區")
    clear = page.get_by_role("button", name="清除篩選")

    # (a) 只列出剛存入的 2 筆，其他篩選不能用
    open_table(page, saved_url)
    expect(page.get_by_text("剛存入的 2 筆")).to_be_visible()
    assert_rows(page, ["j5", "j4"])
    expect(keyword).to_be_disabled()
    expect(area).to_be_disabled()
    expect(clear).to_be_disabled()

    # (b) 還原預設檢視：欄位與排序回到預設，仍只列出這 2 筆，篩選仍不能用
    pick_column(page, "職缺代碼", True)
    page.locator("thead th", has_text="職缺名稱").click()
    page.get_by_role("button", name="還原預設檢視").click()
    assert headers(page) == DEFAULT_HEADERS
    assert_rows(page, ["j5", "j4"])
    expect(keyword).to_be_disabled()
    expect(keyword).to_have_value("Python")

    # (c) 關掉標籤：回到原本的關鍵字篩選，可以調整
    page.get_by_role("button", name="關掉「剛存入」標籤").click()
    expect(count(page)).to_have_text("符合 2 筆／共 5 筆")
    assert_rows(page, ["j5", "j1"])
    expect(keyword).to_be_enabled()
    assert "saved" not in page.url

    # (d) 再帶清單打開一次，之後不帶清單打開：記著的仍是原本的關鍵字篩選
    open_table(page, saved_url)
    expect(page.get_by_text("剛存入的 2 筆")).to_be_visible()
    open_table(page, live_server)
    expect(keyword).to_have_value("Python")
    assert_rows(page, ["j5", "j1"])
