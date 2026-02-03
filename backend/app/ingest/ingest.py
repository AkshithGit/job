from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from datetime import datetime, timezone
from urllib.parse import urlparse

from sqlalchemy.orm import Session

from ..db import SessionLocal
from ..models import Job

# Existing sources (keep what you have)
from .fetch_wwr import fetch_wwr
from .fetch_adzuna import fetch_adzuna
from .fetch_arbeitnow import fetch_arbeitnow
from .fetch_remotive import fetch_remotive

# Some projects may not have these files yet; make sure they exist if you use them:
# from .fetch_remoteok import fetch_remoteok

# ATS sources
from .fetch_greenhouse import fetch_greenhouse
from .fetch_lever import fetch_lever


# -----------------------------
# Helpers
# -----------------------------
def tags_to_str(tags: list[str] | None) -> str | None:
    if not tags:
        return None
    cleaned = []
    for t in tags:
        if t is None:
            continue
        s = str(t).strip()
        if s:
            cleaned.append(s)
    return ",".join(cleaned) if cleaned else None


def normalize_domain(url: str | None) -> str | None:
    if not url:
        return None
    try:
        return urlparse(url).netloc.lower().replace("www.", "") or None
    except Exception:
        return None


def make_fingerprint(title: str, company: str, location: str | None, origin_domain: str | None) -> str:
    base = "|".join([
        (title or "").strip().lower(),
        (company or "").strip().lower(),
        (location or "").strip().lower(),
        (origin_domain or "").strip().lower(),
    ])
    return hashlib.sha1(base.encode("utf-8")).hexdigest()


def looks_like_us_location(loc: str | None) -> bool:
    """
    Strict US location detection for onsite/hybrid roles.
    """
    if not loc:
        return False
    s = loc.strip().lower()

    # Strong non-US signals
    non_us = [
        "germany","deutschland","india","canada","uk","united kingdom","england",
        "australia","singapore","netherlands","france","spain","italy","ireland",
        "sweden","norway","denmark","poland","romania","bulgaria","mexico","brazil",
        "argentina","chile","colombia","peru","south africa","nigeria","kenya",
        "japan","china","hong kong","taiwan","korea","philippines","vietnam","thailand",
        "new zealand","switzerland","austria","belgium","czech","slovakia","hungary",
        "portugal","greece","turkey","israel","uae","dubai","saudi","qatar"
    ]
    for w in non_us:
        if w in s:
            return False

    # Strong US signals
    if "united states" in s or "usa" in s or "u.s." in s:
        return True

    # Common US format: "City, ST"
    states = {
        "al","ak","az","ar","ca","co","ct","de","fl","ga","hi","ia","id","il","in","ks","ky","la","ma","md","me","mi",
        "mn","mo","ms","mt","nc","nd","ne","nh","nj","nm","nv","ny","oh","ok","or","pa","ri","sc","sd","tn","tx","ut",
        "va","vt","wa","wi","wv","wy","dc"
    }
    for st in states:
        if f", {st}" in s:
            return True

    # Sometimes they write "US - Remote" etc.
    if "remote" in s and (" us" in s or "u.s" in s or "usa" in s):
        return True

    return False


def remote_is_us_only(title: str | None, loc: str | None, desc: str | None) -> bool:
    """
    For remote jobs: keep ONLY if text suggests US-only remote.
    This prevents global remote + EU/India etc from flooding your board.
    """
    text = " ".join([(title or ""), (loc or ""), (desc or "")]).lower()

    # Drop global/anywhere remote signals
    global_signals = [
        "worldwide", "global", "anywhere", "work from anywhere",
        "international", "all countries", "any location", "across the globe"
    ]
    if any(x in text for x in global_signals):
        return False

    # Drop if strong non-US countries appear
    non_us = [
        "germany","deutschland","india","canada","uk","united kingdom","england",
        "australia","singapore","netherlands","france","spain","italy","ireland",
        "sweden","norway","denmark","poland","romania","bulgaria","mexico","brazil",
        "japan","china","hong kong","taiwan","korea"
    ]
    if any(x in text for x in non_us):
        return False

    # Keep if US-only signals appear
    us_signals = [
        "united states", "usa", "u.s.", "us only", "must be in us",
        "eligible to work in the us", "us-based", "within the us",
        # timezone hints commonly used for US-only remote roles
        "est", "cst", "pst", "mst",
        # work authorization hints
        "authorized to work in the us", "work authorization in the us"
    ]
    if any(x in text for x in us_signals):
        return True

    # Strict mode: if not explicitly US, reject
    return False


def normalize_job(j: dict) -> dict:
    title = (j.get("title") or "Unknown").strip()
    company = (j.get("company") or "Unknown").strip()
    location = (j.get("location") or None)

    remote = bool(j.get("remote", False))
    contract = bool(j.get("contract", False))

    url = j.get("url") or j.get("apply_url")
    apply_url = j.get("apply_url") or j.get("url")
    origin = j.get("origin_domain") or normalize_domain(apply_url or url)

    desc = j.get("description") or ""
    if not j.get("description_snippet"):
        j["description_snippet"] = (desc[:300] + "...") if len(desc) > 300 else (desc or None)

    j["title"] = title
    j["company"] = company
    j["location"] = location
    j["remote"] = remote
    j["contract"] = contract
    j["url"] = url
    j["apply_url"] = apply_url
    j["origin_domain"] = origin

    j["fingerprint"] = make_fingerprint(title, company, location, origin)
    return j


def upsert_job(db: Session, j: dict) -> tuple[str, int]:
    fp = j["fingerprint"]
    existing = db.query(Job).filter(Job.fingerprint == fp).first()

    if existing:
        existing.title = j["title"]
        existing.company = j["company"]
        existing.location = j.get("location")
        existing.remote = bool(j.get("remote", False))
        existing.contract = bool(j.get("contract", False))
        existing.tags = tags_to_str(j.get("tags"))
        existing.url = j.get("url") or j.get("apply_url")
        existing.apply_url = j.get("apply_url") or j.get("url")
        existing.origin_domain = j.get("origin_domain")
        existing.description = j.get("description")
        existing.description_snippet = j.get("description_snippet")
        existing.source = j.get("source")
        existing.source_job_id = j.get("source_job_id")
        existing.posted_at = j.get("posted_at")
        return "updated", existing.id

    new = Job(
        title=j["title"],
        company=j["company"],
        location=j.get("location"),
        remote=bool(j.get("remote", False)),
        contract=bool(j.get("contract", False)),
        tags=tags_to_str(j.get("tags")),
        url=j.get("url") or j.get("apply_url"),
        apply_url=j.get("apply_url") or j.get("url"),
        origin_domain=j.get("origin_domain"),
        description=j.get("description"),
        description_snippet=j.get("description_snippet"),
        source=j.get("source"),
        source_job_id=j.get("source_job_id"),
        posted_at=j.get("posted_at"),
        fingerprint=fp,
        created_at=datetime.now(timezone.utc),
    )
    db.add(new)
    db.flush()
    return "inserted", new.id


def load_companies(companies_file: Path) -> list[dict]:
    if not companies_file.exists():
        return []
    try:
        return json.loads(companies_file.read_text())
    except Exception:
        return []


# -----------------------------
# Fetch dispatch
# -----------------------------
def run_fetchers(
    sources: list[str],
    query: str | None,
    where: str | None,
    pages: int,
    companies: list[dict],
) -> list[dict]:
    out: list[dict] = []

    for s in sources:
        s = s.strip().lower()

        if s == "wwr":
            out += fetch_wwr(query=query)

        elif s == "adzuna":
            out += fetch_adzuna(query=query, where=where or "United States", pages=pages)

        elif s == "arbeitnow":
            out += fetch_arbeitnow(query=query)

        elif s == "remotive":
            out += fetch_remotive(query=query)

        # elif s == "remoteok":
        #     out += fetch_remoteok(query=query)

        elif s == "greenhouse":
            out += fetch_greenhouse(companies=companies, query=query)

        elif s == "lever":
            out += fetch_lever(companies=companies, query=query)

        else:
            raise SystemExit(f"Unknown source: {s}")

    return out


# -----------------------------
# Main
# -----------------------------
def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--sources",
        nargs="+",
        required=True,
        help="e.g. adzuna wwr arbeitnow remotive greenhouse lever",
    )
    parser.add_argument("--query", default=None, help="search keywords")
    parser.add_argument("--where", default="United States", help="adzuna only")
    parser.add_argument("--pages", type=int, default=1, help="adzuna only")

    # ✅ strict location filter
    parser.add_argument(
        "--country",
        default="US",
        help="US (default) or ALL. US means ONLY US jobs (remote included, but must be US-only).",
    )

    # companies list file (for greenhouse/lever)
    parser.add_argument("--companies-file", default=None, help="Path to companies.json")

    args = parser.parse_args()

    default_companies = Path(__file__).with_name("companies.json")
    companies_file = Path(args.companies_file) if args.companies_file else default_companies
    companies = load_companies(companies_file)

    raw = run_fetchers(args.sources, args.query, args.where, args.pages, companies)
    normalized = [normalize_job(j) for j in raw]

    country = (args.country or "US").upper()

    # ✅ STRICT US-only filtering (remote included but must be US-only)
    if country != "ALL":
        if country == "US":
            filtered = []
            for j in normalized:
                title = j.get("title")
                loc = j.get("location")
                desc = j.get("description") or j.get("description_snippet")

                if j.get("remote"):
                    if remote_is_us_only(title, loc, desc):
                        filtered.append(j)
                else:
                    if looks_like_us_location(loc):
                        filtered.append(j)

            normalized = filtered

    inserted = 0
    updated = 0

    with SessionLocal() as db:
        for j in normalized:
            action, _id = upsert_job(db, j)
            if action == "inserted":
                inserted += 1
            else:
                updated += 1
        db.commit()

    print(
        f"Done. inserted={inserted} updated={updated} kept={len(normalized)} "
        f"country={country} sources={args.sources} companies={len(companies)}"
    )


if __name__ == "__main__":
    main()
