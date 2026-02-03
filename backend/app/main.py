from fastapi import FastAPI, Depends, Query, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import or_
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from fastapi import Request

from .db import Base, engine, get_db
from datetime import datetime, timezone, timedelta
from .models import Job, Profile, Application
from .schemas import (
    JobCreate, JobOut,
    ProfileOut,
    ApplicationCreate, ApplicationOut, ApplicationUpdate
)

app = FastAPI(title="JobBoard API")
templates = Jinja2Templates(directory="app/templates")

Base.metadata.create_all(bind=engine)


# -----------------------------
# Dashboard
# -----------------------------
@app.get("/", response_class=HTMLResponse)
def dashboard(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})


# -----------------------------
# Profiles
# -----------------------------
@app.post("/profiles/bootstrap", response_model=list[ProfileOut])
def bootstrap_profiles(db: Session = Depends(get_db)):
    defaults = [
        ("java", "Java"),
        ("devops", "DevOps"),
        ("dotnet", ".NET"),
    ]
    out = []
    for name, display in defaults:
        existing = db.query(Profile).filter(Profile.name == name).first()
        if not existing:
            existing = Profile(name=name, display_name=display)
            db.add(existing)
            db.commit()
            db.refresh(existing)
        out.append(existing)
    return out


# -----------------------------
# Helpers
# -----------------------------
def tags_to_str(tags):
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


def str_to_tags(s):
    if not s:
        return None
    return [t.strip() for t in s.split(",") if t.strip()]


def job_to_out(job: Job) -> JobOut:
    data = {
        "id": job.id,
        "title": job.title,
        "company": job.company,
        "location": job.location,
        "remote": job.remote,
        "contract": job.contract,
        "tags": str_to_tags(job.tags),
        "url": job.url,
        "description": job.description,
        "source": job.source,
    }
    return JobOut(**data)


def dashboard_job(job: Job, app: Application | None):
    return {
        "id": job.id,
        "title": job.title,
        "company": job.company,
        "location": job.location,
        "remote": job.remote,
        "contract": job.contract,
        "tags": str_to_tags(job.tags),
        "url": job.url,
        "description": job.description,
        "source": job.source,
        "application": None if not app else {
            "id": app.id,
            "status": app.status,
            "applied_date": app.applied_date,
            "followup_date": app.followup_date,
            "application_url": app.application_url,
            "notes": app.notes,
            "profile_id": app.profile_id,
            "job_id": app.job_id,
        }
    }


def apply_exclude_filters(query, exclude_intern: bool, exclude_tutoring: bool, exclude_entry: bool):
    patterns = []

    if exclude_tutoring:
        patterns += [
            "%tutor%", "%tutoring%", "%teacher%", "%instructor%", "%trainer%",
            "%training%", "%bootcamp%", "%course%", "%academy%", "%education%",
            "%school%", "%university%",
        ]

    if exclude_intern:
        patterns += ["%intern%", "%internship%", "%co-op%", "%coop%"]

    if exclude_entry:
        patterns += [
            "%entry level%", "%entry-level%", "%new grad%", "%graduate%",
            "%jr%", "%junior%", "%trainee%", "%apprentice%",
        ]

    if not patterns:
        return query

    match_any = or_(
        *[
            or_(
                Job.title.ilike(p),
                Job.description.ilike(p),
                Job.tags.ilike(p),
            )
            for p in patterns
        ]
    )

    return query.filter(~match_any)


# ✅ Role keyword sets
ROLE_KEYWORDS = {
    "devops": [
        "devops", "site reliability", "sre", "platform", "infrastructure",
        "cloud", "kubernetes", "k8s", "docker", "terraform", "ansible",
        "ci/cd", "jenkins", "github actions", "azure devops", "helm", "argo",
        "observability", "prometheus", "grafana", "splunk", "logging",
        "aws", "azure", "gcp", "eks", "aks",
    ],
    "java": [
        "java", "spring", "spring boot", "microservices", "hibernate",
        "kafka", "j2ee", "rest", "api", "backend", "maven", "gradle",
    ],
    "dotnet": [
        ".net", "dotnet", "c#", "asp.net", "asp.net core", "entity framework",
        "ef core", "azure", "web api", "mvc",
    ],
}

# Optional: mild “anti-keywords” to reduce noise per role (tune anytime)
ROLE_EXCLUDES = {
    "devops": ["teacher", "tutor", "instructor", "student", "working student"],
    "java": ["teacher", "tutor", "instructor"],
    "dotnet": ["teacher", "tutor", "instructor"],
}


def apply_role_filter(query, role: str | None):
    """
    If role is set, require the job to match the role's keywords
    across title/description/tags.
    """
    if not role:
        return query

    role = role.lower().strip()
    if role not in ROLE_KEYWORDS:
        return query

    kws = ROLE_KEYWORDS[role]
    include_any = or_(
        *[
            or_(
                Job.title.ilike(f"%{kw}%"),
                Job.description.ilike(f"%{kw}%"),
                Job.tags.ilike(f"%{kw}%"),
            )
            for kw in kws
        ]
    )
    query = query.filter(include_any)

    # Apply lightweight excludes
    ex = ROLE_EXCLUDES.get(role, [])
    if ex:
        exclude_any = or_(
            *[
                or_(
                    Job.title.ilike(f"%{kw}%"),
                    Job.description.ilike(f"%{kw}%"),
                    Job.tags.ilike(f"%{kw}%"),
                )
                for kw in ex
            ]
        )
        query = query.filter(~exclude_any)

    return query


def apply_common_filters(
    query,
    q: str | None,
    remote: bool | None,
    contract: bool | None,
    source: str | None,
    company: str | None,
    origin_domain: str | None,
    only_ats: bool | None,
):
    if q:
        ql = f"%{q.lower()}%"
        query = query.filter(
            or_(
                Job.title.ilike(ql),
                Job.company.ilike(ql),
                Job.location.ilike(ql),
                Job.description.ilike(ql),
                Job.tags.ilike(ql),
                Job.source.ilike(ql),
                Job.origin_domain.ilike(ql),
            )
        )

    if remote is not None:
        query = query.filter(Job.remote == remote)

    if contract is not None:
        query = query.filter(Job.contract == contract)

    if source:
        query = query.filter(Job.source == source)

    if company:
        query = query.filter(Job.company.ilike(f"%{company}%"))

    if origin_domain:
        query = query.filter(Job.origin_domain.ilike(f"%{origin_domain}%"))

    if only_ats:
        query = query.filter(Job.source.in_(["greenhouse", "lever"]))

    return query


# -----------------------------
# Health
# -----------------------------
@app.get("/health")
def health():
    return {"status": "ok"}


# -----------------------------
# Jobs
# -----------------------------
@app.post("/jobs", response_model=JobOut)
def create_job(payload: JobCreate, db: Session = Depends(get_db)):
    job = Job(
        title=payload.title,
        company=payload.company,
        location=payload.location,
        remote=payload.remote,
        contract=payload.contract,
        tags=tags_to_str(payload.tags),
        url=payload.url,
        description=payload.description,
        source=payload.source,
    )
    db.add(job)
    db.commit()
    db.refresh(job)
    return job_to_out(job)


@app.get("/jobs", response_model=list[JobOut])
def list_jobs(
    q: str | None = Query(None),
    remote: bool | None = None,
    contract: bool | None = None,

    source: str | None = Query(None, description="Exact source match"),
    company: str | None = Query(None, description="Company name contains"),
    origin_domain: str | None = Query(None, description="Origin domain contains"),
    only_ats: bool | None = Query(None, description="If true, greenhouse+lever only"),

    # ✅ NEW: role filter (optional)
    role: str | None = Query(None, description="Role filter: devops|java|dotnet"),

    exclude_intern: bool = Query(True),
    exclude_tutoring: bool = Query(True),
    exclude_entry: bool = Query(True),

    db: Session = Depends(get_db),
):
    query_db = db.query(Job)

    query_db = apply_common_filters(
        query=query_db,
        q=q,
        remote=remote,
        contract=contract,
        source=source,
        company=company,
        origin_domain=origin_domain,
        only_ats=only_ats,
    )

    query_db = apply_exclude_filters(query_db, exclude_intern, exclude_tutoring, exclude_entry)

    # ✅ role filter AFTER excludes/common filters
    query_db = apply_role_filter(query_db, role)

    jobs = query_db.order_by(Job.created_at.desc()).all()
    return [job_to_out(j) for j in jobs]


# -----------------------------
# Applications
# -----------------------------
@app.post("/applications", response_model=ApplicationOut)
def create_application(payload: ApplicationCreate, db: Session = Depends(get_db)):
    job = db.query(Job).filter(Job.id == payload.job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    prof = db.query(Profile).filter(Profile.id == payload.profile_id).first()
    if not prof:
        raise HTTPException(status_code=404, detail="Profile not found")

    exists = db.query(Application).filter(
        Application.job_id == payload.job_id,
        Application.profile_id == payload.profile_id
    ).first()
    if exists:
        raise HTTPException(status_code=409, detail="Already tracked for this profile")

    applied_date = payload.applied_date
    followup_date = payload.followup_date

    if payload.status == "APPLIED" and applied_date and not followup_date:
        followup_date = applied_date + timedelta(days=7)

    a = Application(
        job_id=payload.job_id,
        profile_id=payload.profile_id,
        status=payload.status,
        applied_date=applied_date,
        followup_date=followup_date,
        application_url=payload.application_url,
        notes=payload.notes
    )
    db.add(a)
    db.commit()
    db.refresh(a)
    return a


@app.get("/applications", response_model=list[ApplicationOut])
def list_applications(
    status: str | None = None,
    profile_id: int | None = None,
    due_followup: bool | None = None,
    db: Session = Depends(get_db),
):
    qdb = db.query(Application)

    if status:
        qdb = qdb.filter(Application.status == status)

    if profile_id:
        qdb = qdb.filter(Application.profile_id == profile_id)

    if due_followup:
        now = datetime.now(timezone.utc)
        qdb = qdb.filter(Application.followup_date.isnot(None)).filter(Application.followup_date <= now)

    return qdb.order_by(Application.created_at.desc()).all()


@app.patch("/applications/{app_id}", response_model=ApplicationOut)
def update_application(app_id: int, payload: ApplicationUpdate, db: Session = Depends(get_db)):
    a = db.query(Application).filter(Application.id == app_id).first()
    if not a:
        raise HTTPException(status_code=404, detail="Application not found")

    if payload.status is not None:
        a.status = payload.status
    if payload.applied_date is not None:
        a.applied_date = payload.applied_date
    if payload.followup_date is not None:
        a.followup_date = payload.followup_date
    if payload.application_url is not None:
        a.application_url = payload.application_url
    if payload.notes is not None:
        a.notes = payload.notes

    if a.status == "APPLIED" and a.applied_date and not a.followup_date:
        a.followup_date = a.applied_date + timedelta(days=7)

    db.commit()
    db.refresh(a)
    return a


# -----------------------------
# Dashboard API
# -----------------------------
@app.get("/dashboard/jobs")
def list_dashboard_jobs(
    profile_id: int = Query(..., description="1=java,2=devops,3=dotnet"),
    q: str | None = Query(None),
    remote: bool | None = None,
    contract: bool | None = None,

    source: str | None = Query(None),
    company: str | None = Query(None),
    origin_domain: str | None = Query(None),
    only_ats: bool | None = Query(None),

    exclude_intern: bool = Query(True),
    exclude_tutoring: bool = Query(True),
    exclude_entry: bool = Query(True),

    # ✅ Optional override role
    role: str | None = Query(None, description="Override role filter: devops|java|dotnet"),

    db: Session = Depends(get_db),
):
    query_db = db.query(Job)

    query_db = apply_common_filters(
        query=query_db,
        q=q,
        remote=remote,
        contract=contract,
        source=source,
        company=company,
        origin_domain=origin_domain,
        only_ats=only_ats,
    )

    query_db = apply_exclude_filters(query_db, exclude_intern, exclude_tutoring, exclude_entry)

    # ✅ IMPORTANT: If role not provided, infer from profile_id
    if not role:
        prof = db.query(Profile).filter(Profile.id == profile_id).first()
        if prof:
            role = prof.name  # "java" / "devops" / "dotnet"

    query_db = apply_role_filter(query_db, role)

    jobs = query_db.order_by(Job.created_at.desc()).all()

    apps = db.query(Application).filter(Application.profile_id == profile_id).all()
    app_by_job = {a.job_id: a for a in apps}

    return [dashboard_job(j, app_by_job.get(j.id)) for j in jobs]


@app.get("/dashboard/applications")
def dashboard_applications(
    profile_id: int = Query(...),
    status: str | None = None,
    applied_today: bool | None = None,
    db: Session = Depends(get_db),
):
    qdb = db.query(Application).filter(Application.profile_id == profile_id)

    if status:
        qdb = qdb.filter(Application.status == status)

    if applied_today:
        now = datetime.now(timezone.utc)
        start = datetime(now.year, now.month, now.day, tzinfo=timezone.utc)
        end = start + timedelta(days=1)
        qdb = qdb.filter(Application.applied_date.isnot(None)) \
                 .filter(Application.applied_date >= start) \
                 .filter(Application.applied_date < end)

    apps = qdb.order_by(Application.created_at.desc()).all()

    job_ids = [a.job_id for a in apps]
    jobs = db.query(Job).filter(Job.id.in_(job_ids)).all() if job_ids else []
    job_by_id = {j.id: j for j in jobs}

    out = []
    for a in apps:
        j = job_by_id.get(a.job_id)
        out.append({
            "application": {
                "id": a.id,
                "job_id": a.job_id,
                "profile_id": a.profile_id,
                "status": a.status,
                "applied_date": a.applied_date,
                "followup_date": a.followup_date,
                "application_url": a.application_url,
                "notes": a.notes,
            },
            "job": None if not j else {
                "id": j.id,
                "title": j.title,
                "company": j.company,
                "location": j.location,
                "remote": j.remote,
                "contract": j.contract,
                "tags": str_to_tags(j.tags),
                "url": j.url,
                "source": j.source,
            }
        })
    return out
