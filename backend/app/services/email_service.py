"""
Email Service - Resend 기반 이메일 발송
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
- 리포트 완료 알림
- PDF 다운로드 링크
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""
import os
import logging
from typing import Optional

logger = logging.getLogger(__name__)

# Resend 선택적 import
try:
    import resend
    RESEND_AVAILABLE = True
except ImportError:
    RESEND_AVAILABLE = False
    logger.warning("[Email] resend 패키지 미설치")


class EmailService:
    """Resend 기반 이메일 서비스"""
    
    def __init__(self):
        self._api_key = os.getenv("RESEND_API_KEY")
        self._from_email = os.getenv("EMAIL_FROM", "SajuOS <noreply@sajuos.com>")
        self._frontend_url = os.getenv("FRONTEND_URL", "https://sajuos.com")
        
        if RESEND_AVAILABLE and self._api_key:
            resend.api_key = self._api_key
            self._available = True
            logger.info("[Email] ✅ Resend 초기화 완료")
        else:
            self._available = False
            logger.warning("[Email] ⚠️ Resend 미설정 - 이메일 발송 비활성화")
    
    @property
    def available(self) -> bool:
        return self._available
    
    async def send_report_complete(
        self,
        to_email: str,
        name: str,
        access_token: str,
        target_year: int,
        pdf_url: Optional[str] = None
    ) -> bool:
        """리포트 완료 이메일 발송"""
        if not self.available:
            logger.warning(f"[Email] 발송 스킵 (미설정): {to_email}")
            return False
        
        report_url = f"{self._frontend_url}/report/{access_token}"
        
        html_content = f"""
<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <style>
        body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; line-height: 1.6; color: #333; }}
        .container {{ max-width: 600px; margin: 0 auto; padding: 40px 20px; }}
        .header {{ text-align: center; margin-bottom: 30px; }}
        .logo {{ font-size: 32px; }}
        h1 {{ color: #7c3aed; margin: 0; }}
        .card {{ background: linear-gradient(135deg, #f5f3ff 0%, #fef3c7 100%); border-radius: 16px; padding: 30px; margin: 20px 0; }}
        .button {{ display: inline-block; background: linear-gradient(135deg, #7c3aed 0%, #f59e0b 100%); color: white !important; text-decoration: none; padding: 16px 32px; border-radius: 8px; font-weight: bold; margin: 10px 5px; }}
        .button-secondary {{ background: #6b7280; }}
        .footer {{ text-align: center; color: #9ca3af; font-size: 12px; margin-top: 40px; }}
        .highlight {{ color: #7c3aed; font-weight: bold; }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <div class="logo">🔮</div>
            <h1>사주OS</h1>
            <p>프리미엄 비즈니스 컨설팅 보고서</p>
        </div>
        
        <p>{name}님, 안녕하세요!</p>
        
        <div class="card">
            <h2>✨ {target_year}년 프리미엄 보고서가 완성되었습니다!</h2>
            <p>
                30페이지 분량의 맞춤형 비즈니스 컨설팅 보고서가 준비되었습니다.
                <br>아래 버튼을 클릭하여 확인하세요.
            </p>
        </div>
        
        <div style="text-align: center; margin: 30px 0;">
            <a href="{report_url}" class="button">📊 내 보고서 보기</a>
            {f'<a href="{pdf_url}" class="button button-secondary">📄 PDF 다운로드</a>' if pdf_url else ''}
        </div>
        
        <p>
            <strong>포함된 분석:</strong><br>
            ✅ Executive Summary (경영진 요약)<br>
            ✅ Money & Cashflow (현금흐름 전략)<br>
            ✅ Business Strategy (사업 전략)<br>
            ✅ Team & Partnership (팀/파트너 분석)<br>
            ✅ Health & Performance (건강/에너지)<br>
            ✅ 12-Month Calendar (월별 로드맵)<br>
            ✅ 90-Day Sprint (실행 계획)
        </p>
        
        <p style="background: #fef3c7; padding: 15px; border-radius: 8px;">
            💡 <strong>Tip:</strong> 이 링크는 <span class="highlight">개인 전용</span>입니다. 
            북마크해두시면 언제든 다시 확인하실 수 있어요.
        </p>
        
        <div class="footer">
            <p>
                이 이메일은 사주OS 프리미엄 보고서 구매자에게 발송되었습니다.<br>
                문의: support@sajuos.com
            </p>
            <p>© 2025 사주OS. All rights reserved.</p>
        </div>
    </div>
</body>
</html>
"""
        
        try:
            response = resend.Emails.send({
                "from": self._from_email,
                "to": [to_email],
                "subject": f"🔮 [{name}님] {target_year}년 프리미엄 비즈니스 보고서가 완성되었습니다!",
                "html": html_content
            })
            
            logger.info(f"[Email] ✅ 발송 성공: {to_email} | ID: {response.get('id', 'N/A')}")
            return True
            
        except Exception as e:
            logger.error(f"[Email] ❌ 발송 실패: {to_email} | {e}")
            return False
    
    async def send_report_failed(
        self,
        to_email: str,
        name: str,
        error_message: str,
        report_id: str
    ) -> bool:
        """리포트 생성 실패 이메일"""
        if not self.available:
            return False
        
        retry_url = f"{self._frontend_url}/report/retry/{report_id}"
        
        html_content = f"""
<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <style>
        body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; line-height: 1.6; color: #333; }}
        .container {{ max-width: 600px; margin: 0 auto; padding: 40px 20px; }}
        .error-card {{ background: #fef2f2; border: 1px solid #fecaca; border-radius: 16px; padding: 30px; margin: 20px 0; }}
        .button {{ display: inline-block; background: #7c3aed; color: white !important; text-decoration: none; padding: 16px 32px; border-radius: 8px; font-weight: bold; }}
    </style>
</head>
<body>
    <div class="container">
        <h1>🔮 사주OS</h1>
        <p>{name}님, 안녕하세요.</p>
        
        <div class="error-card">
            <h2>⚠️ 보고서 생성 중 문제가 발생했습니다</h2>
            <p>죄송합니다. 기술적인 문제로 보고서 생성이 완료되지 않았습니다.</p>
            <p style="color: #6b7280; font-size: 14px;">오류: {error_message[:100]}</p>
        </div>
        
        <p>아래 버튼을 클릭하여 다시 시도해주세요. (이미 완료된 섹션은 유지됩니다)</p>
        
        <div style="text-align: center; margin: 30px 0;">
            <a href="{retry_url}" class="button">🔄 다시 시도하기</a>
        </div>
        
        <p>문제가 계속되면 support@sajuos.com으로 문의해주세요.</p>
    </div>
</body>
</html>
"""
        
        try:
            resend.Emails.send({
                "from": self._from_email,
                "to": [to_email],
                "subject": f"⚠️ [{name}님] 보고서 생성 중 문제가 발생했습니다",
                "html": html_content
            })
            return True
        except Exception as e:
            logger.error(f"[Email] 실패 알림 발송 오류: {e}")
            return False


# 싱글톤
email_service = EmailService()
