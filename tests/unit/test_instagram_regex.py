"""
Unit tests for Instagram regex matching and handle normalization.
"""

import re

INSTAGRAM_REGEX = re.compile(r'https?://(?:www\.)?instagram\.com/([a-zA-Z0-9_.]+)')


def test_extracts_instagram_handle():
    url = "https://www.instagram.com/metroboomin/"
    match = INSTAGRAM_REGEX.search(url)
    assert match is not None
    assert match.group(1).rstrip("/") == "metroboomin"


def test_extracts_handle_without_www():
    url = "http://instagram.com/producer_tag123?utm_medium=copy"
    match = INSTAGRAM_REGEX.search(url)
    assert match is not None
    assert match.group(1) == "producer_tag123"


def test_ignores_invalid_urls():
    url = "https://twitter.com/metroboomin"
    assert INSTAGRAM_REGEX.search(url) is None
