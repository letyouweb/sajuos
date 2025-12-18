// API 통신 함수 - Next.js API Route 프록시 사용
// 브라우저는 자기 도메인(/api/saju/...)만 호출 → CORS 문제 없음

import type {
  CalculateRequest,
  CalculateResponse,
  InterpretRequest,
  InterpretResponse,
  HourOption,
} from '@/types';

/**
 * 사주 계산 API
 * POST /api/saju/calculate → 백엔드 /api/v1/calculate 프록시
 */
export async function calculateSaju(
  data: CalculateRequest
): Promise<CalculateResponse> {
  const response = await fetch('/api/saju/calculate', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify(data),
  });

  if (!response.ok) {
    const errorData = await response.json().catch(() => ({}));
    throw new Error(errorData.message || '사주 계산에 실패했습니다.');
  }

  const result = await response.json();
  
  // fallback 결과면 에러 처리
  if (result.calculation_method === 'fallback') {
    throw new Error('사주 계산 정확도가 보장되지 않습니다. 다시 시도해주세요.');
  }

  return result;
}

/**
 * 사주 해석 API
 * POST /api/saju/interpret → 백엔드 /api/v1/interpret 프록시
 */
export async function interpretSaju(
  data: InterpretRequest
): Promise<InterpretResponse> {
  const response = await fetch('/api/saju/interpret', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify(data),
  });

  if (!response.ok) {
    const errorData = await response.json().catch(() => ({}));
    throw new Error(errorData.message || '사주 해석에 실패했습니다.');
  }

  return response.json();
}

/**
 * 시간대 옵션 조회
 * GET /api/saju/hour-options → 백엔드 /api/v1/calculate/hour-options 프록시
 */
export async function getHourOptions(): Promise<HourOption[]> {
  const response = await fetch('/api/saju/hour-options');
  
  if (!response.ok) {
    throw new Error('시간대 옵션을 불러오지 못했습니다.');
  }

  return response.json();
}

/**
 * 고민 유형 조회 (로컬 데이터 - 백엔드 호출 안 함)
 */
export async function getConcernTypes(): Promise<{
  concern_types: Array<{ value: string; label: string; emoji: string }>;
}> {
  // 로컬에서 직접 반환 (백엔드 호출 불필요)
  return {
    concern_types: [
      { value: 'love', label: '연애/결혼', emoji: '💕' },
      { value: 'wealth', label: '재물/금전', emoji: '💰' },
      { value: 'career', label: '직장/사업', emoji: '💼' },
      { value: 'health', label: '건강', emoji: '🏥' },
      { value: 'study', label: '학업/시험', emoji: '📚' },
      { value: 'general', label: '종합/기타', emoji: '🔮' },
    ]
  };
}

/**
 * 헬스체크
 * GET /api/health → 백엔드 /health 프록시
 */
export async function healthCheck(): Promise<{ status: string }> {
  const response = await fetch('/api/health');
  return response.json();
}
