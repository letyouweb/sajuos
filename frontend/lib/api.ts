/**
 * Railway 백엔드 API 통신 모듈
 * 
 * 아키텍처:
 * - Vercel (프론트엔드) → Railway (백엔드) 직접 통신
 * - CORS: Railway에서 sajuos.com 허용 설정됨
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
      console.warn('⚠️ NEXT_PUBLIC_API_URL 미설정 → localhost:8000 사용');
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
        throw new Error('서버 응답 시간이 초과되었습니다. 잠시 후 다시 시도해주세요.');
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
 * POST /api/v1/calculate
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
 * 프리미엄 30페이지 보고서 생성 API
 * POST /api/v1/generate-report
 * 
 * 7개 섹션 병렬 생성 (약 2~3분 소요)
 */
export async function interpretSaju(
  data: InterpretRequest
): Promise<InterpretResponse> {
  const result = await fetchApi<InterpretResponse>(
    '/api/v1/generate-report',
    { 
      method: 'POST', 
      body: data, 
      timeout: 300000 // 5분 (7섹션 병렬 생성 대응)
    }
  );
  
  // 레거시 폴백 응답 체크
  if ((result as any).model_used === 'fallback') {
    throw new Error('AI 해석 서비스에 일시적인 문제가 발생했습니다. 잠시 후 다시 시도해주세요.');
  }
  
  return result;
}

/**
 * 시간대 옵션 조회
 * GET /api/v1/calculate/hour-options
 */
export async function getHourOptions(): Promise<HourOption[]> {
  return fetchApi<HourOption[]>(
    '/api/v1/calculate/hour-options',
    { timeout: 10000 }
  );
}

/**
 * 고민 유형 조회 (로컬 데이터)
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
 * GET /health
 */
export async function healthCheck(): Promise<{ status: string }> {
  return fetchApi<{ status: string }>('/health', { timeout: 5000 });
}

/**
 * API 연결 테스트 (디버깅용)
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
