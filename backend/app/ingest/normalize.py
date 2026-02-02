from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from datetime import datetime
from urllib.parse import urlparse

def clean_ws(s: str | None) -> str:
    if not s:
        return ""
    return re.sub(r"\s+", " ", s).strip()

def origin_domain(url: str | None) -> str | None:
    if not url:
        return None
    try:
        host = urlparse(url).netloc.lower().replace("www.", "")
        return host or None
    except Exception:
        return None

def normalize_location(loc: str | None) -> str:
    loc = clean_ws(loc).lower()
    loc = loc.replace("united states", "us").replace("usa", "us")
    return loc

def fingerprint(title: str, company: str, location: str, origin: str | None) -> str:
    base = f"{title.lower()}|{company.lower()}|{normalize_location(location)}|{(origin or '').lower()}"
    return hashlib.sha1(base.encode("utf-8")).hexdigest()

def tags_to_db(tags: list[str]) -> str:
    return ",".join([clean_ws(t) for t in tags if clean_ws(t)])

@dataclass
class JobNorm:
    source: str
    source_job_id: str | None
    title: str
    company: str
    location: str
    remote: bool
    contract: bool
    posted_at: datetime | None
    apply_url: str
    origin_domain: str | None
    description_snippet: str
    tags: list[str]

    def fp(self) -> str:
        return fingerprint(self.title, self.company, self.location, self.origin_domain)

