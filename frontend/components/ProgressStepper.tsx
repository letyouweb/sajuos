'use client';

import { useEffect, useRef, useState, useCallback } from 'react';

// ===== 타입 정의 =====

export interface SectionProgress {
  id: string;
  title: string;
  status: 'pending' | 'running' | 'retry' | 'done' | 'error';
  attempt: number;
  max_attempts: number;
  elapsed_ms: number;
  char_count: number;
  error_message: string | null;
  stage: string;
}

export interface JobProgress {
  job_id: string;
  status: 'queued' | 'processing' | 'completed' | 'failed';
  overall: {
    total: number;
    done: number;
    percent: number;
  };
  current: {
    section_id: string | null;
    stage: string;
    attempt: number;
    max_attempts: number;
  } | null;
  sections: SectionProgress[];
  eta_sec: number;
  error_message: string | null;
}

// ===== 유틸 함수 =====

const formatEta = (sec: number): string => {
  if (sec < 60) return `약 ${sec}초`;
  const min = Math.floor(sec / 60);
  const remainSec = sec % 60;
  if (remainSec === 0) return `약 ${min}분`;
  return `약 ${min}분 ${remainSec}초`;
};

const getStageText = (stage: string): string => {
  const stageMap: Record<string, string> = {
    initializing: '초기화 중...',
    openai_request: 'AI 요청 전송 중...',
    openai_wait: 'AI 응답 대기 중...',
    validating: '응답 검증 중...',
    guardrail_check: '품질 검사 중...',
    completing: '완료 처리 중...',
    completed: '완료',
    error: '오류 발생',
    retry_rate_limit_429: '⏳ 요청 제한 - 재시도 대기',
    retry_api_error: '⏳ API 오류 - 재시도 대기',
    retry_json_parse_error: '⏳ 응답 파싱 오류 - 재시도',
  };
  return stageMap[stage] || stage;
};

// ===== Hook: SSE 연결 =====

interface UseReportProgressOptions {
  onComplete?: (result: any) => void;
  onError?: (error: string) => void;
}

export function useReportProgress(
  jobId: string | null,
  options: UseReportProgressOptions = {}
) {
  const [progress, setProgress] = useState<JobProgress | null>(null);
  const [isConnected, setIsConnected] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const eventSourceRef = useRef<EventSource | null>(null);
  const { onComplete, onError } = options;

  const connect = useCallback(() => {
    if (!jobId) return;

    const apiUrl = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';
    const url = `${apiUrl}/api/v1/report-progress/stream?job_id=${jobId}`;

    const eventSource = new EventSource(url);
    eventSourceRef.current = eventSource;

    eventSource.onopen = () => {
      setIsConnected(true);
      setError(null);
    };

    eventSource.addEventListener('progress', (event) => {
      try {
        const data: JobProgress = JSON.parse(event.data);
        setProgress(data);
      } catch (e) {
        console.error('Progress parse error:', e);
      }
    });

    eventSource.addEventListener('complete', async (event) => {
      try {
        const data = JSON.parse(event.data);
        // 결과 fetch
        const resultUrl = `${apiUrl}/api/v1/report-result?job_id=${data.job_id}`;
        const response = await fetch(resultUrl);
        const result = await response.json();
        
        if (result.status === 'completed' && result.result) {
          onComplete?.(result.result);
        } else if (result.status === 'failed') {
          onError?.(result.error || '리포트 생성 실패');
        }
      } catch (e) {
        console.error('Complete handler error:', e);
      } finally {
        eventSource.close();
        setIsConnected(false);
      }
    });

    eventSource.addEventListener('error', (event) => {
      try {
        const data = JSON.parse((event as any).data);
        setError(data.error);
        onError?.(data.error);
      } catch {
        // SSE 연결 오류
        console.error('SSE connection error');
      }
    });

    eventSource.onerror = () => {
      // 자동 재연결 시도
      setIsConnected(false);
    };

    return () => {
      eventSource.close();
    };
  }, [jobId, onComplete, onError]);

  useEffect(() => {
    const cleanup = connect();
    return cleanup;
  }, [connect]);

  const disconnect = useCallback(() => {
    eventSourceRef.current?.close();
    setIsConnected(false);
  }, []);

  return { progress, isConnected, error, disconnect };
}

// ===== 컴포넌트: 섹션 스테퍼 아이템 =====

interface StepperItemProps {
  section: SectionProgress;
  isActive: boolean;
  index: number;
}

function StepperItem({ section, isActive, index }: StepperItemProps) {
  const statusColors = {
    pending: 'bg-slate-100 text-slate-400 border-slate-200',
    running: 'bg-purple-50 text-purple-600 border-purple-300 animate-pulse',
    retry: 'bg-amber-50 text-amber-600 border-amber-300',
    done: 'bg-emerald-50 text-emerald-600 border-emerald-300',
    error: 'bg-red-50 text-red-600 border-red-300',
  };

  const statusIcons = {
    pending: '○',
    running: '◉',
    retry: '↻',
    done: '✓',
    error: '✗',
  };

  return (
    <div
      className={`
        flex items-center gap-3 p-3 rounded-lg border-2 transition-all duration-300
        ${statusColors[section.status]}
        ${isActive ? 'ring-2 ring-purple-400 ring-offset-2' : ''}
      `}
    >
      {/* 인덱스 + 아이콘 */}
      <div className="flex-shrink-0 w-8 h-8 rounded-full bg-white flex items-center justify-center font-bold text-sm border">
        {section.status === 'done' ? (
          <span className="text-emerald-500">✓</span>
        ) : section.status === 'error' ? (
          <span className="text-red-500">✗</span>
        ) : section.status === 'retry' ? (
          <span className="text-amber-500 animate-spin">↻</span>
        ) : section.status === 'running' ? (
          <span className="text-purple-500 animate-pulse">●</span>
        ) : (
          <span className="text-slate-400">{index + 1}</span>
        )}
      </div>

      {/* 내용 */}
      <div className="flex-1 min-w-0">
        <div className="font-medium text-sm truncate">{section.title}</div>
        
        {/* 상태 텍스트 */}
        {section.status === 'running' && (
          <div className="text-xs opacity-75">{getStageText(section.stage)}</div>
        )}
        
        {section.status === 'retry' && (
          <div className="text-xs">
            {section.error_message || `재시도 중 (${section.attempt}/${section.max_attempts})`}
          </div>
        )}
        
        {section.status === 'done' && section.elapsed_ms > 0 && (
          <div className="text-xs opacity-75">
            {(section.elapsed_ms / 1000).toFixed(1)}초 | {section.char_count.toLocaleString()}자
          </div>
        )}
        
        {section.status === 'error' && (
          <div className="text-xs">{section.error_message || '오류 발생'}</div>
        )}
      </div>
    </div>
  );
}

// ===== 메인 컴포넌트: ProgressStepper =====

interface ProgressStepperProps {
  jobId: string | null;
  onComplete: (result: any) => void;
  onError: (error: string) => void;
}

export default function ProgressStepper({ jobId, onComplete, onError }: ProgressStepperProps) {
  const { progress, isConnected, error } = useReportProgress(jobId, {
    onComplete,
    onError,
  });

  if (error) {
    return (
      <div className="bg-red-50 border border-red-200 rounded-xl p-6 text-center">
        <div className="text-4xl mb-3">⚠️</div>
        <div className="text-red-700 font-medium">연결 오류</div>
        <div className="text-red-600 text-sm mt-1">{error}</div>
      </div>
    );
  }

  if (!progress) {
    return (
      <div className="flex flex-col items-center justify-center py-12">
        <div className="w-12 h-12 border-4 border-purple-200 border-t-purple-600 rounded-full animate-spin mb-4" />
        <div className="text-slate-600">연결 중...</div>
      </div>
    );
  }

  const { overall, current, sections, eta_sec, status } = progress;

  return (
    <div className="bg-white rounded-2xl shadow-lg border border-slate-200 overflow-hidden">
      {/* 헤더: 전체 진행률 */}
      <div className="bg-gradient-to-r from-purple-600 to-indigo-600 text-white p-6">
        <div className="flex items-center justify-between mb-3">
          <div className="flex items-center gap-2">
            <span className="text-2xl">🔮</span>
            <span className="font-bold text-lg">사주 분석 중</span>
          </div>
          <div className="text-right">
            <div className="text-3xl font-bold">{overall.percent}%</div>
            <div className="text-purple-200 text-sm">
              {overall.done}/{overall.total} 섹션
            </div>
          </div>
        </div>

        {/* 프로그레스 바 */}
        <div className="h-3 bg-white/20 rounded-full overflow-hidden">
          <div
            className="h-full bg-white rounded-full transition-all duration-500 ease-out"
            style={{ width: `${overall.percent}%` }}
          />
        </div>

        {/* 현재 상태 + ETA */}
        <div className="flex items-center justify-between mt-3 text-sm">
          <div className="text-purple-100">
            {current?.section_id ? (
              <>
                <span className="font-medium">
                  {sections.find(s => s.id === current.section_id)?.title}
                </span>
                <span className="ml-2 opacity-75">{getStageText(current.stage)}</span>
              </>
            ) : (
              '대기 중...'
            )}
          </div>
          <div className="text-purple-200">
            남은 시간: {formatEta(eta_sec)}
          </div>
        </div>
      </div>

      {/* 섹션 목록 */}
      <div className="p-4 space-y-2 max-h-96 overflow-y-auto">
        {sections.map((section, index) => (
          <StepperItem
            key={section.id}
            section={section}
            isActive={current?.section_id === section.id}
            index={index}
          />
        ))}
      </div>

      {/* 푸터: 안내 메시지 */}
      <div className="bg-slate-50 border-t border-slate-200 p-4">
        <div className="flex items-start gap-3 text-sm text-slate-600">
          <span className="text-lg">💡</span>
          <div>
            <p className="font-medium">잠깐! 창을 닫아도 괜찮아요</p>
            <p className="text-slate-500 mt-1">
              백그라운드에서 생성 중입니다. 같은 링크로 언제든 다시 확인할 수 있어요.
            </p>
          </div>
        </div>
      </div>

      {/* 연결 상태 표시 */}
      <div className="px-4 pb-4">
        <div className="flex items-center gap-2 text-xs text-slate-400">
          <div className={`w-2 h-2 rounded-full ${isConnected ? 'bg-emerald-400' : 'bg-slate-300'}`} />
          {isConnected ? '실시간 연결됨' : '재연결 중...'}
        </div>
      </div>
    </div>
  );
}
