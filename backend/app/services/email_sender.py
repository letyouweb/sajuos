"""
Email Sender - Resend 기반 이메일 발송
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
프리미엄 리포트 완료 시 이메일 알림 발송
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""
import logging
from typing import Optional
import resend

from app.config import get_settings

logger = logging.getLogger(__name__)


class EmailSender:
    """Resend 기반 이메일 발송"""
    
    _initialized: bool = False
    
    def _init_client(self):
        """Resend 클라이언트 초기화"""
        if self._initialized:
            return
        
        settings = get_settings()
        if not settings.resend_api_key:
            logger.warning("[EmailSender] RESEND_API_KEY 미설정 - 이메일 발송 비활성화")
            return
        
        resend.api_key = settings.resend_api_key
        self._initialized = True
        logger.info("[EmailSender] Resend 초기화 완료")
    
    async def send_report_complete(
        self,
        to_email: str,
        name: str,
        report_id: str,
        access_token: str,
        target_year: int,
        pdf_url: Optional[str] = None
    ) -> bool:
        """리포트 완료 이메일 발송"""
        self._init_client()
        
        settings = get_settings()
        if not settings.resend_api_key:
            logger.warning(f"[EmailSender] 이메일 발송 스킵 (API 키 없음): {to_email}")
            return False
        
        # 리포트 보기 링크 (토큰 기반)
        view_url = f"{settings.frontend_url}/report/{report_id}?token={access_token}"
        
        # 이메일 본문
        subject = f"🎯 {name}님의 {target_year}년 프리미엄 비즈니스 보고서가 완성되었습니다"
        
        html_content = f"""
<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <style>
        body {{ font-family: 'Apple SD Gothic Neo', 'Malgun Gothic', sans-serif; line-height: 1.6; color: #333; }}
        .container {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
        .header {{ background: linear-gradient(135deg, #7c3aed 0%, #f59e0b 100%); color: white; padding: 30px; border-radius: 12px 12px 0 0; text-align: center; }}
        .content {{ background: #fff; padding: 30px; border: 1px solid #e5e7eb; border-top: none; }}
        .button {{ display: inline-block; background: linear-gradient(135deg, #7c3aed 0%, #6d28d9 100%); color: white; padding: 14px 32px; text-decoration: none; border-radius: 8px; font-weight: bold; margin: 20px 0; }}
        .button:hover {{ opacity: 0.9; }}
        .footer {{ text-align: center; padding: 20px; color: #666; font-size: 12px; }}
        .highlight {{ background: #fef3c7; padding: 15px; border-radius: 8px; margin: 15px 0; }}
        .pdf-button {{ display: inline-block; background: #059669; color: white; padding: 12px 24px; text-decoration: none; border-radius: 8px; font-weight: bold; margin-left: 10px; }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1 style="margin: 0; font-size: 24px;">🔮 SajuOS</h1>
            <p style="margin: 10px 0 0; opacity: 0.9;">프리미엄 비즈니스 컨설팅 보고서</p>
        </div>
        <div class="content">
            <h2 style="color: #7c3aed;">🎉 {name}님, 보고서가 완성되었습니다!</h2>
            
            <p>요청하신 <strong>{target_year}년 프리미엄 비즈니스 컨설팅 보고서</strong>가 생성 완료되었습니다.</p>
            
            <div class="highlight">
                <strong>📊 보고서 구성 (7개 섹션, 약 30페이지)</strong>
                <ul style="margin: 10px 0;">
                    <li>Executive Summary - 핵심 전략 요약</li>
                    <li>Money & Cashflow - 재무 분석</li>
                    <li>Business Strategy - 사업 전략</li>
                    <li>Team & Partner - 팀/파트너십</li>
                    <li>Health & Performance - 건강/퍼포먼스</li>
                    <li>12-Month Calendar - 월별 실행 계획</li>
                    <li>90-Day Sprint - 90일 액션플랜</li>
                </ul>
            </div>
            
            <div style="text-align: center; margin: 30px 0;">
                <a href="{view_url}" class="button">📄 보고서 보기</a>
                {f'<a href="{pdf_url}" class="pdf-button">📥 PDF 다운로드</a>' if pdf_url else ''}
            </div>
            
            <p style="color: #666; font-size: 14px;">
                ※ 이 링크는 고객님 전용입니다. 타인과 공유하지 마세요.<br>
                ※ 문의사항은 support@sajuos.com으로 연락 바랍니다.
            </p>
        </div>
        <div class="footer">
            <p>© 2025 SajuOS. All rights reserved.</p>
            <p>본 이메일은 {to_email}로 발송되었습니다.</p>
        </div>
    </div>
</body>
</html>
"""
        
        text_content = f"""
{name}님, {target_year}년 프리미엄 비즈니스 보고서가 완성되었습니다!

보고서 보기: {view_url}
{f"PDF 다운로드: {pdf_url}" if pdf_url else ""}

문의: support@sajuos.com
"""
        
        try:
            result = resend.Emails.send({
                "from": settings.email_from,
                "to": [to_email],
                "reply_to": settings.email_reply_to,
                "subject": subject,
                "html": html_content,
                "text": text_content,
            })
            
            logger.info(f"[EmailSender] ✅ 이메일 발송 성공: {to_email} | ID: {result.get('id', 'N/A')}")
            return True
            
        except Exception as e:
            logger.error(f"[EmailSender] ❌ 이메일 발송 실패: {to_email} | {e}")
            return False
    
    async def send_report_failed(
        self,
        to_email: str,
        name: str,
        report_id: str,
        error_message: str
    ) -> bool:
        """리포트 생성 실패 이메일"""
        self._init_client()
        
        settings = get_settings()
        if not settings.resend_api_key:
            return False
        
        retry_url = f"{settings.frontend_url}/report/{report_id}/retry"
        
        subject = f"⚠️ {name}님의 보고서 생성에 문제가 발생했습니다"
        
        html_content = f"""
<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <style>
        body {{ font-family: 'Apple SD Gothic Neo', sans-serif; line-height: 1.6; color: #333; }}
        .container {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
        .header {{ background: #dc2626; color: white; padding: 30px; border-radius: 12px 12px 0 0; text-align: center; }}
        .content {{ background: #fff; padding: 30px; border: 1px solid #e5e7eb; border-top: none; }}
        .button {{ display: inline-block; background: #7c3aed; color: white; padding: 14px 32px; text-decoration: none; border-radius: 8px; font-weight: bold; }}
        .error-box {{ background: #fef2f2; border: 1px solid #fecaca; padding: 15px; border-radius: 8px; margin: 15px 0; }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1 style="margin: 0;">⚠️ 보고서 생성 오류</h1>
        </div>
        <div class="content">
            <h2>{name}님, 죄송합니다.</h2>
            <p>보고서 생성 중 문제가 발생했습니다. 아래 버튼을 클릭하여 재시도해 주세요.</p>
            
            <div class="error-box">
                <strong>오류 내용:</strong><br>
                {error_message[:200]}
            </div>
            
            <div style="text-align: center; margin: 30px 0;">
                <a href="{retry_url}" class="button">🔄 재시도하기</a>
            </div>
            
            <p style="color: #666; font-size: 14px;">
                문제가 계속되면 support@sajuos.com으로 문의해 주세요.<br>
                보고서 ID: {report_id}
            </p>
        </div>
    </div>
</body>
</html>
"""
        
        try:
            resend.Emails.send({
                "from": settings.email_from,
                "to": [to_email],
                "reply_to": settings.email_reply_to,
                "subject": subject,
                "html": html_content,
            })
            
            logger.info(f"[EmailSender] 실패 알림 발송: {to_email}")
            return True
            
        except Exception as e:
            logger.error(f"[EmailSender] 실패 알림 발송 오류: {e}")
            return False


# 싱글톤 인스턴스
email_sender = EmailSender()
