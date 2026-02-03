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


def fetch_remotive(query: str | None = None, limit: int = 200) -> list[dict]:
    """
    Remotive API: https://remotive.com/api/remote-jobs
    Supports ?search=... server-side.
    """
    base = "https://remotive.com/api/remote-jobs"
    params = {}
    if query and query.strip():
        params["search"] = query.strip()

    resp = requests.get(base, params=params, timeout=30)
    resp.raise_for_status()
    data = resp.json()

    jobs: list[dict] = []
    for j in data.get("jobs", []):
        title = (j.get("title") or "").strip()
        company = (j.get("company_name") or "").strip()
        desc = (j.get("description") or "").strip()
        apply_url = (j.get("url") or "").strip()

        # Remotive gives type like "full_time", "contract" sometimes
        jtype = (j.get("job_type") or "").lower()
        contract = "contract" in jtype

        tags = []
        if j.get("category"):
            tags.append(str(j.get("category")).strip())
        tags += [t for t in (j.get("tags") or []) if isinstance(t, str)]

        posted_at = None
        # Remotive has publication_date sometimes as ISO-like string
        pub = j.get("publication_date")
        if isinstance(pub, str) and pub:
            try:
                posted_at = datetime.fromisoformat(pub.replace("Z", "+00:00"))
            except Exception:
                posted_at = None

        jobs.append({
            "source": "remotive",
            "source_job_id": str(j.get("id") or apply_url),
            "title": title or "Unknown",
            "company": company or "Unknown",
            "location": "Remote",
            "remote": True,
            "contract": contract,
            "tags": tags,
            "url": apply_url,
            "apply_url": apply_url,
            "origin_domain": _origin_domain(apply_url),
            "description": desc,
            "description_snippet": (desc[:300] + "...") if len(desc) > 300 else desc,
            "posted_at": posted_at,
        })

        if len(jobs) >= limit:
            break

    return jobs

