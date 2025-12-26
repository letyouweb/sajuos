'use client';

import { useState } from 'react';
import type { CalculateResponse, InterpretResponse } from '@/types';
import { getAccuracyBadge, getAccuracyBadgeInfo, HOUR_OPTIONS } from '@/types';

interface ResultCardProps {
  calculateResult: CalculateResponse;
  interpretResult: InterpretResponse;
  onReset: () => void;
}

// 프리미엄 보고서 타입
interface PremiumSection {
  id: string;
  title: string;
  confidence: string;
  rulecard_ids: string[];
  body_markdown: string;
  diagnosis?: {
    current_state: string;
    key_issues: string[];
  };
  hypotheses?: Array<{
    id: string;
    statement: string;
    confidence: string;
    evidence: string;
  }>;
  strategy_options?: Array<{
    id: string;
    name: string;
    description: string;
    pros: string[];
    cons: string[];
  }>;
  recommended_strategy?: {
    selected_option: string;
    rationale: string;
    execution_plan: Array<{
      week: number;
      focus: string;
      actions: string[];
    }>;
  };
  kpis?: Array<{
    metric: string;
    target: string;
    measurement: string;
  }>;
  risks?: Array<{
    risk: string;
    probability: string;
    impact: string;
    mitigation: string;
  }>;
  // Sprint 전용
  mission_statement?: string;
  weekly_plans?: Array<{
    week: number;
    theme: string;
    goals: string[];
    daily_actions: string[];
    kpis: string[];
    checkpoint: string;
  }>;
  milestones?: {
    day_30?: { goal: string; success_criteria: string; deliverables: string[] };
    day_60?: { goal: string; success_criteria: string; deliverables: string[] };
    day_90?: { goal: string; success_criteria: string; deliverables: string[] };
  };
  risk_scenarios?: Array<{
    scenario: string;
    trigger: string;
    pivot_plan: string;
  }>;
  // Calendar 전용
  annual_theme?: string;
  monthly_plans?: Array<{
    month: number;
    month_name: string;
    theme: string;
    energy_level: string;
    key_focus: string;
    recommended_actions: string[];
    cautions: string[];
    kpi_targets: string[];
  }>;
  quarterly_milestones?: {
    Q1?: { theme: string; milestone: string; key_metric: string };
    Q2?: { theme: string; milestone: string; key_metric: string };
    Q3?: { theme: string; milestone: string; key_metric: string };
    Q4?: { theme: string; milestone: string; key_metric: string };
  };
  peak_months?: string[];
  risk_months?: string[];
  char_count?: number;
  error?: boolean;
  error_message?: string;
}

interface PremiumReport {
  target_year: number;
  sections: PremiumSection[];
  meta: {
    total_tokens_estimate: number;
    total_chars: number;
    mode: string;
    generated_at: string;
    section_count: number;
    success_count?: number;
    error_count?: number;
    rulecards_used_total: number;
    latency_ms: number;
    concurrency?: number;
    errors?: Array<{
      section: string;
      error_type: string;
      error_message: string;
    }>;
  };
  legacy?: any;
}

export default function ResultCard({
  calculateResult,
  interpretResult,
}: ResultCardProps) {
  const BRAND_NAME = process.env.NEXT_PUBLIC_BRAND_NAME ?? '사주OS';
  
  const [activeSection, setActiveSection] = useState<string>('exec');
  const [showBoundaryModal, setShowBoundaryModal] = useState(false);
  const [showErrorDetails, setShowErrorDetails] = useState(false);
  const [expandedSections, setExpandedSections] = useState<Set<string>>(new Set(['diagnosis', 'strategy']));

  // 프리미엄 보고서 감지
  const report = interpretResult as unknown as PremiumReport;
  const isPremiumReport = !!(report.sections && report.meta?.mode === 'premium_business_30p');
  
  // 레거시 데이터
  const legacy = report.legacy || interpretResult;
  const meta = report.meta;
  const sections = report.sections || [];

  // 정확도 배지
  const accuracyBadge = getAccuracyBadge(calculateResult.quality);
  const badgeInfo = getAccuracyBadgeInfo(accuracyBadge);

  // 섹션 토글
  const toggleSection = (section: string) => {
    const newSet = new Set(expandedSections);
    if (newSet.has(section)) {
      newSet.delete(section);
    } else {
      newSet.add(section);
    }
    setExpandedSections(newSet);
  };

  // 공유 기능
  const handleShare = async () => {
    if (calculateResult.quality.solar_term_boundary) {
      setShowBoundaryModal(true);
      return;
    }
    await doShare();
  };

  const doShare = async () => {
    const shareText = isPremiumReport
      ? `🎯 ${BRAND_NAME} ${report.target_year}년 프리미엄 비즈니스 컨설팅 보고서\n\n${sections.length}개 섹션 | ${meta?.total_chars?.toLocaleString()}자 분석`
      : `🔮 ${BRAND_NAME} 운세 분석\n\n${legacy.summary}`;
    
    if (navigator.share) {
      try {
        await navigator.share({ title: `${BRAND_NAME} 보고서`, text: shareText });
      } catch (err) {}
    } else {
      await navigator.clipboard.writeText(shareText);
      alert('결과가 클립보드에 복사되었습니다!');
    }
  };

  const getHourRange = (jiIndex: number | undefined) => {
    if (jiIndex === undefined) return '';
    const option = HOUR_OPTIONS[jiIndex];
    return option ? `${option.range_start}~${option.range_end}` : '';
  };

  // 신뢰도 배지
  const ConfidenceBadge = ({ level }: { level: string }) => {
    const colors = {
      HIGH: 'bg-green-100 text-green-700',
      MEDIUM: 'bg-yellow-100 text-yellow-700',
      LOW: 'bg-red-100 text-red-700',
    };
    return (
      <span className={`px-2 py-0.5 rounded text-xs font-medium ${colors[level as keyof typeof colors] || colors.MEDIUM}`}>
        {level}
      </span>
    );
  };

  // 섹션 아이콘
  const sectionIcons: Record<string, string> = {
    exec: '📊',
    money: '💰',
    business: '💼',
    team: '👥',
    health: '💪',
    calendar: '📅',
    sprint: '🚀'
  };

  // Sprint 섹션 렌더링
  const renderSprintSection = (section: PremiumSection) => (
    <div className="space-y-6">
      {/* 미션 선언문 */}
      {section.mission_statement && (
        <div className="p-4 bg-gradient-to-r from-purple-100 to-blue-100 rounded-xl border border-purple-200">
          <h4 className="font-bold text-purple-800 mb-2">🎯 90일 미션</h4>
          <p className="text-gray-800">{section.mission_statement}</p>
        </div>
      )}

      {/* 마일스톤 */}
      {section.milestones && (
        <div className="grid md:grid-cols-3 gap-4">
          {section.milestones.day_30 && (
            <div className="p-4 bg-green-50 rounded-xl border border-green-200">
              <h5 className="font-bold text-green-700 mb-2">📍 30일 마일스톤</h5>
              <p className="text-sm font-medium">{section.milestones.day_30.goal}</p>
              <p className="text-xs text-gray-500 mt-1">✓ {section.milestones.day_30.success_criteria}</p>
            </div>
          )}
          {section.milestones.day_60 && (
            <div className="p-4 bg-yellow-50 rounded-xl border border-yellow-200">
              <h5 className="font-bold text-yellow-700 mb-2">📍 60일 마일스톤</h5>
              <p className="text-sm font-medium">{section.milestones.day_60.goal}</p>
              <p className="text-xs text-gray-500 mt-1">✓ {section.milestones.day_60.success_criteria}</p>
            </div>
          )}
          {section.milestones.day_90 && (
            <div className="p-4 bg-blue-50 rounded-xl border border-blue-200">
              <h5 className="font-bold text-blue-700 mb-2">📍 90일 마일스톤</h5>
              <p className="text-sm font-medium">{section.milestones.day_90.goal}</p>
              <p className="text-xs text-gray-500 mt-1">✓ {section.milestones.day_90.success_criteria}</p>
            </div>
          )}
        </div>
      )}

      {/* 주간 계획 */}
      {section.weekly_plans && section.weekly_plans.length > 0 && (
        <div>
          <h4 className="font-bold text-gray-800 mb-3">📋 주간 실행 계획</h4>
          <div className="space-y-3">
            {section.weekly_plans.slice(0, 12).map((week, i) => (
              <div key={i} className="p-3 bg-white border rounded-lg">
                <div className="flex items-center justify-between mb-2">
                  <span className="font-bold text-purple-700">{week.week}주차</span>
                  <span className="text-xs text-gray-500 bg-gray-100 px-2 py-0.5 rounded">{week.theme}</span>
                </div>
                {week.goals && week.goals.length > 0 && (
                  <div className="mb-2">
                    <span className="text-xs text-gray-500">목표:</span>
                    <ul className="text-sm">
                      {week.goals.map((g, j) => <li key={j}>• {g}</li>)}
                    </ul>
                  </div>
                )}
                {week.daily_actions && week.daily_actions.length > 0 && (
                  <div className="text-xs text-gray-600 border-t pt-2 mt-2">
                    {week.daily_actions.slice(0, 3).map((a, j) => <span key={j} className="mr-2">→ {a}</span>)}
                  </div>
                )}
              </div>
            ))}
          </div>
        </div>
      )}

      {/* 리스크 시나리오 */}
      {section.risk_scenarios && section.risk_scenarios.length > 0 && (
        <div className="p-4 bg-red-50 rounded-xl">
          <h4 className="font-bold text-red-700 mb-3">⚠️ 리스크 시나리오</h4>
          {section.risk_scenarios.map((r, i) => (
            <div key={i} className="mb-3 last:mb-0">
              <p className="font-medium text-gray-800">{r.scenario}</p>
              <p className="text-sm text-gray-600">트리거: {r.trigger}</p>
              <p className="text-sm text-green-600">→ 피벗: {r.pivot_plan}</p>
            </div>
          ))}
        </div>
      )}
    </div>
  );

  // Calendar 섹션 렌더링
  const renderCalendarSection = (section: PremiumSection) => (
    <div className="space-y-6">
      {/* 연간 테마 */}
      {section.annual_theme && (
        <div className="p-4 bg-gradient-to-r from-amber-100 to-orange-100 rounded-xl border border-amber-200">
          <h4 className="font-bold text-amber-800 mb-2">🎯 {report.target_year}년 연간 테마</h4>
          <p className="text-gray-800">{section.annual_theme}</p>
        </div>
      )}

      {/* 분기별 마일스톤 */}
      {section.quarterly_milestones && (
        <div className="grid md:grid-cols-4 gap-3">
          {(['Q1', 'Q2', 'Q3', 'Q4'] as const).map((q) => {
            const qm = section.quarterly_milestones?.[q];
            if (!qm) return null;
            return (
              <div key={q} className="p-3 bg-blue-50 rounded-lg border border-blue-200">
                <h5 className="font-bold text-blue-700">{q}</h5>
                <p className="text-xs text-gray-600">{qm.theme}</p>
                <p className="text-sm font-medium mt-1">{qm.milestone}</p>
              </div>
            );
          })}
        </div>
      )}

      {/* 월별 계획 */}
      {section.monthly_plans && section.monthly_plans.length > 0 && (
        <div>
          <h4 className="font-bold text-gray-800 mb-3">📅 월별 전략 캘린더</h4>
          <div className="grid md:grid-cols-3 gap-3">
            {section.monthly_plans.map((month, i) => (
              <div key={i} className={`p-3 rounded-lg border ${
                month.energy_level === 'HIGH' ? 'bg-green-50 border-green-200' :
                month.energy_level === 'LOW' ? 'bg-red-50 border-red-200' :
                'bg-gray-50 border-gray-200'
              }`}>
                <div className="flex items-center justify-between mb-2">
                  <span className="font-bold">{month.month_name || `${month.month}월`}</span>
                  <span className={`text-xs px-2 py-0.5 rounded ${
                    month.energy_level === 'HIGH' ? 'bg-green-200 text-green-700' :
                    month.energy_level === 'LOW' ? 'bg-red-200 text-red-700' :
                    'bg-gray-200 text-gray-700'
                  }`}>{month.energy_level}</span>
                </div>
                <p className="text-xs text-gray-500 mb-2">{month.theme}</p>
                {month.recommended_actions && month.recommended_actions.length > 0 && (
                  <ul className="text-xs text-gray-600">
                    {month.recommended_actions.slice(0, 2).map((a, j) => (
                      <li key={j}>✓ {a}</li>
                    ))}
                  </ul>
                )}
                {month.cautions && month.cautions.length > 0 && (
                  <p className="text-xs text-red-500 mt-1">⚠ {month.cautions[0]}</p>
                )}
              </div>
            ))}
          </div>
        </div>
      )}

      {/* 최고/주의 월 */}
      <div className="grid md:grid-cols-2 gap-4">
        {section.peak_months && section.peak_months.length > 0 && (
          <div className="p-4 bg-green-50 rounded-xl">
            <h4 className="font-bold text-green-700 mb-2">🌟 최고 성과 예상 월</h4>
            <p className="text-sm">{section.peak_months.join(', ')}</p>
          </div>
        )}
        {section.risk_months && section.risk_months.length > 0 && (
          <div className="p-4 bg-orange-50 rounded-xl">
            <h4 className="font-bold text-orange-700 mb-2">⚡ 주의 필요 월</h4>
            <p className="text-sm">{section.risk_months.join(', ')}</p>
          </div>
        )}
      </div>
    </div>
  );

  return (
    <div className="space-y-6 animate-fade-in-up">
      {/* 정확도 배지 */}
      <div className={`flex items-center justify-between p-4 rounded-xl ${
        accuracyBadge === 'high' ? 'bg-green-50 border border-green-200' :
        accuracyBadge === 'boundary' ? 'bg-yellow-50 border border-yellow-200' :
        'bg-blue-50 border border-blue-200'
      }`}>
        <div className="flex items-center gap-2">
          <span className="text-2xl">{badgeInfo.icon}</span>
          <div>
            <p className={`font-bold ${
              accuracyBadge === 'high' ? 'text-green-700' :
              accuracyBadge === 'boundary' ? 'text-yellow-700' : 'text-blue-700'
            }`}>{badgeInfo.label}</p>
            <p className="text-xs text-gray-600">{badgeInfo.tooltip}</p>
          </div>
        </div>
        {isPremiumReport && meta && (
          <div className="text-right text-xs text-gray-500">
            <p className="font-medium text-purple-600">💎 프리미엄 비즈니스 보고서</p>
            <p>{meta.success_count || meta.section_count}개 섹션 · {(meta.total_chars || 0).toLocaleString()}자</p>
            {meta.error_count && meta.error_count > 0 && (
              <p className="text-red-500">⚠️ {meta.error_count}개 섹션 오류</p>
            )}
          </div>
        )}
      </div>

      {/* 에러 상세 정보 (있을 경우) */}
      {isPremiumReport && meta?.errors && meta.errors.length > 0 && (
        <div className="bg-red-50 rounded-xl p-4 border border-red-200">
          <button 
            onClick={() => setShowErrorDetails(!showErrorDetails)}
            className="w-full flex items-center justify-between"
          >
            <span className="font-bold text-red-700">⚠️ {meta.errors.length}개 섹션 생성 오류</span>
            <span>{showErrorDetails ? '▼' : '▶'}</span>
          </button>
          {showErrorDetails && (
            <div className="mt-3 space-y-2">
              {meta.errors.map((err, i) => (
                <div key={i} className="p-3 bg-white rounded-lg text-sm">
                  <p className="font-medium text-red-600">섹션: {err.section}</p>
                  <p className="text-gray-500">타입: {err.error_type}</p>
                  <p className="text-gray-600 text-xs mt-1 break-all">{err.error_message}</p>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* 사주 원국 카드 */}
      <div className="bg-white rounded-2xl shadow-lg overflow-hidden">
        <div className="gradient-bg text-white p-6">
          <h2 className="text-2xl font-bold mb-2">📜 사주 원국</h2>
          <p className="opacity-90">{calculateResult.birth_info}</p>
        </div>
        
        <div className="p-6">
          <div className="grid grid-cols-4 gap-2 mb-6">
            {[
              { label: '시주', pillar: calculateResult.saju.hour_pillar, hanja: '時' },
              { label: '일주', pillar: calculateResult.saju.day_pillar, hanja: '日' },
              { label: '월주', pillar: calculateResult.saju.month_pillar, hanja: '月' },
              { label: '년주', pillar: calculateResult.saju.year_pillar, hanja: '年' },
            ].map((item, idx) => (
              <div key={item.label} className="text-center">
                <p className="text-xs text-gray-500 mb-1">{item.label}({item.hanja})</p>
                <div className="bg-gradient-to-b from-amber-50 to-amber-100 rounded-lg p-3 border border-amber-200">
                  {item.pillar ? (
                    <>
                      <div className="mb-1">
                        <p className="text-2xl font-bold text-purple-700">{item.pillar.gan}</p>
                        <p className="text-xs text-purple-500">{item.pillar.gan_element}</p>
                      </div>
                      <div className="border-t border-amber-200 pt-1">
                        <p className="text-2xl font-bold text-amber-600">{item.pillar.ji}</p>
                        <p className="text-xs text-amber-500">{item.pillar.ji_element}</p>
                      </div>
                      {idx === 0 && item.pillar.ji_index !== undefined && (
                        <p className="text-[10px] text-gray-400 mt-1">{getHourRange(item.pillar.ji_index)}</p>
                      )}
                    </>
                  ) : (
                    <p className="text-gray-400 py-4">-</p>
                  )}
                </div>
              </div>
            ))}
          </div>

          <div className="bg-purple-50 rounded-xl p-4 border border-purple-100">
            <p className="text-sm text-purple-600 font-medium mb-1">당신의 일간 (핵심 의사결정자 특성)</p>
            <p className="text-lg font-bold text-purple-800">
              {calculateResult.day_master} ({calculateResult.day_master_element})
            </p>
            <p className="text-sm text-gray-600 mt-2">{calculateResult.day_master_description}</p>
          </div>
        </div>
      </div>

      {/* 프리미엄 비즈니스 보고서 */}
      {isPremiumReport ? (
        <div className="bg-white rounded-2xl shadow-lg overflow-hidden">
          {/* 헤더 */}
          <div className="bg-gradient-to-r from-purple-700 via-purple-600 to-amber-500 text-white p-6">
            <div className="flex items-center justify-between">
              <div>
                <h2 className="text-2xl font-bold mb-1">💎 {report.target_year}년 비즈니스 컨설팅 보고서</h2>
                <p className="opacity-90">맥킨지급 30페이지 심층 분석 · 99,000원 프리미엄</p>
              </div>
              <div className="text-right">
                <p className="text-sm opacity-75">총 {(meta?.total_chars || 0).toLocaleString()}자</p>
                <p className="text-sm opacity-75">RuleCard {meta?.rulecards_used_total || 0}장 근거</p>
              </div>
            </div>
          </div>

          {/* 섹션 탭 */}
          <div className="border-b overflow-x-auto bg-gray-50">
            <div className="flex">
              {sections.map((section) => (
                <button
                  key={section.id}
                  onClick={() => setActiveSection(section.id)}
                  className={`flex-shrink-0 px-4 py-3 text-sm font-medium transition whitespace-nowrap border-b-2 ${
                    activeSection === section.id
                      ? 'text-purple-700 border-purple-600 bg-white'
                      : 'text-gray-500 border-transparent hover:text-gray-700 hover:bg-gray-100'
                  } ${section.error ? 'text-red-400' : ''}`}
                >
                  {sectionIcons[section.id] || '📄'} {section.title.length > 15 ? section.title.slice(0, 15) + '...' : section.title}
                  {section.error && ' ⚠️'}
                </button>
              ))}
            </div>
          </div>

          {/* 섹션 콘텐츠 */}
          <div className="p-6">
            {sections.map((section) => (
              <div 
                key={section.id} 
                className={activeSection === section.id ? 'block' : 'hidden'}
              >
                {section.error ? (
                  <div className="bg-red-50 rounded-xl p-6">
                    <p className="text-red-600 font-medium mb-2">⚠️ 이 섹션 생성 중 오류가 발생했습니다.</p>
                    {section.error_message && (
                      <p className="text-sm text-gray-600 bg-white p-3 rounded mt-2 break-all">
                        {section.error_message}
                      </p>
                    )}
                    <p className="text-sm text-gray-500 mt-3">
                      💡 팁: 페이지를 새로고침하거나 잠시 후 다시 시도해주세요.
                    </p>
                  </div>
                ) : (
                  <>
                    {/* 섹션 헤더 */}
                    <div className="flex items-center justify-between mb-6">
                      <h3 className="text-xl font-bold text-gray-800">
                        {sectionIcons[section.id]} {section.title}
                      </h3>
                      <div className="flex items-center gap-2">
                        <ConfidenceBadge level={section.confidence} />
                        <span className="text-xs text-gray-400">{(section.char_count || 0).toLocaleString()}자</span>
                      </div>
                    </div>

                    {/* Sprint 섹션 전용 렌더링 */}
                    {section.id === 'sprint' && (section.mission_statement || section.weekly_plans) ? (
                      renderSprintSection(section)
                    ) : section.id === 'calendar' && (section.annual_theme || section.monthly_plans) ? (
                      renderCalendarSection(section)
                    ) : (
                      <>
                        {/* 표준 섹션: 현상 진단 */}
                        {section.diagnosis && (
                          <div className="mb-6">
                            <button 
                              onClick={() => toggleSection('diagnosis')}
                              className="w-full flex items-center justify-between p-4 bg-blue-50 rounded-xl hover:bg-blue-100 transition"
                            >
                              <h4 className="font-bold text-blue-800">📋 현상 진단</h4>
                              <span>{expandedSections.has('diagnosis') ? '▼' : '▶'}</span>
                            </button>
                            {expandedSections.has('diagnosis') && (
                              <div className="mt-3 p-4 bg-gray-50 rounded-xl">
                                <p className="text-gray-700 leading-relaxed">{section.diagnosis.current_state}</p>
                                {section.diagnosis.key_issues?.length > 0 && (
                                  <div className="mt-4">
                                    <p className="text-sm font-medium text-gray-600 mb-2">핵심 이슈:</p>
                                    <ul className="space-y-1">
                                      {section.diagnosis.key_issues.map((issue, i) => (
                                        <li key={i} className="flex items-start text-sm">
                                          <span className="text-red-500 mr-2">!</span>
                                          <span>{issue}</span>
                                        </li>
                                      ))}
                                    </ul>
                                  </div>
                                )}
                              </div>
                            )}
                          </div>
                        )}

                        {/* 핵심 가설 */}
                        {section.hypotheses && section.hypotheses.length > 0 && (
                          <div className="mb-6">
                            <button 
                              onClick={() => toggleSection('hypotheses')}
                              className="w-full flex items-center justify-between p-4 bg-purple-50 rounded-xl hover:bg-purple-100 transition"
                            >
                              <h4 className="font-bold text-purple-800">💡 핵심 가설 ({section.hypotheses.length}개)</h4>
                              <span>{expandedSections.has('hypotheses') ? '▼' : '▶'}</span>
                            </button>
                            {expandedSections.has('hypotheses') && (
                              <div className="mt-3 space-y-3">
                                {section.hypotheses.map((h, i) => (
                                  <div key={i} className="p-4 bg-white border rounded-xl">
                                    <div className="flex items-center justify-between mb-2">
                                      <span className="font-bold text-purple-700">{h.id}</span>
                                      <ConfidenceBadge level={h.confidence} />
                                    </div>
                                    <p className="text-gray-800 font-medium">{h.statement}</p>
                                    {h.evidence && (
                                      <p className="text-sm text-gray-500 mt-2 border-l-2 border-purple-200 pl-3">{h.evidence}</p>
                                    )}
                                  </div>
                                ))}
                              </div>
                            )}
                          </div>
                        )}

                        {/* 전략 옵션 */}
                        {section.strategy_options && section.strategy_options.length > 0 && (
                          <div className="mb-6">
                            <button 
                              onClick={() => toggleSection('strategy')}
                              className="w-full flex items-center justify-between p-4 bg-amber-50 rounded-xl hover:bg-amber-100 transition"
                            >
                              <h4 className="font-bold text-amber-800">🎯 전략 옵션 ({section.strategy_options.length}개)</h4>
                              <span>{expandedSections.has('strategy') ? '▼' : '▶'}</span>
                            </button>
                            {expandedSections.has('strategy') && (
                              <div className="mt-3 space-y-4">
                                {section.strategy_options.map((s, i) => (
                                  <div key={i} className={`p-4 border rounded-xl ${
                                    section.recommended_strategy?.selected_option === s.id 
                                      ? 'border-green-500 bg-green-50' 
                                      : 'bg-white'
                                  }`}>
                                    <div className="flex items-center justify-between mb-2">
                                      <span className="font-bold text-gray-800">{s.id}: {s.name}</span>
                                      {section.recommended_strategy?.selected_option === s.id && (
                                        <span className="px-2 py-0.5 bg-green-500 text-white text-xs rounded">✓ 추천</span>
                                      )}
                                    </div>
                                    <p className="text-gray-600 text-sm mb-3">{s.description}</p>
                                    <div className="grid md:grid-cols-2 gap-3">
                                      <div>
                                        <p className="text-xs font-medium text-green-600 mb-1">장점</p>
                                        <ul className="text-xs text-gray-600">
                                          {s.pros?.map((p, j) => <li key={j}>+ {p}</li>)}
                                        </ul>
                                      </div>
                                      <div>
                                        <p className="text-xs font-medium text-red-600 mb-1">단점</p>
                                        <ul className="text-xs text-gray-600">
                                          {s.cons?.map((c, j) => <li key={j}>- {c}</li>)}
                                        </ul>
                                      </div>
                                    </div>
                                  </div>
                                ))}
                              </div>
                            )}
                          </div>
                        )}

                        {/* KPI */}
                        {section.kpis && section.kpis.length > 0 && (
                          <div className="mb-6">
                            <button 
                              onClick={() => toggleSection('kpis')}
                              className="w-full flex items-center justify-between p-4 bg-indigo-50 rounded-xl hover:bg-indigo-100 transition"
                            >
                              <h4 className="font-bold text-indigo-800">📊 KPI ({section.kpis.length}개)</h4>
                              <span>{expandedSections.has('kpis') ? '▼' : '▶'}</span>
                            </button>
                            {expandedSections.has('kpis') && (
                              <div className="mt-3 overflow-x-auto">
                                <table className="w-full text-sm">
                                  <thead className="bg-indigo-100">
                                    <tr>
                                      <th className="p-2 text-left">지표</th>
                                      <th className="p-2 text-left">목표</th>
                                      <th className="p-2 text-left">측정법</th>
                                    </tr>
                                  </thead>
                                  <tbody>
                                    {section.kpis.map((kpi, i) => (
                                      <tr key={i} className="border-b">
                                        <td className="p-2 font-medium">{kpi.metric}</td>
                                        <td className="p-2 text-indigo-600">{kpi.target}</td>
                                        <td className="p-2 text-gray-500">{kpi.measurement}</td>
                                      </tr>
                                    ))}
                                  </tbody>
                                </table>
                              </div>
                            )}
                          </div>
                        )}

                        {/* 리스크 */}
                        {section.risks && section.risks.length > 0 && (
                          <div className="mb-6">
                            <button 
                              onClick={() => toggleSection('risks')}
                              className="w-full flex items-center justify-between p-4 bg-red-50 rounded-xl hover:bg-red-100 transition"
                            >
                              <h4 className="font-bold text-red-800">⚠️ 리스크 ({section.risks.length}개)</h4>
                              <span>{expandedSections.has('risks') ? '▼' : '▶'}</span>
                            </button>
                            {expandedSections.has('risks') && (
                              <div className="mt-3 space-y-3">
                                {section.risks.map((r, i) => (
                                  <div key={i} className="p-4 bg-white border border-red-200 rounded-xl">
                                    <div className="flex items-center gap-2 mb-2">
                                      <span className={`px-2 py-0.5 rounded text-xs ${
                                        r.probability === 'HIGH' ? 'bg-red-100 text-red-700' :
                                        r.probability === 'MEDIUM' ? 'bg-yellow-100 text-yellow-700' :
                                        'bg-green-100 text-green-700'
                                      }`}>
                                        확률: {r.probability}
                                      </span>
                                      <span className={`px-2 py-0.5 rounded text-xs ${
                                        r.impact === 'HIGH' ? 'bg-red-100 text-red-700' :
                                        r.impact === 'MEDIUM' ? 'bg-yellow-100 text-yellow-700' :
                                        'bg-green-100 text-green-700'
                                      }`}>
                                        영향: {r.impact}
                                      </span>
                                    </div>
                                    <p className="font-medium text-gray-800">{r.risk}</p>
                                    {r.mitigation && (
                                      <p className="text-sm text-green-600 mt-2">✓ 대응: {r.mitigation}</p>
                                    )}
                                  </div>
                                ))}
                              </div>
                            )}
                          </div>
                        )}
                      </>
                    )}

                    {/* 근거 RuleCard */}
                    {section.rulecard_ids && section.rulecard_ids.length > 0 && (
                      <div className="p-4 bg-gray-100 rounded-xl">
                        <p className="text-xs text-gray-500">
                          📚 분석 근거: {section.rulecard_ids.length}개 데이터 포인트 참조
                        </p>
                      </div>
                    )}
                  </>
                )}
              </div>
            ))}
          </div>

          {/* 면책조항 */}
          <div className="px-6 pb-6">
            <div className="p-4 bg-gray-50 rounded-xl text-xs text-gray-500">
              본 보고서는 데이터 기반 분석 참고 자료이며, 법률/재무/의료 등 전문적 조언을 대체하지 않습니다.
            </div>
          </div>
        </div>
      ) : (
        /* 레거시 UI */
        <div className="bg-white rounded-2xl shadow-lg overflow-hidden">
          <div className="p-6">
            <h3 className="text-xl font-bold text-purple-800 mb-4">{legacy.summary}</h3>
            
            {legacy.day_master_analysis && (
              <div className="bg-gray-50 rounded-xl p-4 mb-4">
                <p className="text-gray-600">{legacy.day_master_analysis}</p>
              </div>
            )}

            <div className="grid md:grid-cols-2 gap-4 mb-4">
              <div className="bg-green-50 rounded-xl p-4">
                <h4 className="font-bold text-green-700 mb-2">💪 강점</h4>
                <ul className="space-y-1">
                  {(legacy.strengths || []).map((s: string, i: number) => (
                    <li key={i} className="text-sm text-gray-700">✓ {s}</li>
                  ))}
                </ul>
              </div>
              <div className="bg-orange-50 rounded-xl p-4">
                <h4 className="font-bold text-orange-700 mb-2">⚡ 주의점</h4>
                <ul className="space-y-1">
                  {(legacy.risks || []).map((r: string, i: number) => (
                    <li key={i} className="text-sm text-gray-700">! {r}</li>
                  ))}
                </ul>
              </div>
            </div>

            <div className="text-center py-4 bg-gradient-to-r from-purple-50 to-amber-50 rounded-xl">
              <p className="text-lg text-purple-700 font-medium">✨ {legacy.blessing}</p>
            </div>
          </div>
        </div>
      )}

      {/* 메타 정보 */}
      <div className="text-center text-xs text-gray-400">
        {isPremiumReport && meta ? (
          <>
            <p>처리시간: {((meta.latency_ms || 0) / 1000).toFixed(1)}초 | 섹션: {meta.section_count}개 | 분량: {(meta.total_chars || 0).toLocaleString()}자</p>
            <p>모드: {meta.mode} | 동시성: {meta.concurrency || 1} | 생성: {new Date(meta.generated_at || '').toLocaleString('ko-KR')}</p>
          </>
        ) : (
          <p>Method: {calculateResult.calculation_method}</p>
        )}
      </div>

      {/* 액션 버튼 */}
      <div className="flex gap-4">
        <button
          onClick={handleShare}
          className="flex-1 py-4 bg-gradient-to-r from-amber-500 to-amber-600 hover:from-amber-600 hover:to-amber-700 text-white font-bold rounded-xl shadow-lg transition"
        >
          📤 결과 공유하기
        </button>
        <button
          onClick={() => window.location.reload()}
          className="flex-1 py-4 bg-gray-100 hover:bg-gray-200 text-gray-700 font-bold rounded-xl transition"
        >
          🔄 다시 하기
        </button>
      </div>

      {/* 경계일 모달 */}
      {showBoundaryModal && (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50 p-4">
          <div className="bg-white rounded-2xl p-6 max-w-md w-full">
            <h3 className="text-lg font-bold text-yellow-700 mb-3">⚠️ 절기 경계일 안내</h3>
            <p className="text-gray-600 mb-4">이 날짜는 절기 경계에 가깝습니다.</p>
            <div className="flex gap-3">
              <button onClick={() => { setShowBoundaryModal(false); doShare(); }} className="flex-1 py-3 bg-yellow-500 hover:bg-yellow-600 text-white font-bold rounded-lg">공유</button>
              <button onClick={() => setShowBoundaryModal(false)} className="flex-1 py-3 bg-gray-200 hover:bg-gray-300 text-gray-700 font-bold rounded-lg">취소</button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
