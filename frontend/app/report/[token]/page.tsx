'use client';

import { useEffect, useState } from 'react';
import { useParams } from 'next/navigation';
import ResultCard from '@/components/ResultCard';
import ProgressStepper from '@/components/ProgressStepper';
import { getReportByToken } from '@/lib/api';

type PageStatus = 'loading' | 'generating' | 'completed' | 'error';

export default function ReportPage() {
  const params = useParams();
  const token = params.token as string;
  
  const [status, setStatus] = useState<PageStatus>('loading');
  const [reportData, setReportData] = useState<any>(null);
  const [error, setError] = useState<string | null>(null);
  const [progress, setProgress] = useState(0);

  useEffect(() => {
    if (!token) return;

    const fetchReport = async () => {
      try {
        const data = await getReportByToken(token);
        
        if (data.status === 'completed' && data.result) {
          setReportData({
            calculateResult: data.result.legacy?.saju_data || {},
            interpretResult: data.result,
          });
          setStatus('completed');
        } else if (data.status === 'generating' || data.status === 'pending') {
          setProgress(data.progress || 0);
          setStatus('generating');
          // 폴링 시작
          startPolling();
        } else if (data.status === 'failed') {
          setError(data.error || '리포트 생성 실패');
          setStatus('error');
        }
      } catch (e) {
        setError(e instanceof Error ? e.message : '리포트를 불러올 수 없습니다');
        setStatus('error');
      }
    };

    const startPolling = () => {
      const interval = setInterval(async () => {
        try {
          const data = await getReportByToken(token);
          
          if (data.status === 'completed' && data.result) {
            clearInterval(interval);
            setReportData({
              calculateResult: data.result.legacy?.saju_data || {},
              interpretResult: data.result,
            });
            setStatus('completed');
          } else if (data.status === 'failed') {
            clearInterval(interval);
            setError(data.error || '리포트 생성 실패');
            setStatus('error');
          } else {
            setProgress(data.progress || 0);
          }
        } catch (e) {
          // 폴링 에러는 무시
        }
      }, 3000);

      return () => clearInterval(interval);
    };

    fetchReport();
  }, [token]);

  const BRAND_NAME = process.env.NEXT_PUBLIC_BRAND_NAME ?? '사주OS';

  return (
    <div className="min-h-screen bg-gradient-to-b from-slate-50 to-purple-50 py-8">
      <div className="container mx-auto px-4 max-w-4xl">
        {/* Header */}
        <header className="text-center py-6">
          <h1 className="text-3xl font-bold bg-gradient-to-r from-purple-600 to-amber-500 bg-clip-text text-transparent">
            🔮 {BRAND_NAME}
          </h1>
          <p className="text-slate-600 mt-2">프리미엄 비즈니스 컨설팅 보고서</p>
        </header>

        {/* Loading */}
        {status === 'loading' && (
          <div className="flex flex-col items-center justify-center py-20">
            <div className="w-16 h-16 border-4 border-purple-200 border-t-purple-600 rounded-full animate-spin mb-6" />
            <p className="text-slate-600">보고서를 불러오는 중...</p>
          </div>
        )}

        {/* Generating */}
        {status === 'generating' && (
          <div className="bg-white rounded-2xl shadow-lg p-8 animate-fade-in-up">
            <div className="text-center mb-6">
              <div className="text-4xl mb-3">⏳</div>
              <h2 className="text-xl font-bold text-gray-800">보고서 생성 중입니다</h2>
              <p className="text-gray-600 mt-2">
                잠시만 기다려주세요. 완료되면 자동으로 표시됩니다.
              </p>
            </div>

            {/* 간단한 프로그레스 바 */}
            <div className="max-w-md mx-auto">
              <div className="flex items-center justify-between mb-2">
                <span className="text-sm text-gray-600">진행률</span>
                <span className="text-sm font-bold text-purple-600">{progress}%</span>
              </div>
              <div className="h-3 bg-gray-200 rounded-full overflow-hidden">
                <div
                  className="h-full bg-gradient-to-r from-purple-600 to-amber-500 rounded-full transition-all duration-500"
                  style={{ width: `${progress}%` }}
                />
              </div>
            </div>

            <div className="mt-8 p-4 bg-purple-50 rounded-xl text-center">
              <p className="text-sm text-gray-600">
                💡 이 페이지를 북마크해두시면 언제든 다시 확인하실 수 있어요.
              </p>
            </div>
          </div>
        )}

        {/* Error */}
        {status === 'error' && (
          <div className="bg-red-50 border border-red-200 rounded-2xl p-8 text-center">
            <div className="text-4xl mb-3">⚠️</div>
            <h2 className="text-xl font-bold text-red-700">오류가 발생했습니다</h2>
            <p className="text-red-600 mt-2">{error}</p>
            <button
              onClick={() => window.location.reload()}
              className="mt-6 px-6 py-2 bg-red-600 text-white rounded-lg hover:bg-red-700 transition"
            >
              다시 시도
            </button>
          </div>
        )}

        {/* Completed */}
        {status === 'completed' && reportData && (
          <ResultCard
            calculateResult={reportData.calculateResult}
            interpretResult={reportData.interpretResult}
            onReset={() => window.location.href = '/'}
          />
        )}

        {/* Footer */}
        <footer className="text-center py-8 text-sm text-gray-500">
          <p>© 2025 {BRAND_NAME}. All rights reserved.</p>
          <p className="mt-1">문의: support@sajuos.com</p>
        </footer>
      </div>
    </div>
  );
}
