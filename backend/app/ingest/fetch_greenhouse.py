from __future__ import annotations

import requests
from datetime import datetime, timezone
from urllib.parse import urlparse


def _origin_domain(url: str | None) -> str | None:
    if not url:
        return None
    try:
        return urlparse(url).netloc.lower().replace("www.", "") or None
    except Exception:
        return None


def _matches_query(job: dict, q: str) -> bool:
    if not q:
        return True
    q = q.strip().lower()
    if not q:
        return True
    hay = " ".join([
        str(job.get("title") or ""),
        str(job.get("company") or ""),
        str(job.get("location") or ""),
        str(job.get("description") or ""),
        " ".join(job.get("tags") or []),
    ]).lower()
    return q in hay


def fetch_greenhouse(companies: list[dict], query: str | None = None, limit_per_company: int = 200) -> list[dict]:
    """
    Pull jobs from Greenhouse boards API.

    Endpoint:
      https://boards-api.greenhouse.io/v1/boards/{board}/jobs?content=true

    companies: [{"name": "Stripe", "greenhouse": "stripe"}, ...]
    Returns list of normalized job dicts.
    """
    headers = {"User-Agent": "jobboard/1.0"}
    out: list[dict] = []

    for c in companies:
        board = (c.get("greenhouse") or "").strip()
        if not board:
            continue

        company_name = (c.get("name") or board).strip()

        url = f"https://boards-api.greenhouse.io/v1/boards/{board}/jobs"
        params = {"content": "true"}

        try:
            resp = requests.get(url, params=params, headers=headers, timeout=30)
            if resp.status_code != 200:
                # skip quietly to avoid breaking the whole ingest
                continue
            data = resp.json()
        except Exception:
            continue

        jobs = data.get("jobs") or []
        count = 0

        for j in jobs:
            title = (j.get("title") or "").strip() or "Unknown"
            job_id = str(j.get("id") or "")
            absolute_url = (j.get("absolute_url") or "").strip() or None

            location_name = None
            loc = j.get("location") or {}
            if isinstance(loc, dict):
                location_name = (loc.get("name") or "").strip() or None

            # timestamps
            posted_at = None
            # Greenhouse has "updated_at" / "created_at" ISO strings
            dt_s = j.get("updated_at") or j.get("created_at")
            if isinstance(dt_s, str) and dt_s:
                try:
                    posted_at = datetime.fromisoformat(dt_s.replace("Z", "+00:00"))
                except Exception:
                    posted_at = None

            # content can be HTML. Keep it.
            content = j.get("content") or ""
            desc = content if isinstance(content, str) else ""

            # basic tags
            tags: list[str] = []
            dept = j.get("departments") or []
            if isinstance(dept, list):
                for d in dept[:3]:
                    name = (d.get("name") if isinstance(d, dict) else None)
                    if name:
                        tags.append(str(name).strip())

            offices = j.get("offices") or []
            if isinstance(offices, list):
                for o in offices[:3]:
                    name = (o.get("name") if isinstance(o, dict) else None)
                    if name:
                        tags.append(str(name).strip())

            job_obj = {
                "source": "greenhouse",
                "source_job_id": job_id,
                "title": title,
                "company": company_name,
                "location": location_name,
                "remote": False,   # we can infer later from title/location if you want
                "contract": False, # can be inferred later from text
                "tags": tags,
                "url": absolute_url,
                "apply_url": absolute_url,
                "origin_domain": _origin_domain(absolute_url),
                "description": desc or None,
                "description_snippet": (desc[:300] + "...") if len(desc) > 300 else (desc or None),
                "posted_at": posted_at,
            }

            if not _matches_query(job_obj, query or ""):
                continue

            out.append(job_obj)
            count += 1
            if count >= limit_per_company:
                break

    return out
