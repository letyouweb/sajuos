"use client";

import { useEffect, useState } from "react";
import ResultCard from "@/components/ResultCard";

// 🔥 P0: 절대주소 강제 (환경변수 또는 하드코딩)
const API_BASE = (process.env.NEXT_PUBLIC_API_BASE || "https://api.sajuos.com").replace(/\/$/, "");

/**
 * 🔥 백엔드 응답 형태가 바뀌어도 안 터지게 방어적으로 정규화
 */
function normalizeViewResponse(raw: any) {
  const job = raw?.job ?? raw?.data?.job ?? raw?.[0]?.job ?? raw?.job_data ?? raw?.jobData ?? raw;
  const sections = raw?.sections ?? raw?.data?.sections ?? raw?.report_sections ?? raw?.section_list ?? [];
  // 🔥 P0 수정: input_json (사주 데이터 포함)
  const input = raw?.input ?? raw?.input_json ?? raw?.data?.input ?? {};
  return { job, sections: Array.isArray(sections) ? sections : [], input };
}

/**
 * 🔥🔥🔥 핵심: API 응답의 sections를 ResultCard가 기대하는 형식으로 변환
 */
function transformSectionsForResultCard(apiSections: any[]) {
  if (!apiSections || apiSections.length === 0) return [];
  
  return apiSections.map((s: any) => ({
    id: s?.id || s?.section_id,
    section_id: s?.section_id || s?.id,
    title: s?.title || getTitleForSection(s?.id || s?.section_id),
    status: s?.status,
    content: s?.content || s?.raw_json?.body_markdown || s?.body_markdown,
    body_markdown: s?.body_markdown || s?.raw_json?.body_markdown || s?.content,
    confidence: s?.confidence || s?.raw_json?.confidence || 'MEDIUM',
    rulecard_ids: s?.rulecard_ids || s?.raw_json?.rulecard_ids || [],
    rulecard_selected: s?.rulecard_selected || s?.raw_json?.rulecard_selected,
    char_count: s?.char_count || s?.raw_json?.char_count,
    // 섹션별 데이터 (프리미엄 보고서용)
    diagnosis: s?.diagnosis || s?.raw_json?.diagnosis,
    hypotheses: s?.hypotheses || s?.raw_json?.hypotheses,
    strategy_options: s?.strategy_options || s?.raw_json?.strategy_options,
    recommended_strategy: s?.recommended_strategy || s?.raw_json?.recommended_strategy,
    kpis: s?.kpis || s?.raw_json?.kpis,
    risks: s?.risks || s?.raw_json?.risks,
    // Calendar 전용
    annual_theme: s?.annual_theme || s?.raw_json?.annual_theme,
    annual_revenue_projection: s?.annual_revenue_projection || s?.raw_json?.annual_revenue_projection,
    monthly_plans: s?.monthly_plans || s?.raw_json?.monthly_plans,
    quarterly_milestones: s?.quarterly_milestones || s?.raw_json?.quarterly_milestones,
    peak_months: s?.peak_months || s?.raw_json?.peak_months,
    risk_months: s?.risk_months || s?.raw_json?.risk_months,
    // Sprint 전용
    mission_statement: s?.mission_statement || s?.raw_json?.mission_statement,
    phase_1_offer: s?.phase_1_offer || s?.raw_json?.phase_1_offer,
    phase_2_funnel: s?.phase_2_funnel || s?.raw_json?.phase_2_funnel,
    phase_3_content: s?.phase_3_content || s?.raw_json?.phase_3_content,
    phase_4_automation: s?.phase_4_automation || s?.raw_json?.phase_4_automation,
    milestones: s?.milestones || s?.raw_json?.milestones,
    risk_scenarios: s?.risk_scenarios || s?.raw_json?.risk_scenarios,
    // raw_json 전체 spread
    ...s?.raw_json,
  }));
}

function getTitleForSection(sectionId: string): string {
  const titles: Record<string, string> = {
    exec: 'Executive Summary',
    money: 'Money & Cashflow',
    business: 'Business Strategy',
    team: 'Team & Partner',
    health: 'Health & Performance',
    calendar: '12-Month Calendar',
    sprint: '90-Day Sprint',
  };
  return titles[sectionId] || sectionId;
}

interface ReportClientProps {
  jobId: string;
  token: string;
}

export default function ReportClient({ jobId, token }: ReportClientProps) {
  const [raw, setRaw] = useState<any>(null);
  const [job, setJob] = useState<any>(null);
  const [sections, setSections] = useState<any[]>([]);
  const [input, setInput] = useState<any>({});
  const [error, setError] = useState<string>("");
  const [status, setStatus] = useState<"loading" | "generating" | "completed" | "error">("loading");
  const [progress, setProgress] = useState(0);

  const BRAND_NAME = process.env.NEXT_PUBLIC_BRAND_NAME ?? "사주OS";

  useEffect(() => {
    if (!jobId) {
      setError("Invalid link (jobId missing)");
      setStatus("error");
      return;
    }
    if (!token) {
      setError("Invalid token (token missing). 이메일 링크를 다시 확인해주세요.");
      setStatus("error");
      return;
    }

    let pollingInterval: NodeJS.Timeout | null = null;
    let isMounted = true;

    const fetchView = async () => {
      try {
        const url = `${API_BASE}/api/v1/reports/view/${jobId}?token=${encodeURIComponent(token)}`;
        console.log("[ReportView] Fetching:", url);
        
        const res = await fetch(url, { cache: "no-store" });

        if (!res.ok) {
          const txt = await res.text();
          throw new Error(`view failed ${res.status}: ${txt.slice(0, 300)}`);
        }

        const json = await res.json();
        console.log("[ReportView raw]", json);
        
        if (!isMounted) return;
        
        setRaw(json);

        const n = normalizeViewResponse(json);
        setJob(n.job);
        setSections(n.sections);
        setInput(n.input);

        // 🔥 디버그: sections 확인
        console.log("[ReportView] sections:", n.sections.length, n.sections.map((s: any) => s?.id || s?.section_id));

        const jobStatus = n.job?.status || "unknown";
        const jobProgress = n.job?.progress || 0;
        
        console.log("[ReportView] status:", jobStatus, "progress:", jobProgress);

        if (jobStatus === "completed") {
          setProgress(100);
          setStatus("completed");
        } else if (jobStatus === "failed") {
          setError(n.job?.error || "리포트 생성에 실패했습니다");
          setStatus("error");
        } else if (["running", "queued", "pending"].includes(jobStatus)) {
          setProgress(jobProgress);
          setStatus("generating");
          startPolling();
        } else {
          setProgress(jobProgress);
          setStatus("generating");
          startPolling();
        }
      } catch (e: any) {
        if (!isMounted) return;
        console.error("[ReportView] Error:", e);
        setError(e?.message || "Unknown error");
        setStatus("error");
      }
    };

    const startPolling = () => {
      if (pollingInterval) return;
      
      pollingInterval = setInterval(async () => {
        try {
          const url = `${API_BASE}/api/v1/reports/view/${jobId}?token=${encodeURIComponent(token)}`;
          const res = await fetch(url, { cache: "no-store" });
          
          if (!res.ok) return;
          
          const json = await res.json();
          if (!isMounted) return;
          
          setRaw(json);
          const n = normalizeViewResponse(json);
          setJob(n.job);
          setSections(n.sections);
          setInput(n.input);
          
          const jobStatus = n.job?.status;
          const jobProgress = n.job?.progress || 0;
          
          if (jobStatus === "completed") {
            if (pollingInterval) clearInterval(pollingInterval);
            setProgress(100);
            setStatus("completed");
          } else if (jobStatus === "failed") {
            if (pollingInterval) clearInterval(pollingInterval);
            setError(n.job?.error || "리포트 생성에 실패했습니다");
            setStatus("error");
          } else {
            setProgress(jobProgress);
          }
        } catch (e) {
          console.warn("[ReportView] Polling error (ignored):", e);
        }
      }, 3000);
    };

    fetchView();

    return () => {
      isMounted = false;
      if (pollingInterval) clearInterval(pollingInterval);
    };
  }, [jobId, token]);

  // ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  // 🔥 에러 화면
  // ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  if (status === "error") {
    return (
      <div className="min-h-screen bg-gradient-to-b from-slate-50 to-purple-50 py-8">
        <div className="container mx-auto px-4 max-w-4xl">
          <header className="text-center py-6">
            <h1 className="text-3xl font-bold bg-gradient-to-r from-purple-600 to-amber-500 bg-clip-text text-transparent">
              🔮 {BRAND_NAME}
            </h1>
          </header>
          
          <div className="bg-red-50 border border-red-200 rounded-2xl p-8 text-center">
            <div className="text-5xl mb-4">⚠️</div>
            <h2 className="text-xl font-bold text-red-700 mb-4">오류가 발생했습니다</h2>
            <pre className="text-left bg-white p-4 rounded-lg text-sm text-red-600 overflow-auto max-h-40 mb-6 whitespace-pre-wrap">
              {error}
            </pre>
            
            {raw && (
              <details className="text-left mb-6">
                <summary className="text-sm text-gray-500 cursor-pointer">디버그 정보 (개발자용)</summary>
                <pre className="mt-2 p-4 bg-gray-100 rounded text-xs overflow-auto max-h-60">
                  {JSON.stringify(raw, null, 2)}
                </pre>
              </details>
            )}
            
            <div className="space-x-4">
              <button
                onClick={() => window.location.reload()}
                className="px-6 py-2 bg-red-600 text-white rounded-lg hover:bg-red-700 transition"
              >
                다시 시도
              </button>
              <button
                onClick={() => window.location.href = "/"}
                className="px-6 py-2 bg-gray-200 text-gray-700 rounded-lg hover:bg-gray-300 transition"
              >
                홈으로
              </button>
            </div>
          </div>
        </div>
      </div>
    );
  }

  // ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  // 🔥 로딩 화면
  // ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  if (status === "loading") {
    return (
      <div className="min-h-screen bg-gradient-to-b from-slate-50 to-purple-50 flex items-center justify-center">
        <div className="text-center">
          <div className="w-16 h-16 border-4 border-purple-200 border-t-purple-600 rounded-full animate-spin mb-6 mx-auto" />
          <p className="text-slate-600 text-lg">리포트 불러오는 중...</p>
        </div>
      </div>
    );
  }

  // ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  // 🔥 생성 중 화면
  // ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  if (status === "generating") {
    return (
      <div className="min-h-screen bg-gradient-to-b from-slate-50 to-purple-50 py-8">
        <div className="container mx-auto px-4 max-w-4xl">
          <header className="text-center py-6">
            <h1 className="text-3xl font-bold bg-gradient-to-r from-purple-600 to-amber-500 bg-clip-text text-transparent">
              🔮 {BRAND_NAME}
            </h1>
            <p className="text-slate-600 mt-2">프리미엄 비즈니스 컨설팅 보고서</p>
          </header>

          <div className="bg-white rounded-2xl shadow-lg p-8">
            <div className="text-center mb-6">
              <div className="text-5xl mb-4">⏳</div>
              <h2 className="text-xl font-bold text-gray-800">보고서 생성 중입니다</h2>
              <p className="text-gray-600 mt-2">잠시만 기다려주세요. 완료되면 자동으로 표시됩니다.</p>
            </div>

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

            {sections.length > 0 && (
              <div className="mt-8">
                <h3 className="text-sm font-medium text-gray-700 mb-3">섹션 진행 상태</h3>
                <div className="grid grid-cols-2 md:grid-cols-4 gap-2">
                  {sections.map((s, i) => (
                    <div
                      key={s?.id || s?.section_id || i}
                      className={`px-3 py-2 rounded-lg text-xs font-medium ${
                        s?.status === "completed"
                          ? "bg-green-100 text-green-700"
                          : s?.status === "running"
                          ? "bg-yellow-100 text-yellow-700"
                          : "bg-gray-100 text-gray-500"
                      }`}
                    >
                      {s?.id || s?.section_id || `Section ${i + 1}`}
                    </div>
                  ))}
                </div>
              </div>
            )}

            <div className="mt-8 p-4 bg-purple-50 rounded-xl text-center">
              <p className="text-sm text-gray-600">
                💡 이 페이지를 북마크해두시면 언제든 다시 확인하실 수 있어요.
              </p>
            </div>
          </div>
        </div>
      </div>
    );
  }

  // ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  // 🔥 완료 화면
  // ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  if (status === "completed" && job) {
    const result = job.result_json || job.result || {};
    
    // 🔥 사주 데이터 추출 (input_json 우선)
    const rawSajuData = 
      input?.saju_result ||
      result?.legacy?.saju_data || 
      result?.saju_data || 
      {};
    
    console.log('[ReportView] rawSajuData:', {
      fromInput: !!input?.saju_result,
      fromResult: !!(result?.legacy?.saju_data || result?.saju_data),
    });
    
    const normalizedCalculateResult = {
      success: true,
      birth_info: rawSajuData.birth_info || '',
      saju: rawSajuData.saju || {
        hour_pillar: null,
        day_pillar: null,
        month_pillar: null,
        year_pillar: null,
      },
      day_master: rawSajuData.day_master || '',
      day_master_element: rawSajuData.day_master_element || '',
      day_master_description: rawSajuData.day_master_description || '',
      calculation_method: rawSajuData.calculation_method || 'kasi_api',
      daeun: rawSajuData.daeun || null,
      is_boundary_date: rawSajuData.is_boundary_date || false,
      boundary_warning: rawSajuData.boundary_warning || null,
      quality: rawSajuData.quality || {
        has_birth_time: rawSajuData.saju?.hour_pillar ? true : false,
        solar_term_boundary: false,
        boundary_reason: null,
        timezone: 'Asia/Seoul',
        calculation_method: 'kasi_api',
      },
      ...rawSajuData,
    };
    
    // 🔥🔥🔥 핵심 수정: API 응답의 sections를 result와 합쳐서 ResultCard에 전달
    // API 응답: { job: {..., result_json}, sections: [...] }
    // ResultCard가 기대하는 형태: { sections: [...], meta: {...} }
    
    // sections 가져오기 (API 응답 > result_json.sections > 빈 배열)
    const apiSections = sections || [];  // state에서 가져온 sections
    const resultSections = result?.sections || [];
    const finalSections = apiSections.length > 0 ? apiSections : resultSections;
    
    console.log('[ReportView] sections merge:', {
      apiSectionsCount: apiSections.length,
      resultSectionsCount: resultSections.length,
      finalSectionsCount: finalSections.length,
      sectionIds: finalSections.map((s: any) => s?.id || s?.section_id)
    });
    
    // 🔥 핵심: sections를 포함한 interpretResult 조합
    const interpretResultWithSections = {
      ...result,
      // 🔥 API 응답의 sections를 변환하여 우선 사용
      sections: transformSectionsForResultCard(finalSections),
      // 🔥 meta 정보 (프리미엄 보고서 판단용)
      meta: result?.meta || {
        mode: finalSections.length > 0 ? 'premium_business_30p' : 'basic',
        section_count: finalSections.length,
        total_chars: finalSections.reduce((sum: number, s: any) => sum + (s?.char_count || s?.raw_json?.char_count || 0), 0),
        success_count: finalSections.filter((s: any) => s?.status === 'completed').length,
        latency_ms: 0,
      },
    };
    
    console.log('[ReportView] final interpretResult:', {
      sectionsCount: interpretResultWithSections.sections?.length,
      metaMode: interpretResultWithSections.meta?.mode,
      sectionIds: interpretResultWithSections.sections?.map((s: any) => s.id)
    });

    // sections가 있으면 ResultCard 사용
    if (interpretResultWithSections.sections && interpretResultWithSections.sections.length > 0) {
      return (
        <div className="min-h-screen bg-gradient-to-b from-slate-50 to-purple-50 py-8">
          <div className="container mx-auto px-4 max-w-4xl">
            <header className="text-center py-6">
              <h1 className="text-3xl font-bold bg-gradient-to-r from-purple-600 to-amber-500 bg-clip-text text-transparent">
                🔮 {BRAND_NAME}
              </h1>
              <p className="text-slate-600 mt-2">프리미엄 비즈니스 컨설팅 보고서</p>
            </header>

            <ResultCard
              calculateResult={normalizedCalculateResult}
              interpretResult={interpretResultWithSections}
              onReset={() => window.location.href = "/"}
            />

            <footer className="text-center py-8 text-sm text-gray-500">
              <p>© 2025 {BRAND_NAME}. All rights reserved.</p>
            </footer>
          </div>
        </div>
      );
    }
    
    // sections가 없으면 디버그 모드로 JSON 표시
    return (
      <div className="min-h-screen bg-gradient-to-b from-slate-50 to-purple-50 py-8">
        <div className="container mx-auto px-4 max-w-4xl">
          <header className="text-center py-6">
            <h1 className="text-3xl font-bold bg-gradient-to-r from-purple-600 to-amber-500 bg-clip-text text-transparent">
              🔮 {BRAND_NAME}
            </h1>
          </header>

          <div className="bg-white rounded-2xl shadow-lg p-8">
            <div className="bg-yellow-50 border border-yellow-200 rounded-xl p-4 mb-6">
              <h2 className="text-lg font-bold text-yellow-800 mb-2">⚠️ 섹션 데이터 없음</h2>
              <p className="text-yellow-700 text-sm">
                리포트 생성은 완료되었으나 섹션 데이터가 없습니다.
                <br />아래 디버그 정보를 확인해주세요.
              </p>
            </div>
            
            <div className="mb-6">
              <h3 className="text-lg font-semibold text-gray-700 mb-2">📋 Job 정보</h3>
              <pre className="bg-gray-50 p-4 rounded-lg text-sm overflow-auto max-h-60 whitespace-pre-wrap">
                {JSON.stringify(job, null, 2)}
              </pre>
            </div>

            <div className="mb-6">
              <h3 className="text-lg font-semibold text-gray-700 mb-2">📊 Sections ({sections.length}개)</h3>
              {sections.length === 0 ? (
                <p className="text-red-500 bg-red-50 p-4 rounded-lg">❌ API 응답에 sections가 비어있습니다.</p>
              ) : (
                sections.map((s, i) => (
                  <div key={s?.id || s?.section_id || i} className="mb-4 p-4 bg-gray-50 rounded-lg">
                    <b className="text-purple-600">{s?.id || s?.section_id || `Section ${i + 1}`}</b>
                    <span className={`ml-2 px-2 py-0.5 rounded text-xs ${
                      s?.status === 'completed' ? 'bg-green-100 text-green-700' : 'bg-gray-100 text-gray-500'
                    }`}>{s?.status}</span>
                    <pre className="mt-2 text-xs overflow-auto max-h-40 whitespace-pre-wrap">
                      {JSON.stringify(s, null, 2)}
                    </pre>
                  </div>
                ))
              )}
            </div>

            <div className="flex gap-4">
              <button
                onClick={() => window.location.reload()}
                className="flex-1 py-3 bg-purple-600 text-white rounded-lg hover:bg-purple-700 transition"
              >
                🔄 새로고침
              </button>
              <button
                onClick={() => window.location.href = "/"}
                className="flex-1 py-3 bg-gray-200 text-gray-700 rounded-lg hover:bg-gray-300 transition"
              >
                🏠 홈으로
              </button>
            </div>
          </div>
        </div>
      </div>
    );
  }

  // fallback
  return (
    <div className="min-h-screen bg-gradient-to-b from-slate-50 to-purple-50 flex items-center justify-center">
      <div className="text-center">
        <p className="text-slate-600">데이터를 불러오는 중...</p>
        {raw && (
          <details className="mt-4 text-left max-w-lg">
            <summary className="text-sm text-gray-500 cursor-pointer">Raw Response</summary>
            <pre className="mt-2 p-4 bg-gray-100 rounded text-xs overflow-auto max-h-60">
              {JSON.stringify(raw, null, 2)}
            </pre>
          </details>
        )}
      </div>
    </div>
  );
}
