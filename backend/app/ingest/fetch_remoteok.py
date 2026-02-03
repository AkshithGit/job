from __future__ import annotations
import requests
from urllib.parse import urlparse

REMOTEOK_URL = "https://remoteok.com/api"


def _origin_domain(url: str | None) -> str | None:
    if not url:
        return None
    try:
        return urlparse(url).netloc.replace("www.", "")
    except Exception:
        return None


def fetch_remoteok(query: str | None = None, limit: int = 200) -> list[dict]:
    """
    RemoteOK public feed.
    Returns list of normalized jobs dicts.
    """
    headers = {"User-Agent": "jobboard/1.0"}
    resp = requests.get(REMOTEOK_URL, headers=headers, timeout=30)
    resp.raise_for_status()
    data = resp.json()

    # first element is metadata in remoteok
    items = [x for x in data if isinstance(x, dict) and x.get("id")]

    q = (query or "").strip().lower()
    out: list[dict] = []

    for j in items:
        title = (j.get("position") or j.get("title") or "").strip()
        company = (j.get("company") or "").strip()
        desc = (j.get("description") or "").strip()
        apply_url = (j.get("url") or "").strip()

        # simple query filter (title/company/tags/desc)
        if q:
            hay = " ".join([
                title, company, desc,
                " ".join(j.get("tags") or []),
            ]).lower()
            if q not in hay:
                continue

        tags = [t for t in (j.get("tags") or []) if isinstance(t, str)]

        out.append({
            "source": "remoteok",
            "source_job_id": str(j.get("id")),
            "title": title or "Unknown",
            "company": company or "Unknown",
            "location": "Remote",
            "remote": True,
            "contract": False,  # RemoteOK doesn't have reliable contract flag
            "tags": tags,
            "url": apply_url,
            "apply_url": apply_url,
            "origin_domain": _origin_domain(apply_url),
            "description": desc,
            "description_snippet": (desc[:300] + "...") if len(desc) > 300 else desc,
            "posted_at": None,
        })

        if len(out) >= limit:
            break

    return out
