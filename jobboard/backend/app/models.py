from sqlalchemy import Boolean, DateTime, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column
from .db import Base


from sqlalchemy import ForeignKey
from sqlalchemy.orm import relationship

from datetime import datetime
from sqlalchemy import Boolean, DateTime, Integer, String, Text
from sqlalchemy.sql import func
from sqlalchemy.orm import Mapped, mapped_column

class Job(Base):
    __tablename__ = "jobs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)

    title: Mapped[str] = mapped_column(String(200), index=True)
    company: Mapped[str] = mapped_column(String(200), index=True)
    location: Mapped[str | None] = mapped_column(String(200), nullable=True)

    remote: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    contract: Mapped[bool] = mapped_column(Boolean, default=False, index=True)

    tags: Mapped[str | None] = mapped_column(String(500), nullable=True)

    # Backwards compatible: UI uses this today
    url: Mapped[str | None] = mapped_column(String(1000), nullable=True)

    # Ingestion fields (already exist in DB)
    source_job_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    posted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    apply_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    origin_domain: Mapped[str | None] = mapped_column(Text, nullable=True)

    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    description_snippet: Mapped[str | None] = mapped_column(Text, nullable=True)

    source: Mapped[str | None] = mapped_column(String(200), nullable=True)

    fingerprint: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class Profile(Base):
    __tablename__ = "profiles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(50), unique=True, index=True)  # java/devops/dotnet
    display_name: Mapped[str] = mapped_column(String(100))

    created_at: Mapped[str] = mapped_column(DateTime(timezone=True), server_default=func.now())

    applications: Mapped[list["Application"]] = relationship(back_populates="profile", cascade="all, delete-orphan")


class Application(Base):
    __tablename__ = "applications"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)

    job_id: Mapped[int] = mapped_column(ForeignKey("jobs.id", ondelete="CASCADE"), index=True)
    profile_id: Mapped[int] = mapped_column(ForeignKey("profiles.id", ondelete="CASCADE"), index=True)

    status: Mapped[str] = mapped_column(String(20), index=True)  # SAVED/APPLIED/INTERVIEW/OFFER/REJECTED
    applied_date: Mapped[str | None] = mapped_column(DateTime(timezone=True), nullable=True)
    followup_date: Mapped[str | None] = mapped_column(DateTime(timezone=True), nullable=True)

    application_url: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[str] = mapped_column(DateTime(timezone=True), server_default=func.now())

    job: Mapped["Job"] = relationship("Job")
    profile: Mapped["Profile"] = relationship(back_populates="applications")

