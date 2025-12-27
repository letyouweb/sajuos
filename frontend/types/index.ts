// 사주 API 타입 정의 - 재설계 버전

export interface Pillar {
  gan: string;
  ji: string;
  ganji: string;
  gan_element: string;
  ji_element: string;
  gan_index?: number;
  ji_index?: number;
}

export interface SajuWonGuk {
  year_pillar: Pillar;
  month_pillar: Pillar;
  day_pillar: Pillar;
  hour_pillar: Pillar | null;
}

export interface DaeunInfo {
  start_age: number;
  direction: 'forward' | 'backward';
  current_daeun: string | null;
}

export interface QualityInfo {
  has_birth_time: boolean;
  solar_term_boundary: boolean;
  boundary_reason: string | null;
  timezone: string;
  calculation_method: string;
}

export interface CalculateRequest {
  birth_year: number;
  birth_month: number;
  birth_day: number;
  birth_hour?: number | null;
  birth_minute?: number;
  gender?: 'male' | 'female' | 'other';
  timezone?: string;
}

export interface CalculateResponse {
  success: boolean;
  birth_info: string;
  saju: SajuWonGuk;
  day_master: string;
  day_master_element: string;
  day_master_description: string;
  daeun: DaeunInfo | null;
  quality: QualityInfo;
  is_boundary_date: boolean;
  boundary_warning: string | null;
  calculation_method: string;
}

export interface HourOption {
  index: number;
  ji: string;
  ji_hanja: string;
  range_start: string;
  range_end: string;
  label: string;
}

export interface InterpretRequest {
  saju_result?: CalculateResponse;
  year_pillar?: string;
  month_pillar?: string;
  day_pillar?: string;
  hour_pillar?: string;
  name: string;
  gender?: 'male' | 'female' | 'other';
  concern_type: ConcernType;
  question: string;
}

export interface InterpretResponse {
  success: boolean;
  summary: string;
  structure?: Record<string, unknown>;
  day_master_analysis: string;
  strengths: string[];
  risks: string[];
  answer: string;
  action_plan: string[];
  lucky_periods: string[];
  caution_periods: string[];
  lucky_elements: {
    color?: string;
    direction?: string;
    number?: string;
  } | null;
  blessing: string;
  disclaimer: string;
  model_used: string;
  tokens_used: number | null;
}

export type ConcernType = 'love' | 'wealth' | 'career' | 'health' | 'study' | 'general';

export interface ConcernOption {
  value: ConcernType;
  label: string;
  emoji: string;
}

export const CONCERN_OPTIONS: ConcernOption[] = [
  { value: 'love', label: '연애/결혼', emoji: '💕' },
  { value: 'wealth', label: '재물/금전', emoji: '💰' },
  { value: 'career', label: '직장/사업', emoji: '💼' },
  { value: 'health', label: '건강', emoji: '🏥' },
  { value: 'study', label: '학업/시험', emoji: '📚' },
  { value: 'general', label: '종합운세', emoji: '🔮' },
];

// 시간대 옵션 (2시간 단위)
export const HOUR_OPTIONS: HourOption[] = [
  { index: 0, ji: '자', ji_hanja: '子', range_start: '23:00', range_end: '00:59', label: '子시 (23:00~00:59)' },
  { index: 1, ji: '축', ji_hanja: '丑', range_start: '01:00', range_end: '02:59', label: '丑시 (01:00~02:59)' },
  { index: 2, ji: '인', ji_hanja: '寅', range_start: '03:00', range_end: '04:59', label: '寅시 (03:00~04:59)' },
  { index: 3, ji: '묘', ji_hanja: '卯', range_start: '05:00', range_end: '06:59', label: '卯시 (05:00~06:59)' },
  { index: 4, ji: '진', ji_hanja: '辰', range_start: '07:00', range_end: '08:59', label: '辰시 (07:00~08:59)' },
  { index: 5, ji: '사', ji_hanja: '巳', range_start: '09:00', range_end: '10:59', label: '巳시 (09:00~10:59)' },
  { index: 6, ji: '오', ji_hanja: '午', range_start: '11:00', range_end: '12:59', label: '午시 (11:00~12:59)' },
  { index: 7, ji: '미', ji_hanja: '未', range_start: '13:00', range_end: '14:59', label: '未시 (13:00~14:59)' },
  { index: 8, ji: '신', ji_hanja: '申', range_start: '15:00', range_end: '16:59', label: '申시 (15:00~16:59)' },
  { index: 9, ji: '유', ji_hanja: '酉', range_start: '17:00', range_end: '18:59', label: '酉시 (17:00~18:59)' },
  { index: 10, ji: '술', ji_hanja: '戌', range_start: '19:00', range_end: '20:59', label: '戌시 (19:00~20:59)' },
  { index: 11, ji: '해', ji_hanja: '亥', range_start: '21:00', range_end: '22:59', label: '亥시 (21:00~22:59)' },
];

// 시간대 인덱스 → 대표 시간 (API 전송용)
export function getHourFromJiIndex(jiIndex: number): number {
  const hourMap: Record<number, number> = {
    0: 0,   // 자시 → 0시
    1: 1,   // 축시 → 1시
    2: 3,   // 인시 → 3시
    3: 5,   // 묘시 → 5시
    4: 7,   // 진시 → 7시
    5: 9,   // 사시 → 9시
    6: 11,  // 오시 → 11시
    7: 13,  // 미시 → 13시
    8: 15,  // 신시 → 15시
    9: 17,  // 유시 → 17시
    10: 19, // 술시 → 19시
    11: 21, // 해시 → 21시
  };
  return hourMap[jiIndex] ?? 12;
}

// 정확도 배지 타입
export type AccuracyBadge = 'high' | 'boundary' | 'no_time';

export function getAccuracyBadge(quality?: QualityInfo | null): AccuracyBadge {
  // 🔥 P0: null-safe 처리
  if (!quality) return 'no_time';
  
  if (quality.solar_term_boundary) {
    return 'boundary';
  }
  if (!quality.has_birth_time) {
    return 'no_time';
  }
  return 'high';
}

export function getAccuracyBadgeInfo(badge: AccuracyBadge) {
  switch (badge) {
    case 'high':
      return {
        icon: '✅',
        label: '정확도: 높음',
        color: 'green',
        tooltip: '절기 경계일이 아니며, 출생시간이 반영되었습니다.',
      };
    case 'boundary':
      return {
        icon: '⚠️',
        label: '정확도: 경계일',
        color: 'yellow',
        tooltip: '절기(입절) 경계에 가까워 월주/연주가 바뀔 수 있습니다. 출생시간을 입력하면 정확도가 올라갑니다.',
      };
    case 'no_time':
      return {
        icon: 'ℹ️',
        label: '정확도: 시간 미입력',
        color: 'blue',
        tooltip: '출생시간이 없으면 시주(시기운) 분석은 생략되거나 일반화됩니다.',
      };
  }
}
