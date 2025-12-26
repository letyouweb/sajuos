'use client';

import { useEffect, useRef, useState, useCallback } from 'react';

// ===== 타입 정의 =====

export interface SectionProgress {
  id: string;
  title: string;
  status: 'pending' | 'generating' | 'completed' | 'failed' | 'skipped';
  order: number;
  char_count: number;
  elapsed_ms: number;
  error: string | null;
}

export interface ReportStatus {
  report_id: string;
  status: 'pending' | 'generating' | 'completed' | 'failed';
  progress: number;  // 0-100
  current_step: string;
  sections: SectionProgress[];
  error: string | null;
  created_at: string;
  updated_at: string;
}

// ===== 유틸 함수 =====

const formatEta = (progress: number): string => {
  // 진행률 기반 남은 시간 추정 (평균 섹션당 60초)
  const remainingPercent = 100 - progress;
  const estimatedSec = Math.ceil(remainingPercent * 0.6 * 7); // 7섹션 기준
  
  if (estimatedSec < 60) return `약 ${estimatedSec}초`;
  const min = Math.floor(estimatedSec / 60);
  const sec = estimatedSec % 60;
  if (sec === 0) return `약 ${min}분`;
  return `약 ${min}분 ${sec}초`;
};

const getStatusText = (status: string): string => {
  const statusMap: Record<string, string> = {
    pending: '대기 중',
    generating: '분석 중',
    completed: '완료',
    failed: '실패',
    skipped: '스킵됨',
  };
  return statusMap[status] || status;
};

// 🔥 프리미엄 진행 메시지 변환
const getPremiumStepMessage = (step: string, sectionId?: string): string => {
  // 섹션별 프리미엄 메시지
  const sectionMessages: Record<string, string> = {
    'exec': '🎯 경영진 요약 - 핵심 인사이트 도출 중...',
    'money': '💰 재물운 분석 - 현금흐름 최적화 전략 수립 중...',
    'business': '📈 사업 전략 - 2026 성장 로드맵 설계 중...',
    'team': '👥 팀/파트너십 - 인재 운용 전략 분석 중...',
    'health': '⚡ 컨디션 관리 - 에너지 최적화 구간 분석 중...',
    'calendar': '📅 월별 액션 캘린더 - 골든타임 계산 중...',
    'sprint': '🚀 90일 스프린트 - 우선순위 체크리스트 생성 중...',
  };
  
  if (sectionId && sectionMessages[sectionId]) {
    return sectionMessages[sectionId];
  }
  
  // 기본 메시지 변환
  if (step.includes('초기화')) return '🔮 8,543장 룰카드 중 최적 100장 선별 중...';
  if (step.includes('RuleCards')) return '🔮 사주 데이터 기반 룰카드 매칭 중...';
  
  return step || '준비 중...';
};

const getStatusColor = (status: string): string => {
  const colorMap: Record<string, string> = {
    pending: 'bg-slate-100 text-slate-500 border-slate-200',
    generating: 'bg-purple-50 text-purple-600 border-purple-300 animate-pulse',
    completed: 'bg-emerald-50 text-emerald-600 border-emerald-300',
    failed: 'bg-red-50 text-red-600 border-red-300',
    skipped: 'bg-gray-50 text-gray-500 border-gray-200',
  };
  return colorMap[status] || colorMap.pending;
};

// ===== Hook: 폴링 기반 진행 상태 =====

interface UseReportPollingOptions {
  pollingInterval?: number;  // ms (기본 2500ms)
  onComplete?: (result: any) => void;
  onError?: (error: string) => void;
}

export function useReportPolling(
  reportId: string | null,
  options: UseReportPollingOptions = {}
) {
  const { pollingInterval = 2500, onComplete, onError } = options;
  
  const [status, setStatus] = useState<ReportStatus | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const pollingRef = useRef<NodeJS.Timeout | null>(null);

  const fetchStatus = useCallback(async () => {
    if (!reportId) return;
    
    const apiUrl = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';
    
    try {
      const response = await fetch(`${apiUrl}/api/v1/reports/${reportId}/status`);  // 🔥 통일
      
      if (!response.ok) {
        throw new Error(`상태 조회 실패: ${response.status}`);
      }
      
      const data: ReportStatus = await response.json();
      setStatus(data);
      setError(null);
      
      // 완료 또는 실패 시 폴링 중지
      if (data.status === 'completed') {
        if (pollingRef.current) {
          clearInterval(pollingRef.current);
          pollingRef.current = null;
        }
        
        // 결과 조회
        const resultResponse = await fetch(`${apiUrl}/api/v1/reports/${reportId}/result`);  // 🔥 통일
        const resultData = await resultResponse.json();
        
        if (resultData.completed && resultData.result) {
          onComplete?.(resultData.result);
        }
      } else if (data.status === 'failed') {
        if (pollingRef.current) {
          clearInterval(pollingRef.current);
          pollingRef.current = null;
        }
        onError?.(data.error || '리포트 생성 실패');
      }
      
    } catch (err) {
      const errorMsg = err instanceof Error ? err.message : '알 수 없는 오류';
      setError(errorMsg);
      console.error('Status polling error:', err);
    }
  }, [reportId, onComplete, onError]);

  // 폴링 시작/중지
  useEffect(() => {
    if (!reportId) {
      setStatus(null);
      return;
    }
    
    setIsLoading(true);
    
    // 즉시 첫 조회
    fetchStatus().finally(() => setIsLoading(false));
    
    // 폴링 시작
    pollingRef.current = setInterval(fetchStatus, pollingInterval);
    
    return () => {
      if (pollingRef.current) {
        clearInterval(pollingRef.current);
        pollingRef.current = null;
      }
    };
  }, [reportId, pollingInterval, fetchStatus]);

  const stopPolling = useCallback(() => {
    if (pollingRef.current) {
      clearInterval(pollingRef.current);
      pollingRef.current = null;
    }
  }, []);

  return { status, isLoading, error, stopPolling };
}

// ===== 컴포넌트: 섹션 스테퍼 아이템 =====

interface StepperItemProps {
  section: SectionProgress;
  isActive: boolean;
}

function StepperItem({ section, isActive }: StepperItemProps) {
  return (
    <div
      className={`
        flex items-center gap-3 p-3 rounded-lg border-2 transition-all duration-300
        ${getStatusColor(section.status)}
        ${isActive ? 'ring-2 ring-purple-400 ring-offset-2' : ''}
      `}
    >
      {/* 순서 + 상태 아이콘 */}
      <div className="flex-shrink-0 w-8 h-8 rounded-full bg-white flex items-center justify-center font-bold text-sm border">
        {section.status === 'completed' ? (
          <span className="text-emerald-500">✓</span>
        ) : section.status === 'failed' ? (
          <span className="text-red-500">✗</span>
        ) : section.status === 'generating' ? (
          <span className="text-purple-500 animate-pulse">●</span>
        ) : (
          <span className="text-slate-400">{section.order}</span>
        )}
      </div>

      {/* 섹션 정보 */}
      <div className="flex-1 min-w-0">
        <div className="font-medium text-sm truncate">{section.title}</div>
        
        {section.status === 'generating' && (
          <div className="text-xs opacity-75">AI 생성 중...</div>
        )}
        
        {section.status === 'completed' && section.elapsed_ms > 0 && (
          <div className="text-xs opacity-75">
            {(section.elapsed_ms / 1000).toFixed(1)}초 | {section.char_count.toLocaleString()}자
          </div>
        )}
        
        {section.status === 'failed' && section.error && (
          <div className="text-xs">{section.error.slice(0, 50)}...</div>
        )}
      </div>
    </div>
  );
}

// ===== 메인 컴포넌트: ProgressStepper =====

interface ProgressStepperProps {
  reportId: string | null;
  onComplete: (result: any) => void;
  onError: (error: string) => void;
}

export default function ProgressStepper({ reportId, onComplete, onError }: ProgressStepperProps) {
  const { status, isLoading, error } = useReportPolling(reportId, {
    onComplete,
    onError,
    pollingInterval: 2500,  // 2.5초 간격
  });

  if (error) {
    return (
      <div className="bg-red-50 border border-red-200 rounded-xl p-6 text-center">
        <div className="text-4xl mb-3">⚠️</div>
        <div className="text-red-700 font-medium">연결 오류</div>
        <div className="text-red-600 text-sm mt-1">{error}</div>
        <button 
          onClick={() => window.location.reload()}
          className="mt-4 px-4 py-2 bg-red-100 hover:bg-red-200 rounded-lg text-red-700 text-sm"
        >
          새로고침
        </button>
      </div>
    );
  }

  if (isLoading || !status) {
    return (
      <div className="flex flex-col items-center justify-center py-12">
        <div className="w-12 h-12 border-4 border-purple-200 border-t-purple-600 rounded-full animate-spin mb-4" />
        <div className="text-slate-600">리포트 상태 확인 중...</div>
      </div>
    );
  }

  const { progress, current_step, sections } = status;

  // 현재 활성 섹션 찾기
  const activeSection = sections.find(s => s.status === 'generating');

  return (
    <div className="bg-white rounded-2xl shadow-lg border border-slate-200 overflow-hidden">
      {/* 헤더: 전체 진행률 */}
      <div className="bg-gradient-to-r from-purple-600 to-indigo-600 text-white p-6">
        <div className="flex items-center justify-between mb-3">
          <div className="flex items-center gap-2">
            <span className="text-2xl">🔮</span>
            <span className="font-bold text-lg">프리미엄 보고서 생성</span>
          </div>
          <div className="text-right">
            <div className="text-3xl font-bold">{progress}%</div>
            <div className="text-purple-200 text-sm">
              {sections.filter(s => s.status === 'completed').length}/{sections.length} 섹션
            </div>
          </div>
        </div>

        {/* 프로그레스 바 */}
        <div className="h-3 bg-white/20 rounded-full overflow-hidden">
          <div
            className="h-full bg-white rounded-full transition-all duration-500 ease-out"
            style={{ width: `${progress}%` }}
          />
        </div>

        {/* 현재 상태 + ETA */}
        <div className="flex items-center justify-between mt-3 text-sm">
          <div className="text-purple-100">
            {getPremiumStepMessage(current_step, activeSection?.id)}
          </div>
          <div className="text-purple-200">
            {progress < 100 ? `남은 시간: ${formatEta(progress)}` : '완료!'}
          </div>
        </div>
      </div>

      {/* 섹션 목록 */}
      <div className="p-4 space-y-2 max-h-96 overflow-y-auto">
        {sections
          .sort((a, b) => a.order - b.order)
          .map((section) => (
            <StepperItem
              key={section.id}
              section={section}
              isActive={activeSection?.id === section.id}
            />
          ))}
      </div>

      {/* 푸터: 안내 메시지 */}
      <div className="bg-slate-50 border-t border-slate-200 p-4">
        <div className="flex items-start gap-3 text-sm text-slate-600">
          <span className="text-lg">💡</span>
          <div>
            <p className="font-medium">서버에서 생성 중입니다</p>
            <p className="text-slate-500 mt-1">
              창을 닫아도 백그라운드에서 계속 진행됩니다.
              <br />완료되면 <strong>이메일로 결과 링크</strong>를 보내드려요.
            </p>
          </div>
        </div>
      </div>

      {/* 상태 표시 */}
      <div className="px-4 pb-4">
        <div className="flex items-center gap-2 text-xs text-slate-400">
          <div className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse" />
          실시간 업데이트 중 (2.5초 간격)
        </div>
      </div>
    </div>
  );
}
