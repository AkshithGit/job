from __future__ import annotations

import argparse
from datetime import datetime, timezone
from sqlalchemy.orm import Session

from ..db import SessionLocal
from ..models import Job
from .normalize import tags_to_db
from .sources import fetch_adzuna, fetch_remoteok, fetch_wwr_rss

import re

# Remove “not real job for you” posts
EXCLUDE_PATTERNS = [
    r"\btutor(ing)?\b",
    r"\bteacher\b",
    r"\binstructor\b",
    r"\btrainer\b",
    r"\btraining\b",
    r"\bcourse\b",
    r"\bboot ?camp\b",
    r"\beducation\b",
    r"\bschool\b",
    r"\buniversity\b",
    r"\bstudent\b",
    r"\bacadem(y|ic)\b",
    r"\bcoach(ing)?\b",
    r"\bpart[- ]?time tutor\b",
]

# Exclude junior/early career noise (you can tune)
EXCLUDE_LEVEL_PATTERNS = [
    r"\bintern(ship)?\b",
    r"\bco[- ]?op\b",
    r"\bgraduate\b",
    r"\bnew grad\b",
    r"\bentry[- ]level\b",
    r"\bjr\.?\b",
    r"\bjunior\b",
    r"\btrainee\b",
    r"\bapprentice\b",
]

# Optional: you can exclude “volunteer/unpaid”
EXCLUDE_MISC_PATTERNS = [
    r"\bvolunteer\b",
    r"\bunpaid\b",
]

JAVA_MUST_HAVE = ["java", "spring", "spring boot", "microservices"]
DEVOPS_MUST_HAVE = ["devops", "kubernetes", "docker", "terraform", "ci/cd", "jenkins", "aws", "azure"]
DOTNET_MUST_HAVE = [".net", "dotnet", "c#", "asp.net", "aspnet", "ef core", "entity framework"]

def blob(j):
    # j is JobNorm
    return f"{j.title} {j.company} {j.location} {j.description_snippet or ''}".lower()

def excluded(j, patterns) -> bool:
    t = blob(j)
    return any(re.search(p, t) for p in patterns)

def must_have_any(j, keywords) -> bool:
    t = blob(j)
    return any(k in t for k in keywords)

def profile_keywords(profile: str):
    if profile == "java":
        return JAVA_MUST_HAVE
    if profile == "devops":
        return DEVOPS_MUST_HAVE
    if profile == "dotnet":
        return DOTNET_MUST_HAVE
    return []

def dedupe_by_fp(jobs):
    """Keep one job per fingerprint. Prefer the one with the newest posted_at."""
    best = {}
    for j in jobs:
        fp = j.fp()
        cur = best.get(fp)
        if cur is None:
            best[fp] = j
            continue
        # choose the newest posted_at when available
        if (j.posted_at and (not cur.posted_at or j.posted_at > cur.posted_at)):
            best[fp] = j
        else:
            # otherwise keep existing
            pass
    return list(best.values())

def upsert_by_fingerprint(db: Session, jn) -> None:
    fp = jn.fp()

    existing = db.query(Job).filter(Job.fingerprint == fp).first()
    if existing:
        existing.title = jn.title
        existing.company = jn.company
        existing.location = jn.location
        existing.remote = jn.remote
        existing.contract = jn.contract
        existing.tags = tags_to_db(jn.tags)
        existing.source = jn.source
        existing.source_job_id = jn.source_job_id
        existing.posted_at = jn.posted_at
        existing.apply_url = jn.apply_url
        existing.url = jn.apply_url  # keep UI compatibility
        existing.origin_domain = jn.origin_domain
        existing.description_snippet = jn.description_snippet
        # keep full description as snippet for now
        existing.description = jn.description_snippet
        return

    db.add(Job(
        title=jn.title,
        company=jn.company,
        location=jn.location,
        remote=jn.remote,
        contract=jn.contract,
        tags=tags_to_db(jn.tags),
        url=jn.apply_url,
        apply_url=jn.apply_url,
        origin_domain=jn.origin_domain,
        description=jn.description_snippet,
        description_snippet=jn.description_snippet,
        source=jn.source,
        source_job_id=jn.source_job_id,
        posted_at=jn.posted_at,
        fingerprint=fp,
        created_at=datetime.now(timezone.utc),
    ))

    db.flush()


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--sources", nargs="+", default=["adzuna", "remoteok", "wwr"])
    p.add_argument("--country", default="us")
    p.add_argument("--query", default="java")
    p.add_argument("--where", default="United States")
    p.add_argument("--pages", type=int, default=1)
    p.add_argument("--profile", choices=["java", "devops", "dotnet"], default=None)
    p.add_argument("--exclude_intern", action="store_true", default=True)
    p.add_argument("--exclude_tutoring", action="store_true", default=True)
    p.add_argument("--exclude_entry", action="store_true", default=True)

    args = p.parse_args()

    jobs = []
    if "adzuna" in args.sources:
        jobs += fetch_adzuna(country=args.country, what=args.query, where=args.where, pages=args.pages)
    if "remoteok" in args.sources:
        jobs += fetch_remoteok()
    if "wwr" in args.sources:
        jobs += fetch_wwr_rss()

    # keyword filter
    q = args.query.strip().lower()
    if q:
        jobs = [j for j in jobs if q in (j.title.lower() + " " + j.description_snippet.lower())]

    jobs = dedupe_by_fp(jobs)

    # ---- hard filters (default ON) ----
    jobs = [j for j in jobs if not excluded(j, EXCLUDE_PATTERNS)]
    jobs = [j for j in jobs if not excluded(j, EXCLUDE_LEVEL_PATTERNS)]
    jobs = [j for j in jobs if not excluded(j, EXCLUDE_MISC_PATTERNS)]

    # Optional: require skill keywords for a profile (high signal)
    if args.profile:
        kw = profile_keywords(args.profile)
        if kw:
            jobs = [j for j in jobs if must_have_any(j, kw)]

    with SessionLocal() as db:
        for j in jobs:
            upsert_by_fingerprint(db, j)
        db.commit()

    print(f"Upserted {len(jobs)} jobs @ {datetime.utcnow().isoformat()}Z")

if __name__ == "__main__":
    main()

