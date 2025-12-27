"use client";

import { useEffect, useState } from "react";
import ReactMarkdown from "react-markdown";

// 🔥 P0: 절대주소 강제
const API_BASE = "https://api.sajuos.com";

// 🔥 섹션 순서
const SECTION_ORDER = ["exec", "money", "business", "team", "health", "calendar", "sprint"];

// 🔥 섹션 타이틀 (한글)
const SECTION_TITLES: Record<string, string> = {
  exec: "📊 Executive Summary",
  money: "💰 Money & Cashflow",
  business: "🏢 Business Strategy",
  team: "👥 Team & Partner",
  health: "❤️ Health & Performance",
  calendar: "📅 12-Month Calendar",
  sprint: "🚀 90-Day Sprint",
};

// 🔥 섹션 아이콘
const SECTION_ICONS: Record<string, string> = {
  exec: "📊",
  money: "💰",
  business: "🏢",
  team: "👥",
  health: "❤️",
  calendar: "📅",
  sprint: "🚀",
};

interface ReportClientProps {
  jobId: string;
  token: string;
}

export default function ReportClient({ jobId, token }: ReportClientProps) {
  const [data, setData] = useState<any>(null);
  const [error, setError] = useState<string>("");
  const [status, setStatus] = useState<"loading" | "generating" | "completed" | "error">("loading");
  const [progress, setProgress] = useState(0);
  const [activeSection, setActiveSection] = useState<string>("exec");

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
        
        // 🔥 디버그: API 응답 전체 확인
        console.log("[ReportView] Full API Response:", JSON.stringify({
          jobStatus: json?.job?.status,
          sectionCount: json?.sections?.length,
          sectionIds: json?.sections?.map((s: any) => s.section_id || s.id),
          hasFullMarkdown: !!json?.full_markdown,
          fullMarkdownLength: json?.full_markdown?.length,
          sectionsPreview: json?.sections?.map((s: any) => ({
            id: s.section_id || s.id,
            hasMarkdown: !!s.markdown,
            markdownLength: s.markdown?.length || 0,
            hasRawJson: !!s.raw_json,
            rawJsonKeys: s.raw_json ? Object.keys(s.raw_json) : [],
          })),
        }, null, 2));
        
        if (!isMounted) return;
        
        setData(json);

        const jobStatus = json?.job?.status || "unknown";
        const jobProgress = json?.job?.progress || 0;

        if (jobStatus === "completed") {
          setProgress(100);
          setStatus("completed");
        } else if (jobStatus === "failed") {
          setError(json?.job?.error || "리포트 생성에 실패했습니다");
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
          
          setData(json);
          
          const jobStatus = json?.job?.status;
          const jobProgress = json?.job?.progress || 0;
          
          if (jobStatus === "completed") {
            if (pollingInterval) clearInterval(pollingInterval);
            setProgress(100);
            setStatus("completed");
          } else if (jobStatus === "failed") {
            if (pollingInterval) clearInterval(pollingInterval);
            setError(json?.job?.error || "리포트 생성에 실패했습니다");
            setStatus("error");
          } else {
            setProgress(jobProgress);
          }
        } catch (e) {
          console.warn("[ReportView] Polling error:", e);
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
          <Header brandName={BRAND_NAME} />
          
          <div className="bg-red-50 border border-red-200 rounded-2xl p-8 text-center">
            <div className="text-5xl mb-4">⚠️</div>
            <h2 className="text-xl font-bold text-red-700 mb-4">오류가 발생했습니다</h2>
            <pre className="text-left bg-white p-4 rounded-lg text-sm text-red-600 overflow-auto max-h-40 mb-6 whitespace-pre-wrap">
              {error}
            </pre>
            
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
    const sections = data?.sections || [];
    
    return (
      <div className="min-h-screen bg-gradient-to-b from-slate-50 to-purple-50 py-8">
        <div className="container mx-auto px-4 max-w-4xl">
          <Header brandName={BRAND_NAME} />

          <div className="bg-white rounded-2xl shadow-lg p-8">
            <div className="text-center mb-6">
              <div className="text-5xl mb-4">⏳</div>
              <h2 className="text-xl font-bold text-gray-800">보고서 생성 중입니다</h2>
              <p className="text-gray-600 mt-2">잠시만 기다려주세요. 완료되면 자동으로 표시됩니다.</p>
            </div>

            <div className="max-w-md mx-auto mb-8">
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
              <div className="grid grid-cols-2 md:grid-cols-4 gap-2">
                {SECTION_ORDER.map((sid) => {
                  const section = sections.find((s: any) => s.section_id === sid || s.id === sid);
                  const sectionStatus = section?.status || "pending";
                  return (
                    <div
                      key={sid}
                      className={`px-3 py-2 rounded-lg text-xs font-medium text-center ${
                        sectionStatus === "completed"
                          ? "bg-green-100 text-green-700"
                          : sectionStatus === "running"
                          ? "bg-yellow-100 text-yellow-700 animate-pulse"
                          : "bg-gray-100 text-gray-500"
                      }`}
                    >
                      {SECTION_ICONS[sid]} {sid}
                    </div>
                  );
                })}
              </div>
            )}
          </div>
        </div>
      </div>
    );
  }

  // ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  // 🔥 완료 화면 (핵심!)
  // ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  if (status === "completed" && data) {
    const { job, input, sections, full_markdown } = data;
    const saju = input?.saju_result || {};
    
    // 🔥 P0: solar_term_boundary 등 항상 optional 처리
    const boundary = saju?.quality?.solar_term_boundary 
      ?? saju?.solar_term_boundary 
      ?? job?.result_json?.solar_term_boundary 
      ?? null;
    
    const hasBirthTime = saju?.saju?.hour_pillar || saju?.quality?.has_birth_time;
    const birthInfo = saju?.birth_info || "";
    const dayMaster = saju?.day_master || "";
    const dayMasterElement = saju?.day_master_element || "";
    const dayMasterDesc = saju?.day_master_description || "";
    
    // 사주 기둥
    const pillars = saju?.saju || {};
    
    return (
      <div className="min-h-screen bg-gradient-to-b from-slate-50 to-purple-50 py-8">
        <div className="container mx-auto px-4 max-w-5xl">
          <Header brandName={BRAND_NAME} />

          {/* 🔥 정확도 배지 */}
          <div className="mb-6">
            <div className={`inline-flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium ${
              hasBirthTime 
                ? "bg-green-100 text-green-800 border border-green-200" 
                : "bg-yellow-100 text-yellow-800 border border-yellow-200"
            }`}>
              {hasBirthTime ? "✅" : "⚠️"} 정확도: {hasBirthTime ? "높음" : "보통"}
              {!hasBirthTime && " (출생시간 미입력)"}
              {boundary && ` | 절기 경계: ${boundary}`}
            </div>
          </div>

          {/* 🔥 사주 원국 카드 */}
          <div className="bg-gradient-to-r from-purple-600 to-amber-500 text-white rounded-2xl p-6 mb-8 shadow-lg">
            <h2 className="text-xl font-bold mb-2">📜 사주 원국</h2>
            {birthInfo && <p className="text-purple-100 mb-4">{birthInfo}</p>}
            
            <div className="grid grid-cols-4 gap-3 mb-4">
              {["hour_pillar", "day_pillar", "month_pillar", "year_pillar"].map((key) => {
                const pillar = pillars[key];
                const labels = { hour_pillar: "시주(時)", day_pillar: "일주(日)", month_pillar: "월주(月)", year_pillar: "년주(年)" };
                return (
                  <div key={key} className="bg-white/20 rounded-xl p-3 text-center backdrop-blur">
                    <div className="text-xs text-purple-100 mb-1">{labels[key as keyof typeof labels]}</div>
                    {pillar ? (
                      <div className="text-2xl font-bold">
                        {pillar[0]}<br/>{pillar[1]}
                      </div>
                    ) : (
                      <div className="text-lg text-purple-200">-</div>
                    )}
                  </div>
                );
              })}
            </div>
            
            {dayMaster && (
              <div className="bg-white/10 rounded-lg p-3">
                <div className="text-sm text-purple-100">당신의 일간 (핵심 의사결정자 특성)</div>
                <div className="font-bold text-lg">{dayMaster} ({dayMasterElement})</div>
                {dayMasterDesc && <div className="text-sm text-purple-100 mt-1">{dayMasterDesc}</div>}
              </div>
            )}
          </div>

          {/* 🔥🔥🔥 핵심: 섹션 탭 네비게이션 */}
          {sections && sections.length > 0 && (
            <>
              <div className="flex flex-wrap gap-2 mb-6 bg-white rounded-xl p-2 shadow">
                {SECTION_ORDER.map((sid) => {
                  const section = sections.find((s: any) => s.section_id === sid || s.id === sid);
                  if (!section) return null;
                  
                  return (
                    <button
                      key={sid}
                      onClick={() => setActiveSection(sid)}
                      className={`px-4 py-2 rounded-lg text-sm font-medium transition-all ${
                        activeSection === sid
                          ? "bg-purple-600 text-white shadow"
                          : "bg-gray-100 text-gray-700 hover:bg-gray-200"
                      }`}
                    >
                      {SECTION_ICONS[sid]} {sid.charAt(0).toUpperCase() + sid.slice(1)}
                    </button>
                  );
                })}
              </div>

              {/* 🔥🔥🔥 핵심: 섹션 콘텐츠 렌더링 */}
              <div className="bg-white rounded-2xl shadow-lg overflow-hidden">
                {sections.map((section: any) => {
                  const sid = section.section_id || section.id;
                  if (sid !== activeSection) return null;
                  
                  const markdown = section.markdown || section.body_markdown || section.content || "";
                  const title = section.title || SECTION_TITLES[sid] || sid;
                  
                  return (
                    <div key={sid} className="p-6 md:p-8">
                      <h2 className="text-2xl font-bold text-gray-800 mb-6 pb-4 border-b">
                        {SECTION_ICONS[sid]} {title}
                      </h2>
                      
                      {markdown ? (
                        <div className="prose prose-purple max-w-none">
                          <ReactMarkdown>{markdown}</ReactMarkdown>
                        </div>
                      ) : (
                        <div className="text-gray-500 text-center py-8">
                          콘텐츠 준비 중...
                        </div>
                      )}
                      
                      {/* 섹션 메타 정보 */}
                      <div className="mt-8 pt-4 border-t flex items-center justify-between text-xs text-gray-400">
                        <span>신뢰도: {section.confidence || "MEDIUM"}</span>
                        <span>{section.char_count || markdown.length}자</span>
                      </div>
                    </div>
                  );
                })}
              </div>
            </>
          )}

          {/* 섹션이 없는 경우 full_markdown으로 렌더 */}
          {(!sections || sections.length === 0) && full_markdown && (
            <div className="bg-white rounded-2xl shadow-lg p-6 md:p-8">
              <div className="prose prose-purple max-w-none">
                <ReactMarkdown>{full_markdown}</ReactMarkdown>
              </div>
            </div>
          )}

          {/* 섹션도 full_markdown도 없는 경우 */}
          {(!sections || sections.length === 0) && !full_markdown && (
            <div className="bg-yellow-50 border border-yellow-200 rounded-2xl p-8 text-center">
              <div className="text-5xl mb-4">📭</div>
              <h2 className="text-xl font-bold text-yellow-800 mb-2">섹션 데이터가 없습니다</h2>
              <p className="text-yellow-700">리포트 생성이 완료되었으나 섹션 데이터를 불러올 수 없습니다.</p>
              <pre className="mt-4 p-4 bg-white rounded text-xs text-left overflow-auto max-h-40">
                {JSON.stringify({ job: job?.status, sectionCount: sections?.length }, null, 2)}
              </pre>
            </div>
          )}

          {/* 푸터 */}
          <footer className="text-center py-8 text-sm text-gray-500">
            <p>⚠️ 본 서비스는 오락/참고 목적으로 제공되며, 의학/법률/투자 등 전문적 조언을 대체하지 않습니다.</p>
            <p className="mt-2">© 2025 {BRAND_NAME}. All rights reserved.</p>
          </footer>
        </div>
      </div>
    );
  }

  // fallback
  return (
    <div className="min-h-screen bg-gradient-to-b from-slate-50 to-purple-50 flex items-center justify-center">
      <div className="text-center">
        <p className="text-slate-600">데이터를 불러오는 중...</p>
      </div>
    </div>
  );
}

// 헤더 컴포넌트
function Header({ brandName }: { brandName: string }) {
  return (
    <header className="text-center py-6">
      <h1 className="text-3xl font-bold bg-gradient-to-r from-purple-600 to-amber-500 bg-clip-text text-transparent">
        🔮 {brandName}
      </h1>
      <p className="text-slate-600 mt-2">프리미엄 비즈니스 컨설팅 보고서</p>
    </header>
  );
}
