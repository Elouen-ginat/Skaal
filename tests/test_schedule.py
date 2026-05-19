"""Tests for `skaal.schedule.Cron` / `Every` AWS-expression emit helpers."""

from __future__ import annotations

import pytest

from skaal.schedule import Cron, Every


class TestCronAwsExpression:
    def test_every_day_replaces_dow_with_question_mark(self) -> None:
        # Standard cron `*` `*` is ambiguous for AWS — exactly one of DOM
        # and DOW must be `?`.
        assert Cron(expression="0 * * * *").as_aws_expression() == "cron(0 * * * ? *)"

    def test_explicit_dom_translates_dow_wildcard_to_question_mark(self) -> None:
        assert Cron(expression="0 8 15 * *").as_aws_expression() == "cron(0 8 15 * ? *)"

    def test_explicit_dow_translates_dom_wildcard_to_question_mark(self) -> None:
        assert Cron(expression="0 8 * * 1").as_aws_expression() == "cron(0 8 ? * 1 *)"

    def test_both_explicit_dom_and_dow_raises(self) -> None:
        with pytest.raises(ValueError, match="exactly one of those fields to be `\\?`"):
            Cron(expression="0 8 15 * 1").as_aws_expression()

    def test_appends_year_wildcard(self) -> None:
        # Year field is always `*` regardless of DOM/DOW translation.
        assert Cron(expression="30 14 1 6 *").as_aws_expression().endswith(" *)")


class TestEveryRateExpression:
    @pytest.mark.parametrize(
        ("interval", "expected"),
        [
            ("60s", "rate(1 minute)"),
            ("5m", "rate(5 minutes)"),
            ("1h", "rate(1 hour)"),
            ("2h", "rate(2 hours)"),
            ("30s", "rate(30 seconds)"),
        ],
    )
    def test_renders_singular_or_plural_unit(self, interval: str, expected: str) -> None:
        assert Every(interval=interval).as_rate_expression() == expected
