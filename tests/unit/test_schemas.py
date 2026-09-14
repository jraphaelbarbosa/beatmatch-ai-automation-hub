"""
Unit tests for data contracts in BeatMatch AI Automation Hub.
"""

import pytest
from pydantic import ValidationError
from src.models.schemas import ArtistRecord, LeadDiscoveryPayload, QualityMetrics, HostRunnerJob


def test_artist_record_valid(sample_artist_record):
    assert sample_artist_record.name == "Kaytranada"
    assert sample_artist_record.followers == 2450000
    assert sample_artist_record.popularity == 72
    assert sample_artist_record.status == "ACTIVE"


def test_artist_record_popularity_bounds():
    with pytest.raises(ValidationError):
        ArtistRecord(
            spotify_id="test_id",
            name="Test Artist",
            popularity=150  # Out of 0-100 range
        )


def test_lead_discovery_payload(sample_lead_payload):
    assert sample_lead_payload.lead_id == "LEAD-2026-001"
    assert sample_lead_payload.platform == "SPOTIFY"
    assert 0.0 <= sample_lead_payload.confidence_score <= 1.0


def test_quality_metrics_clean_ratio():
    metrics = QualityMetrics(
        total_records=54000,
        fakes_detected=4000,
        deduplicated_count=5000,
        active_leads=45000
    )
    assert metrics.clean_ratio == 83.33

    empty_metrics = QualityMetrics()
    assert empty_metrics.clean_ratio == 100.0
