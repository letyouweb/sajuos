"""
Report Worker v8 - 실제 DB 스키마에 맞춤
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
DB 컬럼:
- user_email (not email)
- input_json (not input_data)
- result_json
- markdown
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""
import asyncio
import logging
import time
from typing import Dict, Any, Optional, List

from app.services.supabase_service import supabase_service, SECTION_SPECS

logger = logging.getLogger(__name__)


class ReportWorker:
    """백그라운드 리포트 생성 워커"""
    
    _running_jobs: set = set()
    
    async def run_job(self, job_id: str, rulestore: Any = None) -> None:
        """Job 실행"""
        if job_id in self._running_jobs:
            logger.warning(f"[Worker] 이미 실행 중: {job_id}")
            return
        
        self._running_jobs.add(job_id)
        start_time = time.time()
        
        try:
            await self._execute_job(job_id, rulestore)
            elapsed = int((time.time() - start_time) * 1000)
            logger.info(f"[Worker] ✅ Job 완료: {job_id} ({elapsed}ms)")
            
        except Exception as e:
            logger.error(f"[Worker] ❌ Job 실패: {job_id} | {e}")
            try:
                await supabase_service.fail_job(job_id, str(e)[:500])
            except:
                pass
            
            # 실패 이메일
            try:
                job = await supabase_service.get_job(job_id)
                if job:
                    await self._send_failure_email(job, str(e))
            except Exception as email_err:
                logger.warning(f"[Worker] 실패 이메일 발송 실패: {email_err}")
        
        finally:
            self._running_jobs.discard(job_id)
    
    async def _execute_job(self, job_id: str, rulestore: Any = None) -> None:
        """실제 Job 실행"""
        
        # 1. Job 조회
        job = await supabase_service.get_job(job_id)
        if not job:
            raise ValueError(f"Job 없음: {job_id}")
        
        # 🔥 실제 DB 컬럼명 사용
        email = job.get("user_email", "")
        input_json = job.get("input_json") or {}
        
        # input_json에서 데이터 추출
        name = input_json.get("name", "고객")
        target_year = input_json.get("target_year", 2026)
        saju_result = input_json.get("saju_result", {})
        survey_data = input_json.get("survey_data", {})
        question = input_json.get("question", "")
        
        # 2. 상태 업데이트
        await supabase_service.update_progress(job_id, 5, "running")
        
        # 3. 사주 데이터 준비
        saju_data = self._prepare_saju_data(input_json)
        
        # 4. Feature Tags
        feature_tags = self._build_feature_tags(saju_data)
        
        # 5. RuleCards
        rulecards = self._select_rulecards(rulestore, feature_tags)
        
        # 6. 섹션별 생성
        sections_result = {}
        total_sections = len(SECTION_SPECS)
        
        for idx, spec in enumerate(SECTION_SPECS):
            section_id = spec["id"]
            
            progress = int((idx / total_sections) * 90) + 10
            await supabase_service.update_progress(job_id, progress, "running")
            
            try:
                section_content = await self._generate_section(
                    section_id=section_id,
                    saju_data=saju_data,
                    rulecards=rulecards,
                    feature_tags=feature_tags,
                    target_year=target_year,
                    question=question
                )
                
                await supabase_service.save_section(
                    job_id=job_id,
                    section_id=section_id,
                    content_json=section_content
                )
                
                sections_result[section_id] = section_content
                logger.info(f"[Worker] 섹션 완료: {section_id}")
                
            except Exception as e:
                logger.error(f"[Worker] 섹션 실패: {section_id} | {e}")
        
        # 7. 결과 조합
        result_json = {
            "name": name,
            "target_year": target_year,
            "sections": sections_result,
            "generated_at": time.strftime("%Y-%m-%d %H:%M:%S")
        }
        
        markdown = self._build_markdown(result_json)
        
        # 8. 완료
        await supabase_service.complete_job(job_id, result_json, markdown)
        
        # 9. 완료 이메일
        try:
            await self._send_completion_email(email, name, job_id)
        except Exception as e:
            logger.warning(f"[Worker] 완료 이메일 실패: {e}")
    
    async def _generate_section(
        self,
        section_id: str,
        saju_data: Dict,
        rulecards: List,
        feature_tags: List,
        target_year: int,
        question: str
    ) -> Dict[str, Any]:
        """섹션 생성 (OpenAI 호출)"""
        
        try:
            from app.services.report_builder import premium_report_builder
            
            result = await premium_report_builder.regenerate_single_section(
                section_id=section_id,
                saju_data=saju_data,
                rulecards=rulecards,
                feature_tags=feature_tags,
                target_year=target_year,
                user_question=question
            )
            
            return result.get("content", {"summary": f"{section_id} 섹션 생성 완료"})
            
        except Exception as e:
            logger.error(f"섹션 생성 오류: {section_id} | {e}")
            return {"summary": f"{section_id} 생성 실패", "error": str(e)[:200]}
    
    def _prepare_saju_data(self, input_json: Dict) -> Dict:
        """사주 데이터 준비"""
        saju_result = input_json.get("saju_result", {})
        
        return {
            "year_pillar": input_json.get("year_pillar") or saju_result.get("year_pillar", ""),
            "month_pillar": input_json.get("month_pillar") or saju_result.get("month_pillar", ""),
            "day_pillar": input_json.get("day_pillar") or saju_result.get("day_pillar", ""),
            "hour_pillar": input_json.get("hour_pillar") or saju_result.get("hour_pillar", ""),
            "day_master": saju_result.get("day_master", ""),
            "elements": saju_result.get("elements", {}),
        }
    
    def _build_feature_tags(self, saju_data: Dict) -> List[str]:
        """Feature Tags 생성"""
        tags = []
        
        for pillar_key in ["year_pillar", "month_pillar", "day_pillar", "hour_pillar"]:
            pillar = saju_data.get(pillar_key, "")
            if pillar and len(pillar) >= 2:
                tags.append(f"천간:{pillar[0]}")
                tags.append(f"지지:{pillar[1]}")
        
        if saju_data.get("day_master"):
            tags.append(f"일간:{saju_data['day_master']}")
        
        return tags
    
    def _select_rulecards(self, rulestore: Any, feature_tags: List[str]) -> List:
        """RuleCards 선택"""
        if not rulestore:
            return []
        
        try:
            from app.services.rulecard_selector import select_rulecards
            return select_rulecards(rulestore, feature_tags, max_cards=50)
        except:
            return []
    
    def _build_markdown(self, result_json: Dict) -> str:
        """마크다운 생성"""
        lines = []
        lines.append(f"# {result_json.get('name', '고객')}님의 {result_json.get('target_year', 2026)}년 비즈니스 운세 리포트\n")
        
        sections = result_json.get("sections", {})
        for spec in SECTION_SPECS:
            section = sections.get(spec["id"], {})
            lines.append(f"## {spec['title']}\n")
            lines.append(section.get("summary", "내용 없음"))
            lines.append("\n")
        
        return "\n".join(lines)
    
    async def _send_completion_email(self, email: str, name: str, job_id: str):
        """완료 이메일"""
        if not email:
            return
        
        try:
            from app.services.email_sender import email_sender
            await email_sender.send_completion(
                to_email=email,
                name=name,
                job_id=job_id
            )
        except Exception as e:
            logger.warning(f"이메일 발송 실패: {e}")
    
    async def _send_failure_email(self, job: Dict, error: str):
        """실패 이메일"""
        email = job.get("user_email", "")
        if not email:
            return
        
        try:
            from app.services.email_sender import email_sender
            input_json = job.get("input_json") or {}
            name = input_json.get("name", "고객")
            await email_sender.send_failure(
                to_email=email,
                name=name,
                error=error[:200]
            )
        except Exception as e:
            logger.warning(f"실패 이메일 발송 실패: {e}")


# 싱글톤
report_worker = ReportWorker()
