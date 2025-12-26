-- ============================================================
-- SajuOS Premium Report System - Supabase Migration
-- ============================================================
-- 실행: Supabase Dashboard > SQL Editor에서 실행
-- ============================================================

-- 1. reports 테이블 (메인)
CREATE TABLE IF NOT EXISTS reports (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    
    -- 사용자 정보
    email TEXT NOT NULL,
    name TEXT,
    
    -- 사주 입력 데이터 (재시도 시 필요)
    input_data JSONB NOT NULL,
    
    -- 상태 관리
    status TEXT NOT NULL DEFAULT 'pending' 
        CHECK (status IN ('pending', 'generating', 'completed', 'failed')),
    progress INT NOT NULL DEFAULT 0 CHECK (progress >= 0 AND progress <= 100),
    current_step TEXT,
    
    -- 결과
    result_json JSONB,
    pdf_url TEXT,
    
    -- 에러
    error TEXT,
    retry_count INT NOT NULL DEFAULT 0,
    
    -- 보안
    access_token TEXT NOT NULL DEFAULT encode(gen_random_bytes(32), 'hex'),
    
    -- 메타
    target_year INT NOT NULL DEFAULT 2026,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    completed_at TIMESTAMPTZ,
    
    -- 비용 추적
    total_tokens_used INT DEFAULT 0,
    generation_time_ms INT
);

-- 2. report_sections 테이블 (섹션별 저장 - 재시도 시 스킵용)
CREATE TABLE IF NOT EXISTS report_sections (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    report_id UUID NOT NULL REFERENCES reports(id) ON DELETE CASCADE,
    
    -- 섹션 정보
    section_id TEXT NOT NULL,  -- exec, money, business, team, health, calendar, sprint
    section_title TEXT NOT NULL,
    section_order INT NOT NULL,
    
    -- 상태
    status TEXT NOT NULL DEFAULT 'pending'
        CHECK (status IN ('pending', 'generating', 'completed', 'failed', 'skipped')),
    
    -- 결과
    content_json JSONB,
    char_count INT DEFAULT 0,
    rulecard_count INT DEFAULT 0,
    
    -- 에러
    error TEXT,
    attempt_count INT NOT NULL DEFAULT 0,
    
    -- 메타
    started_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    elapsed_ms INT,
    
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    
    -- 유니크 제약
    UNIQUE(report_id, section_id)
);

-- 3. 인덱스
CREATE INDEX IF NOT EXISTS idx_reports_email ON reports(email);
CREATE INDEX IF NOT EXISTS idx_reports_status ON reports(status);
CREATE INDEX IF NOT EXISTS idx_reports_access_token ON reports(access_token);
CREATE INDEX IF NOT EXISTS idx_reports_created_at ON reports(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_report_sections_report_id ON report_sections(report_id);

-- 4. updated_at 자동 갱신 트리거
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ language 'plpgsql';

DROP TRIGGER IF EXISTS update_reports_updated_at ON reports;
CREATE TRIGGER update_reports_updated_at
    BEFORE UPDATE ON reports
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

DROP TRIGGER IF EXISTS update_report_sections_updated_at ON report_sections;
CREATE TRIGGER update_report_sections_updated_at
    BEFORE UPDATE ON report_sections
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

-- 5. RLS (Row Level Security) - 선택적
-- 프로덕션에서는 access_token 기반 접근 제어
ALTER TABLE reports ENABLE ROW LEVEL SECURITY;
ALTER TABLE report_sections ENABLE ROW LEVEL SECURITY;

-- Service Role은 모든 접근 허용 (백엔드용)
CREATE POLICY "Service role full access on reports" ON reports
    FOR ALL USING (auth.role() = 'service_role');

CREATE POLICY "Service role full access on report_sections" ON report_sections
    FOR ALL USING (auth.role() = 'service_role');

-- 6. 통계 뷰 (선택적)
CREATE OR REPLACE VIEW report_stats AS
SELECT 
    DATE_TRUNC('day', created_at) as date,
    COUNT(*) as total_reports,
    COUNT(*) FILTER (WHERE status = 'completed') as completed,
    COUNT(*) FILTER (WHERE status = 'failed') as failed,
    AVG(generation_time_ms) FILTER (WHERE status = 'completed') as avg_generation_time_ms,
    AVG(total_tokens_used) FILTER (WHERE status = 'completed') as avg_tokens
FROM reports
GROUP BY DATE_TRUNC('day', created_at)
ORDER BY date DESC;

-- ============================================================
-- 마이그레이션 완료!
-- ============================================================
