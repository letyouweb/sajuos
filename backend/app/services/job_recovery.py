"""
Job Recovery - 컨테이너 재시작 시 미완료 Job 복구
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
99,000원 유료 서비스에서 Job 손실은 치명적
→ 서버 시작 시 DB에서 미완료 상태 Job을 찾아 자동 재시작
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""
import asyncio
import logging
from typing import Any
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)


async def recover_interrupted_jobs(rulestore: Any = None) -> int:
    """
    서버 시작 시 미완료 Job 복구
    
    복구 대상:
    1. status = 'generating' (진행 중이었던 것)
    2. status = 'queued' 이면서 생성된 지 1시간 이내
    
    Returns:
        복구 시작한 Job 수
    """
    try:
        from app.services.supabase_service import supabase_service
        from app.services.report_worker import report_worker
    except ImportError as e:
        logger.warning(f"[Recovery] Import 실패: {e}")
        return 0
    
    if not supabase_service.is_available():
        logger.info("[Recovery] Supabase 미설정 - 복구 스킵")
        return 0
    
    recovered_count = 0
    
    try:
        # 1. 진행 중이었던 Job (generating)
        generating_jobs = await supabase_service.get_jobs_by_status("generating")
        
        for job in generating_jobs:
            job_id = job["id"]
            logger.info(f"[Recovery] 🔄 미완료 Job 발견: {job_id} (status=generating)")
            
            asyncio.create_task(
                report_worker.run_job(job_id, rulestore)
            )
            recovered_count += 1
        
        # 2. 대기 중이었던 Job (queued, 1시간 이내)
        queued_jobs = await supabase_service.get_jobs_by_status("queued")
        cutoff_time = datetime.utcnow() - timedelta(hours=1)
        
        for job in queued_jobs:
            job_id = job["id"]
            created_at_str = job.get("created_at", "")
            
            try:
                created_at = datetime.fromisoformat(created_at_str.replace("Z", "+00:00"))
                created_at = created_at.replace(tzinfo=None)
                
                if created_at > cutoff_time:
                    logger.info(f"[Recovery] 🔄 대기 중 Job 발견: {job_id} (status=queued)")
                    
                    asyncio.create_task(
                        report_worker.run_job(job_id, rulestore)
                    )
                    recovered_count += 1
                else:
                    # 오래된 queued는 failed로 마킹
                    logger.warning(f"[Recovery] ⚠️ 오래된 Job: {job_id} → failed")
                    await supabase_service.fail_job(
                        job_id, 
                        "서버 재시작 시 타임아웃 (1시간 초과). 재신청 필요."
                    )
            except Exception as e:
                logger.warning(f"[Recovery] 날짜 파싱 실패: {job_id} | {e}")
        
        if recovered_count > 0:
            logger.info(f"[Recovery] ✅ 총 {recovered_count}개 Job 복구 시작")
        else:
            logger.info("[Recovery] ✅ 복구할 미완료 Job 없음")
        
        return recovered_count
        
    except Exception as e:
        logger.error(f"[Recovery] ❌ 복구 실패: {e}")
        return 0
