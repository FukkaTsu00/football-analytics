from football_analytics.gold import CLUB_PATTERN, PLAYER_PATTERN, build_summary, enrich, find_entities, find_topics


def art(title: str = "", content: str = "") -> dict:
    return {"title": title, "content": content, "source": "BBC Sport", "published_at": None}


class TestEntities:
    def test_club_must_be_a_whole_word(self):
        # The old substring matching found "Inter" inside "international"
        assert find_entities(CLUB_PATTERN, art(content="An international break")) == []

    def test_clubs_are_found_and_sorted(self):
        assert find_entities(CLUB_PATTERN, art(content="Napoli beat Inter")) == ["Inter", "Napoli"]

    def test_longest_club_name_wins(self):
        found = find_entities(CLUB_PATTERN, art(content="Manchester City and Manchester United"))
        assert found == ["Manchester City", "Manchester United"]

    def test_player_names_are_case_sensitive(self):
        assert find_entities(PLAYER_PATTERN, art(content="Rice scored")) == ["Rice"]
        assert find_entities(PLAYER_PATTERN, art(content="rice and beans")) == []

    def test_spelling_variants_are_merged(self):
        assert find_entities(PLAYER_PATTERN, art(content="Mbappé, Mbappe")) == ["Mbappe"]


class TestTopics:
    def test_transfer(self):
        assert "transfer" in find_topics(art(title="Chelsea complete signing of winger"))

    def test_injury(self):
        assert "injury" in find_topics(art(content="He is ruled out with a hamstring problem"))

    def test_no_keyword_means_general(self):
        assert find_topics(art(title="Fans celebrate in the city centre")) == ["general"]

    def test_keywords_must_be_whole_words(self):
        # "loan" is a transfer keyword, but not inside "Sloane"
        assert find_topics(art(content="Sloane Square")) == ["general"]


def test_enrich_and_summary():
    enriched = [enrich(art(title="Arsenal signing", content="Saka")), enrich(art(title="Weather today"))]
    assert enriched[0]["enrichment_method"] == "keyword_baseline_v1"
    summary = build_summary(enriched, "2026-10-11")
    assert summary["total_articles"] == 2
    assert summary["top_clubs"] == {"Arsenal": 1}
    assert summary["topics"]["general"] == 1
