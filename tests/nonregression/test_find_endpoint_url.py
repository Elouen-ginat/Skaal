"""Unit tests for the URL parser used by the AWS / GCP non-regression tests."""

from __future__ import annotations

import pytest

from tests.nonregression.conftest import find_endpoint_url


def test_parses_url_from_pulumi_stack_output_line() -> None:
    stdout = "Stack outputs:\n  public_url = https://abc123.execute-api.us-east-1.amazonaws.com\n"
    assert (
        find_endpoint_url(stdout, marker="execute-api")
        == "https://abc123.execute-api.us-east-1.amazonaws.com"
    )


def test_strips_trailing_quote_or_comma() -> None:
    stdout = '  diagnostic: "https://abc123.execute-api.us-east-1.amazonaws.com",\n'
    assert (
        find_endpoint_url(stdout, marker="execute-api")
        == "https://abc123.execute-api.us-east-1.amazonaws.com"
    )


def test_strips_trailing_slash() -> None:
    """httpx adds the path-leading slash; trailing slash on base_url would
    double it for paths like `/todos` and route to `//todos`."""
    stdout = "  public_url = https://abc123.execute-api.us-east-1.amazonaws.com/\n"
    assert (
        find_endpoint_url(stdout, marker="execute-api")
        == "https://abc123.execute-api.us-east-1.amazonaws.com"
    )


def test_stops_at_whitespace_in_log_line() -> None:
    stdout = "info  https://abc123.execute-api.us-east-1.amazonaws.com  [stage=$default]\n"
    assert (
        find_endpoint_url(stdout, marker="execute-api")
        == "https://abc123.execute-api.us-east-1.amazonaws.com"
    )


def test_returns_first_matching_line() -> None:
    stdout = (
        "  intermediate = https://wrong.execute-api.us-east-1.amazonaws.com\n"
        "  public_url = https://correct.execute-api.us-east-1.amazonaws.com\n"
    )
    assert (
        find_endpoint_url(stdout, marker="execute-api")
        == "https://wrong.execute-api.us-east-1.amazonaws.com"
    )


def test_raises_when_no_marker_match() -> None:
    with pytest.raises(AssertionError, match="execute-api"):
        find_endpoint_url("Stack outputs:\n  other = https://example.com\n", marker="execute-api")
