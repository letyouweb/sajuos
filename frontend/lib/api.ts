// API 통신 함수 - 재설계 버전

import type {
  CalculateRequest,
  CalculateResponse,
  InterpretRequest,
  InterpretResponse,
  HourOption,
} from '@/types';

const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

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
    throw new Error(errorData.message || '사주 계산에 실패했습니다.');
  }

  const result = await response.json();
  
  // fallback 결과면 에러 처리
  if (result.calculation_method === 'fallback') {
    throw new Error('사주 계산 정확도가 보장되지 않습니다. 다시 시도해주세요.');
  }

  return result;
}

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
    throw new Error(errorData.message || '사주 해석에 실패했습니다.');
  }

  return response.json();
}

export async function getHourOptions(): Promise<HourOption[]> {
  const response = await fetch(`${API_BASE_URL}/api/v1/calculate/hour-options`);
  
  if (!response.ok) {
    throw new Error('시간대 옵션을 불러오지 못했습니다.');
  }

  return response.json();
}

export async function getConcernTypes(): Promise<{
  concern_types: Array<{ value: string; label: string; emoji: string }>;
}> {
  const response = await fetch(`${API_BASE_URL}/api/v1/interpret/concern-types`);
  
  if (!response.ok) {
    throw new Error('고민 유형을 불러오지 못했습니다.');
  }

  return response.json();
}

export async function healthCheck(): Promise<{ status: string }> {
  const response = await fetch(`${API_BASE_URL}/health`);
  return response.json();
}
