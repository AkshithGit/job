from pydantic import BaseModel
from typing import Optional, List

class JobCreate(BaseModel):
    title: str
    company: str
    location: Optional[str] = None
    remote: bool = False
    contract: bool = False
    tags: Optional[List[str]] = None
    url: Optional[str] = None
    description: Optional[str] = None
    source: Optional[str] = None

class JobOut(BaseModel):
    id: int
    title: str
    company: str
    location: Optional[str]
    remote: bool
    contract: bool
    tags: Optional[List[str]]
    url: Optional[str]
    description: Optional[str]
    source: Optional[str]

    class Config:
        from_attributes = True

from datetime import datetime
from typing import Literal

ApplicationStatus = Literal["SAVED", "APPLIED", "INTERVIEW", "OFFER", "REJECTED"]

class ProfileOut(BaseModel):
    id: int
    name: str
    display_name: str

    class Config:
        from_attributes = True

class ApplicationCreate(BaseModel):
    job_id: int
    profile_id: int
    status: ApplicationStatus = "SAVED"
    applied_date: datetime | None = None
    followup_date: datetime | None = None
    application_url: str | None = None
    notes: str | None = None

class ApplicationUpdate(BaseModel):
    status: ApplicationStatus | None = None
    applied_date: datetime | None = None
    followup_date: datetime | None = None
    application_url: str | None = None
    notes: str | None = None

class ApplicationOut(BaseModel):
    id: int
    job_id: int
    profile_id: int
    status: ApplicationStatus
    applied_date: datetime | None
    followup_date: datetime | None
    application_url: str | None
    notes: str | None

    class Config:
        from_attributes = True

