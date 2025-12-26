"""
Report Worker v3 - 백그라운드 Job 처리
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
P1 요구사항:
- Supabase 영속화 (재시작 복구 가능)
- 섹션별 저장 (중단 시 이어서)
- 완료 시 이메일 발송
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""
import asyncio
import logging
import time
from typing import Dict, Any, Optional, List
from datetime import datetime

from app.services.supabase_service import supabase_service, SECTION_SPECS
from app.services.email_sender import email_sender
from app.services.quality_schema import (
    validate_section_content,
    get_quality_feedback_prompt,
    clean_banned_from_text
)

logger = logging.getLogger(__name__)


class ReportWorker:
    """백그라운드 리포트 생성 워커"""
    
    # 진행 중인 Job 추적 (중복 실행 방지)
    _running_jobs: set = set()
    
    async def run_job(self, job_id: str, rulestore: Any = None) -> None:
        """
        Job 실행 (BackgroundTasks에서 호출)
        """
        # 중복 실행 방지
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
            await supabase_service.fail_job(job_id, str(e)[:500])
            
            # 실패 이메일 발송
            job = await supabase_service.get_job(job_id)
            if job:
                await self._send_failure_email(job, str(e))
        
        finally:
            self._running_jobs.discard(job_id)
    
    async def _execute_job(self, job_id: str, rulestore: Any = None) -> None:
        """실제 Job 실행 로직"""
        
        # 1. Job 정보 조회
        job = await supabase_service.get_job(job_id)
        if not job:
            raise ValueError(f"Job 없음: {job_id}")
        
        input_data = job.get("input_data", {})
        target_year = job.get("target_year", 2026)
        email = job["email"]
        name = job.get("name", "고객")
        
        # 2. 상태를 generating으로 업데이트
        await supabase_service.update_progress(job_id, 5, "준비 중", "generating")
        
        # 3. 사주 데이터 준비
        saju_data = self._prepare_saju_data(input_data)
        
        # 4. Feature Tags 생성
        feature_tags = self._build_feature_tags(saju_data)
        
        # 5. RuleCards 선택
        rulecards = self._select_rulecards(rulestore, feature_tags)
        
        # 6. 설문 컨텍스트
        survey_context = self._build_survey_context(input_data.get("survey_data"))
        
        # 7. 섹션별 생성
        sections_result = {}
        total_sections = len(SECTION_SPECS)
        
        for idx, spec in enumerate(SECTION_SPECS):
            section_id = spec["id"]
            section_title = spec["title"]
            
            # 이미 완료된 섹션 스킵
            existing_sections = await supabase_service.get_sections(job_id)
            completed_ids = {s["section_id"] for s in existing_sections if s["status"] == "completed"}
            
            if section_id in completed_ids:
                logger.info(f"[Worker] 섹션 스킵 (이미 완료): {section_id}")
                continue
            
            # 섹션 상태 업데이트
            progress = int((idx / total_sections) * 90) + 10
            await supabase_service.update_progress(job_id, progress, f"{section_title} 생성 중")
            await supabase_service.update_section_status(job_id, section_id, "generating")
            
            try:
                # 섹션 생성 (최대 3회 재시도)
                section_start = time.time()
                section_content = await self._generate_section_with_quality(
                    section_id=section_id,
                    saju_data=saju_data,
                    rulecards=rulecards,
                    feature_tags=feature_tags,
                    target_year=target_year,
                    survey_context=survey_context,
                    user_question=input_data.get("question", "") + ("\n\n" + survey_context if survey_context else ""),
                    max_retries=3
                )
                section_elapsed = int((time.time() - section_start) * 1000)
                
                # 섹션 저장
                await supabase_service.save_section(
                    job_id=job_id,
                    section_id=section_id,
                    section_title=section_title,
                    section_order=spec["order"],
                    content_json=section_content,
                    char_count=len(str(section_content)),
                    elapsed_ms=section_elapsed
                )
                
                sections_result[section_id] = section_content
                logger.info(f"[Worker] 섹션 완료: {section_id} ({section_elapsed}ms)")
                
            except Exception as e:
                logger.error(f"[Worker] 섹션 실패: {section_id} | {e}")
                await supabase_service.update_section_status(job_id, section_id, "failed", str(e))
                # 실패해도 계속 진행 (다른 섹션은 생성)
        
        # 8. 전체 결과 조합
        result_json = self._build_final_result(sections_result, name, target_year)
        markdown = self._build_markdown(result_json)
        
        total_elapsed = int((time.time() - float(job.get("created_at", time.time()))) * 1000)
        
        # 9. Job 완료 처리
        await supabase_service.complete_job(
            job_id=job_id,
            result_json=result_json,
            markdown=markdown,
            generation_time_ms=total_elapsed
        )
        
        # 10. 완료 이메일 발송
        await self._send_completion_email(job, job_id)
    
    async def _generate_section_with_quality(
        self,
        section_id: str,
        saju_data: Dict,
        rulecards: List,
        feature_tags: List,
        target_year: int,
        survey_context: str,
        user_question: str,
        max_retries: int = 3
    ) -> Dict[str, Any]:
        """섹션 생성 + 품질 검증 + 자동 재시도"""
        
        from app.services.report_builder import premium_report_builder
        
        last_validation = None
        
        for attempt in range(max_retries):
            # 재시도 시 품질 피드백 프롬프트 추가
            quality_feedback = ""
            if last_validation and not last_validation["valid"]:
                quality_feedback = get_quality_feedback_prompt(last_validation)
            
            try:
                # 섹션 생성 (regenerate_single_section 호출)
                result = await premium_report_builder.regenerate_single_section(
                    section_id=section_id,
                    saju_data=saju_data,
                    rulecards=rulecards,
                    feature_tags=feature_tags,
                    target_year=target_year,
                    user_question=user_question + quality_feedback,
                    survey_data=None  # survey_context는 이미 user_question에 포함
                )
                
                content = result.get("content", {})
                
                # 품질 검증
                validation = validate_section_content(content)
                
                if validation["valid"]:
                    # 금지어 클리닝 후 반환
                    cleaned_content = self._clean_content(content)
                    return cleaned_content
                
                # 검증 실패 - 재시도
                last_validation = validation
                logger.warning(
                    f"[Worker] 섹션 품질 불합격 (시도 {attempt+1}/{max_retries}): "
                    f"{section_id} | 점수: {validation['score']}"
                )
                
            except Exception as e:
                logger.error(f"[Worker] 섹션 생성 에러 (시도 {attempt+1}): {e}")
                if attempt == max_retries - 1:
                    raise
        
        # 최대 재시도 후에도 실패 - 마지막 결과 반환 (불완전하더라도)
        logger.warning(f"[Worker] 섹션 품질 최대 재시도 초과: {section_id}")
        return content
    
    def _clean_content(self, content: Dict) -> Dict:
        """콘텐츠 클리닝 (금지어 제거)"""
        if isinstance(content, dict):
            return {k: self._clean_content(v) for k, v in content.items()}
        elif isinstance(content, list):
            return [self._clean_content(item) for item in content]
        elif isinstance(content, str):
            return clean_banned_from_text(content)
        return content
    
    def _prepare_saju_data(self, input_data: Dict) -> Dict:
        """사주 데이터 준비"""
        if "saju_result" in input_data and input_data["saju_result"]:
            return input_data["saju_result"]
        
        return {
            "year_pillar": input_data.get("year_pillar"),
            "month_pillar": input_data.get("month_pillar"),
            "day_pillar": input_data.get("day_pillar"),
            "hour_pillar": input_data.get("hour_pillar"),
        }
    
    def _build_feature_tags(self, saju_data: Dict) -> List[str]:
        """Feature Tags 생성"""
        try:
            from app.services.feature_tags_no_time import build_feature_tags_no_time_from_pillars
            
            pillars = {
                "year": saju_data.get("year_pillar"),
                "month": saju_data.get("month_pillar"),
                "day": saju_data.get("day_pillar"),
                "hour": saju_data.get("hour_pillar"),
            }
            
            return build_feature_tags_no_time_from_pillars(pillars)
        except Exception as e:
            logger.warning(f"[Worker] Feature Tags 생성 실패: {e}")
            return []
    
    def _select_rulecards(self, rulestore: Any, feature_tags: List) -> List:
        """RuleCards 선택"""
        if not rulestore:
            return []
        
        try:
            from app.services.preset_type2 import BUSINESS_OWNER_PRESET_V2
            from app.services.focus_boost import boost_preset_focus
            from app.services.rulecard_selector import select_cards_for_preset
            
            preset = boost_preset_focus(BUSINESS_OWNER_PRESET_V2, feature_tags)
            result = select_cards_for_preset(rulestore, preset, feature_tags)
            
            return result.get("allCards", [])
        except Exception as e:
            logger.warning(f"[Worker] RuleCards 선택 실패: {e}")
            return []
    
    def _build_survey_context(self, survey_data: Optional[Dict]) -> str:
        """설문 컨텍스트 생성"""
        if not survey_data:
            return ""
        
        try:
            from app.services.survey_intake import SurveyResponse, survey_to_prompt_context
            survey = SurveyResponse.from_dict(survey_data)
            return survey_to_prompt_context(survey)
        except Exception as e:
            logger.warning(f"[Worker] 설문 컨텍스트 생성 실패: {e}")
            return ""
    
    def _build_final_result(
        self, 
        sections: Dict[str, Any], 
        name: str, 
        target_year: int
    ) -> Dict[str, Any]:
        """최종 결과 조합"""
        return {
            "meta": {
                "name": name,
                "target_year": target_year,
                "generated_at": datetime.utcnow().isoformat(),
                "version": "3.0.0"
            },
            "sections": sections,
            "summary": f"{name}님의 {target_year}년 프리미엄 비즈니스 컨설팅 보고서"
        }
    
    def _build_markdown(self, result: Dict) -> str:
        """Markdown 생성"""
        lines = [
            f"# {result.get('summary', '프리미엄 비즈니스 보고서')}",
            "",
            f"생성일: {result['meta'].get('generated_at', '')}",
            "",
        ]
        
        for section_id, content in result.get("sections", {}).items():
            if isinstance(content, dict):
                title = content.get("title", section_id)
                summary = content.get("summary", "")
                lines.append(f"## {title}")
                lines.append("")
                lines.append(summary)
                lines.append("")
        
        return "\n".join(lines)
    
    async def _send_completion_email(self, job: Dict, job_id: str) -> None:
        """완료 이메일 발송"""
        try:
            from app.config import get_settings
            settings = get_settings()
            
            await email_sender.send_report_complete(
                to_email=job["email"],
                name=job.get("name", "고객"),
                report_id=job_id,
                access_token=job.get("access_token", ""),
                target_year=job.get("target_year", 2026)
            )
        except Exception as e:
            logger.warning(f"[Worker] 완료 이메일 발송 실패: {e}")
    
    async def _send_failure_email(self, job: Dict, error: str) -> None:
        """실패 이메일 발송"""
        try:
            await email_sender.send_report_failed(
                to_email=job["email"],
                name=job.get("name", "고객"),
                report_id=job["id"],
                error_message=error
            )
        except Exception as e:
            logger.warning(f"[Worker] 실패 이메일 발송 실패: {e}")


# 싱글톤 인스턴스
report_worker = ReportWorker()
