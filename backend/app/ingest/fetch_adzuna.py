from __future__ import annotations
import os
import requests
from datetime import datetime
from urllib.parse import urlparse


def _origin_domain(url: str | None) -> str | None:
    if not url:
        return None
    try:
        return urlparse(url).netloc.replace("www.", "")
    except Exception:
        return None


def fetch_adzuna(query: str | None, where: str = "United States", pages: int = 1) -> list[dict]:
    app_id = os.getenv("ADZUNA_APP_ID", "").strip()
    app_key = os.getenv("ADZUNA_APP_KEY", "").strip()
    if not app_id or not app_key or app_id == "YOUR_ID_HERE":
        raise RuntimeError("Missing ADZUNA_APP_ID / ADZUNA_APP_KEY in container env")

    q = (query or "").strip()
    out: list[dict] = []

    # Adzuna endpoint style: /v1/api/jobs/{country}/search/{page}
    # We'll use US by default
    country = "us"

    for page in range(1, max(1, pages) + 1):
        url = f"https://api.adzuna.com/v1/api/jobs/{country}/search/{page}"
        params = {
            "app_id": app_id,
            "app_key": app_key,
            "results_per_page": 50,
            "what": q,
            "where": where,
            "content-type": "application/json",
        }

        resp = requests.get(url, params=params, timeout=30)
        resp.raise_for_status()
        data = resp.json()

        for j in data.get("results", []):
            title = (j.get("title") or "").strip()
            company = (j.get("company") or {}).get("display_name") or ""
            company = str(company).strip()

            loc = (j.get("location") or {}).get("display_name")
            location = str(loc).strip() if loc else None

            desc = (j.get("description") or "").strip()
            apply_url = (j.get("redirect_url") or "").strip()
            created = j.get("created")

            posted_at = None
            if isinstance(created, str) and created:
                try:
                    posted_at = datetime.fromisoformat(created.replace("Z", "+00:00"))
                except Exception:
                    posted_at = None

            category = (j.get("category") or {}).get("label")
            tags = [str(category).strip()] if category else []

            out.append({
                "source": "adzuna",
                "source_job_id": str(j.get("id") or ""),
                "title": title or "Unknown",
                "company": company or "Unknown",
                "location": location,
                "remote": False,     # Adzuna doesn't always mark remote reliably
                "contract": False,   # We'll infer later if needed
                "tags": tags,
                "url": apply_url,
                "apply_url": apply_url,
                "origin_domain": _origin_domain(apply_url),
                "description": desc,
                "description_snippet": (desc[:300] + "...") if len(desc) > 300 else desc,
                "posted_at": posted_at,
            })

    return out
