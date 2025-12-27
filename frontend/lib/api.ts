/**
 * Railway 백엔드 API 통신 모듈 v3
 * ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
 * 🔥 P0 수정:
 * - 절대주소 사용 (https://api.sajuos.com)
 * - /view/{job_id}?token={token} 형식
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

// ============ 🔥 환경변수 - 절대주소 강제 ============

// 🔥 P0 수정: api.sajuos.com 절대주소 사용
const PROD_API_URL = 'https://api.sajuos.com';
const DEV_API_URL = 'http://localhost:8000';

function getApiBaseUrl(): string {
  // 🔥 프로덕션 환경에서는 무조건 api.sajuos.com
  if (typeof window !== 'undefined' && window.location.hostname !== 'localhost') {
    return PROD_API_URL;
  }
  
  // 개발 환경에서만 환경변수 또는 localhost
  const url = process.env.NEXT_PUBLIC_API_URL;
  if (url) return url;
  
  return DEV_API_URL;
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
  
  console.log(`[API] ${method} ${fullUrl}`);  // 🔥 디버그 로그
  
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

export async function calculateSaju(
  data: CalculateRequest
): Promise<CalculateResponse> {
  return fetchApi<CalculateResponse>(
    '/api/v1/calculate',
    { method: 'POST', body: data, timeout: 15000 }
  );
}

export async function getHourOptions(): Promise<HourOption[]> {
  return fetchApi<HourOption[]>(
    '/api/v1/calculate/hour-options',
    { timeout: 10000 }
  );
}

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

export async function healthCheck(): Promise<{ status: string }> {
  return fetchApi<{ status: string }>('/health', { timeout: 5000 });
}

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


// ============ 🔥 프리미엄 리포트 API ============

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
  survey_data?: {
    industry?: string;
    business_stage?: string;
    monthly_revenue?: string;
    margin_percent?: number;
    cash_reserve?: string;
    primary_bottleneck?: string;
    goal_detail?: string;
    time_availability?: string;
    risk_tolerance?: string;
    urgent_question?: string;
  };
}

export interface ReportStartResponse {
  success: boolean;
  job_id: string;
  status: string;
  message: string;
  poll_url: string;
}

export interface ReportViewResponse {
  job_id: string;
  status: 'pending' | 'running' | 'completed' | 'failed';
  progress: number;
  result?: any;
  markdown?: string;
  error?: string;
}

/**
 * 🔥 프리미엄 리포트 생성 시작
 */
export async function startReportGeneration(
  data: ReportStartRequest
): Promise<ReportStartResponse> {
  return fetchApi<ReportStartResponse>(
    '/api/v1/reports/start',
    { method: 'POST', body: data, timeout: 30000 }
  );
}

/**
 * 🔥 P0 수정: job_id + token으로 리포트 조회
 * 엔드포인트: /api/v1/reports/view/{job_id}?token={token}
 */
export async function getReportByJobIdAndToken(
  jobId: string,
  token: string
): Promise<ReportViewResponse> {
  if (!jobId || !token) {
    throw new Error('job_id와 token이 필요합니다');
  }
  
  // 🔥 핵심: /view/{job_id}?token={token} 형식
  return fetchApi<ReportViewResponse>(
    `/api/v1/reports/view/${jobId}?token=${encodeURIComponent(token)}`,
    { timeout: 15000 }
  );
}

/**
 * 리포트 상태 조회 (폴링용, 토큰 옵션)
 */
export async function getReportStatus(
  jobId: string,
  token?: string
): Promise<ReportViewResponse> {
  const tokenParam = token ? `?token=${encodeURIComponent(token)}` : '';
  return fetchApi<ReportViewResponse>(
    `/api/v1/reports/${jobId}${tokenParam}`,
    { timeout: 10000 }
  );
}

/**
 * 리포트 결과 조회
 */
export async function getReportResult(
  jobId: string,
  token?: string
): Promise<ReportViewResponse> {
  const tokenParam = token ? `?token=${encodeURIComponent(token)}` : '';
  return fetchApi<ReportViewResponse>(
    `/api/v1/reports/${jobId}/result${tokenParam}`,
    { timeout: 10000 }
  );
}

/**
 * @deprecated getReportByJobIdAndToken 사용
 */
export async function getReportByToken(accessToken: string): Promise<ReportViewResponse> {
  // 레거시 호환: token만 있으면 job_id로 간주하고 에러
  console.warn('[API] getReportByToken is deprecated. Use getReportByJobIdAndToken instead.');
  throw new Error('job_id와 token이 모두 필요합니다. URL 형식: /report/{job_id}?token={token}');
}


// ============ 레거시 API ============

export async function interpretSaju(
  data: InterpretRequest
): Promise<InterpretResponse> {
  const result = await fetchApi<InterpretResponse>(
    '/api/v1/generate-report?mode=premium',
    { method: 'POST', body: data, timeout: 600000 }
  );
  
  if ((result as any).model_used === 'fallback') {
    throw new Error('AI 해석 서비스에 일시적인 문제가 발생했습니다.');
  }
  
  return result;
}

export async function regenerateSection(
  data: InterpretRequest,
  sectionId: string
): Promise<any> {
  return fetchApi<any>(
    `/api/v1/regenerate-section?section_id=${sectionId}`,
    { method: 'POST', body: data, timeout: 120000 }
  );
}
