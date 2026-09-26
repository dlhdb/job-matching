"""
網頁上的作業：抓取、評分、試跑這類要跑一段時間的工作，在伺服器的背景執行緒跑。

頁面重新整理或關掉都不影響作業，重新打開時向各功能的 API 取回進度。同一時間只跑一個作業。
"""

import threading
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any


@dataclass
class Job:
    """一個作業：種類、停止旗標與目前的進度"""

    kind: str  # 給人看的名稱，例如「抓取」
    stop: threading.Event = field(default_factory=threading.Event)
    progress: Any = None  # 由作業自己更新，各功能決定內容

    @property
    def stopping(self) -> bool:
        """是否已經要求停止"""
        return self.stop.is_set()


class JobBusy(Exception):
    """已有作業在跑，不能開始新的作業"""

    def __init__(self, running: str):
        super().__init__(f"同一時間只能跑一個作業，目前正在{running}")
        self.running = running


class JobRunner:
    """同一時間只跑一個作業的執行器"""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._current: Job | None = None

    def start(self, kind: str, target: Callable[[Job], None]) -> Job:
        """
        在背景執行緒開始一個作業

        target 結束前要自己把結果交給所屬的功能，執行器在 target 結束後才釋放：
        查詢的一方才不會看到「作業已結束、結果卻還沒出現」的空檔。

        :param kind: str, 作業的種類
        :param target: callable, target(job)；以 job.stop 判斷是否停止，並更新 job.progress
        :return: Job, 剛開始的作業
        :raises JobBusy: 已有作業在跑
        """
        with self._lock:
            if self._current is not None:
                raise JobBusy(self._current.kind)
            job = Job(kind)
            self._current = job
        # daemon：web app 關閉時不等作業跑完
        threading.Thread(target=self._run, args=(job, target), name=f"job-{kind}", daemon=True).start()
        return job

    def _run(self, job: Job, target: Callable[[Job], None]) -> None:
        try:
            target(job)
        finally:
            with self._lock:
                self._current = None

    def current(self) -> Job | None:
        """
        目前在跑的作業

        :return: Job or None, 沒有作業在跑時為 None
        """
        with self._lock:
            return self._current

    def stop(self, kind: str) -> bool:
        """
        要求停止某種作業；作業在下一次檢查停止旗標時結束

        :param kind: str, 要停止的作業種類
        :return: bool, 有這種作業在跑時為 True
        """
        job = self.current()
        if job is None or job.kind != kind:
            return False
        job.stop.set()
        return True
