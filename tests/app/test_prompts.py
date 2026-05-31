"""Tests for system prompt: conditional RAG section (8.5) and grounding boundary + citation markers (3.1)."""

from app.prompts import (
    DOSSIER_SYSTEM_PROMPT,
    INVESTIGATION_SYSTEM_PROMPT,
    SYSTEM_PROMPT,
    get_system_prompt,
)


class TestGetSystemPrompt:
    def test_rag_disabled_returns_base_prompt(self):
        """When rag_enabled=False, get_system_prompt returns the base prompt unchanged."""
        result = get_system_prompt(rag_enabled=False)
        assert result == SYSTEM_PROMPT

    def test_rag_enabled_includes_document_search_section(self):
        """When rag_enabled=True, get_system_prompt appends DOCUMENT SEARCH section."""
        result = get_system_prompt(rag_enabled=True)
        assert "DOCUMENT SEARCH" in result

    def test_rag_enabled_contains_base_prompt(self):
        """When rag_enabled=True, the base prompt content is preserved."""
        result = get_system_prompt(rag_enabled=True)
        # Key phrases from the base prompt must still be present
        assert "STRICT CONSTRAINTS" in result
        assert "DATA PROVENANCE" in result
        assert "MULTI-TURN CONTEXT RESOLUTION" in result

    def test_rag_disabled_excludes_document_search_section(self):
        """When rag_enabled=False, DOCUMENT SEARCH section is NOT in the prompt."""
        result = get_system_prompt(rag_enabled=False)
        assert "DOCUMENT SEARCH" not in result

    def test_rag_enabled_includes_search_documents_tool_hint(self):
        """Prompt instructs Claude to use search_documents tool."""
        result = get_system_prompt(rag_enabled=True)
        assert "search_documents" in result

    def test_rag_enabled_includes_cross_referencing_instructions(self):
        """Prompt includes cross-referencing workflow instructions."""
        result = get_system_prompt(rag_enabled=True)
        assert "CROSS-REFERENCING" in result

    def test_rag_enabled_includes_citation_format_for_documents(self):
        """Prompt includes document citation format instructions."""
        result = get_system_prompt(rag_enabled=True)
        assert "DOCUMENT CITATION FORMAT" in result
        assert "Do not construct citations manually" in result

    def test_rag_enabled_includes_grounding_boundary_extension(self):
        """Prompt extends the grounding boundary to document content."""
        result = get_system_prompt(rag_enabled=True)
        assert "user-provided context" in result

    def test_default_parameter_is_rag_disabled(self):
        """Default call (no args) returns base prompt — safe when RAG is off."""
        result = get_system_prompt()
        assert result == SYSTEM_PROMPT

    def test_system_prompt_backward_compat_alias(self):
        """SYSTEM_PROMPT constant still importable and equals base prompt with default threshold."""
        from app.prompts import SYSTEM_PROMPT as sp

        assert sp == get_system_prompt(rag_enabled=False, staleness_threshold_years=2)


class TestGroundingBoundary:
    """Story 3.1: grounding boundary reinforcement and citation marker instructions."""

    def test_base_prompt_does_not_contain_citation_markers(self):
        """AC7: Citation markers [n] are NOT present in base prompt."""
        result = get_system_prompt(rag_enabled=False)
        assert "[1]" not in result
        assert "[2]" not in result
        assert "marker" not in result.lower()

    def test_base_prompt_includes_data_sources_instructions(self):
        """AC7: LLM is told Data Sources section is appended automatically."""
        result = get_system_prompt(rag_enabled=False)
        assert "Data Sources" in result
        assert "appended automatically" in result

    def test_base_prompt_grounding_boundary_causation(self):
        """AC3: Causation constraint is explicit."""
        result = get_system_prompt(rag_enabled=False)
        assert "causation" in result.lower()

    def test_base_prompt_grounding_boundary_no_opinions(self):
        """AC4: No-opinions constraint is explicit."""
        result = get_system_prompt(rag_enabled=False)
        assert "opinions" in result.lower()

    def test_no_old_inline_citation_format(self):
        """AC5: Old citation instruction 'Example: (Source: ...)' removed from prompt."""
        result = get_system_prompt(rag_enabled=False)
        assert 'Example: "(Source:' not in result

    def test_rag_document_section_does_not_use_numbered_markers(self):
        """AC8: Document search section does NOT reference [n] markers."""
        result = get_system_prompt(rag_enabled=True)
        assert "[n]" not in result
        assert "Do not construct citations manually" in result


class TestDataFreshnessTransparency:
    """Story 3.3: Data freshness transparency instructions in system prompt."""

    def test_base_prompt_contains_data_freshness_section(self):
        """AC5: DATA FRESHNESS section present in base prompt."""
        result = get_system_prompt()
        assert "DATA FRESHNESS" in result

    def test_default_staleness_threshold_is_two_years(self):
        """AC6: Default staleness threshold is 2 years."""
        result = get_system_prompt()
        assert "2 years" in result

    def test_custom_staleness_threshold_injected(self):
        """AC6: Custom threshold is injected correctly."""
        result = get_system_prompt(staleness_threshold_years=3)
        assert "3 years" in result
        assert "{staleness_threshold}" not in result

    def test_no_placeholder_in_default_prompt(self):
        """Ensure placeholder is always resolved, never left raw."""
        result = get_system_prompt()
        assert "{staleness_threshold}" not in result

    def test_system_prompt_alias_resolves_placeholder(self):
        """SYSTEM_PROMPT alias must have resolved placeholder."""
        assert "{staleness_threshold}" not in SYSTEM_PROMPT
        assert "2 years" in SYSTEM_PROMPT

    def test_freshness_does_not_mandate_year_on_every_sentence(self):
        """AC1 refined: Prompt does NOT mandate year annotation on every sentence."""
        result = get_system_prompt()
        # The old over-eager instruction is gone
        assert "for every data claim, include the year inline" not in result.lower()
        # But the section is still present
        assert "DATA FRESHNESS" in result

    def test_freshness_includes_staleness_warning_instruction(self):
        """AC2: Prompt instructs Claude to warn about stale data."""
        result = get_system_prompt()
        assert "staleness" in result.lower() or "stale" in result.lower() or "warning" in result.lower()

    def test_freshness_includes_multi_country_recency_instruction(self):
        """AC3: Prompt instructs Claude to flag year discrepancies in multi-country comparisons."""
        result = get_system_prompt()
        assert "multi-country" in result.lower() or "discrepancy" in result.lower() or "differ" in result.lower()

    def test_rag_prompt_also_has_data_freshness(self):
        """DATA FRESHNESS section present even when RAG is enabled."""
        result = get_system_prompt(rag_enabled=True)
        assert "DATA FRESHNESS" in result

    def test_system_appends_data_sources_instruction_present(self):
        """AC5: Prompt tells Claude that Data Sources section is appended automatically."""
        result = get_system_prompt()
        assert "appended automatically" in result
        assert "Do not generate any source list" in result


class TestDossierPrompts:
    """Story 10.4: Phase-aware system prompts for investigation and dossier modes."""

    def test_investigation_prompt_asks_one_question_at_a_time(self):
        # AC7: when the assistant must ask the journalist anything, it asks a single
        # focused question rather than bombarding them. PR #76 reworked the flow to
        # infer items and minimize questions, replacing the old "one short question at
        # a time" wording with "ask ONE/one focused question". The guarantee is
        # preserved; assert the current canonical phrasing (case-insensitive).
        assert "one focused question" in INVESTIGATION_SYSTEM_PROMPT.lower()

    def test_investigation_prompt_no_apply_ops(self):
        assert "apply_ops" not in INVESTIGATION_SYSTEM_PROMPT

    def test_dossier_prompt_uses_apply_ops(self):
        assert "apply_ops" in DOSSIER_SYSTEM_PROMPT

    def test_dossier_prompt_no_inline_output(self):
        assert "Never output the document content inline" in DOSSIER_SYSTEM_PROMPT
