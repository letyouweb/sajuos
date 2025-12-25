'use client';

import { useState } from 'react';
import type { CalculateResponse, InterpretResponse } from '@/types';
import { getAccuracyBadge, getAccuracyBadgeInfo, HOUR_OPTIONS } from '@/types';

interface ResultCardProps {
  calculateResult: CalculateResponse;
  interpretResult: InterpretResponse;
  onReset: () => void;
}

export default function ResultCard({
  calculateResult,
  interpretResult,
  onReset,
}: ResultCardProps) {
  const BRAND_NAME = process.env.NEXT_PUBLIC_BRAND_NAME ?? '사주OS';
  
  const [activeTab, setActiveTab] = useState<'summary' | 'detail' | 'calendar' | 'action'>('summary');
  const [showBoundaryModal, setShowBoundaryModal] = useState(false);

  // 30페이지 구조 데이터 추출
  const structure = (interpretResult as any).structure || {};
  const execSummary = structure.section_1_executive_summary || {};
  const dayMasterProfile = structure.section_2_day_master_profile || {};
  const moneyWealth = structure.section_3_money_wealth || {};
  const businessCareer = structure.section_4_business_career || {};
  const relationships = structure.section_5_relationships_team || {};
  const healthPerf = structure.section_6_health_performance || {};
  const monthlyCalendar = structure.section_7_monthly_calendar || {};
  const sprint90 = structure.section_8_90day_sprint || {};
  const luckyElements = structure.section_9_lucky_elements || {};
  const closingMessage = structure.closing_message || {};

  // 정확도 배지 계산
  const accuracyBadge = getAccuracyBadge(calculateResult.quality);
  const badgeInfo = getAccuracyBadgeInfo(accuracyBadge);

  const handleShare = async () => {
    if (calculateResult.quality.solar_term_boundary) {
      setShowBoundaryModal(true);
      return;
    }
    await doShare();
  };

  const doShare = async () => {
    const shareText = `🔮 ${BRAND_NAME} 2026년 프리미엄 보고서\n\n${execSummary.one_line_insight || interpretResult.summary}\n\n✨ ${closingMessage.blessing || interpretResult.blessing}`;
    
    if (navigator.share) {
      try {
        await navigator.share({ title: `${BRAND_NAME} 2026년 보고서`, text: shareText });
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

  // 월별 데이터 배열
  const months = ['january', 'february', 'march', 'april', 'may', 'june', 'july', 'august', 'september', 'october', 'november', 'december'];
  const monthLabels = ['1월', '2월', '3월', '4월', '5월', '6월', '7월', '8월', '9월', '10월', '11월', '12월'];

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
              accuracyBadge === 'boundary' ? 'text-yellow-700' :
              'text-blue-700'
            }`}>{badgeInfo.label}</p>
            <p className="text-xs text-gray-600">{badgeInfo.tooltip}</p>
          </div>
        </div>
      </div>

      {/* 사주 원국 카드 */}
      <div className="bg-white rounded-2xl shadow-lg overflow-hidden result-card">
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
            <p className="text-sm text-purple-600 font-medium mb-1">당신의 일간 (나를 나타내는 글자)</p>
            <p className="text-lg font-bold text-purple-800">
              {dayMasterProfile.day_master_element || `${calculateResult.day_master} (${calculateResult.day_master_element})`}
            </p>
            <p className="text-sm text-gray-600 mt-2">{calculateResult.day_master_description}</p>
          </div>

          <div className="mt-4 text-center">
            <p className="text-xs text-gray-400">기준: KST(Asia/Seoul) · 시주는 2시간 단위(범위 기준)로 계산됩니다.</p>
          </div>
        </div>
      </div>

      {/* 2026 프리미엄 보고서 */}
      <div className="bg-white rounded-2xl shadow-lg overflow-hidden result-card">
        <div className="bg-gradient-to-r from-purple-600 to-amber-500 text-white p-6">
          <h2 className="text-2xl font-bold mb-2">📊 2026년 프리미엄 컨설팅 보고서</h2>
          <p className="text-lg opacity-90">{execSummary.one_line_insight || interpretResult.summary}</p>
        </div>

        {/* 탭 네비게이션 */}
        <div className="flex border-b overflow-x-auto">
          {[
            { key: 'summary', label: '📋 종합분석' },
            { key: 'detail', label: '💰 재물/사업' },
            { key: 'calendar', label: '📅 월별운세' },
            { key: 'action', label: '🚀 90일플랜' },
          ].map((tab) => (
            <button
              key={tab.key}
              onClick={() => setActiveTab(tab.key as any)}
              className={`flex-1 py-4 px-2 text-sm font-medium transition whitespace-nowrap ${
                activeTab === tab.key
                  ? 'text-purple-600 border-b-2 border-purple-600 bg-purple-50'
                  : 'text-gray-500 hover:text-gray-700'
              }`}
            >
              {tab.label}
            </button>
          ))}
        </div>

        <div className="p-6">
          {/* 종합분석 탭 */}
          {activeTab === 'summary' && (
            <div className="space-y-6">
              {/* Executive Summary */}
              {execSummary.year_overview && (
                <div className="bg-gradient-to-r from-purple-50 to-amber-50 rounded-xl p-5">
                  <h3 className="font-bold text-purple-800 mb-3 text-lg">🎯 2026년 전체 방향</h3>
                  <p className="text-gray-700 leading-relaxed whitespace-pre-wrap">{execSummary.year_overview}</p>
                </div>
              )}

              {/* 기회 & 리스크 */}
              <div className="grid md:grid-cols-2 gap-4">
                <div className="bg-green-50 rounded-xl p-4">
                  <h4 className="font-bold text-green-700 mb-3">💪 핵심 기회</h4>
                  <ul className="space-y-2">
                    {(execSummary.key_opportunities || interpretResult.strengths || []).map((s: string, i: number) => (
                      <li key={i} className="text-sm text-gray-700 flex items-start">
                        <span className="text-green-500 mr-2 flex-shrink-0">✓</span>
                        <span>{s}</span>
                      </li>
                    ))}
                  </ul>
                </div>
                <div className="bg-orange-50 rounded-xl p-4">
                  <h4 className="font-bold text-orange-700 mb-3">⚡ 핵심 리스크</h4>
                  <ul className="space-y-2">
                    {(execSummary.key_risks || interpretResult.risks || []).map((r: string, i: number) => (
                      <li key={i} className="text-sm text-gray-700 flex items-start">
                        <span className="text-orange-500 mr-2 flex-shrink-0">!</span>
                        <span>{r}</span>
                      </li>
                    ))}
                  </ul>
                </div>
              </div>

              {/* 일간(나) 심층 분석 */}
              {dayMasterProfile.personality_analysis && (
                <div className="bg-gray-50 rounded-xl p-5">
                  <h3 className="font-bold text-gray-800 mb-3 text-lg">🧬 일간(나) 심층 프로파일</h3>
                  <p className="text-gray-700 leading-relaxed whitespace-pre-wrap mb-4">{dayMasterProfile.personality_analysis}</p>
                  
                  {dayMasterProfile.communication_style && (
                    <div className="mt-3 p-3 bg-white rounded-lg">
                      <p className="text-sm font-medium text-purple-600">💬 커뮤니케이션 스타일</p>
                      <p className="text-sm text-gray-600">{dayMasterProfile.communication_style}</p>
                    </div>
                  )}
                  {dayMasterProfile.decision_making_pattern && (
                    <div className="mt-3 p-3 bg-white rounded-lg">
                      <p className="text-sm font-medium text-purple-600">🎯 의사결정 패턴</p>
                      <p className="text-sm text-gray-600">{dayMasterProfile.decision_making_pattern}</p>
                    </div>
                  )}
                  {dayMasterProfile.leadership_archetype && (
                    <div className="mt-3 p-3 bg-white rounded-lg">
                      <p className="text-sm font-medium text-purple-600">👑 리더십 유형</p>
                      <p className="text-sm text-gray-600">{dayMasterProfile.leadership_archetype}</p>
                    </div>
                  )}
                </div>
              )}

              {/* 건강 & 퍼포먼스 */}
              {healthPerf.energy_system_analysis && (
                <div className="bg-blue-50 rounded-xl p-5">
                  <h3 className="font-bold text-blue-800 mb-3 text-lg">💪 Health & Performance</h3>
                  <p className="text-gray-700 leading-relaxed whitespace-pre-wrap">{healthPerf.energy_system_analysis}</p>
                  {healthPerf.burnout_risk && (
                    <div className="mt-3 p-3 bg-white rounded-lg">
                      <p className="text-sm font-medium text-red-600">⚠️ 번아웃 리스크</p>
                      <p className="text-sm text-gray-600">{healthPerf.burnout_risk}</p>
                    </div>
                  )}
                </div>
              )}

              {/* 행운 요소 */}
              <div className="bg-amber-50 rounded-xl p-4">
                <h4 className="font-bold text-amber-700 mb-3">🍀 행운 요소</h4>
                <div className="grid grid-cols-3 gap-4">
                  <div className="text-center">
                    <p className="text-xs text-gray-500">행운의 색</p>
                    <p className="font-bold text-amber-800">
                      {(luckyElements.lucky_colors || [])[0] || interpretResult.lucky_elements?.color || '-'}
                    </p>
                  </div>
                  <div className="text-center">
                    <p className="text-xs text-gray-500">행운의 방향</p>
                    <p className="font-bold text-amber-800">
                      {(luckyElements.lucky_directions || [])[0] || interpretResult.lucky_elements?.direction || '-'}
                    </p>
                  </div>
                  <div className="text-center">
                    <p className="text-xs text-gray-500">행운의 숫자</p>
                    <p className="font-bold text-amber-800">
                      {(luckyElements.lucky_numbers || [])[0] || interpretResult.lucky_elements?.number || '-'}
                    </p>
                  </div>
                </div>
              </div>
            </div>
          )}

          {/* 재물/사업 탭 */}
          {activeTab === 'detail' && (
            <div className="space-y-6">
              {/* Money & Wealth */}
              {moneyWealth.wealth_structure_analysis && (
                <div className="bg-green-50 rounded-xl p-5">
                  <h3 className="font-bold text-green-800 mb-3 text-lg">💰 재물 구조 분석</h3>
                  <p className="text-gray-700 leading-relaxed whitespace-pre-wrap">{moneyWealth.wealth_structure_analysis}</p>
                </div>
              )}
              {moneyWealth.income_optimization && (
                <div className="bg-emerald-50 rounded-xl p-5">
                  <h3 className="font-bold text-emerald-800 mb-3">📈 수익 최적화 전략</h3>
                  <p className="text-gray-700 leading-relaxed whitespace-pre-wrap">{moneyWealth.income_optimization}</p>
                </div>
              )}
              {moneyWealth.cashflow_forecast_2026 && (
                <div className="bg-teal-50 rounded-xl p-5">
                  <h3 className="font-bold text-teal-800 mb-3">💵 2026년 현금흐름 예측</h3>
                  <p className="text-gray-700 leading-relaxed whitespace-pre-wrap">{moneyWealth.cashflow_forecast_2026}</p>
                </div>
              )}
              {moneyWealth.money_action_plan && (
                <div className="bg-white border border-green-200 rounded-xl p-4">
                  <h4 className="font-bold text-green-700 mb-3">✅ 재물 액션 플랜</h4>
                  {(moneyWealth.money_action_plan || []).map((action: string, i: number) => (
                    <div key={i} className="flex items-start mb-2">
                      <span className="flex-shrink-0 w-6 h-6 bg-green-500 text-white rounded-full flex items-center justify-center text-xs mr-2">{i+1}</span>
                      <p className="text-sm text-gray-700">{action}</p>
                    </div>
                  ))}
                </div>
              )}

              {/* Business & Career */}
              {businessCareer.career_dna_analysis && (
                <div className="bg-purple-50 rounded-xl p-5 mt-6">
                  <h3 className="font-bold text-purple-800 mb-3 text-lg">💼 커리어 DNA 분석</h3>
                  <p className="text-gray-700 leading-relaxed whitespace-pre-wrap">{businessCareer.career_dna_analysis}</p>
                </div>
              )}
              {businessCareer["2026_business_climate"] && (
                <div className="bg-indigo-50 rounded-xl p-5">
                  <h3 className="font-bold text-indigo-800 mb-3">🌤️ 2026년 비즈니스 환경</h3>
                  <p className="text-gray-700 leading-relaxed whitespace-pre-wrap">{businessCareer["2026_business_climate"]}</p>
                </div>
              )}
              {businessCareer.growth_leverage_points && (
                <div className="bg-violet-50 rounded-xl p-5">
                  <h3 className="font-bold text-violet-800 mb-3">🚀 성장 레버리지 포인트</h3>
                  <p className="text-gray-700 leading-relaxed whitespace-pre-wrap">{businessCareer.growth_leverage_points}</p>
                </div>
              )}

              {/* Relationships */}
              {relationships.relationship_pattern && (
                <div className="bg-pink-50 rounded-xl p-5 mt-6">
                  <h3 className="font-bold text-pink-800 mb-3 text-lg">👥 관계 패턴 분석</h3>
                  <p className="text-gray-700 leading-relaxed whitespace-pre-wrap">{relationships.relationship_pattern}</p>
                </div>
              )}
            </div>
          )}

          {/* 월별운세 탭 */}
          {activeTab === 'calendar' && (
            <div className="space-y-4">
              <h3 className="font-bold text-purple-800 text-lg mb-4">📅 2026년 12개월 전술 캘린더</h3>
              
              {/* 최고/주의 달 하이라이트 */}
              <div className="grid md:grid-cols-2 gap-4 mb-6">
                <div className="bg-green-50 rounded-xl p-4">
                  <h4 className="font-bold text-green-700 mb-2">🌟 최고의 달</h4>
                  {(monthlyCalendar.best_months || interpretResult.lucky_periods || []).map((m: string, i: number) => (
                    <p key={i} className="text-sm text-gray-700">✓ {m}</p>
                  ))}
                </div>
                <div className="bg-red-50 rounded-xl p-4">
                  <h4 className="font-bold text-red-700 mb-2">⚠️ 주의할 달</h4>
                  {(monthlyCalendar.caution_months || interpretResult.caution_periods || []).map((m: string, i: number) => (
                    <p key={i} className="text-sm text-gray-700">! {m}</p>
                  ))}
                </div>
              </div>

              {/* 12개월 상세 */}
              <div className="grid md:grid-cols-2 lg:grid-cols-3 gap-3">
                {months.map((month, idx) => {
                  const data = monthlyCalendar[month] || {};
                  return (
                    <div key={month} className="bg-gray-50 rounded-lg p-3 border border-gray-100">
                      <h5 className="font-bold text-purple-700 mb-2">{monthLabels[idx]}</h5>
                      {data.theme && <p className="text-sm font-medium text-gray-800 mb-1">{data.theme}</p>}
                      {data.opportunities && <p className="text-xs text-green-600">✓ {data.opportunities}</p>}
                      {data.cautions && <p className="text-xs text-orange-600">! {data.cautions}</p>}
                      {data.action && <p className="text-xs text-blue-600 mt-1">→ {data.action}</p>}
                    </div>
                  );
                })}
              </div>
            </div>
          )}

          {/* 90일 플랜 탭 */}
          {activeTab === 'action' && (
            <div className="space-y-6">
              <h3 className="font-bold text-purple-800 text-lg">🚀 90일 스프린트 실행 계획</h3>
              
              {sprint90.sprint_overview && (
                <div className="bg-purple-50 rounded-xl p-5">
                  <p className="text-gray-700 leading-relaxed">{sprint90.sprint_overview}</p>
                </div>
              )}

              {/* 주간별 플랜 */}
              <div className="space-y-4">
                {sprint90.week_1_4 && (
                  <div className="bg-blue-50 rounded-xl p-4">
                    <h4 className="font-bold text-blue-700 mb-2">📌 1-4주차: {sprint90.week_1_4.focus}</h4>
                    {(sprint90.week_1_4.actions || []).map((a: string, i: number) => (
                      <p key={i} className="text-sm text-gray-700 ml-4">• {a}</p>
                    ))}
                    {sprint90.week_1_4.kpi && <p className="text-xs text-blue-600 mt-2">KPI: {sprint90.week_1_4.kpi}</p>}
                  </div>
                )}
                {sprint90.week_5_8 && (
                  <div className="bg-indigo-50 rounded-xl p-4">
                    <h4 className="font-bold text-indigo-700 mb-2">📌 5-8주차: {sprint90.week_5_8.focus}</h4>
                    {(sprint90.week_5_8.actions || []).map((a: string, i: number) => (
                      <p key={i} className="text-sm text-gray-700 ml-4">• {a}</p>
                    ))}
                    {sprint90.week_5_8.kpi && <p className="text-xs text-indigo-600 mt-2">KPI: {sprint90.week_5_8.kpi}</p>}
                  </div>
                )}
                {sprint90.week_9_12 && (
                  <div className="bg-violet-50 rounded-xl p-4">
                    <h4 className="font-bold text-violet-700 mb-2">📌 9-12주차: {sprint90.week_9_12.focus}</h4>
                    {(sprint90.week_9_12.actions || []).map((a: string, i: number) => (
                      <p key={i} className="text-sm text-gray-700 ml-4">• {a}</p>
                    ))}
                    {sprint90.week_9_12.kpi && <p className="text-xs text-violet-600 mt-2">KPI: {sprint90.week_9_12.kpi}</p>}
                  </div>
                )}
              </div>

              {sprint90.success_metrics && (
                <div className="bg-green-50 rounded-xl p-4">
                  <h4 className="font-bold text-green-700 mb-2">🎯 90일 성공 지표</h4>
                  <p className="text-gray-700">{sprint90.success_metrics}</p>
                </div>
              )}

              {/* 레거시 액션 플랜 (fallback) */}
              {!sprint90.sprint_overview && interpretResult.action_plan && (
                <div className="space-y-3">
                  {interpretResult.action_plan.map((action, i) => (
                    <div key={i} className="flex items-start p-4 bg-blue-50 rounded-xl">
                      <span className="flex-shrink-0 w-8 h-8 bg-blue-500 text-white rounded-full flex items-center justify-center font-bold mr-3">{i + 1}</span>
                      <p className="text-gray-700 pt-1">{action}</p>
                    </div>
                  ))}
                </div>
              )}

              {/* 축복 메시지 */}
              <div className="text-center py-6 bg-gradient-to-r from-purple-50 to-amber-50 rounded-xl">
                <p className="text-xl text-purple-700 font-medium">
                  ✨ {closingMessage.blessing || interpretResult.blessing}
                </p>
                {closingMessage.final_advice && (
                  <p className="text-sm text-gray-600 mt-3 px-4">{closingMessage.final_advice}</p>
                )}
              </div>
            </div>
          )}
        </div>

        {/* 면책조항 */}
        <div className="px-6 pb-6">
          <div className="disclaimer">
            {structure.disclaimer || interpretResult.disclaimer}
          </div>
        </div>
      </div>

      {/* 정확도 배지 (하단) */}
      <div className={`p-3 rounded-lg text-center ${
        accuracyBadge === 'high' ? 'bg-green-50' :
        accuracyBadge === 'boundary' ? 'bg-yellow-50' :
        'bg-blue-50'
      }`}>
        <p className={`text-sm ${
          accuracyBadge === 'high' ? 'text-green-600' :
          accuracyBadge === 'boundary' ? 'text-yellow-600' :
          'text-blue-600'
        }`}>{badgeInfo.icon} {badgeInfo.label}</p>
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
          onClick={onReset}
          className="flex-1 py-4 bg-gray-100 hover:bg-gray-200 text-gray-700 font-bold rounded-xl transition"
        >
          🔄 다시 하기
        </button>
      </div>

      {/* 메타 정보 */}
      <div className="text-center text-xs text-gray-400">
        <p>Model: {interpretResult.model_used} | Tokens: {interpretResult.tokens_used || 'N/A'}</p>
        <p>Method: {calculateResult.calculation_method}</p>
      </div>

      {/* 경계일 모달 */}
      {showBoundaryModal && (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50 p-4">
          <div className="bg-white rounded-2xl p-6 max-w-md w-full">
            <h3 className="text-lg font-bold text-yellow-700 mb-3">⚠️ 절기 경계일 안내</h3>
            <p className="text-gray-600 mb-4">이 날짜는 절기 경계에 가깝습니다. 출생시간에 따라 결과에 오차가 있을 수 있습니다.</p>
            <div className="flex gap-3">
              <button onClick={() => { setShowBoundaryModal(false); doShare(); }} className="flex-1 py-3 bg-yellow-500 hover:bg-yellow-600 text-white font-bold rounded-lg">공유하기</button>
              <button onClick={() => setShowBoundaryModal(false)} className="flex-1 py-3 bg-gray-200 hover:bg-gray-300 text-gray-700 font-bold rounded-lg">취소</button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
