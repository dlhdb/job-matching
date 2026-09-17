#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
104人力銀行職缺撈取工具 (104 Job Bank Scraper)
---------------------------------------------
此腳本可從 104 人力銀行的搜尋 API (https://www.104.com.tw/jobs/search/api/jobs)
安全、穩定且快速地撈取指定關鍵字的職缺，並將結果儲存為 CSV 與 JSON 檔案。

功能特色：
1. 支援「多個關鍵字批量撈取」：可同時輸入多個獨立關鍵字，腳本會自動輪詢、合併並自動進行「資料去重」(Deduplication)，避免重複的職缺重複寫入。
2. 支援命令列參數 (CLI Args) 與親切的互動式引導模式。
3. 內建熱門縣市名稱自動對應 104 地區代碼 (Area Code)。
4. 自動進行請求頻率限制 (Rate Limiting) 與隨機延遲，避免對 104 伺服器造成負擔。
5. 提供美觀的終端機表格預覽，並使用 Emojis 提升視覺體驗。
6. 匯出 CSV 採用帶有 BOM 的 UTF-8 編碼 (utf-8-sig)，確保 Microsoft Excel 開啟時中文不會亂碼。
7. 提供豐富的欄位提取，包含職缺名稱、公司名稱、薪資區間、地區、工作描述、電腦專長、科系要求、更新日期及直接應徵連結等。

使用說明：
- 互動模式：直接執行 `uv run src/fetch_104_jobs.py`
- 命令列模式：`uv run src/fetch_104_jobs.py --keyword "Python,React,AI" --pages 3 --area "台北市"`
"""

import sys
import os
import time
import random
import json
import csv
import argparse
from datetime import datetime
from pathlib import Path
import requests

# 輸出目錄以專案根目錄為基準，不受執行時的工作目錄影響（已列入 .gitignore）
OUTPUT_DIR = Path(__file__).resolve().parents[1] / "output" / "104"

# 104 熱門縣市代碼對應表
POPULAR_AREAS = {
    "台北市": "6001001000",
    "新北市": "6001002000",
    "桃園市": "6001008000",
    "台中市": "6001005000",
    "台南市": "6001014000",
    "高雄市": "6001016000",
    "基隆市": "6001004000",
    "新竹市": "6001006000",
    "新竹縣": "6001007000",
    "苗栗縣": "6001009000",
    "彰化縣": "6001010000",
    "南投縣": "6001011000",
    "雲林縣": "6001012000",
    "嘉義市": "6001013000",
    "嘉義縣": "6001015000",
    "屏東縣": "6001017000",
    "宜蘭縣": "6001003000",
    "花蓮縣": "6001018000",
    "台東縣": "6001019000",
    "澎湖縣": "6001020000",
    "金門縣": "6001021000",
    "連江縣": "6001022000"
}

# 104 API 要求的請求標頭。缺少 User-Agent 或 Referer 時，104 一律回 403，兩者皆不可移除
DEFAULT_HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Referer': 'https://www.104.com.tw/jobs/search/',
    'Accept': 'application/json, text/plain, */*',
    'Accept-Language': 'zh-TW,zh;q=0.9,en-US;q=0.8,en;q=0.7',
}

# CSV 欄位名稱常數，確保表頭完整且一致。新增欄位時需同步 parse_jobs()
CSV_FIELDNAMES = [
    '職缺代碼', '職缺名稱', '公司名稱', '產業類別', '地區',
    '薪資待遇', '薪資下限', '薪資上限', '更新日期', '應徵人數',
    '工作內容', '電腦專長', '科系要求', '特色標籤', '職缺連結', '公司連結',
]

# ---------------------------------------------------------------------------
# 通用工具函式
# ---------------------------------------------------------------------------

def format_date(date_str):
    """
    將 104 回傳的日期字串 (如 20260521) 轉換為 ISO 格式 (如 2026-05-21)
    
    :param date_str: str, 原始日期字串，格式為 YYYYMMDD (例如 "20260521")
    :return: str, 清洗後的 ISO 日期字串 (例如 "2026-05-21")，若轉換失敗則返回原始字串
    """
    if not date_str:
        return ""
    try:
        return datetime.strptime(date_str, "%Y%m%d").strftime("%Y-%m-%d")
    except ValueError:
        return date_str

def _normalize_url(relative_url):
    """將 104 的 protocol-relative URL 轉為完整 HTTPS URL"""
    if relative_url.startswith('//'):
        return 'https:' + relative_url
    return relative_url

def _extract_job_id(job_url):
    """從職缺 URL 中提取 base36 job_id"""
    if '/job/' not in job_url:
        return None
    parts = job_url.split('/job/')
    return parts[1].split('?')[0].split('/')[0] if len(parts) > 1 else None

def _extract_tag_descriptions(tags):
    """從 tags 字典中提取所有 desc 欄位"""
    if not isinstance(tags, dict):
        return []
    return [v.get('desc', '') for v in tags.values() if isinstance(v, dict) and v.get('desc')]

def _extract_skill_descriptions(pc_skills):
    """從 pcSkills 列表中提取所有 description 欄位"""
    if not isinstance(pc_skills, list):
        return []
    return [s.get('description', '') for s in pc_skills if isinstance(s, dict) and s.get('description')]

def truncate_display(text, max_width):
    """依照終端顯示寬度截斷字串（CJK 字元計 2 寬度）"""
    if text is None:
        return "null"
    width = 0
    chars = []
    for ch in text:
        w = 2 if ord(ch) > 127 else 1
        if width + w > max_width:
            chars.append("..")
            break
        chars.append(ch)
        width += w
    return "".join(chars)

def resolve_area(area_input):
    """
    將使用者輸入的地區名稱解析為 (area_code, area_label)。
    支援精確比對與模糊比對，若無法辨識或未輸入則返回 (None, "全台灣")。
    
    :param area_input: str or None, 使用者輸入的地區名稱
    :return: tuple (str or None, str), (地區代碼, 顯示用地區名稱)
    """
    if not area_input:
        return None, "全台灣"
    if area_input in POPULAR_AREAS:
        return POPULAR_AREAS[area_input], area_input
    # 模糊比對
    for city, code in POPULAR_AREAS.items():
        if area_input in city or city in area_input:
            return code, city
    return None, "全台灣"

def parse_keywords(raw_input):
    """
    拆分關鍵字輸入，支援半形與全形逗號，並移除重複的關鍵字（保留首次出現的順序）
    
    :param raw_input: str, 使用者輸入的關鍵字原始字串
    :return: list, 清理且不重複的關鍵字列表
    """
    if raw_input == "":
        return [""]
    keywords = [k.strip() for k in raw_input.replace('，', ',').split(',') if k.strip()]
    return list(dict.fromkeys(keywords))

# ---------------------------------------------------------------------------
# API 請求函式
# ---------------------------------------------------------------------------

def fetch_jobs(keyword, page=1, area_code=None, ro=0):
    """
    向 104 後端 API 發送 HTTP 請求，獲取特定關鍵字的單頁職缺原始資料與分頁元數據
    
    :param keyword: str, 搜尋關鍵字 (例如 "Python")
    :param page: int, 可選參數，要抓取的目標頁碼，預設為 1
    :param area_code: str, 可選參數，104 專屬地區代碼 (例如台北市為 "6001001000")
    :param ro: int, 可選參數，職缺性質過濾器，0 代表全部 (預設)，1 代表全職，2 代表兼職/工讀
    :return: tuple (list, dict), 內含原始職缺資料列表 (list) 與分頁元數據資訊 (dict)
    """
    url = 'https://www.104.com.tw/jobs/search/api/jobs'
    
    params = {
        'page': page,
        'mode': 's',  # s 代表簡單模式
        'ro': ro,
    }
    
    if keyword:
        params['keyword'] = keyword
        
    if area_code:
        params['area'] = area_code
        
    try:
        response = requests.get(url, headers=DEFAULT_HEADERS, params=params, timeout=10)
        
        if response.status_code == 200:
            result = response.json()
            jobs_list = result.get('data', [])
            pagination = result.get('metadata', {}).get('pagination', {})
            return jobs_list, pagination
        else:
            print(f"[-] 請求失敗，HTTP 狀態碼: {response.status_code}")
            return [], {}
    except requests.exceptions.RequestException as e:
        print(f"[-] 網路請求發生異常: {e}")
        return [], {}

def fetch_job_detail(job_id):
    """
    向 104 職缺詳細資料 API 發送請求，獲取完整的職缺詳細資訊
    
    :param job_id: str, 104 職缺的 base36 代碼 (例如 "8s12x")
    :return: dict, 包含工作描述、薪資描述與薪資類型的字典，若獲取失敗則返回 None
    """
    url = f'https://www.104.com.tw/job/ajax/content/{job_id}'
    headers = DEFAULT_HEADERS.copy()
    # 詳情 API 會校驗 Referer 是否為該職缺自身的頁面，沿用搜尋頁的 Referer 會被擋
    headers['Referer'] = f'https://www.104.com.tw/job/{job_id}'
    
    try:
        response = requests.get(url, headers=headers, timeout=5)
        if response.status_code == 200:
            result = response.json()
            data = result.get('data', {})
            job_detail = data.get('jobDetail', {})
            return {
                'jobDescription': job_detail.get('jobDescription', ''),
                'salary': job_detail.get('salary', ''),
                'salaryType': job_detail.get('salaryType'),
                'salaryMin': job_detail.get('salaryMin'),
                'salaryMax': job_detail.get('salaryMax'),
            }
    except Exception as e:
        print(f"\n[!] 獲取職缺 {job_id} 詳細內容時發生異常: {e}")
    return None

# ---------------------------------------------------------------------------
# 資料解析與持久化
# ---------------------------------------------------------------------------

def parse_jobs(raw_jobs):
    """
    解析、清洗並結構化原始的 104 JSON 職缺列表資料，轉換為便於儲存與分析的字典格式
    
    :param raw_jobs: list, 包含原始 JSON 格式職缺資料的列表
    :return: list, 清洗整理後、鍵值中文化的職缺字典列表 (可直接寫入 CSV/JSON)
    """
    parsed_list = []
    if raw_jobs:
        print(f"\n📥 正在向 104 發送請求以獲取共 {len(raw_jobs)} 筆職缺的完整工作內容...")
        
    for idx, item in enumerate(raw_jobs, 1):
        if idx % 10 == 0 or idx == len(raw_jobs):
            print(f"   ⏳ 已處理 {idx}/{len(raw_jobs)} 筆職缺詳細內容...")
            
        # 處理連結
        links = item.get('link', {})
        job_url = _normalize_url(links.get('job', ''))
        company_url = _normalize_url(links.get('cust', ''))

        job_id = _extract_job_id(job_url)
        detail_data = None
        if job_id:
            # 逐筆發送詳情請求，加入延遲以控制請求頻率；不加延遲會被 104 拒絕請求
            time.sleep(random.uniform(0.1, 0.3))
            detail_data = fetch_job_detail(job_id)

        # 詳情請求失敗時，「薪資待遇」與「工作內容」保持 None，不可用搜尋 API 的 description 回填：
        # 那只是關鍵字高亮的截斷摘要，回填會讓下游 AI 收到看似完整、實則殘缺的資料
        majors = item.get('major', [])
        job_data = {
            '職缺代碼': item.get('jobNo', ''),
            '職缺名稱': item.get('jobName', ''),
            '公司名稱': item.get('custName', ''),
            '產業類別': item.get('coIndustryDesc', ''),
            '地區': (item.get('jobAddrNoDesc', '') + " " + item.get('jobAddress', '')).strip(),
            '薪資待遇': detail_data.get('salary') if detail_data else None,
            '薪資下限': item.get('salaryLow'),
            '薪資上限': item.get('salaryHigh'),
            '更新日期': format_date(item.get('appearDate', '')),
            '應徵人數': item.get('applyCnt', 0),
            '工作內容': detail_data.get('jobDescription') if detail_data else None,
            '電腦專長': ', '.join(_extract_skill_descriptions(item.get('pcSkills', []))),
            '科系要求': ', '.join(majors) if isinstance(majors, list) else str(majors),
            '特色標籤': ', '.join(_extract_tag_descriptions(item.get('tags', {}))),
            '職缺連結': job_url,
            '公司連結': company_url,
        }
        parsed_list.append(job_data)
    return parsed_list

def save_to_csv(jobs_data, filename):
    """
    將解析後的職缺字典列表寫入 CSV 檔案，使用 utf-8-sig 編碼以防 Excel 開啟中文亂碼
    
    :param jobs_data: list, 包含結構化職缺字典的列表
    :param filename: str, 要寫入的目標 CSV 檔案路徑與名稱
    :return: None
    """
    if not jobs_data:
        print("[-] 沒有職缺資料可儲存為 CSV")
        return
    
    try:
        # 使用 utf-8-sig 在檔案開頭寫入 BOM (Byte Order Mark) 解決 Excel 亂碼
        with open(filename, 'w', newline='', encoding='utf-8-sig') as f:
            writer = csv.DictWriter(f, fieldnames=CSV_FIELDNAMES)
            writer.writeheader()
            writer.writerows(jobs_data)
        print(f"[+] 成功儲存至 CSV 檔案: {os.path.abspath(filename)}")
    except IOError as e:
        print(f"[-] 儲存 CSV 檔案時出錯: {e}")

def save_to_json(jobs_data, filename):
    """
    將解析後的職缺字典列表寫入標準 JSON 檔案，以 UTF-8 編碼儲存
    
    :param jobs_data: list, 包含結構化職缺字典的列表
    :param filename: str, 要寫入的目標 JSON 檔案路徑與名稱
    :return: None
    """
    if not jobs_data:
        print("[-] 沒有職缺資料可儲存為 JSON")
        return
        
    try:
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(jobs_data, f, ensure_ascii=False, indent=4)
        print(f"[+] 成功儲存至 JSON 檔案: {os.path.abspath(filename)}")
    except IOError as e:
        print(f"[-] 儲存 JSON 檔案時出錯: {e}")

# ---------------------------------------------------------------------------
# 終端機顯示
# ---------------------------------------------------------------------------

def display_summary_table(jobs, limit=10):
    """
    在終端機輸出排版美觀的職缺摘要表格，並支援長欄位繁體中文的寬度截斷防溢出
    
    :param jobs: list, 包含結構化職缺字典的列表
    :param limit: int, 可選參數，要在終端機預覽的最大職缺筆數，預設為 10
    :return: None
    """
    if not jobs:
        print("[-] 無可供顯示的職缺")
        return
        
    display_jobs = jobs[:limit]
    print("\n" + "=" * 100)
    print(f" 🚀 撈取結果精選預覽 (顯示前 {len(display_jobs)} 筆 / 合併去重共 {len(jobs)} 筆職缺)")
    print("=" * 100)
    
    # 定義表格排版格式
    header_fmt = "{:<3} | {:<25} | {:<20} | {:<12} | {:<12} | {:<10}"
    row_fmt = "{:<3} | {:<25} | {:<20} | {:<12} | {:<12} | {:<10}"
    
    print(header_fmt.format("編號", "職缺名稱", "公司名稱", "地區", "薪資待遇", "更新日期"))
    print("-" * 100)
    
    for i, job in enumerate(display_jobs, 1):
        title = truncate_display(job['職缺名稱'], 24)
        company = truncate_display(job['公司名稱'], 18)
        area = truncate_display(job['地區'].split(' ')[0], 12)  # 只取行政區
        salary = truncate_display(job['薪資待遇'], 12)
        date = job['更新日期']
        
        print(row_fmt.format(i, title, company, area, salary, date))
        
    print("=" * 100 + "\n")

# ---------------------------------------------------------------------------
# 互動模式與核心撈取邏輯
# ---------------------------------------------------------------------------

def run_interactive():
    """
    啟動互動引導求職配置介面，讓使用者以問答方式設定關鍵字、地區、頁數與性質
    
    :return: None
    """
    print("""
===================================================
   🌟 歡迎使用 104 人力銀行職缺撈取工具 🌟
===================================================
    """)
    
    # 1. 取得關鍵字
    keyword_input = ""
    while not keyword_input.strip():
        keyword_input = input("👉 請輸入關鍵字 (若有多個關鍵字請用逗號分隔，例如: Python, React, AI): ").strip()
    
    keywords = parse_keywords(keyword_input)
        
    # 2. 選擇地區
    print("\n📍 常見地區選項:")
    print("   " + ", ".join(list(POPULAR_AREAS.keys())[:10]))
    print("   " + ", ".join(list(POPULAR_AREAS.keys())[10:]))
    area_input = input("\n👉 請輸入要求職的縣市名稱 (直接按 Enter 代表全台灣地區): ").strip()
    
    area_code, area_label = resolve_area(area_input)
    if area_input and area_code:
        print(f"[+] 已自動對應地區「{area_label}」代碼: {area_code}")
    elif area_input:
        print(f"[!] 無法識別「{area_input}」，將使用預設的【全台灣地區】進行搜尋。")

    # 3. 取得要抓取的頁數
    pages_input = input("\n👉 請輸入每個關鍵字撈取的頁數 (預設 3 頁，每頁約 30 筆職缺): ").strip()
    try:
        pages = int(pages_input) if pages_input else 3
        if pages <= 0:
            pages = 3
    except ValueError:
        print("[!] 輸入無效，將使用預設值 3 頁")
        pages = 3

    # 4. 取得職缺類型
    print("\n💼 職缺性質:")
    print("   [0] 全部職缺 (預設)")
    print("   [1] 全職工作")
    print("   [2] 兼職/工讀")
    ro_input = input("👉 請輸入性質代碼 (0/1/2): ").strip()
    try:
        ro = int(ro_input) if ro_input in ['0', '1', '2'] else 0
    except ValueError:
        ro = 0

    # 執行撈取任務
    execute_scraping(keywords, pages, area_code, area_label, ro)

def execute_scraping(keywords, pages, area_code, area_label, ro):
    """
    執行主要的 API 撈取核心邏輯，包含多關鍵字輪詢、分頁迭代、安全延遲防護、資料去重與持久化寫入
    
    :param keywords: list/str, 目標搜尋關鍵字列表 (例如 ["Python", "Django"])，若傳入單一字串將自動轉為列表
    :param pages: int, 每個關鍵字需要抓取的頁數 (每頁 30 筆)
    :param area_code: str, 104 地區專屬編碼 (若為 None 則代表搜尋全台灣)
    :param area_label: str, 用於日誌顯示的地區人類可讀標記 (例如 "台北市" 或 "全台灣")
    :param ro: int, 職缺性質過濾器，0 代表全部，1 代表全職，2 代表兼職/工讀
    :return: None
    """
    if isinstance(keywords, str):
        keywords = [keywords]
        
    all_raw_jobs = []
    seen_job_nos = set()
    
    print("\n 開始搜尋職缺:")
    print(f"   🔹 關鍵字列表: {', '.join(keywords)}")
    print(f"   🔹 地區: {area_label}")
    print(f"   🔹 每個關鍵字撈取: {pages} 頁")
    print(f"   🔹 職缺性質: {'全部' if ro == 0 else '全職' if ro == 1 else '兼職/工讀'}")
    print("-" * 50)

    for keyword in keywords:
        print(f"\n🔑 正在撈取關鍵字【{keyword}】的職缺...")
        keyword_jobs_count = 0
        keyword_added_count = 0
        
        for p in range(1, pages + 1):
            print(f"   ⏳ 正在撈取第 {p}/{pages} 頁...")
            
            # 呼叫 API 撈取資料
            jobs_list, pagination = fetch_jobs(keyword, page=p, area_code=area_code, ro=ro)
            
            if not jobs_list:
                print(f"   [!] 第 {p} 頁沒有回傳職缺，可能已達該關鍵字搜尋上限。")
                break
                
            # 去重合併資料
            added_this_page = 0
            for job in jobs_list:
                job_no = job.get('jobNo', '')
                if job_no not in seen_job_nos:
                    seen_job_nos.add(job_no)
                    all_raw_jobs.append(job)
                    added_this_page += 1
            
            keyword_jobs_count += len(jobs_list)
            keyword_added_count += added_this_page
            
            # 獲取總分頁狀態
            last_page = pagination.get('lastPage', p)
            
            print(f"   [✓] 成功取得第 {p} 頁，本頁職缺: {len(jobs_list)} 筆 (新增去重職缺: {added_this_page} 筆)")
            
            if p >= last_page:
                print(f"   [i] 已到達此關鍵字最後一頁 (共 {last_page} 頁)，停止此關鍵字撈取。")
                break
                
            # 分頁間隨機延遲 1 ~ 2 秒，控制請求頻率
            if p < pages:
                delay = round(random.uniform(1.0, 2.0), 2)
                time.sleep(delay)
                
        print(f"📝 關鍵字【{keyword}】共掃描 {keyword_jobs_count} 筆職缺 (已成功收錄 {keyword_added_count} 筆非重複職缺)")
        
        # 多關鍵字切換時進行較長的安全延遲 2 ~ 3.5 秒
        if len(keywords) > 1 and keyword != keywords[-1]:
            delay = round(random.uniform(2.0, 3.5), 2)
            print(f"💤 切換下一個關鍵字，隨機安全延遲 {delay} 秒...")
            time.sleep(delay)

    print("-" * 50)
    print(f"🎉 所有關鍵字撈取完畢！合併去重後共成功取得 {len(all_raw_jobs)} 筆職缺資料。")

    if not all_raw_jobs:
        print("[-] 未撈取到任何職缺，程式結束。")
        return

    # 執行資料整理與中文化清洗
    print("⚙️ 正在整理與清洗職缺欄位...")
    parsed_jobs = parse_jobs(all_raw_jobs)

    # 動態產生包含時間戳記的持久化儲存檔名
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    combined_kw = "_".join(keywords)
    if len(combined_kw) > 30:
        combined_kw = combined_kw[:30] + "_etc"
    clean_keyword = "".join(x for x in combined_kw if x.isalnum() or x in ('-', '_')).strip()
    if not clean_keyword:
        clean_keyword = "all"
    
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    csv_filename = OUTPUT_DIR / f"jobs_104_{clean_keyword}_{timestamp}.csv"
    json_filename = OUTPUT_DIR / f"jobs_104_{clean_keyword}_{timestamp}.json"

    # 持久化寫入硬碟
    save_to_csv(parsed_jobs, csv_filename)
    save_to_json(parsed_jobs, json_filename)

    # 印出預覽表格
    display_summary_table(parsed_jobs, limit=10)
    
    print("💡 提示:")
    print(f"   1. 您可以使用 Microsoft Excel 開啟「{csv_filename}」，內建 UTF-8 BOM 編碼確保繁體中文正常顯示。")
    print(f"   2. JSON 格式檔案「{json_filename}」適合用於進一步的資料庫匯入或網頁開發。")
    print("=" * 60)

# ---------------------------------------------------------------------------
# 程式入口
# ---------------------------------------------------------------------------

def main():
    """
    程式入口函式，負責初始化命令列參數解析器，判斷執行模式 (CLI / 互動引導模式) 
    
    :return: None
    """
    parser = argparse.ArgumentParser(description="104 人力銀行職缺撈取工具")
    parser.add_argument("-k", "--keyword", type=str, help="搜尋關鍵字 (例如: Python、AI工程師，多個關鍵字請用逗號分隔)")
    parser.add_argument("-p", "--pages", type=int, default=3, help="每個關鍵字要撈取的頁數 (預設: 3)")
    parser.add_argument("-a", "--area", type=str, help="縣市名稱 (例如: 台北市、新竹市)")
    parser.add_argument("-t", "--type", type=int, choices=[0, 1, 2], default=0, help="職缺性質 (0: 全部, 1: 全職, 2: 兼職/工讀)")
    
    args = parser.parse_args()
    
    # 若有帶關鍵字參數，則直接以 CLI 模式執行，否則進入互動引導模式
    if args.keyword is not None:
        keywords = parse_keywords(args.keyword)
        area_code, area_label = resolve_area(args.area)
        execute_scraping(keywords, args.pages, area_code, area_label, args.type)
    else:
        run_interactive()

if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n[-] 使用者取消操作，程式終止。")
        sys.exit(0)
