from __future__ import annotations
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse

BASE = "https://weworkremotely.com"
LIST_URL = "https://weworkremotely.com/remote-jobs/search?term="


def _origin_domain(url: str | None) -> str | None:
    if not url:
        return None
    try:
        return urlparse(url).netloc.replace("www.", "")
    except Exception:
        return None


def fetch_wwr(query: str | None = None, limit: int = 200) -> list[dict]:
    """
    Lightweight HTML parse for WWR.
    """
    term = (query or "").strip()
    url = LIST_URL + requests.utils.quote(term) if term else f"{BASE}/remote-jobs"

    headers = {"User-Agent": "jobboard/1.0"}
    resp = requests.get(url, headers=headers, timeout=30)
    resp.raise_for_status()

    soup = BeautifulSoup(resp.text, "html.parser")

    out: list[dict] = []
    for a in soup.select("section.jobs article ul li a"):
        href = a.get("href") or ""
        if not href.startswith("/remote-jobs/"):
            continue

        job_url = urljoin(BASE, href)
        company_el = a.select_one("span.company")
        title_el = a.select_one("span.title")
        region_el = a.select_one("span.region")

        company = (company_el.get_text(strip=True) if company_el else "Unknown")
        title = (title_el.get_text(strip=True) if title_el else "Unknown")
        region = (region_el.get_text(strip=True) if region_el else None)

        # fetch detail for description snippet (optional but useful)
        desc = ""
        try:
            dresp = requests.get(job_url, headers=headers, timeout=30)
            if dresp.status_code == 200:
                dsoup = BeautifulSoup(dresp.text, "html.parser")
                content = dsoup.select_one("div.listing-container")
                if content:
                    desc = content.get_text(" ", strip=True)
        except Exception:
            desc = ""

        out.append({
            "source": "wwr",
            "source_job_id": job_url,
            "title": title,
            "company": company,
            "location": region or "Remote",
            "remote": True,
            "contract": False,
            "tags": [],
            "url": job_url,
            "apply_url": job_url,
            "origin_domain": _origin_domain(job_url),
            "description": desc or None,
            "description_snippet": ((desc[:300] + "...") if len(desc) > 300 else desc) if desc else None,
            "posted_at": None,
        })

        if len(out) >= limit:
            break

    return out
