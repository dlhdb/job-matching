"""設定頁的瀏覽器行為：前後端串起來，以 Playwright 操作真的 Chromium。資料庫是 isolate_db，啟動時寫入三份第 1 版。"""

from contextlib import closing
from datetime import datetime

import pytest
import yaml
from playwright.sync_api import Browser, Page, expect

from job_db import add_version, current_versions, list_versions, open_db
from job_scoring.settings import DEFAULTS

T = datetime(2026, 9, 5, 20, 12, 40)

# 讓 localStorage 一讀寫就丟例外，模擬不允許保存網站資料的瀏覽器
BLOCK_STORAGE = """
Object.defineProperty(window, "localStorage", {
  get() { throw new DOMException("blocked", "SecurityError"); },
});
"""


@pytest.fixture
def db(isolate_db, live_server):
    """
    伺服器啟動（寫入第 1 版）之後的資料庫路徑，用來準備版本與檢查結果

    每次存取都另開連線再關掉：連線開著讀過資料就會留著讀取的交易，伺服器寫入時會等不到鎖。

    :return: Path
    """
    return isolate_db


def query(db, fn, *args):
    """
    開一條連線呼叫 fn(conn, *args)，用完就關

    :return: fn 的回傳值
    """
    with closing(open_db(db)) as conn:
        return fn(conn, *args)


def prefs_text(preferences_data, expected=70000):
    data = {**preferences_data, "薪資": {**preferences_data["薪資"], "期望月薪": expected}}
    return yaml.safe_dump(data, allow_unicode=True)


def add(db, kind, content, name):
    query(db, lambda conn: add_version(conn, kind, name=name, description="", content=content, saved_at=T))


def current(db, kind):
    return query(db, current_versions)[kind]["版本"]


def score_count(db):
    return query(db, lambda conn: conn.execute("SELECT COUNT(*) FROM job_scores").fetchone()[0])


def open_settings(page: Page, url: str, tab: str = "偏好") -> None:
    """打開設定頁並切到指定的分頁"""
    page.goto(f"{url}/settings")
    page.get_by_role("tab", name=tab).click()
    expect(page.get_by_role("tab", name=tab)).to_have_attribute("aria-selected", "true")


def editor(page: Page, label: str = "偏好"):
    return page.get_by_label(f"{label}的編輯區")


def primary(page: Page):
    return page.locator(".set-actions .btn.primary")


def versions(page: Page):
    return page.get_by_role("list", name="版本紀錄").get_by_role("listitem")


def status(page: Page):
    return page.locator(".set-status")


def test_settings_default(live_server, db, page: Page):
    # AC-settings-default：三份都只有第 1 版，是預設內容；偏好與經歷標出預設範例
    for tab, label, marked in (("偏好", "偏好", True), ("經歷", "經歷", True), ("提示詞模板", "提示詞模板", False)):
        open_settings(page, live_server, tab)
        expect(versions(page)).to_have_count(1)
        expect(versions(page).first).to_contain_text("第 1 版")
        kind = {"偏好": "preferences", "經歷": "experience", "提示詞模板": "template"}[tab]
        expect(editor(page, label)).to_have_value(DEFAULTS[kind])
        expect(status(page)).to_contain_text("目前設定：第 1 版")
        if marked:
            expect(status(page).locator(".tag.default")).to_have_text("預設範例")
        else:
            expect(status(page).locator(".tag.default")).to_have_count(0)


def test_settings_version(live_server, db, page: Page, preferences_data):
    open_settings(page, live_server)
    edited = prefs_text(preferences_data)

    # (a) 修改後按「儲存並套用」，不填名稱：不能儲存
    editor(page).fill(edited)
    expect(primary(page)).to_have_text("儲存並套用")
    expect(primary(page)).to_be_enabled()
    primary(page).click()
    dialog = page.get_by_role("dialog")
    expect(dialog).to_contain_text("存成第 2 版")
    expect(dialog.get_by_role("button", name="儲存並套用")).to_be_disabled()
    expect(dialog).to_contain_text("名稱必填")

    # (b) 填名稱、描述留白後儲存：多了第 2 版並成為目前設定，版本紀錄由新到舊
    dialog.get_by_label("名稱（必填）").fill("後端與 LLM")
    dialog.get_by_role("button", name="儲存並套用").click()
    expect(dialog).to_be_hidden()
    expect(versions(page)).to_have_count(2)
    expect(versions(page).first).to_contain_text("第 2 版 後端與 LLM 目前")
    expect(versions(page).nth(1)).not_to_contain_text("目前")
    expect(status(page)).to_contain_text("目前設定：第 2 版「後端與 LLM」")
    expect(status(page).locator(".tag.default")).to_have_count(0)
    expect(page.locator(".notice")).to_contain_text("不會自動重評")
    second = query(db, list_versions, "preferences")[0]
    assert (second["版本"], second["名稱"], second["描述"], second["內容"]) == (2, "後端與 LLM", "", edited)
    assert current(db, "preferences") == 2

    # (c) 修改第 2 版的名稱與描述，內容不變；沒有刪除或修改內容的操作
    page.get_by_role("button", name="編輯第 2 版的名稱與描述").click()
    dialog = page.get_by_role("dialog")
    expect(dialog.get_by_label("名稱（必填）")).to_have_value("後端與 LLM")
    dialog.get_by_label("名稱（必填）").fill("後端")
    dialog.get_by_label("描述").fill("第一次填")
    dialog.get_by_role("button", name="儲存", exact=True).click()
    expect(versions(page).first).to_contain_text("第 2 版 後端 目前第一次填")
    second = query(db, list_versions, "preferences")[0]
    assert (second["名稱"], second["描述"], second["內容"]) == ("後端", "第一次填", edited)
    expect(page.get_by_role("button", name="刪除")).to_have_count(0)


def test_settings_apply(live_server, db, page: Page, preferences_data):
    add(db, "preferences", prefs_text(preferences_data, 72000), "第二版")
    add(db, "preferences", prefs_text(preferences_data, 73000), "第三版")

    # (a) 編輯區是第 3 版，主按鈕停用並顯示「已是目前設定」
    open_settings(page, live_server)
    expect(editor(page)).to_have_value(prefs_text(preferences_data, 73000))
    expect(primary(page)).to_have_text("已是目前設定")
    expect(primary(page)).to_be_disabled()

    # (b) 點第 1 版：編輯區換成第 1 版，主按鈕是「套用第 1 版」，目前設定仍是第 3 版
    versions(page).nth(2).get_by_role("button").first.click()
    expect(editor(page)).to_have_value(DEFAULTS["preferences"])
    expect(primary(page)).to_have_text("套用第 1 版")
    expect(versions(page).nth(2)).to_contain_text("編輯中")
    assert current(db, "preferences") == 3

    # (c) 套用第 1 版：目前設定改成第 1 版，仍是 3 個版本
    primary(page).click()
    expect(primary(page)).to_have_text("已是目前設定")
    expect(versions(page).nth(2)).to_contain_text("目前")
    assert current(db, "preferences") == 1
    assert len(query(db, list_versions, "preferences")) == 3

    # (d) 修改後儲存並套用：多了第 4 版並成為目前設定，沒有任何評分紀錄新增或改變
    editor(page).fill(prefs_text(preferences_data, 74000))
    primary(page).click()
    page.get_by_role("dialog").get_by_label("名稱（必填）").fill("第四版")
    page.get_by_role("dialog").get_by_role("button", name="儲存並套用").click()
    expect(versions(page)).to_have_count(4)
    assert current(db, "preferences") == 4
    assert score_count(db) == 0

    # (e) 載入第 2 版，改過再改回和第 2 版相同：主按鈕是「套用第 2 版」
    versions(page).nth(2).get_by_role("button").first.click()
    expect(primary(page)).to_have_text("套用第 2 版")
    editor(page).fill("改過")
    expect(primary(page)).to_have_text("儲存並套用")
    editor(page).fill(prefs_text(preferences_data, 72000))
    expect(primary(page)).to_have_text("套用第 2 版")


def test_settings_editor(live_server, db, page: Page, browser: Browser):
    add(db, "experience", "第二版的經歷", "第二版")

    # (a) 修改編輯區，關掉分頁後重新打開：仍是修改後的內容，目前設定仍是第 2 版
    open_settings(page, live_server, "經歷")
    editor(page, "經歷").fill("修改中的經歷")
    context = page.context
    page.close()
    page = context.new_page()
    open_settings(page, live_server, "經歷")
    expect(editor(page, "經歷")).to_have_value("修改中的經歷")
    expect(status(page)).to_contain_text("目前設定：第 2 版")
    expect(status(page)).to_contain_text("有修改，還沒儲存")
    assert current(db, "experience") == 2

    # (b) 點第 1 版：先詢問是否蓋掉還沒儲存的修改
    versions(page).nth(1).get_by_role("button").first.click()
    confirm = page.get_by_role("dialog")
    expect(confirm).to_contain_text("載入第 1 版會蓋掉修改")

    # (c) 取消後編輯區不變；捨棄修改後回到第 2 版的內容
    confirm.get_by_role("button", name="取消").click()
    expect(confirm).to_be_hidden()
    expect(editor(page, "經歷")).to_have_value("修改中的經歷")
    page.get_by_role("button", name="捨棄修改").click()
    expect(editor(page, "經歷")).to_have_value("第二版的經歷")
    expect(page.get_by_role("button", name="捨棄修改")).to_be_disabled()

    # (d) 還原預設：編輯區換成預設範例，主按鈕是「儲存並套用」
    page.get_by_role("button", name="還原預設").click()
    expect(editor(page, "經歷")).to_have_value(DEFAULTS["experience"])
    expect(primary(page)).to_have_text("儲存並套用")
    expect(page.get_by_role("button", name="還原預設")).to_be_disabled()

    # (e) 在不允許保存的瀏覽器打開：編輯區是目前設定的內容，沒有錯誤訊息
    blocked = browser.new_context()
    blocked.add_init_script(BLOCK_STORAGE)
    other = blocked.new_page()
    open_settings(other, live_server, "經歷")
    expect(editor(other, "經歷")).to_have_value("第二版的經歷")
    editor(other, "經歷").fill("記不住的修改")
    expect(primary(other)).to_have_text("儲存並套用")
    expect(other.locator(".notice")).to_have_count(0)
    blocked.close()


def test_settings_check(live_server, db, page: Page, preferences_data):
    open_settings(page, live_server, "提示詞模板")
    template = editor(page, "提示詞模板")
    messages = page.get_by_role("list", name="檢查結果")

    # (a) 模板沒有 USER 標記：顯示原因，主按鈕停用
    template.fill(DEFAULTS["template"].replace("<!-- USER -->", ""))
    expect(messages).to_contain_text("缺少 <!-- SYSTEM --> 或 <!-- USER --> 標記")
    expect(primary(page)).to_be_disabled()

    # (b) 用了 $年資：顯示原因與可以用的變數
    template.fill(DEFAULTS["template"] + "\n- 年資：$年資")
    expect(messages).to_contain_text("不認得的變數：$年資（可以用的變數：$目標方向")
    expect(primary(page)).to_be_disabled()

    # (c) 沒用到 $工作經歷：只提醒，可以儲存
    template.fill(DEFAULTS["template"].replace("$工作經歷", ""))
    expect(messages).to_contain_text("提醒：沒有用到 $工作經歷：AI 收不到這項資料")
    expect(messages.locator(".error")).to_have_count(0)
    expect(primary(page)).to_be_enabled()

    # (d) 偏好有錯：顯示原因，主按鈕停用
    page.get_by_role("tab", name="偏好").click()
    del preferences_data["權重"]
    editor(page).fill(yaml.safe_dump(preferences_data, allow_unicode=True))
    expect(page.get_by_role("list", name="檢查結果")).to_contain_text("權重：缺少這個欄位")
    expect(primary(page)).to_be_disabled()

    # (e) 經歷只有一行：沒有檢查訊息，可以儲存
    page.get_by_role("tab", name="經歷").click()
    editor(page, "經歷").fill("只有一行文字")
    expect(primary(page)).to_be_enabled()
    expect(page.get_by_role("list", name="檢查結果")).to_have_count(0)


def test_settings_reload_failure_after_save(live_server, db, page: Page, preferences_data):
    open_settings(page, live_server)
    editor(page).fill(prefs_text(preferences_data))
    primary(page).click()
    page.get_by_role("dialog").get_by_label("名稱（必填）").fill("後端與 LLM")
    # 存進去之後，重新取得設定失敗
    page.route("**/api/settings", lambda route: route.fulfill(status=500, body="壞掉了"))
    page.get_by_role("dialog").get_by_role("button", name="儲存並套用").click()

    # 版本已存入；畫面上的設定已過時，整頁改成請使用者重新整理，不能再按一次存成重複的版本
    expect(page.locator(".notice.warn")).to_contain_text("已把偏好存成第 2 版並套用，但取不到最新的設定")
    expect(page.locator(".notice.warn")).to_contain_text("請重新整理頁面")
    expect(editor(page)).to_have_count(0)
    assert current(db, "preferences") == 2
    assert len(query(db, list_versions, "preferences")) == 2

    # 重新整理後是新的目前設定，編輯區沒有留下修改
    page.unroute("**/api/settings")
    open_settings(page, live_server)
    expect(editor(page)).to_have_value(prefs_text(preferences_data))
    expect(primary(page)).to_have_text("已是目前設定")


def test_settings_typing_during_apply_kept(live_server, db, page: Page, preferences_data):
    add(db, "preferences", prefs_text(preferences_data), "第二版")
    held = []
    page.route("**/api/settings/preferences/current", lambda route: held.append(route))

    open_settings(page, live_server)
    versions(page).nth(1).get_by_role("button").first.click()
    primary(page).click()
    expect(primary(page)).to_be_disabled()
    assert len(held) == 1

    # 套用還沒回來時切到經歷打字
    page.get_by_role("tab", name="經歷").click()
    editor(page, "經歷").fill("打到一半的經歷")
    held[0].continue_()

    expect(page.locator(".notice")).to_contain_text("已套用偏好第 1 版「預設範例」")
    expect(editor(page, "經歷")).to_have_value("打到一半的經歷")
    assert current(db, "preferences") == 1
    # 重新打開後經歷的修改仍在，偏好是剛套用的第 1 版
    open_settings(page, live_server, "經歷")
    expect(editor(page, "經歷")).to_have_value("打到一半的經歷")
    page.get_by_role("tab", name="偏好").click()
    expect(editor(page)).to_have_value(DEFAULTS["preferences"])


def test_settings_rename_keeps_unsaved_edits(live_server, db, page: Page):
    open_settings(page, live_server, "經歷")
    editor(page, "經歷").fill("還沒儲存的經歷")

    page.get_by_role("button", name="編輯第 1 版的名稱與描述").click()
    page.get_by_role("dialog").get_by_label("名稱（必填）").fill("改過的名稱")
    page.get_by_role("dialog").get_by_role("button", name="儲存", exact=True).click()

    expect(versions(page).first).to_contain_text("改過的名稱")
    expect(editor(page, "經歷")).to_have_value("還沒儲存的經歷")
    open_settings(page, live_server, "經歷")
    expect(editor(page, "經歷")).to_have_value("還沒儲存的經歷")


def test_settings_typing_same_tab_during_apply_kept(live_server, db, page: Page, preferences_data):
    add(db, "preferences", prefs_text(preferences_data), "第二版")
    held = []
    page.route("**/api/settings/preferences/current", lambda route: held.append(route))

    open_settings(page, live_server)
    versions(page).nth(1).get_by_role("button").first.click()
    primary(page).click()
    expect(primary(page)).to_be_disabled()
    assert len(held) == 1

    # 套用還沒回來時在同一個分頁打字：套用的是第 1 版，打的字留在編輯區，以第 1 版為底
    editor(page).fill("套用中打的字")
    held[0].continue_()

    expect(page.locator(".notice")).to_contain_text("已套用偏好第 1 版")
    expect(editor(page)).to_have_value("套用中打的字")
    expect(status(page)).to_contain_text("目前設定：第 1 版")
    expect(status(page)).to_contain_text("有修改，還沒儲存")
    assert current(db, "preferences") == 1


def test_settings_check_failure_retries(live_server, db, page: Page):
    failures = []

    def _fail_once(route):
        if not failures:
            failures.append(route.request.url)
            route.fulfill(status=500, body="暫時壞掉")
        else:
            route.continue_()

    page.route("**/api/settings/check", _fail_once)
    open_settings(page, live_server, "經歷")
    editor(page, "經歷").fill("改過的經歷")

    # 第一次檢查失敗時顯示原因，之後自動重試成功，主按鈕可以按
    expect(page.locator(".notice.warn")).to_contain_text("無法檢查內容，稍後自動重試")
    expect(primary(page)).to_be_enabled(timeout=10000)
    expect(page.locator(".notice.warn")).to_have_count(0)
    assert len(failures) == 1
