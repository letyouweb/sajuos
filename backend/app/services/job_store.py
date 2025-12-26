"""
Job Store - 프리미엄 리포트 진행 상태 관리
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
SSE 스트리밍을 위한 Job 상태 관리 + 이벤트 발행
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""
import asyncio
import uuid
import time
import logging
from dataclasses import dataclass, field, asdict
from typing import Dict, Any, Optional, List
from datetime import datetime
from enum import Enum

logger = logging.getLogger(__name__)


class SectionStatus(str, Enum):
    PENDING = "pending"      # 대기
    RUNNING = "running"      # 생성 중
    RETRY = "retry"          # 재시도 중
    DONE = "done"            # 완료
    ERROR = "error"          # 실패


class JobStatus(str, Enum):
    QUEUED = "queued"        # 대기열
    PROCESSING = "processing" # 처리 중
    COMPLETED = "completed"   # 완료
    FAILED = "failed"         # 실패


@dataclass
class SectionProgress:
    id: str
    title: str
    status: SectionStatus = SectionStatus.PENDING
    attempt: int = 0
    max_attempts: int = 3
    started_at: Optional[float] = None
    completed_at: Optional[float] = None
    elapsed_ms: int = 0
    char_count: int = 0
    error_message: Optional[str] = None
    stage: str = ""  # openai_wait, validating, guardrail_check

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "title": self.title,
            "status": self.status.value,
            "attempt": self.attempt,
            "max_attempts": self.max_attempts,
            "elapsed_ms": self.elapsed_ms,
            "char_count": self.char_count,
            "error_message": self.error_message,
            "stage": self.stage
        }


@dataclass
class JobProgress:
    job_id: str
    status: JobStatus = JobStatus.QUEUED
    total_sections: int = 7
    done_sections: int = 0
    percent: int = 0
    current_section_id: Optional[str] = None
    current_stage: str = ""
    sections: Dict[str, SectionProgress] = field(default_factory=dict)
    eta_sec: int = 300
    started_at: float = field(default_factory=time.time)
    completed_at: Optional[float] = None
    final_result: Optional[Dict[str, Any]] = None
    error_message: Optional[str] = None
    
    # 평균 소요시간 추적
    section_times: List[int] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "job_id": self.job_id,
            "status": self.status.value,
            "overall": {
                "total": self.total_sections,
                "done": self.done_sections,
                "percent": self.percent
            },
            "current": {
                "section_id": self.current_section_id,
                "stage": self.current_stage,
                "attempt": self.sections[self.current_section_id].attempt if self.current_section_id and self.current_section_id in self.sections else 0,
                "max_attempts": 3
            } if self.current_section_id else None,
            "sections": [s.to_dict() for s in self.sections.values()],
            "eta_sec": self.eta_sec,
            "error_message": self.error_message
        }
    
    def update_percent(self):
        """진행률 계산 - 섹션 내 미세 진행도 포함"""
        base_percent = int((self.done_sections / self.total_sections) * 100)
        
        # 현재 진행 중인 섹션의 스테이지에 따른 미세 조정
        micro_adjust = 0
        if self.current_section_id and self.current_section_id in self.sections:
            current = self.sections[self.current_section_id]
            if current.status == SectionStatus.RUNNING:
                stage_weights = {
                    "initializing": 1,
                    "openai_request": 2,
                    "openai_wait": 5,
                    "validating": 8,
                    "guardrail_check": 10,
                    "completing": 12
                }
                micro_adjust = stage_weights.get(current.stage, 3)
                # 한 섹션당 약 14% (100/7), micro는 그 안에서 비율
                micro_adjust = int(micro_adjust * 14 / 100)
        
        self.percent = min(base_percent + micro_adjust, 99)
        if self.status == JobStatus.COMPLETED:
            self.percent = 100
    
    def update_eta(self):
        """남은 시간 추정 (최근 평균 기반)"""
        if not self.section_times:
            # 기본 추정: 섹션당 40초
            remaining = self.total_sections - self.done_sections
            self.eta_sec = remaining * 40
        else:
            avg_time = sum(self.section_times) / len(self.section_times)
            remaining = self.total_sections - self.done_sections
            self.eta_sec = int(remaining * avg_time / 1000)


class JobStore:
    """메모리 기반 Job 저장소 (싱글톤)"""
    
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._jobs: Dict[str, JobProgress] = {}
            cls._instance._subscribers: Dict[str, List[asyncio.Queue]] = {}
            cls._instance._lock = asyncio.Lock()
        return cls._instance
    
    async def create_job(self, section_specs: List[tuple]) -> str:
        """새 Job 생성 - section_specs: [(id, title), ...]"""
        job_id = str(uuid.uuid4())[:8]
        
        sections = {}
        for sid, title in section_specs:
            sections[sid] = SectionProgress(id=sid, title=title)
        
        job = JobProgress(
            job_id=job_id,
            total_sections=len(section_specs),
            sections=sections
        )
        
        async with self._lock:
            self._jobs[job_id] = job
            self._subscribers[job_id] = []
        
        logger.info(f"[JobStore] Job 생성: {job_id} | Sections: {len(section_specs)}")
        return job_id
    
    async def get_job(self, job_id: str) -> Optional[JobProgress]:
        """Job 조회"""
        return self._jobs.get(job_id)
    
    async def subscribe(self, job_id: str) -> asyncio.Queue:
        """SSE 구독자 등록"""
        queue = asyncio.Queue()
        async with self._lock:
            if job_id not in self._subscribers:
                self._subscribers[job_id] = []
            self._subscribers[job_id].append(queue)
        return queue
    
    async def unsubscribe(self, job_id: str, queue: asyncio.Queue):
        """SSE 구독 해제"""
        async with self._lock:
            if job_id in self._subscribers:
                try:
                    self._subscribers[job_id].remove(queue)
                except ValueError:
                    pass
    
    async def emit_progress(self, job_id: str):
        """모든 구독자에게 진행 상태 브로드캐스트"""
        job = self._jobs.get(job_id)
        if not job:
            return
        
        job.update_percent()
        job.update_eta()
        
        event_data = job.to_dict()
        
        async with self._lock:
            queues = self._subscribers.get(job_id, [])
            for queue in queues:
                try:
                    await queue.put(event_data)
                except Exception as e:
                    logger.warning(f"[JobStore] emit 실패: {e}")
    
    # ===== Progress Update Methods =====
    
    async def start_job(self, job_id: str):
        """Job 시작"""
        job = self._jobs.get(job_id)
        if job:
            job.status = JobStatus.PROCESSING
            job.started_at = time.time()
            await self.emit_progress(job_id)
    
    async def section_start(self, job_id: str, section_id: str):
        """섹션 시작"""
        job = self._jobs.get(job_id)
        if job and section_id in job.sections:
            section = job.sections[section_id]
            section.status = SectionStatus.RUNNING
            section.started_at = time.time()
            section.attempt += 1
            section.stage = "initializing"
            
            job.current_section_id = section_id
            job.current_stage = "initializing"
            
            await self.emit_progress(job_id)
    
    async def section_stage(self, job_id: str, section_id: str, stage: str):
        """섹션 스테이지 업데이트"""
        job = self._jobs.get(job_id)
        if job and section_id in job.sections:
            section = job.sections[section_id]
            section.stage = stage
            job.current_stage = stage
            await self.emit_progress(job_id)
    
    async def section_retry(self, job_id: str, section_id: str, reason: str, wait_sec: float):
        """섹션 재시도"""
        job = self._jobs.get(job_id)
        if job and section_id in job.sections:
            section = job.sections[section_id]
            section.status = SectionStatus.RETRY
            section.stage = f"retry_{reason}"
            section.error_message = f"{reason} - {wait_sec:.1f}초 후 재시도 ({section.attempt}/{section.max_attempts})"
            await self.emit_progress(job_id)
    
    async def section_done(self, job_id: str, section_id: str, char_count: int = 0):
        """섹션 완료"""
        job = self._jobs.get(job_id)
        if job and section_id in job.sections:
            section = job.sections[section_id]
            section.status = SectionStatus.DONE
            section.completed_at = time.time()
            section.char_count = char_count
            section.stage = "completed"
            
            if section.started_at:
                elapsed = int((section.completed_at - section.started_at) * 1000)
                section.elapsed_ms = elapsed
                job.section_times.append(elapsed)
            
            job.done_sections += 1
            job.current_section_id = None
            job.current_stage = ""
            
            await self.emit_progress(job_id)
    
    async def section_error(self, job_id: str, section_id: str, error_message: str):
        """섹션 에러"""
        job = self._jobs.get(job_id)
        if job and section_id in job.sections:
            section = job.sections[section_id]
            section.status = SectionStatus.ERROR
            section.error_message = error_message[:200]
            section.stage = "error"
            
            # 에러 시에도 done으로 카운트 (skip)
            job.done_sections += 1
            
            await self.emit_progress(job_id)
    
    async def complete_job(self, job_id: str, result: Dict[str, Any]):
        """Job 완료"""
        job = self._jobs.get(job_id)
        if job:
            job.status = JobStatus.COMPLETED
            job.completed_at = time.time()
            job.percent = 100
            job.final_result = result
            job.current_section_id = None
            job.current_stage = "completed"
            await self.emit_progress(job_id)
            
            # 완료 이벤트 전송 후 구독자 정리
            await asyncio.sleep(0.5)
            async with self._lock:
                # 모든 큐에 종료 신호
                for queue in self._subscribers.get(job_id, []):
                    try:
                        await queue.put({"type": "complete", "job_id": job_id})
                    except:
                        pass
    
    async def fail_job(self, job_id: str, error_message: str):
        """Job 실패"""
        job = self._jobs.get(job_id)
        if job:
            job.status = JobStatus.FAILED
            job.error_message = error_message[:500]
            job.current_stage = "failed"
            await self.emit_progress(job_id)
    
    async def cleanup_old_jobs(self, max_age_sec: int = 3600):
        """오래된 Job 정리 (1시간 이상)"""
        now = time.time()
        async with self._lock:
            to_delete = []
            for job_id, job in self._jobs.items():
                age = now - job.started_at
                if age > max_age_sec and job.status in [JobStatus.COMPLETED, JobStatus.FAILED]:
                    to_delete.append(job_id)
            
            for job_id in to_delete:
                del self._jobs[job_id]
                if job_id in self._subscribers:
                    del self._subscribers[job_id]
            
            if to_delete:
                logger.info(f"[JobStore] 정리된 Job: {len(to_delete)}개")


# 싱글톤 인스턴스
job_store = JobStore()
