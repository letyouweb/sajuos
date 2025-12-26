/**
 * Railway 백엔드 API 통신 모듈
 * - 99,000원 프리미엄 리포트: 10분 타임아웃 (순차 처리)
 */

import type {
  CalculateRequest,
  CalculateResponse,
  InterpretRequest,
  InterpretResponse,
  HourOption,
  ConcernOption,
} from '@/types';

// ============ 환경변수 ============

function getApiBaseUrl(): string {
  const url = process.env.NEXT_PUBLIC_API_URL;
  if (!url) {
    if (process.env.NODE_ENV === 'development') {
      return 'http://localhost:8000';
    }
    return 'https://api.sajuos.com';
  }
  return url;
}

const API_BASE_URL = getApiBaseUrl();

// ============ 공통 Fetch ============

interface FetchOptions {
  method?: 'GET' | 'POST';
  body?: unknown;
  timeout?: number;
}

async function fetchApi<T>(
  endpoint: string,
  options: FetchOptions = {}
): Promise<T> {
  const { method = 'GET', body, timeout = 30000 } = options;
  const fullUrl = `${API_BASE_URL}${endpoint}`;
  
  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), timeout);
  
  try {
    const response = await fetch(fullUrl, {
      method,
      headers: { 'Content-Type': 'application/json' },
      body: body ? JSON.stringify(body) : undefined,
      signal: controller.signal,
    });
    
    clearTimeout(timeoutId);
    
    if (!response.ok) {
      const errorData = await response.json().catch(() => ({}));
      const errorMessage = 
        errorData.message || 
        errorData.detail?.message || 
        errorData.detail ||
        `서버 오류 (${response.status})`;
      throw new Error(errorMessage);
    }
    
    return await response.json();
    
  } catch (error) {
    clearTimeout(timeoutId);
    
    if (error instanceof Error) {
      if (error.name === 'AbortError') {
        throw new Error('프리미엄 보고서 생성 중입니다. 최대 10분까지 소요될 수 있습니다. 잠시만 기다려주세요.');
      }
      if (error.message.includes('fetch') || error.message.includes('Failed')) {
        throw new Error('서버에 연결할 수 없습니다. 네트워크 연결을 확인해주세요.');
      }
      throw error;
    }
    
    throw new Error('알 수 없는 오류가 발생했습니다.');
  }
}

// ============ API 함수들 ============

/**
 * 사주 계산 API
 */
export async function calculateSaju(
  data: CalculateRequest
): Promise<CalculateResponse> {
  return fetchApi<CalculateResponse>(
    '/api/v1/calculate',
    { method: 'POST', body: data, timeout: 15000 }
  );
}

/**
 * 99,000원 프리미엄 비즈니스 컨설팅 보고서 API
 * - 7개 섹션 순차 생성 (안정성 우선)
 * - 최대 10분 소요 (600초)
 */
export async function interpretSaju(
  data: InterpretRequest
): Promise<InterpretResponse> {
  const result = await fetchApi<InterpretResponse>(
    '/api/v1/generate-report?mode=premium',
    { 
      method: 'POST', 
      body: data, 
      timeout: 600000 // 10분 (순차 처리 대응)
    }
  );
  
  // 레거시 폴백 체크
  if ((result as any).model_used === 'fallback') {
    throw new Error('AI 해석 서비스에 일시적인 문제가 발생했습니다.');
  }
  
  return result;
}

/**
 * 단일 섹션 재생성 API (Sprint 복구용)
 */
export async function regenerateSection(
  data: InterpretRequest,
  sectionId: string
): Promise<any> {
  return fetchApi<any>(
    `/api/v1/regenerate-section?section_id=${sectionId}`,
    { 
      method: 'POST', 
      body: data, 
      timeout: 120000 // 2분
    }
  );
}

/**
 * 시간대 옵션 조회
 */
export async function getHourOptions(): Promise<HourOption[]> {
  return fetchApi<HourOption[]>(
    '/api/v1/calculate/hour-options',
    { timeout: 10000 }
  );
}

/**
 * 고민 유형 (로컬)
 */
export function getConcernTypes(): { concern_types: ConcernOption[] } {
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
 */
export async function healthCheck(): Promise<{ status: string }> {
  return fetchApi<{ status: string }>('/health', { timeout: 5000 });
}

/**
 * 연결 테스트
 */
export async function testConnection(): Promise<{
  success: boolean;
  apiUrl: string;
  error?: string;
}> {
  try {
    await healthCheck();
    return { success: true, apiUrl: API_BASE_URL };
  } catch (error) {
    return {
      success: false,
      apiUrl: API_BASE_URL,
      error: error instanceof Error ? error.message : '알 수 없는 오류'
    };
  }
}
