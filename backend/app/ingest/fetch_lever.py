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


def fetch_lever(companies: list[dict], query: str | None = None, limit_per_company: int = 200) -> list[dict]:
    """
    Pull jobs from Lever postings API (JSON).

    Endpoint:
      https://api.lever.co/v0/postings/{company}?mode=json

    companies: [{"name": "HashiCorp", "lever": "hashicorp"}, ...]
    Returns list of normalized job dicts.
    """
    headers = {"User-Agent": "jobboard/1.0"}
    out: list[dict] = []

    for c in companies:
        slug = (c.get("lever") or "").strip()
        if not slug:
            continue

        company_name = (c.get("name") or slug).strip()
        url = f"https://api.lever.co/v0/postings/{slug}"
        params = {"mode": "json"}

        try:
            resp = requests.get(url, params=params, headers=headers, timeout=30)
            if resp.status_code != 200:
                continue
            data = resp.json()
        except Exception:
            continue

        if not isinstance(data, list):
            continue

        count = 0
        for j in data:
            if not isinstance(j, dict):
                continue

            title = (j.get("text") or j.get("title") or "").strip() or "Unknown"
            job_id = str(j.get("id") or "")

            hosted_url = (j.get("hostedUrl") or "").strip() or None
            apply_url = hosted_url

            categories = j.get("categories") or {}
            location = None
            if isinstance(categories, dict):
                location = (categories.get("location") or "").strip() or None

            # createdAt is milliseconds since epoch (usually)
            posted_at = None
            created_ms = j.get("createdAt")
            if isinstance(created_ms, (int, float)):
                try:
                    posted_at = datetime.fromtimestamp(created_ms / 1000, tz=timezone.utc)
                except Exception:
                    posted_at = None

            # description can be html/plain
            desc = (j.get("descriptionPlain") or j.get("description") or "")
            if not isinstance(desc, str):
                desc = ""

            # tags (team/commitment/location)
            tags: list[str] = []
            if isinstance(categories, dict):
                for key in ("team", "commitment", "location", "department"):
                    v = categories.get(key)
                    if isinstance(v, str) and v.strip():
                        tags.append(v.strip())

            job_obj = {
                "source": "lever",
                "source_job_id": job_id,
                "title": title,
                "company": company_name,
                "location": location,
                "remote": False,
                "contract": ("contract" in " ".join(tags).lower()),
                "tags": tags,
                "url": hosted_url,
                "apply_url": apply_url,
                "origin_domain": _origin_domain(apply_url),
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
