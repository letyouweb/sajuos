"""
Report Worker v9 - 가드레일 실패 시 Job failed 처리
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
P0 요구사항:
1) 가드레일 실패 → Job failed (completed 아님!)
2) 자동 리라이트 1회 후 재검사
3) 재검사도 실패 → Job failed로 종료
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
            success, error_msg = await self._execute_job(job_id, rulestore)
            elapsed = int((time.time() - start_time) * 1000)
            
            if success:
                logger.info(f"[Worker] ✅ Job 완료: {job_id} ({elapsed}ms)")
            else:
                logger.error(f"[Worker] ❌ Job 실패 (가드레일): {job_id} | {error_msg}")
            
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
    
    async def _execute_job(self, job_id: str, rulestore: Any = None) -> tuple[bool, str]:
        """
        실제 Job 실행
        Returns: (success: bool, error_msg: str)
        """
        # 1. Job 조회
        job = await supabase_service.get_job(job_id)
        if not job:
            raise ValueError(f"Job 없음: {job_id}")
        
        email = job.get("user_email", "")
        input_json = job.get("input_json") or {}
        
        name = input_json.get("name", "고객")
        target_year = input_json.get("target_year", 2026)
        question = input_json.get("question", "")
        
        # 2. 상태 업데이트
        await supabase_service.update_progress(job_id, 5, "running")
        
        # 3. 데이터 준비
        saju_data = self._prepare_saju_data(input_json)
        feature_tags = self._build_feature_tags(saju_data)
        rulecards = self._select_rulecards(rulestore, feature_tags)
        
        # 4. 섹션별 생성 + 가드레일 검사
        sections_result = {}
        failed_sections = []  # 가드레일 실패한 섹션들
        total_sections = len(SECTION_SPECS)
        
        for idx, spec in enumerate(SECTION_SPECS):
            section_id = spec["id"]
            
            progress = int((idx / total_sections) * 90) + 10
            await supabase_service.update_progress(job_id, progress, "running")
            
            try:
                # 🔥 P0-1: 가드레일 결과 포함하여 섹션 생성
                section_result = await self._generate_section_with_guardrail(
                    section_id=section_id,
                    saju_data=saju_data,
                    rulecards=rulecards,
                    feature_tags=feature_tags,
                    target_year=target_year,
                    question=question
                )
                
                content = section_result.get("content", {})
                guardrail_errors = section_result.get("guardrail_errors", [])
                
                # 🔥 가드레일 실패 체크
                if guardrail_errors:
                    failed_sections.append({
                        "section_id": section_id,
                        "errors": guardrail_errors
                    })
                    logger.warning(f"[Worker] 섹션 가드레일 실패: {section_id} | {guardrail_errors}")
                
                # 섹션 저장 (실패해도 일단 저장)
                await supabase_service.save_section(
                    job_id=job_id,
                    section_id=section_id,
                    content_json={
                        **content,
                        "guardrail_passed": len(guardrail_errors) == 0,
                        "guardrail_errors": guardrail_errors
                    }
                )
                
                sections_result[section_id] = content
                logger.info(f"[Worker] 섹션 완료: {section_id} (가드레일: {'✅' if not guardrail_errors else '❌'})")
                
            except Exception as e:
                logger.error(f"[Worker] 섹션 실패: {section_id} | {e}")
                failed_sections.append({
                    "section_id": section_id,
                    "errors": [f"Exception: {str(e)[:100]}"]
                })
        
        # 🔥 P0-1: 가드레일 실패한 섹션이 있으면 Job failed
        if failed_sections:
            error_summary = "; ".join([
                f"{fs['section_id']}: {', '.join(fs['errors'][:2])}"
                for fs in failed_sections[:3]
            ])
            
            await supabase_service.fail_job(job_id, f"가드레일 실패: {error_summary[:400]}")
            
            # 실패 이메일
            try:
                await self._send_failure_email(job, error_summary[:200])
            except:
                pass
            
            return False, error_summary
        
        # 5. 모든 섹션 성공 → 결과 조합
        result_json = {
            "name": name,
            "target_year": target_year,
            "sections": sections_result,
            "generated_at": time.strftime("%Y-%m-%d %H:%M:%S")
        }
        
        markdown = self._build_markdown(result_json)
        
        # 6. 완료
        await supabase_service.complete_job(job_id, result_json, markdown)
        
        # 7. 완료 이메일
        try:
            await self._send_completion_email(email, name, job_id)
        except Exception as e:
            logger.warning(f"[Worker] 완료 이메일 실패: {e}")
        
        return True, ""
    
    async def _generate_section_with_guardrail(
        self,
        section_id: str,
        saju_data: Dict,
        rulecards: List,
        feature_tags: List,
        target_year: int,
        question: str,
        max_retries: int = 2  # 🔥 P0-5: 자동 리라이트 1회 포함
    ) -> Dict[str, Any]:
        """
        섹션 생성 + 가드레일 검사 + 자동 리라이트
        Returns: {"content": {...}, "guardrail_errors": [...]}
        """
        try:
            from app.services.report_builder import premium_report_builder
            
            # 첫 번째 생성
            result = await premium_report_builder.regenerate_single_section(
                section_id=section_id,
                saju_data=saju_data,
                rulecards=rulecards,
                feature_tags=feature_tags,
                target_year=target_year,
                user_question=question
            )
            
            content = result.get("content", {})
            guardrail_errors = result.get("guardrail_errors", [])
            
            # 🔥 P0-5: 가드레일 실패 시 자동 리라이트 1회
            if guardrail_errors and max_retries > 0:
                logger.info(f"[Worker] 자동 리라이트 시도: {section_id}")
                
                # 리라이트 프롬프트 추가
                rewrite_instruction = self._build_rewrite_prompt(guardrail_errors)
                
                result = await premium_report_builder.regenerate_single_section(
                    section_id=section_id,
                    saju_data=saju_data,
                    rulecards=rulecards,
                    feature_tags=feature_tags,
                    target_year=target_year,
                    user_question=question + "\n\n" + rewrite_instruction
                )
                
                content = result.get("content", {})
                guardrail_errors = result.get("guardrail_errors", [])
                
                if guardrail_errors:
                    logger.warning(f"[Worker] 리라이트 후에도 가드레일 실패: {section_id} | {guardrail_errors}")
                else:
                    logger.info(f"[Worker] 리라이트 성공: {section_id}")
            
            return {
                "content": content,
                "guardrail_errors": guardrail_errors
            }
            
        except Exception as e:
            logger.error(f"섹션 생성 오류: {section_id} | {e}")
            return {
                "content": {"summary": f"{section_id} 생성 실패", "error": str(e)[:200]},
                "guardrail_errors": [f"Exception: {str(e)[:100]}"]
            }
    
    def _build_rewrite_prompt(self, errors: List[str]) -> str:
        """🔥 P0-5: 리라이트 프롬프트 생성"""
        prompt_parts = [
            "⚠️ 이전 응답이 품질 검사에 실패했습니다. 다음 규칙을 반드시 지켜주세요:",
            ""
        ]
        
        for error in errors[:5]:
            if "LANGUAGE_NOT_KOREAN" in error:
                prompt_parts.append("- 영어 사용 금지! AI, KPI, ROI, OKR 같은 비즈니스 약어만 허용. 나머지는 모두 한국어로.")
            elif "banned_phrase" in error:
                prompt_parts.append("- 자기계발서 문구 금지! '노력하면', '성장의 기회', '긍정적인' 같은 공허한 표현 대신 구체적 수치와 액션을 사용.")
            elif "low_specificity" in error:
                prompt_parts.append("- 구체성 강화! 모든 문장에 날짜(3월 2주차), 수치(30% 증가), 액션(계약서 발송), 검증방법(주간 리뷰)을 포함.")
            elif "duplicate" in error:
                prompt_parts.append("- 중복 제거! 다른 섹션과 겹치는 내용 없이 이 섹션 고유의 관점으로 작성.")
        
        prompt_parts.extend([
            "",
            "특히 sprint 섹션은 반드시:",
            "1) 이번 주 목표 3개 (각각 수치/기한/성공기준 포함)",
            "2) 실행 체크리스트 7개 (누가/언제/무엇/완료조건)",
            "3) 리스크 3개 + 대응 3개",
            "4) KPI 3개 (측정 방식 포함)"
        ])
        
        return "\n".join(prompt_parts)
    
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
            lines.append(section.get("body_markdown", section.get("summary", "내용 없음")))
            lines.append("\n")
        
        return "\n".join(lines)
    
    async def _send_completion_email(self, email: str, name: str, job_id: str):
        """완료 이메일"""
        if not email:
            return
        
        try:
            from app.services.email_sender import email_sender
            
            job = await supabase_service.get_job(job_id)
            access_token = job.get("public_token", "") if job else ""
            
            await email_sender.send_report_complete(
                to_email=email,
                name=name,
                report_id=job_id,
                access_token=access_token,
                target_year=2026
            )
            logger.info(f"[Worker] ✅ 완료 이메일 발송: {email}")
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
            job_id = job.get("id", "")
            
            await email_sender.send_report_failed(
                to_email=email,
                name=name,
                report_id=job_id,
                error_message=error[:200]
            )
            logger.info(f"[Worker] 실패 이메일 발송: {email}")
        except Exception as e:
            logger.warning(f"실패 이메일 발송 실패: {e}")


# 싱글톤
report_worker = ReportWorker()
