'use client';

import { useState } from 'react';
import type { CalculateResponse, InterpretResponse } from '@/types';
import { getAccuracyBadge, getAccuracyBadgeInfo, HOUR_OPTIONS } from '@/types';

interface ResultCardProps {
  calculateResult: CalculateResponse;
  interpretResult: InterpretResponse;
  onReset: () => void;
}

// 새 보고서 구조 타입
interface ReportSection {
  title: string;
  markdown: string;
  highlights?: any[];
  risks?: any[];
  actionItems?: any[];
  evidence?: { ruleCardIds: string[]; topTags: string[] };
  confidence?: string;
  [key: string]: any;
}

interface PremiumReport {
  meta?: {
    reportType: string;
    targetYear: number;
    sectionCount: number;
    ruleCardsUsedTotal: number;
    confidence: { overall: string; bySection: Record<string, string> };
    latencyMs: { total: number; bySection: Record<string, number> };
  };
  toc?: { id: string; title: string }[];
  sections?: Record<string, ReportSection>;
  render?: { mergedMarkdown: string; notes: string };
  legacy?: any;
}

export default function ResultCard({
  calculateResult,
  interpretResult,
}: ResultCardProps) {
  const BRAND_NAME = process.env.NEXT_PUBLIC_BRAND_NAME ?? '사주OS';
  
  const [activeSection, setActiveSection] = useState<string>('exec');
  const [showBoundaryModal, setShowBoundaryModal] = useState(false);

  // 새 리포트 구조 감지
  const report = interpretResult as unknown as PremiumReport;
  const isPremiumReport = !!report.sections && !!report.meta;
  
  // 레거시 또는 새 구조에서 데이터 추출
  const legacy = report.legacy || interpretResult;
  const meta = report.meta;
  const sections = report.sections || {};
  const toc = report.toc || [];

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
    const summary = isPremiumReport 
      ? sections.exec?.highlights?.[0]?.content || legacy.summary
      : legacy.summary;
    const blessing = isPremiumReport
      ? legacy.blessing
      : (interpretResult as any).blessing;
      
    const shareText = `🔮 ${BRAND_NAME} ${meta?.targetYear || 2026}년 프리미엄 보고서\n\n${summary}\n\n✨ ${blessing}`;
    
    if (navigator.share) {
      try {
        await navigator.share({ title: `${BRAND_NAME} 프리미엄 보고서`, text: shareText });
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

  // 마크다운 렌더링 (간단 버전)
  const renderMarkdown = (md: string) => {
    if (!md) return null;
    
    // 간단한 마크다운 → HTML 변환
    const lines = md.split('\n');
    const elements: JSX.Element[] = [];
    
    lines.forEach((line, idx) => {
      if (line.startsWith('## ')) {
        elements.push(<h2 key={idx} className="text-xl font-bold text-purple-800 mt-6 mb-3">{line.slice(3)}</h2>);
      } else if (line.startsWith('### ')) {
        elements.push(<h3 key={idx} className="text-lg font-bold text-purple-700 mt-4 mb-2">{line.slice(4)}</h3>);
      } else if (line.startsWith('- ')) {
        elements.push(<li key={idx} className="ml-4 text-gray-700">{line.slice(2)}</li>);
      } else if (line.startsWith('**') && line.endsWith('**')) {
        elements.push(<p key={idx} className="font-bold text-gray-800 mt-2">{line.slice(2, -2)}</p>);
      } else if (line.trim()) {
        elements.push(<p key={idx} className="text-gray-700 mb-2">{line}</p>);
      }
    });
    
    return <div className="prose prose-sm max-w-none">{elements}</div>;
  };

  // 섹션별 아이콘
  const sectionIcons: Record<string, string> = {
    exec: '📊',
    money: '💰',
    business: '💼',
    team: '👥',
    health: '💪',
    calendar: '📅',
    sprint: '🚀'
  };

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
        {isPremiumReport && meta && (
          <div className="text-right text-xs text-gray-500">
            <p>✨ 프리미엄 리포트</p>
            <p>{meta.sectionCount}개 섹션 · {meta.ruleCardsUsedTotal}장 RuleCard</p>
          </div>
        )}
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
              {calculateResult.day_master} ({calculateResult.day_master_element})
            </p>
            <p className="text-sm text-gray-600 mt-2">{calculateResult.day_master_description}</p>
          </div>

          <div className="mt-4 text-center">
            <p className="text-xs text-gray-400">기준: KST(Asia/Seoul) · 시주는 2시간 단위(범위 기준)로 계산됩니다.</p>
          </div>
        </div>
      </div>

      {/* 프리미엄 보고서 */}
      {isPremiumReport ? (
        <div className="bg-white rounded-2xl shadow-lg overflow-hidden">
          {/* 헤더 */}
          <div className="bg-gradient-to-r from-purple-600 via-purple-500 to-amber-500 text-white p-6">
            <div className="flex items-center justify-between">
              <div>
                <h2 className="text-2xl font-bold mb-1">📊 {meta?.targetYear}년 프리미엄 컨설팅 보고서</h2>
                <p className="opacity-90">비즈니스 오너를 위한 30페이지 심층 분석</p>
              </div>
              <div className="text-right">
                <span className={`px-3 py-1 rounded-full text-sm font-medium ${
                  meta?.confidence?.overall === 'HIGH' ? 'bg-green-500' :
                  meta?.confidence?.overall === 'MEDIUM' ? 'bg-yellow-500' : 'bg-red-500'
                }`}>
                  신뢰도: {meta?.confidence?.overall}
                </span>
              </div>
            </div>
          </div>

          {/* 목차 탭 */}
          <div className="border-b overflow-x-auto">
            <div className="flex">
              {toc.map((item) => (
                <button
                  key={item.id}
                  onClick={() => setActiveSection(item.id)}
                  className={`flex-shrink-0 px-4 py-3 text-sm font-medium transition whitespace-nowrap ${
                    activeSection === item.id
                      ? 'text-purple-600 border-b-2 border-purple-600 bg-purple-50'
                      : 'text-gray-500 hover:text-gray-700 hover:bg-gray-50'
                  }`}
                >
                  {sectionIcons[item.id] || '📄'} {item.title.length > 12 ? item.title.slice(0, 12) + '...' : item.title}
                </button>
              ))}
            </div>
          </div>

          {/* 섹션 콘텐츠 */}
          <div className="p-6">
            {Object.entries(sections).map(([sectionId, section]) => (
              <div 
                key={sectionId} 
                className={activeSection === sectionId ? 'block' : 'hidden'}
              >
                {/* 섹션 헤더 */}
                <div className="flex items-center justify-between mb-4">
                  <h3 className="text-xl font-bold text-gray-800">
                    {sectionIcons[sectionId]} {section.title}
                  </h3>
                  <span className={`px-2 py-1 rounded text-xs ${
                    section.confidence === 'HIGH' ? 'bg-green-100 text-green-700' :
                    section.confidence === 'MEDIUM' ? 'bg-yellow-100 text-yellow-700' :
                    'bg-red-100 text-red-700'
                  }`}>
                    {section.confidence}
                  </span>
                </div>

                {/* 마크다운 콘텐츠 */}
                <div className="bg-gray-50 rounded-xl p-5 mb-4">
                  {renderMarkdown(section.markdown)}
                </div>

                {/* 하이라이트 */}
                {section.highlights && section.highlights.length > 0 && (
                  <div className="mb-4">
                    <h4 className="font-bold text-green-700 mb-2">💡 핵심 포인트</h4>
                    <div className="grid md:grid-cols-2 gap-2">
                      {section.highlights.slice(0, 10).map((h: any, i: number) => (
                        <div key={i} className="bg-green-50 rounded-lg p-3 text-sm">
                          {typeof h === 'string' ? h : h.content || JSON.stringify(h)}
                        </div>
                      ))}
                    </div>
                  </div>
                )}

                {/* 리스크 */}
                {section.risks && section.risks.length > 0 && (
                  <div className="mb-4">
                    <h4 className="font-bold text-orange-700 mb-2">⚠️ 리스크 요인</h4>
                    <div className="space-y-2">
                      {section.risks.slice(0, 5).map((r: any, i: number) => (
                        <div key={i} className="bg-orange-50 rounded-lg p-3 text-sm">
                          {typeof r === 'string' ? r : r.content || r.scenario || JSON.stringify(r)}
                        </div>
                      ))}
                    </div>
                  </div>
                )}

                {/* 액션 아이템 */}
                {section.actionItems && section.actionItems.length > 0 && (
                  <div className="mb-4">
                    <h4 className="font-bold text-blue-700 mb-2">✅ 실행 계획</h4>
                    <div className="space-y-2">
                      {section.actionItems.slice(0, 10).map((a: any, i: number) => (
                        <div key={i} className="flex items-start bg-blue-50 rounded-lg p-3">
                          <span className="flex-shrink-0 w-6 h-6 bg-blue-500 text-white rounded-full flex items-center justify-center text-xs mr-2">{i+1}</span>
                          <span className="text-sm">{typeof a === 'string' ? a : a.action || JSON.stringify(a)}</span>
                        </div>
                      ))}
                    </div>
                  </div>
                )}

                {/* 월별 캘린더 (calendar 섹션) */}
                {sectionId === 'calendar' && section.monthlyCalendar && (
                  <div className="mt-4">
                    <h4 className="font-bold text-purple-700 mb-3">📅 월별 상세</h4>
                    <div className="grid md:grid-cols-3 lg:grid-cols-4 gap-3">
                      {section.monthlyCalendar.map((month: any, i: number) => (
                        <div key={i} className="bg-white border rounded-lg p-3">
                          <h5 className="font-bold text-purple-600 mb-1">{month.month}</h5>
                          <p className="text-xs text-gray-600 mb-2">{month.theme}</p>
                          {month.keywords && (
                            <div className="flex flex-wrap gap-1">
                              {month.keywords.map((kw: string, j: number) => (
                                <span key={j} className="px-2 py-0.5 bg-purple-100 text-purple-700 rounded text-xs">{kw}</span>
                              ))}
                            </div>
                          )}
                        </div>
                      ))}
                    </div>
                  </div>
                )}

                {/* 주간 플랜 (sprint 섹션) */}
                {sectionId === 'sprint' && section.weeklyPlan && (
                  <div className="mt-4">
                    <h4 className="font-bold text-purple-700 mb-3">📋 주간 계획</h4>
                    <div className="space-y-2">
                      {section.weeklyPlan.slice(0, 12).map((week: any, i: number) => (
                        <div key={i} className="bg-white border rounded-lg p-3">
                          <div className="flex items-center justify-between mb-2">
                            <span className="font-bold text-purple-600">{week.week}주차</span>
                            <span className="text-xs text-gray-500">{week.theme}</span>
                          </div>
                          {week.goals && (
                            <ul className="text-sm text-gray-700">
                              {week.goals.map((g: any, j: number) => (
                                <li key={j} className="ml-2">• {typeof g === 'string' ? g : g.goal}</li>
                              ))}
                            </ul>
                          )}
                        </div>
                      ))}
                    </div>
                  </div>
                )}

                {/* 증거 (RuleCard IDs) */}
                {section.evidence?.ruleCardIds && section.evidence.ruleCardIds.length > 0 && (
                  <div className="mt-4 p-3 bg-gray-100 rounded-lg">
                    <p className="text-xs text-gray-500">
                      📚 근거: {section.evidence.ruleCardIds.length}개 RuleCard 참조
                    </p>
                  </div>
                )}
              </div>
            ))}
          </div>

          {/* 면책조항 */}
          <div className="px-6 pb-6">
            <div className="disclaimer">
              {report.render?.notes || legacy.disclaimer || '본 보고서는 오락/참고 목적으로 제공됩니다.'}
            </div>
          </div>
        </div>
      ) : (
        /* 레거시 UI (단일 호출 결과) */
        <div className="bg-white rounded-2xl shadow-lg overflow-hidden result-card">
          <div className="p-6">
            <h3 className="text-xl font-bold text-purple-800 mb-4">{legacy.summary}</h3>
            
            {legacy.day_master_analysis && (
              <div className="bg-gray-50 rounded-xl p-4 mb-4">
                <h4 className="font-bold text-gray-700 mb-2">🧬 일간 분석</h4>
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

            {legacy.answer && (
              <div className="bg-purple-50 rounded-xl p-4 mb-4">
                <h4 className="font-bold text-purple-700 mb-2">💬 답변</h4>
                <p className="text-gray-700">{legacy.answer}</p>
              </div>
            )}

            <div className="text-center py-4 bg-gradient-to-r from-purple-50 to-amber-50 rounded-xl">
              <p className="text-lg text-purple-700 font-medium">✨ {legacy.blessing}</p>
            </div>
          </div>

          <div className="px-6 pb-6">
            <div className="disclaimer">{legacy.disclaimer}</div>
          </div>
        </div>
      )}

      {/* 메타 정보 */}
      <div className="text-center text-xs text-gray-400">
        {isPremiumReport && meta ? (
          <>
            <p>Model: {meta.latencyMs?.total ? `${(meta.latencyMs.total / 1000).toFixed(1)}s` : 'N/A'} | Sections: {meta.sectionCount} | RuleCards: {meta.ruleCardsUsedTotal}</p>
            <p>Mode: {meta.reportType} | Confidence: {meta.confidence?.overall}</p>
          </>
        ) : (
          <>
            <p>Model: {(interpretResult as any).model_used} | Tokens: {(interpretResult as any).tokens_used || 'N/A'}</p>
            <p>Method: {calculateResult.calculation_method}</p>
          </>
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
