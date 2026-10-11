import pytest

from football_analytics.text import article_id, clean_text, parse_published_at


class TestCleanText:
    def test_removes_noise_and_extra_spaces(self):
        raw = "Saka   scores\xa0again . This video can not be played"
        assert clean_text(raw) == "Saka scores again."

    @pytest.mark.parametrize("value", [None, "", "   "])
    def test_empty_values_give_empty_string(self, value):
        assert clean_text(value) == ""


class TestParsePublishedAt:
    def test_iso_with_z_and_milliseconds(self):
        assert parse_published_at("2026-04-26T08:33:27.520Z") == "2026-04-26T08:33:27Z"

    def test_offset_is_converted_to_utc(self):
        assert parse_published_at("2026-04-26T10:00:00+02:00") == "2026-04-26T08:00:00Z"

    def test_no_timezone_is_treated_as_utc(self):
        assert parse_published_at("2026-04-26T10:00:00") == "2026-04-26T10:00:00Z"

    @pytest.mark.parametrize("value", [None, "", "yesterday", "26/04/2026"])
    def test_unparseable_returns_none_instead_of_crashing(self, value):
        assert parse_published_at(value) is None


def test_article_id_ignores_query_fragment_and_trailing_slash():
    url = "https://www.bbc.com/sport/football/articles/abc"
    assert article_id(url) == article_id(url + "/?utm_source=x#comments")
    assert len(article_id(url)) == 16
    assert article_id(url) != article_id("https://www.bbc.com/sport/football/articles/abd")