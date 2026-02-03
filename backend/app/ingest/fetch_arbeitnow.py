from __future__ import annotations
import requests
from datetime import datetime, timezone
from urllib.parse import urlparse


def _origin_domain(url: str | None) -> str | None:
    if not url:
        return None
    try:
        return urlparse(url).netloc.replace("www.", "")
    except Exception:
        return None


def fetch_arbeitnow(query: str | None = None, limit: int = 200) -> list[dict]:
    """
    Arbeitnow public API: https://arbeitnow.com/api/job-board-api
    Returns remote-heavy jobs; we filter using query if provided.
    """
    url = "https://www.arbeitnow.com/api/job-board-api"
    jobs: list[dict] = []
    next_url = url
    q = (query or "").strip().lower()

    while next_url and len(jobs) < limit:
        resp = requests.get(next_url, timeout=30)
        resp.raise_for_status()
        data = resp.json()

        for j in data.get("data", []):
            title = (j.get("title") or "").strip()
            company = (j.get("company_name") or "").strip()
            desc = (j.get("description") or "").strip()
            apply_url = (j.get("url") or "").strip()

            # query filter (simple keyword match)
            hay = f"{title} {company} {desc}".lower()
            if q and q not in hay:
                continue

            location = "Remote" if j.get("remote") else (j.get("location") or None)

            jobs.append({
                "source": "arbeitnow",
                "source_job_id": j.get("slug") or apply_url,
                "title": title or "Unknown",
                "company": company or "Unknown",
                "location": location,
                "remote": bool(j.get("remote", False)),
                "contract": False,  # Arbeitnow doesn't explicitly mark contract reliably
                "tags": ["remote"] if j.get("remote") else [],
                "url": apply_url,
                "apply_url": apply_url,
                "origin_domain": _origin_domain(apply_url),
                "description": desc,
                "description_snippet": (desc[:300] + "...") if len(desc) > 300 else desc,
                "posted_at": None,
            })

            if len(jobs) >= limit:
                break

        next_url = data.get("links", {}).get("next")

    return jobs

