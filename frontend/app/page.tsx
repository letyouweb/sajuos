'use client';

import { useState } from 'react';
import SajuForm from '@/components/SajuForm';
import ResultCard from '@/components/ResultCard';
import ProgressStepper from '@/components/ProgressStepper';
import type { CalculateResponse, InterpretResponse, ConcernType } from '@/types';
import { calculateSaju, startReportGeneration } from '@/lib/api';

type Step = 'input' | 'calculating' | 'generating' | 'result';

export default function Home() {
  const BRAND_NAME = process.env.NEXT_PUBLIC_BRAND_NAME ?? '사주OS';
  const BRAND_TAGLINE = process.env.NEXT_PUBLIC_BRAND_TAGLINE ?? '당신의 사주를 한 번에 정리해드려요';

  const getTodayKst = () =>
    new Date().toLocaleDateString('en-CA', { timeZone: 'Asia/Seoul' });

  const [step, setStep] = useState<Step>('input');
  const [reportId, setReportId] = useState<string | null>(null);
  const [calculateResult, setCalculateResult] = useState<CalculateResponse | null>(null);
  const [interpretResult, setInterpretResult] = useState<InterpretResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  const handleSubmit = async (formData: {
    name: string;
    email: string;  // 🔥 이메일 필드 추가
    birthYear: number;
    birthMonth: number;
    birthDay: number;
    birthHour: number | null;
    birthMinute: number;
    gender: 'male' | 'female' | 'other';
    concernType: ConcernType;
    question: string;
  }) => {
    setStep('calculating');
    setError(null);
    setReportId(null);

    try {
      // 1. 사주 계산 (절기 기반)
      const calcResult = await calculateSaju({
        birth_year: formData.birthYear,
        birth_month: formData.birthMonth,
        birth_day: formData.birthDay,
        birth_hour: formData.birthHour,
        birth_minute: formData.birthMinute,
        gender: formData.gender,
      });
      setCalculateResult(calcResult);

      // 2. 🔥 Supabase 기반 비동기 리포트 생성 시작
      const todayKst = getTodayKst();
      const questionWithDate = `${formData.question}\n\n(기준일: ${todayKst} KST)`;
      
      const response = await startReportGeneration({
        email: formData.email,
        name: formData.name,
        saju_result: calcResult,
        question: questionWithDate,
        concern_type: formData.concernType,
        target_year: 2025,
      });

      if (!response.success) {
        throw new Error(response.message || '리포트 생성 시작 실패');
      }

      // Report ID 저장 → ProgressStepper에 전달
      setReportId(response.report_id);
      setStep('generating');

    } catch (err) {
      const errorMessage = err instanceof Error ? err.message : '알 수 없는 오류가 발생했습니다.';
      setError(errorMessage);
      setStep('input');
    }
  };

  const handleReportComplete = (result: any) => {
    // 폴링 완료 시 결과 설정
    setInterpretResult(result);
    setStep('result');
  };

  const handleReportError = (errorMsg: string) => {
    setError(errorMsg);
    // 에러 시에도 재시도 가능하도록 step은 유지
    // setStep('input');
  };

  const handleReset = () => {
    setStep('input');
    setReportId(null);
    setCalculateResult(null);
    setInterpretResult(null);
    setError(null);
  };

  return (
    <div className="space-y-8">
      {/* Header */}
      <header className="text-center py-8">
        <h1 className="text-4xl font-bold bg-gradient-to-r from-purple-600 to-amber-500 bg-clip-text text-transparent mb-3">
          🔮 {BRAND_NAME}
        </h1>
        <p className="text-slate-700 text-lg">{BRAND_TAGLINE}</p>
      </header>

      {/* Error Message */}
      {error && (
        <div className="bg-red-50 border border-red-200 text-red-700 px-4 py-3 rounded-lg animate-fade-in-up">
          <div className="flex items-start gap-3">
            <span className="text-xl">⚠️</span>
            <div>
              <p className="font-medium">오류 발생</p>
              <p className="text-sm mt-1">{error}</p>
              <p className="text-xs text-red-500 mt-2">
                네트워크 연결과 서버 상태를 확인해주세요.
              </p>
            </div>
          </div>
        </div>
      )}

      {/* Step: Input Form */}
      {step === 'input' && <SajuForm onSubmit={handleSubmit} />}

      {/* Step: Calculating (사주 계산 중) */}
      {step === 'calculating' && (
        <div className="flex flex-col items-center justify-center py-20 animate-fade-in-up">
          <div className="w-16 h-16 border-4 border-purple-200 border-t-purple-600 rounded-full animate-spin mb-6" />
          <p className="text-xl font-medium text-slate-700">사주 원국 계산 중...</p>
          <p className="text-slate-500 mt-2">절기 기반 정확한 계산 🌟</p>
        </div>
      )}

      {/* Step: Generating (폴링 기반 실시간 진행) */}
      {step === 'generating' && (
        <div className="animate-fade-in-up">
          <ProgressStepper
            reportId={reportId}
            onComplete={handleReportComplete}
            onError={handleReportError}
          />
          
          {/* 재시도 버튼 (에러 발생 시) */}
          {error && (
            <div className="mt-4 text-center">
              <button
                onClick={handleReset}
                className="px-6 py-3 bg-purple-600 hover:bg-purple-700 text-white rounded-lg font-medium transition"
              >
                처음부터 다시하기
              </button>
            </div>
          )}
        </div>
      )}

      {/* Step: Result */}
      {step === 'result' && calculateResult && interpretResult && (
        <ResultCard
          calculateResult={calculateResult}
          interpretResult={interpretResult}
          onReset={handleReset}
        />
      )}
    </div>
  );
}
