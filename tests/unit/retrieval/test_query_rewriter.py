"""Tests for the query rewriter: normalization, typo correction, synonym
expansion, intent-aware rewriting, multi-query generation, and the
QueryRewriter facade end-to-end."""

from src.retrieval.query_rewriter import (
    IntentAwareRewriter,
    MultiQueryGenerator,
    QueryNormalizer,
    QueryRewriter,
    SynonymExpander,
    TypoCorrector,
)


# --------------------------------------------------------------- normalize


def test_normalizer_replaces_noise_phrases():
    normalizer = QueryNormalizer()
    assert normalizer.apply("điện thoại siêu rẻ") == "điện thoại giá thấp"


def test_normalizer_collapses_whitespace():
    normalizer = QueryNormalizer()
    assert normalizer.apply("laptop   cho    sinh viên") == "laptop cho sinh viên"


def test_normalizer_leaves_unmatched_text_unchanged():
    normalizer = QueryNormalizer()
    assert normalizer.apply("laptop cho sinh viên") == "laptop cho sinh viên"


# --------------------------------------------------------------- typo fix


def test_typo_corrector_fixes_brand_misspelling():
    corrector = TypoCorrector()
    assert corrector.apply("dien thoai sam sung") == "điện thoại samsung"


def test_typo_corrector_restores_diacritics_from_toneless_input():
    # "gia re" (toneless Vietnamese, very common when typing without an IME)
    # is corrected to "giá rẻ" via the enriched lookup table.
    corrector = TypoCorrector()
    assert corrector.apply("dien thoai gia re") == "điện thoại giá rẻ"


def test_typo_corrector_accepts_custom_table_overriding_default():
    corrector = TypoCorrector(corrections={"foo": "bar"})
    assert corrector.apply("foo baz") == "bar baz"
    # Default-table corrections should NOT apply when a custom table is given.
    assert corrector.apply("sam sung") == "sam sung"


def test_typo_corrector_case_insensitive():
    corrector = TypoCorrector()
    assert corrector.apply("Iphon 15 pro") == "iphone 15 pro"


def test_typo_corrector_no_match_unchanged():
    corrector = TypoCorrector()
    assert corrector.apply("samsung galaxy s24") == "samsung galaxy s24"


# --------------------------------------------------------------- synonyms


def test_synonym_expander_appends_new_terms():
    expander = SynonymExpander()
    result = expander.apply("điện thoại pin trâu")
    assert result.startswith("điện thoại pin trâu")
    assert "pin khỏe" in result


def test_synonym_expander_does_not_duplicate_existing_terms():
    expander = SynonymExpander()
    result = expander.apply("điện thoại giá thấp")
    # "rẻ" isn't present, so nothing from that entry should be appended.
    assert result == "điện thoại giá thấp"


# --------------------------------------------------------------- intent-aware


def test_intent_aware_rewriter_appends_use_case_and_priority_terms():
    rewriter = IntentAwareRewriter()
    result = rewriter.apply(
        "điện thoại tầm 10 triệu",
        {"use_case": ["gaming"], "priorities": ["battery"]},
    )
    assert "hiệu năng mạnh chơi game mượt" in result
    assert "pin trâu thời lượng pin dài" in result


def test_intent_aware_rewriter_skips_terms_already_present():
    rewriter = IntentAwareRewriter()
    # Both battery phrases ("pin trâu thời lượng pin dài" and "sạc nhanh")
    # already appear in the query, so nothing should be appended.
    query = "điện thoại pin trâu thời lượng pin dài sạc nhanh"
    result = rewriter.apply(query, {"use_case": [], "priorities": ["battery"]})
    assert result == query


def test_intent_aware_rewriter_appends_only_missing_phrase():
    rewriter = IntentAwareRewriter()
    # "pin trâu thời lượng pin dài" is present but "sạc nhanh" is not.
    result = rewriter.apply(
        "điện thoại pin trâu thời lượng pin dài",
        {"use_case": [], "priorities": ["battery"]},
    )
    assert "sạc nhanh" in result
    assert result.count("pin trâu thời lượng pin dài") == 1


def test_intent_aware_rewriter_no_hints_is_noop():
    rewriter = IntentAwareRewriter()
    assert rewriter.apply("điện thoại", {}) == "điện thoại"


# --------------------------------------------------------------- multi-query


def test_multi_query_generator_default_single_variant():
    generator = MultiQueryGenerator()
    variants = generator.generate("dt sam sung", "điện thoại samsung", max_variants=1)
    assert variants == ["điện thoại samsung"]


def test_multi_query_generator_fans_out_with_original_and_core():
    generator = MultiQueryGenerator()
    variants = generator.generate(
        "cho tôi cái điện thoại pin trâu", "điện thoại pin trâu", max_variants=3
    )
    assert variants[0] == "điện thoại pin trâu"
    assert "cho tôi cái điện thoại pin trâu" in variants
    assert len(variants) <= 3


def test_multi_query_generator_dedupes_case_insensitively():
    generator = MultiQueryGenerator()
    variants = generator.generate("Laptop Gaming", "laptop gaming", max_variants=3)
    assert variants == ["laptop gaming"]


# --------------------------------------------------------------- facade


def test_query_rewriter_tracks_applied_strategies():
    rewriter = QueryRewriter()
    result = rewriter.rewrite("dien thoai sam sung sieu re")
    assert "typo_correction" in result.applied_strategies
    assert "samsung" in result.rewritten_query.lower()


def test_query_rewriter_applies_intent_hints():
    rewriter = QueryRewriter()
    result = rewriter.rewrite(
        "laptop tầm 20 triệu", intent_hints={"use_case": ["work"], "priorities": []}
    )
    assert "intent_aware" in result.applied_strategies
    assert "phù hợp công việc văn phòng" in result.rewritten_query


def test_query_rewriter_default_max_variants_is_single_query():
    rewriter = QueryRewriter()
    result = rewriter.rewrite("laptop cho sinh viên")
    assert result.query_variants == [result.rewritten_query]


def test_query_rewriter_no_op_when_nothing_matches():
    rewriter = QueryRewriter()
    result = rewriter.rewrite("laptop cho sinh viên")
    assert result.rewritten_query == "laptop cho sinh viên"
    assert result.applied_strategies == []


# ------------------------------------------------------------- data-driven


def test_default_rules_json_has_expected_shape():
    """Every strategy's default vocabulary comes from the bundled JSON file."""
    from src.retrieval.query_rewriter import _load_default_rules

    rules = _load_default_rules()
    assert set(rules) == {
        "noise_replacements",
        "typo_corrections",
        "synonyms",
        "use_case_terms",
        "priority_terms",
        "stopwords",
    }
    assert len(rules["typo_corrections"]) > 10
    # use_case_terms/priority_terms map to a *list* of phrases, one entry per
    # UserIntentParser key, so multiple phrases can be enriched independently.
    assert isinstance(rules["use_case_terms"]["gaming"], list)
    assert isinstance(rules["priority_terms"]["battery"], list)


def test_synonym_expander_custom_table_overrides_default():
    expander = SynonymExpander(synonyms={"foo": ["bar", "baz"]})
    result = expander.apply("foo query")
    assert "bar" in result and "baz" in result
    assert "giá thấp" not in expander.apply("điện thoại rẻ")


def test_multi_query_generator_custom_stopwords_overrides_default():
    generator = MultiQueryGenerator(stopwords=frozenset({"foo"}))
    variants = generator.generate("bar foo baz", "bar foo baz", max_variants=2)
    assert "bar baz" in variants
