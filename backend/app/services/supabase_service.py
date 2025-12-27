# app/services/supabase_service.py
# ------------------------------------------------------------
# SajuOS Supabase persistence layer (server-side / service_role)
#
# ✅ 기대 테이블 (권장 스키마)
# - public.report_jobs:
#   id(uuid, pk), created_at, updated_at,
#   status(text), progress(int4), step(text),
#   user_email(text, nullable), public_token(text, nullable/unique),
#   input_json(jsonb, nullable), result_json(jsonb, nullable),
#   markdown(text, nullable), error(text, nullable)
#
# - public.report_sections:
#   id(uuid, pk), created_at, updated_at,
#   job_id(uuid, fk -> report_jobs.id), section_id(text),
#   status(text), progress(int4),
#   evidence_json(jsonb), actions_json(jsonb), risks_json(jsonb), opportunities_json(jsonb),
#   markdown(text), raw_json(jsonb)
#
#   + UNIQUE(job_id, section_id) 권장 (upsert용)
# ------------------------------------------------------------

from __future__ import annotations

import os
import time
from typing import Any, Dict, Optional, List, Tuple

from supabase import create_client, Client


def _now_ms() -> int:
    return int(time.time() * 1000)


def _clamp_progress(p: Optional[int]) -> Optional[int]:
    if p is None:
        return None
    try:
        p = int(p)
    except Exception:
        return None
    return max(0, min(100, p))


class SupabaseService:
    """
    Server-side service using SUPABASE_SERVICE_ROLE_KEY.
    - Lazy init to avoid boot crash
    - Upsert sections by (job_id, section_id)
    """

    _client: Optional[Client] = None

    def __init__(
        self,
        supabase_url: Optional[str] = None,
        supabase_service_role_key: Optional[str] = None,
        jobs_table: str = "report_jobs",
        sections_table: str = "report_sections",
        enabled: Optional[bool] = None,
    ):
        self.supabase_url = supabase_url or os.getenv("SUPABASE_URL", "").strip()
        self.supabase_service_role_key = (
            supabase_service_role_key
            or os.getenv("SUPABASE_SERVICE_ROLE_KEY", "").strip()
            or os.getenv("SUPABASE_SERVICE_KEY", "").strip()
        )
        self.jobs_table = jobs_table
        self.sections_table = sections_table
        self.enabled = enabled if enabled is not None else bool(self.supabase_url and self.supabase_service_role_key)

    def _get_client(self) -> Client:
        if not self.enabled:
            raise RuntimeError(
                "SupabaseService is disabled. Set SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY (server-side only)."
            )

        if SupabaseService._client is None:
            SupabaseService._client = create_client(self.supabase_url, self.supabase_service_role_key)

        return SupabaseService._client

    # --------------------------
    # Jobs (report_jobs)
    # --------------------------
    def create_job(
        self,
        *,
        user_email: Optional[str],
        input_json: Optional[Dict[str, Any]],
        initial_step: str = "queued",
        status: str = "pending",
    ) -> Dict[str, Any]:
        """
        Create a job row.
        Returns the inserted job row (at least: id, public_token if exists).
        """
        client = self._get_client()

        payload: Dict[str, Any] = {
            "status": status,
            "progress": 0,
            "step": initial_step,
            "user_email": user_email,
            "input_json": input_json,
        }

        resp = client.table(self.jobs_table).insert(payload).execute()
        if getattr(resp, "error", None):
            raise RuntimeError(f"Supabase create_job error: {resp.error}")

        data = resp.data[0] if resp.data else {}
        return data

    def update_job_progress(
        self,
        *,
        job_id: str,
        progress: Optional[int] = None,
        step: Optional[str] = None,
        status: Optional[str] = None,
        extra_updates: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Update progress/status/step while generating.
        """
        client = self._get_client()

        updates: Dict[str, Any] = {}
        p = _clamp_progress(progress)
        if p is not None:
            updates["progress"] = p
        if step is not None:
            updates["step"] = step
        if status is not None:
            updates["status"] = status
        if extra_updates:
            updates.update(extra_updates)

        if not updates:
            return self.get_job(job_id=job_id)

        resp = client.table(self.jobs_table).update(updates).eq("id", job_id).execute()
        if getattr(resp, "error", None):
            raise RuntimeError(f"Supabase update_job_progress error: {resp.error}")

        return resp.data[0] if resp.data else {}

    def fail_job(
        self,
        *,
        job_id: str,
        error_message: str,
        step: str = "failed",
    ) -> Dict[str, Any]:
        return self.update_job_progress(
            job_id=job_id,
            status="failed",
            progress=100,
            step=step,
            extra_updates={"error": error_message[:4000]},
        )

    def complete_job(
        self,
        *,
        job_id: str,
        result_json: Optional[Dict[str, Any]] = None,
        markdown: Optional[str] = None,
        step: str = "done",
    ) -> Dict[str, Any]:
        updates: Dict[str, Any] = {
            "status": "completed",
            "progress": 100,
            "step": step,
        }
        if result_json is not None:
            updates["result_json"] = result_json
        if markdown is not None:
            updates["markdown"] = markdown

        client = self._get_client()
        resp = client.table(self.jobs_table).update(updates).eq("id", job_id).execute()
        if getattr(resp, "error", None):
            raise RuntimeError(f"Supabase complete_job error: {resp.error}")

        return resp.data[0] if resp.data else {}

    def get_job(self, *, job_id: str) -> Dict[str, Any]:
        client = self._get_client()
        resp = client.table(self.jobs_table).select("*").eq("id", job_id).single().execute()
        if getattr(resp, "error", None):
            raise RuntimeError(f"Supabase get_job error: {resp.error}")
        return resp.data or {}

    def get_job_by_public_token(self, *, public_token: str) -> Dict[str, Any]:
        client = self._get_client()
        resp = client.table(self.jobs_table).select("*").eq("public_token", public_token).single().execute()
        if getattr(resp, "error", None):
            raise RuntimeError(f"Supabase get_job_by_public_token error: {resp.error}")
        return resp.data or {}

    # --------------------------
    # Sections (report_sections)
    # --------------------------
    def upsert_section(
        self,
        *,
        job_id: str,
        section_id: str,
        status: Optional[str] = None,
        progress: Optional[int] = None,
        evidence: Optional[List[Any]] = None,
        actions: Optional[List[Any]] = None,
        risks: Optional[List[Any]] = None,
        opportunities: Optional[List[Any]] = None,
        markdown: Optional[str] = None,
        raw_json: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Upsert a section row keyed by (job_id, section_id).
        Requires UNIQUE(job_id, section_id) on report_sections.
        """
        client = self._get_client()

        payload: Dict[str, Any] = {
            "job_id": job_id,
            "section_id": section_id,
        }

        if status is not None:
            payload["status"] = status
        p = _clamp_progress(progress)
        if p is not None:
            payload["progress"] = p

        # Evidence→Action quality structure
        if evidence is not None:
            payload["evidence_json"] = evidence
        if actions is not None:
            payload["actions_json"] = actions
        if risks is not None:
            payload["risks_json"] = risks
        if opportunities is not None:
            payload["opportunities_json"] = opportunities

        if markdown is not None:
            payload["markdown"] = markdown
        if raw_json is not None:
            payload["raw_json"] = raw_json

        resp = (
            client.table(self.sections_table)
            .upsert(payload, on_conflict="job_id,section_id")
            .execute()
        )
        if getattr(resp, "error", None):
            raise RuntimeError(f"Supabase upsert_section error: {resp.error}")

        return resp.data[0] if resp.data else {}

    def get_sections(self, *, job_id: str) -> List[Dict[str, Any]]:
        client = self._get_client()
        resp = client.table(self.sections_table).select("*").eq("job_id", job_id).execute()
        if getattr(resp, "error", None):
            raise RuntimeError(f"Supabase get_sections error: {resp.error}")
        return resp.data or []

    def get_section(self, *, job_id: str, section_id: str) -> Dict[str, Any]:
        client = self._get_client()
        resp = (
            client.table(self.sections_table)
            .select("*")
            .eq("job_id", job_id)
            .eq("section_id", section_id)
            .single()
            .execute()
        )
        if getattr(resp, "error", None):
            raise RuntimeError(f"Supabase get_section error: {resp.error}")
        return resp.data or {}

    # --------------------------
    # Convenience: atomic-ish helpers
    # --------------------------
    def start_generation(
        self,
        *,
        user_email: Optional[str],
        input_json: Optional[Dict[str, Any]],
        initial_sections: Optional[List[str]] = None,
    ) -> Tuple[str, Optional[str]]:
        """
        1) create job
        2) (optional) create initial section rows
        Returns (job_id, public_token)
        """
        job = self.create_job(user_email=user_email, input_json=input_json, initial_step="queued", status="pending")
        job_id = job.get("id")
        public_token = job.get("public_token")

        if not job_id:
            raise RuntimeError("Supabase start_generation: missing job_id from insert result")

        if initial_sections:
            for s in initial_sections:
                self.upsert_section(
                    job_id=job_id,
                    section_id=s,
                    status="pending",
                    progress=0,
                    raw_json={"_created_at_ms": _now_ms()},
                )

        return job_id, public_token


# ------------------------------------------------------------
# Example usage (FastAPI / Background Task)
# ------------------------------------------------------------
#
# from app.services.supabase_service import SupabaseService
#
# sb = SupabaseService()
# job_id, public_token = sb.start_generation(
#     user_email="test@sajuos.com",
#     input_json={"birth":"1978-05-16 11:20", "gender":"F"},
#     initial_sections=["exec","money","strategy","team","health","calendar","sprint"],
# )
# sb.update_job_progress(job_id=job_id, status="running", step="exec", progress=5)
# sb.upsert_section(job_id=job_id, section_id="exec", status="running", progress=10)
# sb.upsert_section(job_id=job_id, section_id="exec",
#                  status="completed", progress=100,
#                  evidence=[{"fact":"..."}], actions=[{"do":"..."}],
#                  risks=[{"risk":"..."}], opportunities=[{"opp":"..."}],
#                  markdown="### Executive Summary ...",
#                  raw_json={"model":"gpt-4o"})
# sb.complete_job(job_id=job_id, result_json={"ok":True}, markdown="# Full report ...")
#
# ------------------------------------------------------------
