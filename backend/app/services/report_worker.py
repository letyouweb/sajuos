"""
Report Worker - 백그라운드 리포트 생성 워커
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
탭을 닫아도 계속 진행되는 백그라운드 Job 처리
- 섹션별 순차 생성 + Supabase 저장
- 완료된 섹션은 스킵 (재시도 가능)
- 완료 시 이메일 발송
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""
import asyncio
import logging
import time
from typing import Dict, Any, List, Optional
from datetime import datetime

from app.services.supabase_store import supabase_store, SECTION_SPECS
from app.services.email_sender import email_sender
from app.services.report_builder import premium_report_builder, PREMIUM_SECTIONS
from app.services.feature_tags_no_time import build_feature_tags_no_time_from_pillars
from app.services.preset_type2 import BUSINESS_OWNER_PRESET_V2
from app.services.focus_boost import boost_preset_focus
from app.services.rulecard_selector import select_cards_for_preset

logger = logging.getLogger(__name__)


class ReportWorker:
    """백그라운드 리포트 생성 워커"""
    
    # 진행 중인 Job 추적 (메모리 - 중복 실행 방지)
    _running_jobs: set = set()
    
    async def start_report_generation(
        self,
        report_id: str,
        rulestore: Any = None
    ) -> None:
        """
        백그라운드 리포트 생성 시작
        - BackgroundTasks에서 호출됨
        - 탭을 닫아도 계속 진행
        """
        # 중복 실행 방지
        if report_id in self._running_jobs:
            logger.warning(f"[Worker] 이미 실행 중: {report_id}")
            return
        
        self._running_jobs.add(report_id)
        
        try:
            await self._run_generation(report_id, rulestore)
        except Exception as e:
            logger.error(f"[Worker] 리포트 생성 실패: {report_id} | {e}")
            await supabase_store.fail_report(report_id, str(e)[:500])
            
            # 실패 이메일 발송
            report = await supabase_store.get_report(report_id)
            if report:
                await email_sender.send_report_failed(
                    to_email=report["email"],
                    name=report.get("name", "고객"),
                    report_id=report_id,
                    error_message=str(e)
                )
        finally:
            self._running_jobs.discard(report_id)
    
    async def _run_generation(
        self,
        report_id: str,
        rulestore: Any = None
    ) -> None:
        """실제 생성 로직"""
        start_time = time.time()
        
        # 리포트 정보 조회
        report = await supabase_store.get_report(report_id)
        if not report:
            raise ValueError(f"리포트 없음: {report_id}")
        
        input_data = report["input_data"]
        target_year = report.get("target_year", 2026)
        
        logger.info(f"[Worker] ========== 리포트 생성 시작 ==========")
        logger.info(f"[Worker] Report ID: {report_id}")
        logger.info(f"[Worker] Target Year: {target_year}")
        
        # 상태: generating
        await supabase_store.update_report_status(
            report_id, "generating", progress=0, current_step="초기화 중..."
        )
        
        # 사주 데이터 준비
        saju_data = self._extract_saju_data(input_data)
        
        # RuleCards + FeatureTags 준비
        rulecards, feature_tags = await self._prepare_rulecards(
            saju_data, rulestore, target_year
        )
        
        logger.info(f"[Worker] RuleCards: {len(rulecards)} | FeatureTags: {len(feature_tags)}")
        
        # 미완료 섹션 조회 (재시도 지원)
        pending_sections = await supabase_store.get_pending_sections(report_id)
        
        if not pending_sections:
            # 모든 섹션이 이미 완료됨
            logger.info(f"[Worker] 모든 섹션 완료 - 결과 조합 단계")
        else:
            # 섹션별 생성
            for section_info in pending_sections:
                section_id = section_info["section_id"]
                
                try:
                    await self._generate_section(
                        report_id=report_id,
                        section_id=section_id,
                        saju_data=saju_data,
                        rulecards=rulecards,
                        feature_tags=feature_tags,
                        target_year=target_year,
                        user_question=input_data.get("question", "")
                    )
                except Exception as e:
                    # 섹션 실패 - 계속 진행 (다른 섹션은 생성)
                    logger.error(f"[Worker] 섹션 실패: {section_id} | {e}")
                    await supabase_store.update_section_fail(report_id, section_id, str(e))
        
        # 모든 섹션 조회 + 결과 조합
        all_sections = await supabase_store.get_sections(report_id)
        final_result = await self._assemble_report(all_sections, target_year, report)
        
        # 생성 시간 계산
        generation_time_ms = int((time.time() - start_time) * 1000)
        
        # 완료 처리
        await supabase_store.complete_report(
            report_id=report_id,
            result_json=final_result,
            pdf_url=None,  # TODO: PDF 생성
            generation_time_ms=generation_time_ms,
            total_tokens_used=0  # TODO: 토큰 추적
        )
        
        # 완료 이메일 발송
        updated_report = await supabase_store.get_report(report_id)
        if updated_report:
            await email_sender.send_report_complete(
                to_email=updated_report["email"],
                name=updated_report.get("name", "고객"),
                report_id=report_id,
                access_token=updated_report["access_token"],
                target_year=target_year,
                pdf_url=updated_report.get("pdf_url")
            )
        
        logger.info(f"[Worker] ========== 리포트 완료 ==========")
        logger.info(f"[Worker] Report ID: {report_id}")
        logger.info(f"[Worker] 생성 시간: {generation_time_ms / 1000:.1f}초")
    
    def _extract_saju_data(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
        """input_data에서 사주 데이터 추출"""
        if "saju_result" in input_data:
            return input_data["saju_result"]
        
        # 직접 기둥 데이터
        return {
            "year_pillar": input_data.get("year_pillar", {}),
            "month_pillar": input_data.get("month_pillar", {}),
            "day_pillar": input_data.get("day_pillar", {}),
            "hour_pillar": input_data.get("hour_pillar"),
            "day_master": input_data.get("day_master", ""),
            "day_master_element": input_data.get("day_master_element", ""),
        }
    
    async def _prepare_rulecards(
        self,
        saju_data: Dict[str, Any],
        rulestore: Any,
        target_year: int
    ) -> tuple:
        """RuleCards + FeatureTags 준비"""
        if not rulestore:
            return [], []
        
        # 기둥 추출
        year_p = self._get_pillar_ganji(saju_data.get("year_pillar", {}))
        month_p = self._get_pillar_ganji(saju_data.get("month_pillar", {}))
        day_p = self._get_pillar_ganji(saju_data.get("day_pillar", {}))
        
        if not (year_p and month_p and day_p):
            return [], []
        
        # FeatureTags 생성
        ft = build_feature_tags_no_time_from_pillars(
            year_p, month_p, day_p, overlay_year=target_year
        )
        feature_tags = ft.get("tags", [])
        
        # RuleCard 선택
        boosted = boost_preset_focus(BUSINESS_OWNER_PRESET_V2, feature_tags)
        selection = select_cards_for_preset(rulestore, boosted, feature_tags)
        
        all_cards = []
        for sec in selection.get("sections", []):
            all_cards.extend(sec.get("cards", []))
        
        return all_cards, feature_tags
    
    def _get_pillar_ganji(self, pillar_data) -> str:
        """기둥에서 간지 추출"""
        if isinstance(pillar_data, dict):
            if pillar_data.get("ganji"):
                return pillar_data["ganji"]
            gan = pillar_data.get("gan", "")
            ji = pillar_data.get("ji", "")
            if gan and ji:
                return gan + ji
        elif isinstance(pillar_data, str):
            return pillar_data
        return ""
    
    async def _generate_section(
        self,
        report_id: str,
        section_id: str,
        saju_data: Dict[str, Any],
        rulecards: List[Dict[str, Any]],
        feature_tags: List[str],
        target_year: int,
        user_question: str
    ) -> Dict[str, Any]:
        """단일 섹션 생성"""
        
        # 섹션 시작 표시
        await supabase_store.update_section_start(report_id, section_id)
        
        section_start = time.time()
        
        try:
            # report_builder의 단일 섹션 생성 호출
            result = await premium_report_builder.regenerate_single_section(
                section_id=section_id,
                saju_data=saju_data,
                rulecards=rulecards,
                feature_tags=feature_tags,
                target_year=target_year,
                user_question=user_question
            )
            
            elapsed_ms = int((time.time() - section_start) * 1000)
            
            # 결과에서 콘텐츠 추출
            content_json = result.get("section", {})
            char_count = len(content_json.get("body_markdown", ""))
            rulecard_count = content_json.get("rulecard_selected", 0)
            
            # 섹션 완료 저장
            await supabase_store.update_section_complete(
                report_id=report_id,
                section_id=section_id,
                content_json=content_json,
                char_count=char_count,
                rulecard_count=rulecard_count,
                elapsed_ms=elapsed_ms
            )
            
            return content_json
            
        except Exception as e:
            await supabase_store.update_section_fail(report_id, section_id, str(e))
            raise
    
    async def _assemble_report(
        self,
        sections: List[Dict[str, Any]],
        target_year: int,
        report: Dict[str, Any]
    ) -> Dict[str, Any]:
        """섹션들을 최종 리포트로 조합"""
        
        assembled_sections = []
        total_chars = 0
        success_count = 0
        error_count = 0
        
        for section in sections:
            content = section.get("content_json", {})
            status = section.get("status", "pending")
            
            if status == "completed" and content:
                assembled_sections.append(content)
                total_chars += section.get("char_count", 0)
                success_count += 1
            else:
                # 에러 섹션
                error_count += 1
                assembled_sections.append({
                    "id": section["section_id"],
                    "title": section["section_title"],
                    "error": True,
                    "error_message": section.get("error", "생성 실패"),
                })
        
        # 최종 리포트 구조
        return {
            "target_year": target_year,
            "sections": assembled_sections,
            "meta": {
                "total_chars": total_chars,
                "mode": "premium_business_30p",
                "generated_at": datetime.utcnow().isoformat(),
                "section_count": len(sections),
                "success_count": success_count,
                "error_count": error_count,
            },
            "legacy": {
                "summary": f"{target_year}년 프리미엄 비즈니스 컨설팅 보고서",
                "blessing": "성공적인 한 해 되세요! 🎯",
            }
        }
    
    async def retry_report(self, report_id: str, rulestore: Any = None) -> bool:
        """
        실패한 리포트 재시도
        - 완료된 섹션은 스킵
        - 실패/pending 섹션만 재생성
        """
        report = await supabase_store.get_report(report_id)
        if not report:
            return False
        
        if report["status"] not in ["failed", "generating"]:
            logger.warning(f"[Worker] 재시도 불가 상태: {report['status']}")
            return False
        
        # 실패한 섹션 리셋
        sections = await supabase_store.get_sections(report_id)
        for section in sections:
            if section["status"] == "failed":
                await supabase_store.reset_section_for_retry(
                    report_id, section["section_id"]
                )
        
        # 재생성 시작
        await self.start_report_generation(report_id, rulestore)
        return True


# 싱글톤 인스턴스
report_worker = ReportWorker()
