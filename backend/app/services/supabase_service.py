# app/services/supabase_service.py
from __future__ import annotations

import os
from typing import Any, Dict, Optional, List

import httpx


class SupabaseError(RuntimeError):
    pass


class SupabaseService:
    """
    Supabase(PostgREST) REST client for server-side usage.

    Required ENV (Railway/Local .env):
      - SUPABASE_URL=https://xxxx.supabase.co
      - SUPABASE_SERVICE_ROLE_KEY=xxxxx   (SERVER ONLY, DO NOT EXPOSE TO FRONTEND)
    Optional:
      - SUPABASE_REPORT_JOBS_TABLE=report_jobs
      - SUPABASE_REST_SCHEMA=public
      - SUPABASE_TIMEOUT_SECONDS=20

    Expected table (example):
      table: report_jobs
        - id (uuid or text) PRIMARY KEY
        - email (text)
        - status (text)        e.g. pending/generating/completed/failed
        - progress (int)       0~100
        - stage (text)         e.g. "rules_pick", "section_3_done" ...
        - payload (jsonb)      input answers
        - result (jsonb)       final report json (or summary)
        - result_url (text)    optional pdf link
        - error (text)         error message
        - created_at (timestamptz default now())
        - updated_at (timestamptz default now())
    """

    def __init__(
        self,
        supabase_url: Optional[str] = None,
        service_role_key: Optional[str] = None,
        *,
        schema: Optional[str] = None,
        jobs_table: Optional[str] = None,
        timeout_seconds: Optional[int] = None,
    ) -> None:
        self.supabase_url = (supabase_url or os.getenv("SUPABASE_URL") or "").rstrip("/")
        self.service_role_key = service_role_key or os.getenv("SUPABASE_SERVICE_ROLE_KEY") or ""
        self.schema = schema or os.getenv("SUPABASE_REST_SCHEMA") or "public"
        self.jobs_table = jobs_table or os.getenv("SUPABASE_REPORT_JOBS_TABLE") or "report_jobs"

        if timeout_seconds is None:
            timeout_seconds = int(os.getenv("SUPABASE_TIMEOUT_SECONDS") or "20")

        if not self.supabase_url:
            raise SupabaseError("SUPABASE_URL is missing.")
        if not self.service_role_key:
            raise SupabaseError("SUPABASE_SERVICE_ROLE_KEY is missing. (server-side only)")

        self.rest_url = f"{self.supabase_url}/rest/v1"
        self.timeout = httpx.Timeout(timeout_seconds)

        # PostgREST schema selection headers (optional)
        self.base_headers = {
            "apikey": self.service_role_key,
            "Authorization": f"Bearer {self.service_role_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
            "Accept-Profile": self.schema,
            "Content-Profile": self.schema,
        }

    def _url(self, table: str) -> str:
        return f"{self.rest_url}/{table}"

    async def health_check(self) -> bool:
        """
        Quick check that Supabase REST is reachable. This doesn't guarantee table exists.
        """
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            # A lightweight call: request OpenAPI for schema (may be restricted), so instead do a harmless HEAD.
            # PostgREST doesn't always support HEAD well; use GET on empty select for jobs_table.
            url = self._url(self.jobs_table)
            r = await client.get(url, headers=self.base_headers, params={"select": "id", "limit": 1})
            return 200 <= r.status_code < 300

    async def create_job(self, job: Dict[str, Any], *, table: Optional[str] = None) -> Dict[str, Any]:
        """
        Insert a new job row. Returns created row (representation).
        job must contain at least `id`.
        """
        tbl = table or self.jobs_table
        if "id" not in job:
            raise SupabaseError("create_job requires job['id'].")

        headers = dict(self.base_headers)
        headers["Prefer"] = "return=representation"

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            r = await client.post(self._url(tbl), headers=headers, json=job)
            if r.status_code >= 400:
                raise SupabaseError(f"Supabase create_job failed: {r.status_code} {r.text}")
            data = r.json()
            # PostgREST returns list
            return data[0] if isinstance(data, list) and data else data

    async def upsert_job(
        self,
        job: Dict[str, Any],
        *,
        table: Optional[str] = None,
        on_conflict: str = "id",
    ) -> Dict[str, Any]:
        """
        Upsert job row by on_conflict key (default: id).
        """
        tbl = table or self.jobs_table
        if on_conflict not in job:
            raise SupabaseError(f"upsert_job requires job['{on_conflict}'].")

        headers = dict(self.base_headers)
        headers["Prefer"] = "return=representation,resolution=merge-duplicates"

        params = {"on_conflict": on_conflict}

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            r = await client.post(self._url(tbl), headers=headers, params=params, json=job)
            if r.status_code >= 400:
                raise SupabaseError(f"Supabase upsert_job failed: {r.status_code} {r.text}")
            data = r.json()
            return data[0] if isinstance(data, list) and data else data

    async def update_job(
        self,
        job_id: str,
        patch: Dict[str, Any],
        *,
        table: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Patch a job by id. Returns updated row.
        """
        tbl = table or self.jobs_table
        if not job_id:
            raise SupabaseError("update_job requires job_id.")
        if not patch:
            raise SupabaseError("update_job requires non-empty patch dict.")

        headers = dict(self.base_headers)
        headers["Prefer"] = "return=representation"

        params = {"id": f"eq.{job_id}"}

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            r = await client.patch(self._url(tbl), headers=headers, params=params, json=patch)
            if r.status_code >= 400:
                raise SupabaseError(f"Supabase update_job failed: {r.status_code} {r.text}")
            data = r.json()
            return data[0] if isinstance(data, list) and data else data

    async def get_job(
        self,
        job_id: str,
        *,
        table: Optional[str] = None,
        select: str = "*",
    ) -> Optional[Dict[str, Any]]:
        """
        Fetch a job by id. Returns row or None.
        """
        tbl = table or self.jobs_table
        if not job_id:
            raise SupabaseError("get_job requires job_id.")

        params = {"id": f"eq.{job_id}", "select": select, "limit": 1}

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            r = await client.get(self._url(tbl), headers=self.base_headers, params=params)
            if r.status_code >= 400:
                raise SupabaseError(f"Supabase get_job failed: {r.status_code} {r.text}")
            data = r.json()
            if isinstance(data, list):
                return data[0] if data else None
            return data or None

    async def list_jobs_by_email(
        self,
        email: str,
        *,
        table: Optional[str] = None,
        limit: int = 20,
        order: str = "created_at.desc",
        select: str = "*",
    ) -> List[Dict[str, Any]]:
        """
        Fetch recent jobs for a given email.
        """
        tbl = table or self.jobs_table
        if not email:
            raise SupabaseError("list_jobs_by_email requires email.")

        params = {
            "email": f"eq.{email}",
            "select": select,
            "order": order,
            "limit": max(1, min(limit, 100)),
        }

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            r = await client.get(self._url(tbl), headers=self.base_headers, params=params)
            if r.status_code >= 400:
                raise SupabaseError(f"Supabase list_jobs_by_email failed: {r.status_code} {r.text}")
            data = r.json()
            return data if isinstance(data, list) else [data]
