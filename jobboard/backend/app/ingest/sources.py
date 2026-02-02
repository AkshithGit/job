from __future__ import annotations
import re

import os
import requests
import feedparser
from dateutil import parser as dtparse

from .normalize import JobNorm, clean_ws, origin_domain

ADZUNA_BASE = "https://api.adzuna.com/v1/api/jobs"

def fetch_adzuna(country: str, what: str, where: str | None, pages: int = 1, results_per_page: int = 50) -> list[JobNorm]:
    app_id = os.getenv("ADZUNA_APP_ID")
    app_key = os.getenv("ADZUNA_APP_KEY")
    if not app_id or not app_key:
        raise RuntimeError("Missing ADZUNA_APP_ID or ADZUNA_APP_KEY")

    out: list[JobNorm] = []
    for page in range(1, pages + 1):
        params = {
            "app_id": app_id,
            "app_key": app_key,
            "what": what,
            "results_per_page": results_per_page,
            "content-type": "application/json",
        }
        if where:
            params["where"] = where

        url = f"{ADZUNA_BASE}/{country}/search/{page}"
        r = requests.get(url, params=params, timeout=30)
        r.raise_for_status()
        data = r.json()

        for j in data.get("results", []):
            title = clean_ws(j.get("title"))
            company = clean_ws((j.get("company") or {}).get("display_name"))
            location = clean_ws(((j.get("location") or {}).get("display_name")) or "")
            desc = clean_ws(j.get("description") or "")
            snippet = desc[:300]

            apply_url = clean_ws(j.get("redirect_url") or j.get("adref") or j.get("url") or j.get("adzuna_url") or "")

            created = j.get("created") or j.get("created_at")
            posted_at = None
            if created:
                try:
                    posted_at = dtparse.parse(created)
                except Exception:
                    posted_at = None

            contract_time = (j.get("contract_time") or "").lower()
            contract = "contract" in contract_time

            # Remote heuristic
            remote = ("remote" in title.lower()) or ("remote" in location.lower()) or ("remote" in desc.lower())

            tags = []
            cat = (j.get("category") or {}).get("label")
            if cat:
                tags.append(clean_ws(cat))

            out.append(JobNorm(
                source="adzuna",
                source_job_id=str(j.get("id")) if j.get("id") is not None else None,
                title=title or "Unknown",
                company=company or "Unknown",
                location=location or "US",
                remote=remote,
                contract=contract,
                posted_at=posted_at,
                apply_url=apply_url,
                origin_domain=origin_domain(apply_url),
                description_snippet=snippet,
                tags=tags,
            ))
    return out

def fetch_remoteok() -> list[JobNorm]:
    url = "https://remoteok.com/api"
    r = requests.get(url, timeout=30, headers={"User-Agent": "jobboard/1.0"})
    r.raise_for_status()
    data = r.json()

    out: list[JobNorm] = []
    for item in data:
        if not isinstance(item, dict) or "position" not in item:
            continue

        title = clean_ws(item.get("position"))
        company = clean_ws(item.get("company"))
        location = clean_ws(item.get("location") or "Remote")
        tags = [clean_ws(t) for t in (item.get("tags") or []) if clean_ws(t)]

        listing_url = item.get("url")
        apply_url = clean_ws(item.get("apply_url") or listing_url or "")

        date_str = item.get("date")
        posted_at = None
        if date_str:
            try:
                posted_at = dtparse.parse(date_str)
            except Exception:
                posted_at = None

        desc = clean_ws(item.get("description") or "")
        snippet = desc[:300]

        contract = any(t.lower() in ("contract", "freelance") for t in tags)

        out.append(JobNorm(
            source="remoteok",
            source_job_id=str(item.get("id")) if item.get("id") is not None else None,
            title=title or "Unknown",
            company=company or "Unknown",
            location=location,
            remote=True,
            contract=contract,
            posted_at=posted_at,
            apply_url=apply_url,
            origin_domain=origin_domain(apply_url),
            description_snippet=snippet,
            tags=tags,
        ))
    return out

def fetch_wwr_rss() -> list[JobNorm]:
    feed_url = "https://weworkremotely.com/remote-jobs.rss"
    feed = feedparser.parse(feed_url)

    out: list[JobNorm] = []
    for e in feed.entries:
        title_raw = clean_ws(getattr(e, "title", "") or "")
        link = clean_ws(getattr(e, "link", "") or "")
        summary = getattr(e, "summary", "") or ""
        # strip HTML tags from RSS summary
        summary_text = re.sub(r"<[^>]+>", " ", summary)
        summary_text = clean_ws(summary_text)
        snippet = summary_text[:300]

        # "Company: Role" common in WWR
        company = "Unknown"
        title = title_raw
        if ":" in title_raw:
            left, right = title_raw.split(":", 1)
            company = clean_ws(left)
            title = clean_ws(right)

        published = getattr(e, "published", None)
        posted_at = None
        if published:
            try:
                posted_at = dtparse.parse(published)
            except Exception:
                posted_at = None

        out.append(JobNorm(
            source="wwr",
            source_job_id=clean_ws(getattr(e, "id", None) or link) or None,
            title=title or "Unknown",
            company=company or "Unknown",
            location="Remote",
            remote=True,
            contract=False,
            posted_at=posted_at,
            apply_url=link,
            origin_domain=origin_domain(link),
            description_snippet=snippet,
            tags=[],
        ))
    return out

