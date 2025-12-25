"""
Saju Engine v3 - KASI API 통합 (Source of Truth)

우선순위:
1. KASI API (한국천문연구원) - Source of Truth
2. ephem (NASA JPL) - Fallback

특징:
- KASI API 실패시 자동으로 ephem fallback
- 서비스 중단 없는 고가용성
- 오늘 날짜 명시적 주입 (연도 착각 방지)
"""
import math
import re
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional, Dict, Any, Tuple
from dataclasses import dataclass
import httpx

try:
    import ephem
    EPHEM_AVAILABLE = True
except ImportError:
    EPHEM_AVAILABLE = False

logger = logging.getLogger(__name__)


# ============ 상수 정의 ============

GAN = list("갑을병정무기경신임계")
JI = list("자축인묘진사오미신유술해")

GAN_HANJA = list("甲乙丙丁戊己庚辛壬癸")
JI_HANJA = list("子丑寅卯辰巳午未申酉戌亥")

GAN_TO_ELEMENT = {
    "갑": "목", "을": "목", "병": "화", "정": "화", "무": "토",
    "기": "토", "경": "금", "신": "금", "임": "수", "계": "수"
}

JI_TO_ELEMENT = {
    "자": "수", "축": "토", "인": "목", "묘": "목", "진": "토", "사": "화",
    "오": "화", "미": "토", "신": "금", "유": "금", "술": "토", "해": "수"
}

DAY_MASTER_DESC = {
    "갑": "큰 나무(甲木) - 곧고 뻗어나가는 성장의 기운",
    "을": "작은 나무(乙木) - 유연하고 적응력 있는 기운",
    "병": "태양(丙火) - 밝고 뜨거운 열정의 기운",
    "정": "촛불(丁火) - 따뜻하고 은은한 빛의 기운",
    "무": "큰 산(戊土) - 안정적이고 묵직한 기운",
    "기": "논밭(己土) - 포용하고 키워내는 기운",
    "경": "바위/쇠(庚金) - 강하고 결단력 있는 기운",
    "신": "보석(辛金) - 섬세하고 빛나는 기운",
    "임": "큰 물(壬水) - 넓고 깊은 지혜의 기운",
    "계": "이슬/비(癸水) - 촉촉하고 스며드는 기운"
}

# 시간대 옵션
HOUR_OPTIONS = [
    {"index": 0, "ji": "자", "ji_hanja": "子", "start": "23:00", "end": "00:59"},
    {"index": 1, "ji": "축", "ji_hanja": "丑", "start": "01:00", "end": "02:59"},
    {"index": 2, "ji": "인", "ji_hanja": "寅", "start": "03:00", "end": "04:59"},
    {"index": 3, "ji": "묘", "ji_hanja": "卯", "start": "05:00", "end": "06:59"},
    {"index": 4, "ji": "진", "ji_hanja": "辰", "start": "07:00", "end": "08:59"},
    {"index": 5, "ji": "사", "ji_hanja": "巳", "start": "09:00", "end": "10:59"},
    {"index": 6, "ji": "오", "ji_hanja": "午", "start": "11:00", "end": "12:59"},
    {"index": 7, "ji": "미", "ji_hanja": "未", "start": "13:00", "end": "14:59"},
    {"index": 8, "ji": "신", "ji_hanja": "申", "start": "15:00", "end": "16:59"},
    {"index": 9, "ji": "유", "ji_hanja": "酉", "start": "17:00", "end": "18:59"},
    {"index": 10, "ji": "술", "ji_hanja": "戌", "start": "19:00", "end": "20:59"},
    {"index": 11, "ji": "해", "ji_hanja": "亥", "start": "21:00", "end": "22:59"},
]

# 절기 이름 (월지 인덱스별)
SOLAR_TERM_NAMES = [
    "동지~소한 (자월)", "소한~입춘 (축월)", "입춘~경칩 (인월)",
    "경칩~청명 (묘월)", "청명~입하 (진월)", "입하~망종 (사월)",
    "망종~소서 (오월)", "소서~입추 (미월)", "입추~백로 (신월)",
    "백로~한로 (유월)", "한로~입동 (술월)", "입동~동지 (해월)",
]


class CalculationError(Exception):
    """계산 오류"""
    pass


# ============ 간지 정규화 (가짜 mismatch 방지) ============

def _norm_ganji(x) -> str:
    """
    간지 문자열 정규화
    - KASI: '무인(戊寅)' → '무인'
    - ephem: '무인' → '무인'
    - 괄호+한자, invisible chars 제거
    """
    s = str(x)
    
    # 1. 괄호와 그 안의 내용 제거: '무인(戊寅)' → '무인'
    s = re.sub(r"\([^)]*\)", "", s)
    
    # 2. invisible chars 제거
    s = s.replace("\u200b", "")  # zero-width space
    s = s.replace("\ufeff", "")  # BOM
    s = s.replace("\xa0", "")    # NBSP
    
    # 3. 모든 공백 제거
    s = re.sub(r"\s+", "", s)
    
    # 4. 한글 간지만 추출 (2글자)
    hangul_match = re.search(r"[가-힣]{2}", s)
    if hangul_match:
        return hangul_match.group(0)
    
    return s.strip()


class SajuManager:
    """
    사주 계산 통합 매니저
    
    Source of Truth 우선순위:
    1. KASI API (한국천문연구원) - 실시간 데이터
    2. ephem (NASA JPL) - Fallback
    
    특징:
    - API 실패시 자동 fallback으로 서비스 무중단
    - KASI vs ephem 결과 비교/검증
    - 오늘 날짜 명시적 관리
    """
    
    # KASI API URLs
    KASI_LUNAR_URL = "http://apis.data.go.kr/B090041/openapi/service/LrsrCldInfoService/getLunCalInfo"
    KASI_SOLAR_TERM_URL = "http://apis.data.go.kr/B090041/openapi/service/SpcdeInfoService/get24DivisionsInfo"
    
    def __init__(self, kasi_api_key: Optional[str] = None):
        self.kasi_api_key = kasi_api_key
        self.ephem_available = EPHEM_AVAILABLE
        
        # Anchor: 2000년 1월 1일 = 무오일 (60갑자 중 54번째)
        self.ANCHOR_DATE = datetime(2000, 1, 1)
        self.ANCHOR_IDX = 54
        
        logger.info(f"SajuManager initialized - KASI: {'✓' if kasi_api_key else '✗'}, ephem: {'✓' if EPHEM_AVAILABLE else '✗'}")
    
    # ============ 날짜 유틸리티 ============
    
    @staticmethod
    def get_today_kst() -> datetime:
        """오늘 날짜 (KST) 반환 - 연도 착각 방지용"""
        kst = timezone(timedelta(hours=9))
        return datetime.now(kst)
    
    @staticmethod
    def get_today_string() -> str:
        """오늘 날짜 문자열 (YYYY-MM-DD KST)"""
        today = SajuManager.get_today_kst()
        return today.strftime("%Y-%m-%d")
    
    @staticmethod
    def inject_today_context(question: str) -> str:
        """질문에 오늘 날짜 컨텍스트 주입 (2024년 버그 방지)"""
        today = SajuManager.get_today_string()
        today_dt = SajuManager.get_today_kst()
        year = today_dt.year
        
        return f"{question}\n\n[시스템 컨텍스트: 오늘은 {year}년 {today_dt.month}월 {today_dt.day}일입니다. 운세 해석시 반드시 {year}년 기준으로 답변하세요.]"
    
    # ============ KASI API 연동 ============
    
    async def _fetch_kasi_lunar(
        self,
        year: int,
        month: int,
        day: int
    ) -> Optional[Dict[str, Any]]:
        """
        KASI 음양력 API 호출
        
        Returns:
            {
                "year_ganji": "갑진",   # 세차
                "month_ganji": "병자",  # 월건
                "day_ganji": "임오",    # 일진
                "lunar_date": {...}
            }
        """
        if not self.kasi_api_key:
            logger.debug("KASI API key not configured")
            return None
        
        params = {
            "serviceKey": self.kasi_api_key,
            "solYear": str(year),
            "solMonth": str(month).zfill(2),
            "solDay": str(day).zfill(2),
            "_type": "json"
        }
        
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(self.KASI_LUNAR_URL, params=params)
                resp.raise_for_status()
                data = resp.json()
                
                items = (
                    data.get("response", {})
                    .get("body", {})
                    .get("items", {})
                    .get("item", {})
                )
                
                if items:
                    return {
                        "year_ganji": items.get("lunSecha", ""),
                        "month_ganji": items.get("lunWolgeon", ""),
                        "day_ganji": items.get("lunIljin", ""),
                        "lunar_year": items.get("lunYear", ""),
                        "lunar_month": items.get("lunMonth", ""),
                        "lunar_day": items.get("lunDay", ""),
                        "is_leap": items.get("lunLeapmonth", "") == "윤"
                    }
                
                logger.warning(f"KASI API returned empty for {year}-{month}-{day}")
                return None
                
        except httpx.TimeoutException:
            logger.error(f"KASI API timeout for {year}-{month}-{day}")
            return None
        except httpx.HTTPError as e:
            logger.error(f"KASI API HTTP error: {e}")
            return None
        except Exception as e:
            logger.error(f"KASI API unexpected error: {e}")
            return None
    
    async def _fetch_kasi_solar_terms(
        self,
        year: int,
        month: int
    ) -> Optional[list]:
        """KASI 24절기 API 호출"""
        if not self.kasi_api_key:
            return None
        
        params = {
            "serviceKey": self.kasi_api_key,
            "solYear": str(year),
            "solMonth": str(month).zfill(2),
            "_type": "json"
        }
        
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(self.KASI_SOLAR_TERM_URL, params=params)
                resp.raise_for_status()
                data = resp.json()
                
                items = (
                    data.get("response", {})
                    .get("body", {})
                    .get("items", {})
                    .get("item", [])
                )
                
                if items:
                    if isinstance(items, dict):
                        items = [items]
                    return [
                        {
                            "name": item.get("dateName", ""),
                            "date": str(item.get("locdate", "")),
                        }
                        for item in items
                    ]
                
                return None
                
        except Exception as e:
            logger.error(f"KASI Solar Terms API error: {e}")
            return None
    
    # ============ ephem Fallback ============
    
    def _ephem_solar_longitude(
        self,
        year: int,
        month: int,
        day: int,
        hour: int,
        minute: int = 0
    ) -> float:
        """ephem으로 태양 황경 계산"""
        if not EPHEM_AVAILABLE:
            raise CalculationError("ephem 라이브러리 미설치")
        
        dt_kst = datetime(year, month, day, hour, minute)
        dt_utc = dt_kst - timedelta(hours=9)
        
        sun = ephem.Sun()
        observer = ephem.Observer()
        observer.date = dt_utc
        sun.compute(observer)
        
        ecliptic = ephem.Ecliptic(sun)
        return math.degrees(ecliptic.lon)
    
    def _ephem_calculate_ganji(
        self,
        year: int,
        month: int,
        day: int,
        hour: int = 12
    ) -> Dict[str, str]:
        """ephem 기반 간지 계산 (Fallback)"""
        # 태양 황경
        solar_lon = self._ephem_solar_longitude(year, month, day, hour)
        
        # 월지 인덱스
        normalized = (solar_lon + 45) % 360
        term_idx = int(normalized / 30)
        month_ji_idx = (term_idx + 2) % 12
        
        # 년주
        cal_year = year
        if month <= 2 and month_ji_idx <= 1:
            cal_year = year - 1
        
        year_gan_idx = (cal_year - 4) % 10
        year_ji_idx = (cal_year - 4) % 12
        
        # 월간 (연두법)
        start_gan_idx = (year_gan_idx % 5) * 2 + 2
        gap = month_ji_idx - 2
        if gap < 0:
            gap += 12
        month_gan_idx = (start_gan_idx + gap) % 10
        
        # 일주 (Anchor 기반)
        target_dt = datetime(year, month, day)
        days_diff = (target_dt - self.ANCHOR_DATE).days
        curr_day_idx = (self.ANCHOR_IDX + days_diff) % 60
        day_gan_idx = curr_day_idx % 10
        day_ji_idx = curr_day_idx % 12
        
        return {
            "year_ganji": GAN[year_gan_idx] + JI[year_ji_idx],
            "month_ganji": GAN[month_gan_idx] + JI[month_ji_idx],
            "day_ganji": GAN[day_gan_idx] + JI[day_ji_idx],
            "solar_longitude": round(solar_lon, 2),
            "month_ji_idx": month_ji_idx
        }
    
    # ============ 통합 계산 ============
    
    async def calculate(
        self,
        year: int,
        month: int,
        day: int,
        hour: Optional[int] = None,
        minute: int = 0,
        use_solar_time: bool = True
    ) -> Dict[str, Any]:
        """
        사주 계산 (KASI 우선, ephem Fallback)
        
        Args:
            year, month, day: 양력 생년월일
            hour: 출생 시 (0-23), None이면 시주 생략
            minute: 출생 분
            use_solar_time: 태양시 보정 적용 여부
        
        Returns:
            사주 결과 딕셔너리
        """
        
        # 1. KASI API 시도
        kasi_data = await self._fetch_kasi_lunar(year, month, day)
        source = "kasi_api"
        
        # 2. Fallback to ephem
        if not kasi_data or not kasi_data.get("year_ganji"):
            logger.info(f"Falling back to ephem for {year}-{month}-{day}")
            
            if not EPHEM_AVAILABLE:
                raise CalculationError(
                    "KASI API 실패 및 ephem 미설치로 계산 불가"
                )
            
            ephem_data = self._ephem_calculate_ganji(year, month, day, hour or 12)
            
            kasi_data = {
                "year_ganji": ephem_data["year_ganji"],
                "month_ganji": ephem_data["month_ganji"],
                "day_ganji": ephem_data["day_ganji"],
            }
            source = "ephem_fallback"
            solar_longitude = ephem_data.get("solar_longitude", 0)
            month_ji_idx = ephem_data.get("month_ji_idx", 0)
        else:
            # KASI 데이터 있으면 ephem으로 추가 정보만 계산
            if EPHEM_AVAILABLE:
                ephem_data = self._ephem_calculate_ganji(year, month, day, hour or 12)
                solar_longitude = ephem_data.get("solar_longitude", 0)
                month_ji_idx = ephem_data.get("month_ji_idx", 0)
                
                # 검증: KASI vs ephem 비교 (정규화 후)
                kasi_day = _norm_ganji(kasi_data["day_ganji"])
                ephem_day = _norm_ganji(ephem_data["day_ganji"])
                
                if kasi_day != ephem_day:
                    logger.warning(
                        "⚠️ KASI vs ephem 불일치! KASI: %r, ephem: %r → KASI 우선 사용",
                        kasi_data['day_ganji'], ephem_data['day_ganji']
                    )
                else:
                    logger.info("✅ 간지 일치: %s", kasi_day)
            else:
                solar_longitude = 0
                month_ji_idx = 0
        
        # 3. 간지 파싱
        year_ganji = kasi_data["year_ganji"]
        month_ganji = kasi_data["month_ganji"]
        day_ganji = kasi_data["day_ganji"]
        
        year_gan_idx = GAN.index(year_ganji[0]) if len(year_ganji) >= 2 else 0
        year_ji_idx = JI.index(year_ganji[1]) if len(year_ganji) >= 2 else 0
        month_gan_idx = GAN.index(month_ganji[0]) if len(month_ganji) >= 2 else 0
        month_ji_idx_parsed = JI.index(month_ganji[1]) if len(month_ganji) >= 2 else 0
        day_gan_idx = GAN.index(day_ganji[0]) if len(day_ganji) >= 2 else 0
        day_ji_idx = JI.index(day_ganji[1]) if len(day_ganji) >= 2 else 0
        
        # 4. 시주 계산 (항상 내부 계산)
        hour_pillar = None
        hour_range = None
        
        if hour is not None:
            adjusted_minute = hour * 60 + minute
            if use_solar_time:
                adjusted_minute -= 30
                if adjusted_minute < 0:
                    adjusted_minute += 1440
            
            eff_hour = adjusted_minute // 60
            hour_ji_idx = ((eff_hour + 1) // 2) % 12
            
            start_time_gan = (day_gan_idx % 5) * 2
            hour_gan_idx = (start_time_gan + hour_ji_idx) % 10
            
            hour_pillar = self._make_pillar(hour_gan_idx, hour_ji_idx)
            h_opt = HOUR_OPTIONS[hour_ji_idx]
            hour_range = f"{h_opt['start']}~{h_opt['end']}"
        
        # 5. 경계일 확인
        is_boundary = False
        boundary_reason = None
        if EPHEM_AVAILABLE and solar_longitude:
            for boundary in range(0, 360, 15):
                diff = abs((solar_longitude - boundary + 180) % 360 - 180)
                if diff <= 1.5:
                    is_boundary = True
                    boundary_reason = "near_ipchun" if boundary == 315 else "near_term_change"
                    break
        
        # 6. 결과 반환
        return {
            "year_pillar": self._make_pillar(year_gan_idx, year_ji_idx),
            "month_pillar": self._make_pillar(month_gan_idx, month_ji_idx_parsed),
            "day_pillar": self._make_pillar(day_gan_idx, day_ji_idx),
            "hour_pillar": hour_pillar,
            "hour_range": hour_range,
            "day_master": GAN[day_gan_idx],
            "day_master_element": GAN_TO_ELEMENT[GAN[day_gan_idx]],
            "day_master_description": DAY_MASTER_DESC[GAN[day_gan_idx]],
            "meta": {
                "source": source,
                "solar_time_applied": use_solar_time,
                "solar_longitude_deg": solar_longitude,
                "is_boundary": is_boundary,
                "boundary_reason": boundary_reason,
                "calculation_method": source,
                "timezone": "Asia/Seoul",
                "today_kst": self.get_today_string()
            }
        }
    
    def _make_pillar(self, gan_idx: int, ji_idx: int) -> Dict[str, Any]:
        """Pillar 딕셔너리 생성"""
        return {
            "ganji": GAN[gan_idx] + JI[ji_idx],
            "gan": GAN[gan_idx],
            "ji": JI[ji_idx],
            "gan_hanja": GAN_HANJA[gan_idx],
            "ji_hanja": JI_HANJA[ji_idx],
            "gan_element": GAN_TO_ELEMENT[GAN[gan_idx]],
            "ji_element": JI_TO_ELEMENT[JI[ji_idx]],
            "gan_index": gan_idx,
            "ji_index": ji_idx
        }
    
    @staticmethod
    def get_hour_options():
        """시간대 선택 옵션"""
        return [
            {
                "index": h["index"],
                "ji": h["ji"],
                "ji_hanja": h["ji_hanja"],
                "range_start": h["start"],
                "range_end": h["end"],
                "label": f"{h['ji_hanja']}시 ({h['ji']}시) - {h['start']}~{h['end']}"
            }
            for h in HOUR_OPTIONS
        ]


# ============ 하위 호환용 ScientificSajuEngine ============

class ScientificSajuEngine:
    """
    기존 코드 호환용 래퍼
    
    내부적으로 SajuManager 사용
    동기 함수 → 비동기 어댑터
    """
    
    def __init__(self):
        if not EPHEM_AVAILABLE:
            raise ImportError("ephem 라이브러리가 필요합니다.")
        
        self.ANCHOR_DATE = datetime(2000, 1, 1)
        self.ANCHOR_IDX = 54
    
    def _get_solar_longitude(self, year: int, month: int, day: int, hour: int, minute: int = 0) -> float:
        dt_kst = datetime(year, month, day, hour, minute)
        dt_utc = dt_kst - timedelta(hours=9)
        
        sun = ephem.Sun()
        observer = ephem.Observer()
        observer.date = dt_utc
        sun.compute(observer)
        
        ecliptic = ephem.Ecliptic(sun)
        return math.degrees(ecliptic.lon)
    
    def _get_solar_term_index(self, solar_longitude: float) -> Tuple[int, str]:
        deg = solar_longitude
        normalized = (deg + 45) % 360
        term_idx = int(normalized / 30)
        month_ji_idx = (term_idx + 2) % 12
        term_name = SOLAR_TERM_NAMES[month_ji_idx]
        return month_ji_idx, term_name
    
    def _is_near_boundary(self, solar_longitude: float) -> Tuple[bool, Optional[str]]:
        deg = solar_longitude
        for boundary in range(0, 360, 15):
            diff = abs((deg - boundary + 180) % 360 - 180)
            if diff <= 1.5:
                if boundary == 315:
                    return True, "near_ipchun"
                return True, "near_term_change"
        return False, None
    
    def calculate(
        self,
        year: int,
        month: int,
        day: int,
        hour: Optional[int] = None,
        minute: int = 0,
        use_solar_time: bool = True
    ) -> Dict[str, Any]:
        """동기 계산 (ephem only - 기존 호환)"""
        try:
            calc_hour = hour if hour is not None else 12
            solar_lon = self._get_solar_longitude(year, month, day, calc_hour, minute)
            solar_idx, solar_term = self._get_solar_term_index(solar_lon)
            is_boundary, boundary_reason = self._is_near_boundary(solar_lon)
            
            cal_year = year
            if month <= 2:
                if solar_idx <= 1:
                    cal_year = year - 1
            
            year_gan_idx = (cal_year - 4) % 10
            year_ji_idx = (cal_year - 4) % 12
            
            month_ji_idx = solar_idx
            start_gan_idx = (year_gan_idx % 5) * 2 + 2
            gap = month_ji_idx - 2
            if gap < 0:
                gap += 12
            month_gan_idx = (start_gan_idx + gap) % 10
            
            target_dt = datetime(year, month, day)
            days_diff = (target_dt - self.ANCHOR_DATE).days
            curr_day_idx = (self.ANCHOR_IDX + days_diff) % 60
            day_gan_idx = curr_day_idx % 10
            day_ji_idx = curr_day_idx % 12
            
            hour_gan_idx = None
            hour_ji_idx = None
            hour_range = None
            
            if hour is not None:
                adjusted_minute = hour * 60 + minute
                if use_solar_time:
                    adjusted_minute -= 30
                    if adjusted_minute < 0:
                        adjusted_minute += 1440
                
                eff_hour = adjusted_minute // 60
                hour_ji_idx = ((eff_hour + 1) // 2) % 12
                start_time_gan = (day_gan_idx % 5) * 2
                hour_gan_idx = (start_time_gan + hour_ji_idx) % 10
                
                h_opt = HOUR_OPTIONS[hour_ji_idx]
                hour_range = f"{h_opt['start']}~{h_opt['end']}"
            
            return {
                "year_pillar": self._make_pillar(year_gan_idx, year_ji_idx),
                "month_pillar": self._make_pillar(month_gan_idx, month_ji_idx),
                "day_pillar": self._make_pillar(day_gan_idx, day_ji_idx),
                "hour_pillar": self._make_pillar(hour_gan_idx, hour_ji_idx) if hour is not None else None,
                "hour_range": hour_range,
                "day_master": GAN[day_gan_idx],
                "day_master_element": GAN_TO_ELEMENT[GAN[day_gan_idx]],
                "day_master_description": DAY_MASTER_DESC[GAN[day_gan_idx]],
                "meta": {
                    "solar_time_applied": use_solar_time,
                    "solar_longitude_deg": round(solar_lon, 2),
                    "solar_term_idx": solar_idx,
                    "solar_term_name": solar_term,
                    "is_boundary": is_boundary,
                    "boundary_reason": boundary_reason,
                    "calculation_method": "ephem_astronomical",
                    "timezone": "Asia/Seoul"
                }
            }
            
        except Exception as e:
            raise CalculationError(f"사주 계산 실패: {str(e)}")
    
    def _make_pillar(self, gan_idx: int, ji_idx: int) -> Dict[str, Any]:
        return {
            "ganji": GAN[gan_idx] + JI[ji_idx],
            "gan": GAN[gan_idx],
            "ji": JI[ji_idx],
            "gan_hanja": GAN_HANJA[gan_idx],
            "ji_hanja": JI_HANJA[ji_idx],
            "gan_element": GAN_TO_ELEMENT[GAN[gan_idx]],
            "ji_element": JI_TO_ELEMENT[JI[ji_idx]],
            "gan_index": gan_idx,
            "ji_index": ji_idx
        }
    
    @staticmethod
    def get_hour_options():
        return [
            {
                "index": h["index"],
                "ji": h["ji"],
                "ji_hanja": h["ji_hanja"],
                "range_start": h["start"],
                "range_end": h["end"],
                "label": f"{h['ji_hanja']}시 ({h['ji']}시) - {h['start']}~{h['end']}"
            }
            for h in HOUR_OPTIONS
        ]


# ============ 싱글톤 인스턴스 ============

scientific_engine = None
if EPHEM_AVAILABLE:
    scientific_engine = ScientificSajuEngine()


# ============ 테스트 ============

def run_tests():
    """회귀 테스트"""
    if not EPHEM_AVAILABLE:
        print("❌ ephem 미설치")
        return False
    
    engine = ScientificSajuEngine()
    passed = True
    
    print("=" * 60)
    print("🧪 Saju Engine v3 - Tests")
    print("=" * 60)
    
    # Test 1
    res = engine.calculate(1978, 5, 16, 11, 0, use_solar_time=True)
    print(f"\n[1978-05-16 11:00]")
    print(f"  년: {res['year_pillar']['ganji']} | 월: {res['month_pillar']['ganji']} | 일: {res['day_pillar']['ganji']} | 시: {res['hour_pillar']['ganji']}")
    
    if (res['year_pillar']['ganji'] == '무오' and
        res['month_pillar']['ganji'] == '정사' and
        res['day_pillar']['ganji'] == '무인' and
        res['hour_pillar']['ganji'] == '정사'):
        print("  ✅ PASS")
    else:
        print("  ❌ FAIL")
        passed = False
    
    # Test 2
    res2 = engine.calculate(2000, 1, 1, 12, 0)
    print(f"\n[2000-01-01 Anchor]")
    print(f"  일주: {res2['day_pillar']['ganji']}")
    
    if res2['day_pillar']['ganji'] == '무오':
        print("  ✅ PASS")
    else:
        print("  ❌ FAIL")
        passed = False
    
    # Test 3: 오늘 날짜
    today = SajuManager.get_today_string()
    print(f"\n[오늘 날짜 (KST)]")
    print(f"  {today}")
    print("  ✅ datetime.now() 정상 작동")
    
    print("\n" + "=" * 60)
    print("🎉 ALL TESTS PASSED" if passed else "❌ SOME TESTS FAILED")
    print("=" * 60)
    
    return passed


if __name__ == "__main__":
    run_tests()
