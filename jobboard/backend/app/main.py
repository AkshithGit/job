from fastapi import FastAPI, Depends, Query, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import or_

from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from fastapi import Request

from .db import Base, engine, get_db
from datetime import datetime, timezone, timedelta
from .models import Job, Profile, Application
from .schemas import JobCreate, JobOut, ProfileOut, ApplicationCreate, ApplicationOut, ApplicationUpdate


app = FastAPI(title="JobBoard API")

templates = Jinja2Templates(directory="app/templates")

# Create tables at startup
Base.metadata.create_all(bind=engine)

@app.get("/", response_class=HTMLResponse)
def dashboard(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

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
    # Build dict manually so Pydantic gets tags as list, not CSV string
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


@app.get("/health")
def health():
    return {"status": "ok"}

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
    db: Session = Depends(get_db),
):
    query = db.query(Job)

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

    jobs = query.order_by(Job.created_at.desc()).all()

    return [job_to_out(j) for j in jobs]

@app.post("/applications", response_model=ApplicationOut)
def create_application(payload: ApplicationCreate, db: Session = Depends(get_db)):
    # Validate job/profile exist
    job = db.query(Job).filter(Job.id == payload.job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    prof = db.query(Profile).filter(Profile.id == payload.profile_id).first()
    if not prof:
        raise HTTPException(status_code=404, detail="Profile not found")

    # Prevent duplicates per (job, profile)
    exists = db.query(Application).filter(
        Application.job_id == payload.job_id,
        Application.profile_id == payload.profile_id
    ).first()
    if exists:
        raise HTTPException(status_code=409, detail="Already tracked for this profile")

    applied_date = payload.applied_date
    followup_date = payload.followup_date

    # Default followup 7 days after applied_date if status APPLIED
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
    q = db.query(Application)

    if status:
        q = q.filter(Application.status == status)

    if profile_id:
        q = q.filter(Application.profile_id == profile_id)

    if due_followup:
        now = datetime.now(timezone.utc)
        q = q.filter(Application.followup_date.isnot(None)).filter(Application.followup_date <= now)

    return q.order_by(Application.created_at.desc()).all()


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

    # If moved to APPLIED and followup missing, auto set followup in 7 days
    if a.status == "APPLIED" and a.applied_date and not a.followup_date:
        a.followup_date = a.applied_date + timedelta(days=7)

    db.commit()
    db.refresh(a)
    return a

@app.get("/dashboard/jobs")
def list_dashboard_jobs(
    profile_id: int = Query(..., description="Profile id: 1=java,2=devops,3=dotnet"),
    q: str | None = Query(None),
    remote: bool | None = None,
    contract: bool | None = None,
    db: Session = Depends(get_db),
):
    # Fetch jobs (filtered)
    query = db.query(Job)

    if q:
        ql = f"%{q.lower()}%"
        query = query.filter(
            or_(
                Job.title.ilike(ql),
                Job.company.ilike(ql),
                Job.description.ilike(ql),
            )
        )
    if remote is not None:
        query = query.filter(Job.remote == remote)
    if contract is not None:
        query = query.filter(Job.contract == contract)

    jobs = query.order_by(Job.created_at.desc()).all()

    # Fetch applications for this profile in one shot
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
    q = db.query(Application).filter(Application.profile_id == profile_id)

    if status:
        q = q.filter(Application.status == status)

    if applied_today:
        # Today in UTC (simple, reliable)
        now = datetime.now(timezone.utc)
        start = datetime(now.year, now.month, now.day, tzinfo=timezone.utc)
        end = start + timedelta(days=1)
        q = q.filter(Application.applied_date.isnot(None)) \
             .filter(Application.applied_date >= start) \
             .filter(Application.applied_date < end)

    apps = q.order_by(Application.created_at.desc()).all()

    # Include job details inline so UI can display nicely
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

