"""
向 104 人力銀行抓取職缺：依關鍵字與縣市搜尋、以職缺代碼去重，再逐筆取職缺頁面的完整內容，
整理成職缺欄位契約的中文欄位。

抓取中可以停止，並以回呼回報進度；抓到的職缺只回傳給呼叫端，不寫檔也不寫入資料庫。
"""

import random
import threading
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Any

import requests

# 104 的 22 個縣市與地區代碼；抓取頁的縣市選單依這裡的順序列出
AREAS = {
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

def parse_keywords(raw_input):
    """
    拆分關鍵字輸入，支援半形與全形逗號，並移除重複的關鍵字（保留首次出現的順序）
    
    :param raw_input: str, 使用者輸入的關鍵字原始字串
    :return: list, 清理且不重複的關鍵字列表；只有空白與逗號時為空清單
    """
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
# 資料解析
# ---------------------------------------------------------------------------

def _job_url(item):
    """取出原始職缺的完整職缺連結"""
    return _normalize_url(item.get('link', {}).get('job', ''))

def parse_job(item, detail):
    """
    把一筆 104 搜尋結果與它的職缺頁面內容整理成職缺欄位契約的欄位

    :param item: dict, 搜尋 API 回傳的單筆原始職缺
    :param detail: dict or None, fetch_job_detail 的結果；取不到時為 None
    :return: dict, 鍵依職缺欄位契約的順序
    """
    links = item.get('link', {})
    # 取不到職缺頁面內容時，「薪資待遇」與「工作內容」保持 None，不可用搜尋 API 的 description 回填：
    # 那只是關鍵字高亮的截斷摘要，回填會讓下游 AI 收到看似完整、實則殘缺的資料
    majors = item.get('major', [])
    return {
        '職缺代碼': item.get('jobNo', ''),
        '職缺名稱': item.get('jobName', ''),
        '公司名稱': item.get('custName', ''),
        '產業類別': item.get('coIndustryDesc', ''),
        '地區': (item.get('jobAddrNoDesc', '') + " " + item.get('jobAddress', '')).strip(),
        '薪資待遇': detail.get('salary') if detail else None,
        '薪資下限': item.get('salaryLow'),
        '薪資上限': item.get('salaryHigh'),
        '更新日期': format_date(item.get('appearDate', '')),
        '應徵人數': item.get('applyCnt', 0),
        '工作內容': detail.get('jobDescription') if detail else None,
        '電腦專長': ', '.join(_extract_skill_descriptions(item.get('pcSkills', []))),
        '科系要求': ', '.join(majors) if isinstance(majors, list) else str(majors),
        '特色標籤': ', '.join(_extract_tag_descriptions(item.get('tags', {}))),
        '職缺連結': _job_url(item),
        '公司連結': _normalize_url(links.get('cust', '')),
    }

# ---------------------------------------------------------------------------
# 抓取
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class SearchProgress:
    """正要搜尋某個關鍵字的第幾頁"""

    keyword: str
    page: int
    pages: int
    found: int  # 目前已找到幾筆不重複的職缺


@dataclass(frozen=True)
class DetailProgress:
    """正要取第幾筆職缺的頁面內容，index 從 1 開始"""

    index: int
    total: int


Progress = SearchProgress | DetailProgress


@dataclass
class ScrapeResult:
    """一次抓取的結果"""

    jobs: list[dict[str, Any]]  # 取完頁面內容的職缺，依職缺欄位契約
    found: int  # 搜尋到幾筆不重複的職缺，包含停止時還沒取內容的
    stopped: bool
    finished_at: datetime  # 抓完或停止的時間，精確到秒


def _sleep(seconds: float, stop: threading.Event) -> None:
    """請求之間的延遲；要求停止時立刻結束等待"""
    stop.wait(seconds)


def _search(
    keywords: list[str],
    pages: int,
    area_code: str | None,
    job_type: int,
    stop: threading.Event,
    on_progress: Callable[[Progress], None],
) -> list[dict[str, Any]]:
    """
    逐一關鍵字、逐頁搜尋，以職缺代碼去重後累積成原始職缺清單

    :return: list[dict], 不重複的原始職缺，保留第一次出現的那筆
    """
    found: list[dict[str, Any]] = []
    seen: set[Any] = set()
    for k, keyword in enumerate(keywords):
        if k > 0:
            # 切換關鍵字時延遲較久
            _sleep(random.uniform(2.0, 3.5), stop)
        for page in range(1, pages + 1):
            if page > 1:
                _sleep(random.uniform(1.0, 2.0), stop)
            if stop.is_set():
                return found
            on_progress(SearchProgress(keyword, page, pages, len(found)))
            jobs_list, pagination = fetch_jobs(keyword, page=page, area_code=area_code, ro=job_type)
            # 空頁（含請求失敗）代表這個關鍵字沒有更多結果
            if not jobs_list:
                break
            for job in jobs_list:
                job_no = job.get('jobNo', '')
                if job_no not in seen:
                    seen.add(job_no)
                    found.append(job)
            if page >= pagination.get('lastPage', page):
                break
    return found


def _fetch_details(
    raw_jobs: list[dict[str, Any]], stop: threading.Event, on_progress: Callable[[Progress], None]
) -> list[dict[str, Any]]:
    """
    逐筆取職缺頁面的內容並整理欄位；要求停止後不再發出請求，只回傳已取完的職缺

    :return: list[dict], 依職缺欄位契約整理好的職缺
    """
    jobs = []
    for index, item in enumerate(raw_jobs, 1):
        if stop.is_set():
            break
        on_progress(DetailProgress(index, len(raw_jobs)))
        detail = None
        job_id = _extract_job_id(_job_url(item))
        if job_id:
            # 取職缺頁面前不加延遲會被 104 拒絕
            _sleep(random.uniform(0.1, 0.3), stop)
            if stop.is_set():
                break
            detail = fetch_job_detail(job_id)
        jobs.append(parse_job(item, detail))
    return jobs


def scrape(
    keywords: list[str],
    pages: int,
    area_code: str | None,
    job_type: int,
    *,
    stop: threading.Event,
    on_progress: Callable[[Progress], None],
) -> ScrapeResult:
    """
    抓取 104 職缺：所有關鍵字都搜完、去重之後，才逐筆取職缺頁面的內容

    stop 被設定後不再發出新的請求，已送出的請求照常完成；還沒取內容的職缺不列入結果。

    :param keywords: list[str], 去重後的關鍵字
    :param pages: int, 每個關鍵字最多抓幾頁
    :param area_code: str or None, 104 的地區代碼；None 代表全台灣
    :param job_type: int, 職缺性質：0 全部、1 全職、2 兼職／工讀
    :param stop: threading.Event, 要求停止的旗標
    :param on_progress: callable, 每個請求送出前以 SearchProgress 或 DetailProgress 回報進度
    :return: ScrapeResult
    """
    raw_jobs = _search(keywords, pages, area_code, job_type, stop, on_progress)
    jobs = [] if stop.is_set() else _fetch_details(raw_jobs, stop, on_progress)
    return ScrapeResult(
        jobs=jobs,
        found=len(raw_jobs),
        stopped=stop.is_set(),
        finished_at=datetime.now().replace(microsecond=0),
    )
