"""Tests for the apply_ops patch engine (Story 10.3).

`apply_single_op` is tested as a pure string transform — no Chainlit mocking.
"""

from app.chat import APPLY_OPS_TOOL, apply_single_op


class TestApplySingleOpReplace:
    """AC3, AC4: replace op matching."""

    def test_replace_success(self):
        new, err = apply_single_op("hello world", {"type": "replace", "find": "world", "content": "there"})
        assert new == "hello there"
        assert err is None

    def test_replace_not_found(self):
        original = "hello world"
        new, err = apply_single_op(original, {"type": "replace", "find": "missing", "content": "x"})
        assert new == original
        assert err == "Text not found: 'missing'"

    def test_replace_ambiguous(self):
        original = "foo bar foo"
        new, err = apply_single_op(original, {"type": "replace", "find": "foo", "content": "baz"})
        assert new == original
        assert err is not None
        assert "Ambiguous" in err
        assert "2 times" in err


class TestApplySingleOpDelete:
    """AC3, AC4: delete op matching."""

    def test_delete_success(self):
        new, err = apply_single_op("hello world", {"type": "delete", "find": " world"})
        assert new == "hello"
        assert err is None

    def test_delete_not_found(self):
        original = "hello world"
        new, err = apply_single_op(original, {"type": "delete", "find": "missing"})
        assert new == original
        assert err == "Text not found: 'missing'"

    def test_delete_ambiguous(self):
        original = "foo foo"
        new, err = apply_single_op(original, {"type": "delete", "find": "foo"})
        assert new == original
        assert err is not None
        assert "Ambiguous" in err


class TestApplySingleOpInsertAfter:
    """AC5: insert_after op."""

    def test_insert_after_success(self):
        new, err = apply_single_op(
            "# Title\n\nbody",
            {"type": "insert_after", "anchor": "# Title", "content": "## Subtitle"},
        )
        assert new == "# Title\n\n## Subtitle\n\nbody"
        assert err is None

    def test_insert_after_anchor_not_found(self):
        original = "hello"
        new, err = apply_single_op(original, {"type": "insert_after", "anchor": "missing", "content": "x"})
        assert new == original
        assert err == "Anchor not found: 'missing'"

    def test_insert_after_ambiguous(self):
        original = "foo bar foo"
        new, err = apply_single_op(original, {"type": "insert_after", "anchor": "foo", "content": "x"})
        assert new == original
        assert err is not None
        assert "Ambiguous" in err


class TestApplySingleOpInsertBefore:
    """AC5: insert_before op."""

    def test_insert_before_success(self):
        new, err = apply_single_op(
            "body",
            {"type": "insert_before", "anchor": "body", "content": "# Title"},
        )
        assert new == "# Title\n\nbody"
        assert err is None


class TestApplySingleOpAppend:
    """AC6: append op."""

    def test_append_on_empty_doc(self):
        new, err = apply_single_op("", {"type": "append", "content": "first paragraph"})
        assert new == "first paragraph"
        assert err is None

    def test_append_on_non_empty_doc(self):
        new, err = apply_single_op("intro", {"type": "append", "content": "next"})
        assert new == "intro\n\nnext"
        assert err is None


class TestApplySingleOpPrepend:
    """AC7: prepend op."""

    def test_prepend(self):
        new, err = apply_single_op("body", {"type": "prepend", "content": "# Title"})
        assert new == "# Title\n\nbody"
        assert err is None

    def test_prepend_on_empty_doc(self):
        new, err = apply_single_op("", {"type": "prepend", "content": "first"})
        assert new == "first"
        assert err is None


class TestApplySingleOpUnknown:
    def test_unknown_op_type_returns_error(self):
        original = "hello"
        new, err = apply_single_op(original, {"type": "rotate", "content": "x"})
        assert new == original
        assert err == "Unknown op type: 'rotate'"


class TestApplyOpsToolSchema:
    """AC9: tool schema registered verbatim."""

    def test_name(self):
        assert APPLY_OPS_TOOL["name"] == "apply_ops"

    def test_required_top_level(self):
        assert APPLY_OPS_TOOL["input_schema"]["required"] == ["ops", "summary"]

    def test_op_types_enum(self):
        op_types = APPLY_OPS_TOOL["input_schema"]["properties"]["ops"]["items"]["properties"]["type"]["enum"]
        assert set(op_types) == {
            "replace",
            "insert_after",
            "insert_before",
            "delete",
            "append",
            "prepend",
        }

    def test_op_required(self):
        required = APPLY_OPS_TOOL["input_schema"]["properties"]["ops"]["items"]["required"]
        assert required == ["type"]
