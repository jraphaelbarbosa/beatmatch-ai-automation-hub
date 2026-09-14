"""
Unit tests for SIPA quality cleaning heuristics and fake detection.
"""

import pytest
import pandas as pd


def is_fake_candidate(name: str, popularity: int, followers: int) -> bool:
    """Pure heuristic extracted from sipa_cleaner for test verification."""
    cond_short_name = len(str(name).strip()) <= 1
    generic_terms = ['rnb', 'rap', 'hip hop', 'pop', 'trap', 'genre', 'type beat']
    pattern = '|'.join(generic_terms)
    cond_generic = any(term in str(name).lower() for term in generic_terms)
    cond_inactive = (popularity == 0) and (followers < 5)

    return (cond_short_name or cond_generic) and cond_inactive


def test_detects_generic_inactive_fake():
    assert is_fake_candidate("Trap Type Beat", popularity=0, followers=1) is True
    assert is_fake_candidate("Pop Music", popularity=0, followers=0) is True


def test_detects_short_inactive_name():
    assert is_fake_candidate("X", popularity=0, followers=2) is True


def test_preserves_real_artist_with_generic_name():
    # Real active artist with popularity/followers must NOT be flagged
    assert is_fake_candidate("Pop Smoke", popularity=80, followers=5000000) is False
