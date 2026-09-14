"""
Data contracts and schema definitions for BeatMatch AI Automation Hub.
Enforces validation and serialization across scrapers, enrichers, and quality engines using Pydantic v2.
"""

from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, Field


class ArtistRecord(BaseModel):
    """Normalized artist entity extracted from Spotify / streaming platforms."""
    spotify_id: str = Field(..., min_length=1, description="Unique Spotify artist identifier")
    name: str = Field(..., min_length=1, description="Artist name")
    followers: int = Field(default=0, ge=0, description="Spotify follower count")
    popularity: int = Field(default=0, ge=0, le=100, description="Spotify popularity index (0-100)")
    status: Literal["NEW", "ENRICHED", "PENDING", "FAILED", "FAKED", "ACTIVE"] = Field(
        default="NEW",
        description="Pipeline processing state"
    )
    genres: list[str] = Field(default_factory=list, description="Associated music genres")
    instagram_url: str | None = Field(default=None, description="Discovered Instagram profile URL")


class LeadDiscoveryPayload(BaseModel):
    """Lead discovery contract dispatched to Monday.com Work OS and outreach queues."""
    lead_id: str = Field(..., min_length=1, description="Unique lead identifier")
    artist_name: str = Field(..., min_length=1, description="Artist or producer display name")
    platform: Literal["SPOTIFY", "YOUTUBE", "INSTAGRAM", "TWITTER"] = Field(
        default="SPOTIFY",
        description="Source platform"
    )
    profile_url: str = Field(..., description="Canonical link to the producer profile")
    confidence_score: float = Field(
        default=0.8,
        ge=0.0,
        le=1.0,
        description="Verification confidence level (0.0 to 1.0)"
    )
    discovered_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="UTC discovery timestamp"
    )


class QualityMetrics(BaseModel):
    """Telemetry report recording SIPA data cleaning and deduplication metrics."""
    total_records: int = Field(default=0, ge=0, description="Total records evaluated in database")
    fakes_detected: int = Field(default=0, ge=0, description="Inactive or generic spam profiles flagged")
    deduplicated_count: int = Field(default=0, ge=0, description="Duplicate profiles pruned")
    active_leads: int = Field(default=0, ge=0, description="Production-grade leads retained")

    @property
    def clean_ratio(self) -> float:
        if self.total_records == 0:
            return 100.0
        return round((self.active_leads / self.total_records) * 100, 2)


class HostRunnerJob(BaseModel):
    """Job execution model for the background VPS host runner service."""
    job_id: str = Field(..., min_length=1, description="Unique task runner execution ID")
    task_name: str = Field(..., min_length=1, description="Pipeline job name")
    status: Literal["IDLE", "RUNNING", "COMPLETED", "FAILED"] = "IDLE"
    started_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="UTC start time"
    )
