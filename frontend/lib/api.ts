// API 통신 함수 - Railway 백엔드 직접 호출
// CORS 설정 필수: Railway에서 sajuqueen.com 허용해야 함

import type {
  CalculateRequest,
  CalculateResponse,
  InterpretRequest,
  InterpretResponse,
  HourOption,
} from '@/types';

// 백엔드 URL (Railway)
const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

/**
 * 사주 계산 API
 * POST ${API_BASE_URL}/api/v1/calculate
 */
export async function calculateSaju(
  data: CalculateRequest
): Promise<CalculateResponse> {
  const response = await fetch(`${API_BASE_URL}/api/v1/calculate`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify(data),
  });

  if (!response.ok) {
    const errorData = await response.json().catch(() => ({}));
    throw new Error(errorData.message || errorData.detail?.message || '사주 계산에 실패했습니다.');
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
 * POST ${API_BASE_URL}/api/v1/interpret
 */
export async function interpretSaju(
  data: InterpretRequest
): Promise<InterpretResponse> {
  const response = await fetch(`${API_BASE_URL}/api/v1/interpret`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify(data),
  });

  if (!response.ok) {
    const errorData = await response.json().catch(() => ({}));
    throw new Error(errorData.message || errorData.detail?.message || '사주 해석에 실패했습니다.');
  }

  return response.json();
}

/**
 * 시간대 옵션 조회
 * GET ${API_BASE_URL}/api/v1/calculate/hour-options
 */
export async function getHourOptions(): Promise<HourOption[]> {
  const response = await fetch(`${API_BASE_URL}/api/v1/calculate/hour-options`);
  
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
 * GET ${API_BASE_URL}/health
 */
export async function healthCheck(): Promise<{ status: string }> {
  const response = await fetch(`${API_BASE_URL}/health`);
  return response.json();
}
