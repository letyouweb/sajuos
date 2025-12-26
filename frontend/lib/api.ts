/**
 * Railway 백엔드 API 통신 모듈 v2
 * ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
 * - Supabase 영구 저장 기반
 * - 탭 닫아도 백그라운드 진행
 * - 폴링 방식 진행 상태 조회
 * ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
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

export const API_BASE_URL = getApiBaseUrl();

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
        throw new Error('요청 시간이 초과되었습니다. 다시 시도해주세요.');
      }
      if (error.message.includes('fetch') || error.message.includes('Failed')) {
        throw new Error('서버에 연결할 수 없습니다. 네트워크 연결을 확인해주세요.');
      }
      throw error;
    }
    
    throw new Error('알 수 없는 오류가 발생했습니다.');
  }
}

// ============ 기본 API 함수들 ============

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


// ============ 🔥 프리미엄 리포트 API (Supabase 기반) ============

export interface ReportStartRequest {
  email: string;
  name?: string;
  saju_result?: CalculateResponse;
  year_pillar?: string;
  month_pillar?: string;
  day_pillar?: string;
  hour_pillar?: string;
  target_year?: number;
  question?: string;
  concern_type?: string;
}

export interface ReportStartResponse {
  success: boolean;
  report_id: string;
  status: string;
  message: string;
  status_url: string;
  result_url: string;
}

export interface ReportStatusResponse {
  report_id: string;
  status: 'pending' | 'generating' | 'completed' | 'failed';
  progress: number;
  current_step: string;
  sections: Array<{
    id: string;
    title: string;
    status: string;
    order: number;
    char_count: number;
    elapsed_ms: number;
    error: string | null;
  }>;
  error: string | null;
  created_at: string;
  updated_at: string;
}

export interface ReportResultResponse {
  completed: boolean;
  report_id?: string;
  result?: any;
  pdf_url?: string;
  generated_at?: string;
  generation_time_ms?: number;
  status?: string;
  progress?: number;
  message?: string;
  error?: string;  // 에러 메시지
  name?: string;
  target_year?: number;
}

/**
 * 🔥 프리미엄 리포트 생성 시작 (Supabase 저장)
 * - 즉시 report_id 반환
 * - 백그라운드에서 생성 (탭 닫아도 계속)
 * - 완료 시 이메일 발송
 */
export async function startReportGeneration(
  data: ReportStartRequest
): Promise<ReportStartResponse> {
  return fetchApi<ReportStartResponse>(
    '/api/reports/start',
    { method: 'POST', body: data, timeout: 30000 }
  );
}

/**
 * 리포트 진행 상태 조회 (폴링용)
 */
export async function getReportStatus(
  reportId: string
): Promise<ReportStatusResponse> {
  return fetchApi<ReportStatusResponse>(
    `/api/reports/${reportId}/status`,
    { timeout: 10000 }
  );
}

/**
 * 리포트 결과 조회
 */
export async function getReportResult(
  reportId: string,
  token?: string
): Promise<ReportResultResponse> {
  const tokenParam = token ? `?token=${token}` : '';
  return fetchApi<ReportResultResponse>(
    `/api/reports/${reportId}/result${tokenParam}`,
    { timeout: 10000 }
  );
}

/**
 * 토큰으로 리포트 조회 (이메일 링크용)
 */
export async function getReportByToken(
  accessToken: string
): Promise<ReportResultResponse> {
  return fetchApi<ReportResultResponse>(
    `/api/reports/view/${accessToken}`,
    { timeout: 10000 }
  );
}

/**
 * 실패한 리포트 재시도
 */
export async function retryReport(
  reportId: string
): Promise<{ success: boolean; message: string }> {
  return fetchApi<{ success: boolean; message: string }>(
    `/api/reports/${reportId}/retry`,
    { method: 'POST', timeout: 10000 }
  );
}


// ============ 레거시 API (호환성 유지) ============

/**
 * 레거시 동기 리포트 생성 (구버전 호환)
 * @deprecated startReportGeneration 사용 권장
 */
export async function interpretSaju(
  data: InterpretRequest
): Promise<InterpretResponse> {
  const result = await fetchApi<InterpretResponse>(
    '/api/v1/generate-report?mode=premium',
    { 
      method: 'POST', 
      body: data, 
      timeout: 600000 // 10분
    }
  );
  
  if ((result as any).model_used === 'fallback') {
    throw new Error('AI 해석 서비스에 일시적인 문제가 발생했습니다.');
  }
  
  return result;
}

/**
 * 단일 섹션 재생성 API
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
      timeout: 120000
    }
  );
}
