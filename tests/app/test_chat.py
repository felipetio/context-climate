"""Unit tests for streaming Claude API integration and MCP tool use in app/chat.py."""

import contextlib
import importlib
import inspect
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


@pytest.fixture(autouse=True)
def set_required_env_vars(monkeypatch):
    """Provide required env vars so Settings and app/chat load without a .env file."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    monkeypatch.setenv("DATABASE_URL", "postgresql://user:password@localhost:5432/testdb")
    monkeypatch.setenv("MCP_SERVER_URL", "http://localhost:8001")
    monkeypatch.setenv("CONVERSATION_HISTORY_LIMIT", "10")


def _make_fake_content_block(block_type="text", text="Hello, world!", **kwargs):
    """Build a minimal fake content block (text or tool_use)."""
    block = MagicMock()
    block.type = block_type
    if block_type == "text":
        block.text = text
    elif block_type == "tool_use":
        block.name = kwargs.get("name", "search_indicators")
        block.input = kwargs.get("input", {"query": "test"})
        block.id = kwargs.get("id", "toolu_01ABC")

    # Build a dict resembling Anthropic's .model_dump() output
    full_dump = {"type": block_type, "extra_null": None, **kwargs}
    if block_type == "text":
        full_dump.setdefault("text", text)
    elif block_type == "tool_use":
        full_dump.setdefault("name", block.name)
        full_dump.setdefault("input", block.input)
        full_dump.setdefault("id", block.id)

    def fake_model_dump(exclude_none=False, **_kw):
        if exclude_none:
            return {k: v for k, v in full_dump.items() if v is not None}
        return dict(full_dump)

    block.model_dump = MagicMock(side_effect=fake_model_dump)
    return block


def _make_final_message(stop_reason="end_turn", content_blocks=None):
    """Build a fake Anthropic Message response object."""
    msg = MagicMock()
    msg.stop_reason = stop_reason
    msg.content = content_blocks or [_make_fake_content_block("text", "Hello, world!")]
    return msg


class FakeStream:
    """Fake async context manager simulating anthropic streaming response."""

    def __init__(self, tokens=None, stop_reason="end_turn", content_blocks=None):
        self._tokens = tokens or ["Hello", ", ", "world", "!"]
        self._stop_reason = stop_reason
        self._content_blocks = content_blocks

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_):
        pass

    @property
    def text_stream(self):
        async def _gen():
            for token in self._tokens:
                yield token

        return _gen()

    async def get_final_message(self):
        return _make_final_message(self._stop_reason, self._content_blocks)


class FakeStreamError:
    """Fake async context manager that raises on entry."""

    def __init__(self, exc):
        self._exc = exc

    async def __aenter__(self):
        raise self._exc

    async def __aexit__(self, *_):
        pass


def _make_fake_cl_message():
    """Build a mock cl.Message that accumulates tokens into .content."""
    msg = AsyncMock()
    accumulated = []

    async def stream_token(text):
        accumulated.append(text)
        msg.content = "".join(accumulated)

    msg.stream_token = stream_token
    msg.content = ""
    msg.update = AsyncMock()
    msg.send = AsyncMock()
    msg.remove = AsyncMock()
    return msg


@pytest.fixture()
def reload_chat():
    """Reload app.chat after env vars are patched so settings is re-instantiated."""
    import app.chat
    import app.config

    importlib.reload(app.config)
    importlib.reload(app.chat)
    return app.chat


class TestStreamingResponse:
    async def test_normal_streaming_assembles_correct_content(self, reload_chat):
        """Happy-path: tokens are streamed and message content is assembled."""
        tokens = ["Hello", ", ", "world", "!"]
        msg_mock = _make_fake_cl_message()

        with (
            patch("app.chat.cl.Message", return_value=msg_mock),
            patch("app.chat.cl.user_session") as session_mock,
            patch("app.chat.client.messages.stream", return_value=FakeStream(tokens)),
        ):
            session_mock.get.return_value = []
            session_mock.set = MagicMock()

            incoming = MagicMock()
            incoming.content = "What is the GDP of Kenya?"

            await reload_chat.on_message(incoming)

        assert msg_mock.content == "Hello, world!"
        msg_mock.update.assert_awaited_once()

    async def test_assistant_reply_appended_to_history(self, reload_chat):
        """After a successful response, the assistant message is stored in history."""
        tokens = ["Hello"]
        msg_mock = _make_fake_cl_message()

        captured_history = []

        def fake_set(key, value):
            if key == "history":
                captured_history.clear()
                captured_history.extend(value)

        with (
            patch("app.chat.cl.Message", return_value=msg_mock),
            patch("app.chat.cl.user_session") as session_mock,
            patch("app.chat.client.messages.stream", return_value=FakeStream(tokens)),
        ):
            session_mock.get.return_value = []
            session_mock.set.side_effect = fake_set

            incoming = MagicMock()
            incoming.content = "Hi"

            await reload_chat.on_message(incoming)

        assert len(captured_history) == 2
        assert captured_history[0] == {"role": "user", "content": "Hi"}
        assert captured_history[1]["role"] == "assistant"

    async def test_history_trimmed_to_limit(self, reload_chat):
        """History is trimmed to conversation_history_limit before each API call."""
        tokens = ["ok"]
        msg_mock = _make_fake_cl_message()

        # Pre-populate history with 20 messages (well above any limit)
        pre_history = [{"role": "user" if i % 2 == 0 else "assistant", "content": f"msg{i}"} for i in range(20)]

        captured_messages = []

        def fake_stream(**kwargs):
            # Deep-copy messages at call time to avoid mutation after stream
            import copy

            captured_messages.extend(copy.deepcopy(kwargs.get("messages", [])))
            return FakeStream(tokens)

        limit = 4
        with (
            patch("app.chat.cl.Message", return_value=msg_mock),
            patch("app.chat.cl.user_session") as session_mock,
            patch("app.chat.client.messages.stream", side_effect=fake_stream),
            patch("app.chat.settings") as settings_mock,
        ):
            settings_mock.conversation_history_limit = limit
            session_mock.get.return_value = pre_history.copy()
            session_mock.set = MagicMock()

            incoming = MagicMock()
            incoming.content = "new message"

            await reload_chat.on_message(incoming)

        # messages passed to stream should be trimmed to last `limit`
        assert len(captured_messages) <= limit

    async def test_system_prompt_included_in_every_call(self, reload_chat):
        """system prompt must be present in every API call (Story 10.4: investigation prompt in default phase)."""
        from app.prompts import INVESTIGATION_SYSTEM_PROMPT

        tokens = ["response"]
        msg_mock = _make_fake_cl_message()
        captured_call_args = {}

        def fake_stream(**kwargs):
            captured_call_args.update(kwargs)
            return FakeStream(tokens)

        with (
            patch("app.chat.cl.Message", return_value=msg_mock),
            patch("app.chat.cl.user_session") as session_mock,
            patch("app.chat.client.messages.stream", side_effect=fake_stream),
            patch("app.chat.settings") as settings_mock,
        ):
            settings_mock.rag_enabled = False
            settings_mock.staleness_threshold_years = 2
            settings_mock.claude_model = "claude-3-5-sonnet-20241022"
            settings_mock.claude_max_tokens = 4096
            settings_mock.max_tool_rounds = 20
            settings_mock.conversation_history_limit = 10
            session_mock.get.return_value = []
            session_mock.set = MagicMock()

            incoming = MagicMock()
            incoming.content = "test"

            await reload_chat.on_message(incoming)

        assert captured_call_args.get("system") == INVESTIGATION_SYSTEM_PROMPT

    async def test_conversation_history_passed_to_api(self, reload_chat):
        """Prior conversation turns are included in the messages list."""
        tokens = ["second response"]
        msg_mock = _make_fake_cl_message()
        captured_messages = []

        def fake_stream(**kwargs):
            # Deep-copy to capture snapshot before any post-stream mutation
            import copy

            captured_messages.extend(copy.deepcopy(kwargs.get("messages", [])))
            return FakeStream(tokens)

        existing_history = [
            {"role": "user", "content": "first message"},
            {"role": "assistant", "content": "first response"},
        ]

        with (
            patch("app.chat.cl.Message", return_value=msg_mock),
            patch("app.chat.cl.user_session") as session_mock,
            patch("app.chat.client.messages.stream", side_effect=fake_stream),
        ):
            session_mock.get.return_value = existing_history.copy()
            session_mock.set = MagicMock()

            incoming = MagicMock()
            incoming.content = "second message"

            await reload_chat.on_message(incoming)

        roles = [m["role"] for m in captured_messages]
        assert "user" in roles
        assert "assistant" in roles
        # new user message should be last in the snapshot passed to the API
        assert captured_messages[-1]["role"] == "user"
        assert captured_messages[-1]["content"] == "second message"


class TestErrorHandling:
    async def test_api_error_surfaces_as_ui_message(self, reload_chat):
        """Any exception during the API call must produce a visible error message."""
        error_msg_mock = AsyncMock()
        error_msg_mock.send = AsyncMock()
        streaming_msg_mock = AsyncMock()
        streaming_msg_mock.send = AsyncMock()
        streaming_msg_mock.remove = AsyncMock()
        streaming_msg_mock.content = ""

        call_count = 0

        def make_message(**kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return streaming_msg_mock
            return error_msg_mock

        exc = Exception("Simulated Anthropic authentication failure")

        with (
            patch("app.chat.cl.Message", side_effect=make_message),
            patch("app.chat.cl.user_session") as session_mock,
            patch("app.chat.client.messages.stream", return_value=FakeStreamError(exc)),
        ):
            session_mock.get.return_value = []
            session_mock.set = MagicMock()

            incoming = MagicMock()
            incoming.content = "trigger error"

            await reload_chat.on_message(incoming)

        # The streaming placeholder must be removed
        streaming_msg_mock.remove.assert_awaited_once()
        # An error message must have been sent
        error_msg_mock.send.assert_awaited_once()

    async def test_network_error_surfaces_as_ui_message(self, reload_chat):
        """httpx connection errors must also be surfaced, not silently swallowed."""
        import httpx

        error_msg_mock = AsyncMock()
        error_msg_mock.send = AsyncMock()
        streaming_msg_mock = AsyncMock()
        streaming_msg_mock.send = AsyncMock()
        streaming_msg_mock.remove = AsyncMock()
        streaming_msg_mock.content = ""

        call_count = 0

        def make_message(**kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return streaming_msg_mock
            return error_msg_mock

        exc = httpx.ConnectError("Connection refused")

        with (
            patch("app.chat.cl.Message", side_effect=make_message),
            patch("app.chat.cl.user_session") as session_mock,
            patch("app.chat.client.messages.stream", return_value=FakeStreamError(exc)),
        ):
            session_mock.get.return_value = []
            session_mock.set = MagicMock()

            incoming = MagicMock()
            incoming.content = "trigger network error"

            await reload_chat.on_message(incoming)

        streaming_msg_mock.remove.assert_awaited_once()
        error_msg_mock.send.assert_awaited_once()

    async def test_error_message_contains_warning_text(self, reload_chat):
        """The error message content must start with the expected warning emoji."""
        sent_messages = []

        streaming_msg_mock = AsyncMock()
        streaming_msg_mock.send = AsyncMock()
        streaming_msg_mock.remove = AsyncMock()
        streaming_msg_mock.content = ""

        class CapturingMessage:
            def __init__(self, content="", **kwargs):
                self.content = content
                sent_messages.append(self)

            async def send(self):
                pass

        call_count = 0

        def make_message(**kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return streaming_msg_mock
            return CapturingMessage(**kwargs)

        exc = RuntimeError("Some error")

        with (
            patch("app.chat.cl.Message", side_effect=make_message),
            patch("app.chat.cl.user_session") as session_mock,
            patch("app.chat.client.messages.stream", return_value=FakeStreamError(exc)),
        ):
            session_mock.get.return_value = []
            session_mock.set = MagicMock()

            incoming = MagicMock()
            incoming.content = "trigger error"

            await reload_chat.on_message(incoming)

        assert len(sent_messages) == 1
        assert sent_messages[0].content.startswith("⚠️")


def _make_session_mock_with_history(
    history=None, mcp_session=None, mcp_tools=None, dossier=None, doc=None, investigation=None
):
    """Return a cl.user_session mock that serves the given values by key."""
    store = {
        "history": history if history is not None else [],
        "mcp_session": mcp_session,
        "mcp_tools": mcp_tools if mcp_tools is not None else [],
        "dossier": dossier,
        "doc": doc,
        "investigation": investigation,
    }

    def fake_get(key, default=None):
        value = store.get(key)
        if value is None and key not in store:
            return default
        if value is None:
            return default
        return value

    mock = MagicMock()
    mock.get.side_effect = fake_get
    mock.set = MagicMock()
    return mock


class TestMcpToolUse:
    """Tests for the MCP agentic tool-use loop."""

    async def test_tools_passed_to_claude_when_mcp_connected(self, reload_chat):
        """When MCP tools are available, they must be passed to the Claude API call."""
        tools = [{"name": "search_indicators", "description": "Search", "input_schema": {"type": "object"}}]
        msg_mock = _make_fake_cl_message()
        captured_call_kwargs = {}

        def fake_stream(**kwargs):
            captured_call_kwargs.update(kwargs)
            return FakeStream(["OK"])

        with (
            patch("app.chat.cl.Message", return_value=msg_mock),
            patch("app.chat.cl.user_session", _make_session_mock_with_history(mcp_tools=tools)),
            patch("app.chat.client.messages.stream", side_effect=fake_stream),
        ):
            incoming = MagicMock()
            incoming.content = "search GDP"
            await reload_chat.on_message(incoming)

        # apply_ops is gated on dossier phase (Story 10.4). Default session phase is
        # "investigating", so MCP tools are passed but apply_ops is not.
        passed_tools = captured_call_kwargs.get("tools") or []
        passed_names = [t["name"] for t in passed_tools]
        assert "search_indicators" in passed_names
        assert "apply_ops" not in passed_names

    async def test_configurable_model_used_in_api_call(self, reload_chat):
        """The model from settings.claude_model is used in the Claude API call."""
        msg_mock = _make_fake_cl_message()
        captured_call_kwargs = {}

        def fake_stream(**kwargs):
            captured_call_kwargs.update(kwargs)
            return FakeStream(["OK"])

        with (
            patch("app.chat.cl.Message", return_value=msg_mock),
            patch("app.chat.cl.user_session", _make_session_mock_with_history()),
            patch("app.chat.client.messages.stream", side_effect=fake_stream),
            patch("app.chat.settings") as settings_mock,
        ):
            settings_mock.claude_model = "claude-sonnet-4-5-20250514"
            settings_mock.claude_max_tokens = 4096
            settings_mock.max_tool_rounds = 20
            settings_mock.conversation_history_limit = 10
            incoming = MagicMock()
            incoming.content = "test"
            await reload_chat.on_message(incoming)

        assert captured_call_kwargs["model"] == "claude-sonnet-4-5-20250514"

    async def test_configurable_max_tokens_used_in_api_call(self, reload_chat):
        """The max_tokens from settings.claude_max_tokens is used in the Claude API call."""
        msg_mock = _make_fake_cl_message()
        captured_call_kwargs = {}

        def fake_stream(**kwargs):
            captured_call_kwargs.update(kwargs)
            return FakeStream(["OK"])

        with (
            patch("app.chat.cl.Message", return_value=msg_mock),
            patch("app.chat.cl.user_session", _make_session_mock_with_history()),
            patch("app.chat.client.messages.stream", side_effect=fake_stream),
            patch("app.chat.settings") as settings_mock,
        ):
            settings_mock.claude_model = "claude-haiku-4-5"
            settings_mock.claude_max_tokens = 8192
            settings_mock.max_tool_rounds = 20
            settings_mock.conversation_history_limit = 10
            incoming = MagicMock()
            incoming.content = "test"
            await reload_chat.on_message(incoming)

        assert captured_call_kwargs["max_tokens"] == 8192

    async def test_apply_ops_registered_in_dossier_phase(self, reload_chat):
        """In dossier phase, the local apply_ops tool is registered (Story 10.4)."""
        msg_mock = _make_fake_cl_message()
        captured_call_kwargs = {}
        doc_mock = MagicMock()
        doc_mock.props = {"content": "# Dossier", "version": 1}

        def fake_stream(**kwargs):
            captured_call_kwargs.update(kwargs)
            return FakeStream(["OK"])

        with (
            patch("app.chat.cl.Message", return_value=msg_mock),
            patch(
                "app.chat.cl.user_session",
                _make_session_mock_with_history(dossier={"phase": "dossier"}, doc=doc_mock),
            ),
            patch("app.chat.client.messages.stream", side_effect=fake_stream),
        ):
            incoming = MagicMock()
            incoming.content = "hello"
            await reload_chat.on_message(incoming)

        passed_tools = captured_call_kwargs.get("tools") or []
        passed_names = [t["name"] for t in passed_tools]
        # Story 11.2 added `update_investigation_item` alongside apply_ops in dossier phase.
        # This assertion remains focused on apply_ops registration (the Story 10.4 contract).
        assert "apply_ops" in passed_names

    async def test_apply_ops_not_registered_in_investigating_phase(self, reload_chat):
        """In investigating phase (default), apply_ops is NOT exposed to the LLM (Story 10.4)."""
        msg_mock = _make_fake_cl_message()
        captured_call_kwargs = {}

        def fake_stream(**kwargs):
            captured_call_kwargs.update(kwargs)
            return FakeStream(["OK"])

        with (
            patch("app.chat.cl.Message", return_value=msg_mock),
            patch("app.chat.cl.user_session", _make_session_mock_with_history()),
            patch("app.chat.client.messages.stream", side_effect=fake_stream),
        ):
            incoming = MagicMock()
            incoming.content = "hello"
            await reload_chat.on_message(incoming)

        passed_tools = captured_call_kwargs.get("tools") or []
        passed_names = [t["name"] for t in passed_tools]
        assert "apply_ops" not in passed_names

    async def test_investigation_system_prompt_used_in_investigating_phase(self, reload_chat):
        """In investigating phase, INVESTIGATION_SYSTEM_PROMPT is used (Story 10.4 AC3)."""
        msg_mock = _make_fake_cl_message()
        captured_call_kwargs = {}

        def fake_stream(**kwargs):
            captured_call_kwargs.update(kwargs)
            return FakeStream(["OK"])

        with (
            patch("app.chat.cl.Message", return_value=msg_mock),
            patch("app.chat.cl.user_session", _make_session_mock_with_history()),
            patch("app.chat.client.messages.stream", side_effect=fake_stream),
        ):
            incoming = MagicMock()
            incoming.content = "hi"
            await reload_chat.on_message(incoming)

        system = captured_call_kwargs.get("system", "")
        assert "one short question at a time" in system
        assert "apply_ops" not in system

    async def test_dossier_system_prompt_prefixed_with_document_state(self, reload_chat):
        """In dossier phase, system prompt is prefixed with [Current document (vN): ...] (AC4)."""
        msg_mock = _make_fake_cl_message()
        captured_call_kwargs = {}
        doc_mock = MagicMock()
        doc_mock.props = {"content": "# Section A\n\nBody.", "version": 3}

        def fake_stream(**kwargs):
            captured_call_kwargs.update(kwargs)
            return FakeStream(["OK"])

        with (
            patch("app.chat.cl.Message", return_value=msg_mock),
            patch(
                "app.chat.cl.user_session",
                _make_session_mock_with_history(dossier={"phase": "dossier"}, doc=doc_mock),
            ),
            patch("app.chat.client.messages.stream", side_effect=fake_stream),
        ):
            incoming = MagicMock()
            incoming.content = "edit"
            await reload_chat.on_message(incoming)

        system = captured_call_kwargs.get("system", "")
        assert system.startswith("[Current document (v3):\n# Section A\n\nBody.\n]\n\n")
        assert "apply_ops" in system

    async def test_tool_use_loop_calls_mcp_and_sends_result_back(self, reload_chat):
        """When Claude returns tool_use, MCP is called and result fed back to Claude."""
        tool_block = _make_fake_content_block(
            "tool_use",
            name="search_indicators",
            input={"query": "CO2"},
            id="toolu_001",
        )
        text_block = _make_fake_content_block("text", "Here are the results.")

        # First call: Claude requests a tool
        stream_with_tool = FakeStream(
            tokens=[],
            stop_reason="tool_use",
            content_blocks=[tool_block],
        )
        # Second call: Claude provides final answer
        stream_final = FakeStream(
            tokens=["Here", " are", " the", " results."],
            stop_reason="end_turn",
            content_blocks=[text_block],
        )

        call_count = 0

        def fake_stream(**kwargs):
            nonlocal call_count
            call_count += 1
            return stream_with_tool if call_count == 1 else stream_final

        # Fake MCP call_tool result
        fake_mcp_result = MagicMock()
        fake_mcp_result.isError = False
        fake_text_content = MagicMock()
        fake_text_content.text = '{"data": [{"id": "CO2_001"}]}'
        fake_mcp_result.content = [fake_text_content]

        fake_mcp_session = AsyncMock()
        fake_mcp_session.call_tool = AsyncMock(return_value=fake_mcp_result)

        tools = [{"name": "search_indicators", "description": "Search", "input_schema": {"type": "object"}}]
        msg_mock = _make_fake_cl_message()

        step_mock = AsyncMock()
        step_mock.__aenter__ = AsyncMock(return_value=step_mock)
        step_mock.__aexit__ = AsyncMock(return_value=False)
        step_mock.input = ""
        step_mock.output = ""

        with (
            patch("app.chat.cl.Message", return_value=msg_mock),
            patch(
                "app.chat.cl.user_session",
                _make_session_mock_with_history(mcp_session=fake_mcp_session, mcp_tools=tools),
            ),
            patch("app.chat.client.messages.stream", side_effect=fake_stream),
            patch("app.chat.cl.Step", return_value=step_mock),
        ):
            incoming = MagicMock()
            incoming.content = "Find CO2 indicators"
            await reload_chat.on_message(incoming)

        # MCP tool should have been called
        fake_mcp_session.call_tool.assert_awaited_once_with("search_indicators", arguments={"query": "CO2"})
        # Claude should have been called twice (once for tool_use, once for final)
        assert call_count == 2

    async def test_tool_result_appended_to_history_in_loop(self, reload_chat):
        """Tool results are appended to history before the follow-up Claude call."""
        tool_block = _make_fake_content_block(
            "tool_use",
            name="get_data",
            input={"database_id": "WB_WDI", "indicator": "CO2"},
            id="toolu_002",
        )
        text_block = _make_fake_content_block("text", "Data found.")

        stream_with_tool = FakeStream(tokens=[], stop_reason="tool_use", content_blocks=[tool_block])
        stream_final = FakeStream(tokens=["Data found."], stop_reason="end_turn", content_blocks=[text_block])

        call_count = 0
        captured_histories = []

        def fake_stream(**kwargs):
            nonlocal call_count
            call_count += 1
            captured_histories.append(list(kwargs.get("messages", [])))
            return stream_with_tool if call_count == 1 else stream_final

        fake_mcp_result = MagicMock()
        fake_mcp_result.isError = False
        fake_text = MagicMock()
        fake_text.text = "tool output text"
        fake_mcp_result.content = [fake_text]

        fake_mcp_session = AsyncMock()
        fake_mcp_session.call_tool = AsyncMock(return_value=fake_mcp_result)

        tools = [{"name": "get_data", "description": "Get data", "input_schema": {"type": "object"}}]
        msg_mock = _make_fake_cl_message()
        step_mock = AsyncMock()
        step_mock.__aenter__ = AsyncMock(return_value=step_mock)
        step_mock.__aexit__ = AsyncMock(return_value=False)
        step_mock.input = ""
        step_mock.output = ""

        with (
            patch("app.chat.cl.Message", return_value=msg_mock),
            patch(
                "app.chat.cl.user_session",
                _make_session_mock_with_history(mcp_session=fake_mcp_session, mcp_tools=tools),
            ),
            patch("app.chat.client.messages.stream", side_effect=fake_stream),
            patch("app.chat.cl.Step", return_value=step_mock),
        ):
            incoming = MagicMock()
            incoming.content = "Get WDI data"
            await reload_chat.on_message(incoming)

        # Second call should have more history items than the first
        assert len(captured_histories[1]) > len(captured_histories[0])
        # The second history should include a user turn with tool results
        second_call_last = captured_histories[1][-1]
        assert second_call_last["role"] == "user"
        assert isinstance(second_call_last["content"], list)
        assert second_call_last["content"][0]["type"] == "tool_result"

    async def test_mcp_unavailable_error_surfaced_gracefully(self, reload_chat):
        """When MCP session is None, tool output is an error message — not a crash."""
        tool_block = _make_fake_content_block(
            "tool_use",
            name="search_indicators",
            input={"query": "population"},
            id="toolu_003",
        )
        text_block = _make_fake_content_block("text", "MCP unavailable, sorry.")

        stream_with_tool = FakeStream(tokens=[], stop_reason="tool_use", content_blocks=[tool_block])
        stream_final = FakeStream(
            tokens=["MCP unavailable, sorry."], stop_reason="end_turn", content_blocks=[text_block]
        )

        call_count = 0

        def fake_stream(**kwargs):
            nonlocal call_count
            call_count += 1
            return stream_with_tool if call_count == 1 else stream_final

        tools = [{"name": "search_indicators", "description": "Search", "input_schema": {"type": "object"}}]
        msg_mock = _make_fake_cl_message()
        step_mock = AsyncMock()
        step_mock.__aenter__ = AsyncMock(return_value=step_mock)
        step_mock.__aexit__ = AsyncMock(return_value=False)
        step_mock.input = ""
        step_mock.output = ""

        # mcp_session is None — simulates unavailable MCP server
        with (
            patch("app.chat.cl.Message", return_value=msg_mock),
            patch("app.chat.cl.user_session", _make_session_mock_with_history(mcp_session=None, mcp_tools=tools)),
            patch("app.chat.client.messages.stream", side_effect=fake_stream),
            patch("app.chat.cl.Step", return_value=step_mock),
        ):
            incoming = MagicMock()
            incoming.content = "Find population data"
            await reload_chat.on_message(incoming)

        # Should still complete (2 Claude calls) without crashing
        assert call_count == 2
        msg_mock.update.assert_awaited_once()

    async def test_mcp_tool_error_passed_to_claude(self, reload_chat):
        """When MCP tool returns an error, the error text is sent to Claude as tool_result."""
        tool_block = _make_fake_content_block(
            "tool_use",
            name="get_data",
            input={"database_id": "BAD_DB", "indicator": "BAD_IND"},
            id="toolu_004",
        )
        text_block = _make_fake_content_block("text", "I could not retrieve that data.")

        stream_with_tool = FakeStream(tokens=[], stop_reason="tool_use", content_blocks=[tool_block])
        stream_final = FakeStream(
            tokens=["I could not retrieve that data."], stop_reason="end_turn", content_blocks=[text_block]
        )

        call_count = 0
        captured_second_messages = []

        def fake_stream(**kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 2:
                captured_second_messages.extend(kwargs.get("messages", []))
            return stream_with_tool if call_count == 1 else stream_final

        # MCP returns an error result
        fake_mcp_result = MagicMock()
        fake_mcp_result.isError = True
        fake_err_text = MagicMock()
        fake_err_text.text = "Database not found"
        fake_mcp_result.content = [fake_err_text]

        fake_mcp_session = AsyncMock()
        fake_mcp_session.call_tool = AsyncMock(return_value=fake_mcp_result)

        tools = [{"name": "get_data", "description": "Get data", "input_schema": {"type": "object"}}]
        msg_mock = _make_fake_cl_message()
        step_mock = AsyncMock()
        step_mock.__aenter__ = AsyncMock(return_value=step_mock)
        step_mock.__aexit__ = AsyncMock(return_value=False)
        step_mock.input = ""
        step_mock.output = ""

        with (
            patch("app.chat.cl.Message", return_value=msg_mock),
            patch(
                "app.chat.cl.user_session",
                _make_session_mock_with_history(mcp_session=fake_mcp_session, mcp_tools=tools),
            ),
            patch("app.chat.client.messages.stream", side_effect=fake_stream),
            patch("app.chat.cl.Step", return_value=step_mock),
        ):
            incoming = MagicMock()
            incoming.content = "Get bad data"
            await reload_chat.on_message(incoming)

        # The tool result content sent to Claude should contain the error text
        tool_result_turn = captured_second_messages[-1]
        assert tool_result_turn["role"] == "user"
        tool_result_content = tool_result_turn["content"][0]["content"]
        assert "Error" in tool_result_content
        assert "Database not found" in tool_result_content

    async def test_mcp_tools_to_anthropic_format(self, reload_chat):
        """_mcp_tools_to_anthropic converts MCP Tool objects to Anthropic tool dicts."""
        from app.chat import _mcp_tools_to_anthropic

        tool = MagicMock()
        tool.name = "search_indicators"
        tool.description = "Search for indicators"
        tool.inputSchema = {"type": "object", "properties": {"query": {"type": "string"}}}

        result = _mcp_tools_to_anthropic([tool])
        assert len(result) == 1
        assert result[0]["name"] == "search_indicators"
        assert result[0]["description"] == "Search for indicators"
        assert result[0]["input_schema"] == tool.inputSchema

    async def test_extract_tool_result_text_success(self, reload_chat):
        """_extract_tool_result_text joins text blocks from a successful MCP result."""
        from app.chat import _extract_tool_result_text

        result = MagicMock()
        result.isError = False
        block = MagicMock()
        block.text = '{"data": [1, 2, 3]}'
        result.content = [block]

        text = _extract_tool_result_text(result)
        assert text == '{"data": [1, 2, 3]}'

    async def test_extract_tool_result_text_error(self, reload_chat):
        """_extract_tool_result_text prefixes with 'Error:' when isError=True."""
        from app.chat import _extract_tool_result_text

        result = MagicMock()
        result.isError = True
        block = MagicMock()
        block.text = "Connection refused"
        result.content = [block]

        text = _extract_tool_result_text(result)
        assert text.startswith("Error:")
        assert "Connection refused" in text


class TestAgenticLoopIntegration:
    """AC1/AC2: Integration-level tests verifying full agentic loop history structure."""

    async def test_multi_tool_chain_produces_correct_history_structure(self, reload_chat):
        """AC1: A multi-step tool chain (search_indicators -> get_data) produces correct history."""
        search_block = _make_fake_content_block(
            "tool_use", name="search_indicators", input={"query": "CO2"}, id="toolu_search"
        )
        get_data_block = _make_fake_content_block(
            "tool_use", name="get_data", input={"database_id": "WB_WDI", "indicator": "CO2"}, id="toolu_getdata"
        )
        final_text_block = _make_fake_content_block("text", "Brazil's CO2 emissions are 500Mt.")

        # Step 1: Claude calls search_indicators
        stream_search = FakeStream(tokens=[], stop_reason="tool_use", content_blocks=[search_block])
        # Step 2: Claude calls get_data
        stream_getdata = FakeStream(tokens=[], stop_reason="tool_use", content_blocks=[get_data_block])
        # Step 3: Claude produces final answer
        stream_final = FakeStream(
            tokens=["Brazil's CO2 emissions are 500Mt."], stop_reason="end_turn", content_blocks=[final_text_block]
        )

        call_count = 0
        captured_histories = []

        def fake_stream(**kwargs):
            nonlocal call_count
            call_count += 1
            import copy

            captured_histories.append(copy.deepcopy(kwargs.get("messages", [])))
            if call_count == 1:
                return stream_search
            elif call_count == 2:
                return stream_getdata
            else:
                return stream_final

        # Fake MCP results for both calls
        fake_search_result = MagicMock()
        fake_search_result.isError = False
        fake_search_text = MagicMock()
        fake_search_text.text = '{"success": true, "data": [{"INDICATOR_ID": "CO2"}]}'
        fake_search_result.content = [fake_search_text]

        fake_data_result = MagicMock()
        fake_data_result.isError = False
        fake_data_text = MagicMock()
        fake_data_text.text = '{"success": true, "data": [{"VALUE": 500}]}'
        fake_data_result.content = [fake_data_text]

        fake_mcp_session = AsyncMock()
        call_tool_results = [fake_search_result, fake_data_result]
        fake_mcp_session.call_tool = AsyncMock(side_effect=call_tool_results)

        tools = [
            {"name": "search_indicators", "description": "Search", "input_schema": {"type": "object"}},
            {"name": "get_data", "description": "Get data", "input_schema": {"type": "object"}},
        ]
        msg_mock = _make_fake_cl_message()
        step_mock = AsyncMock()
        step_mock.__aenter__ = AsyncMock(return_value=step_mock)
        step_mock.__aexit__ = AsyncMock(return_value=False)
        step_mock.input = ""
        step_mock.output = ""

        with (
            patch("app.chat.cl.Message", return_value=msg_mock),
            patch(
                "app.chat.cl.user_session",
                _make_session_mock_with_history(mcp_session=fake_mcp_session, mcp_tools=tools),
            ),
            patch("app.chat.client.messages.stream", side_effect=fake_stream),
            patch("app.chat.cl.Step", return_value=step_mock),
        ):
            incoming = MagicMock()
            incoming.content = "What are CO2 emissions in Brazil?"
            await reload_chat.on_message(incoming)

        # 3 Claude calls: search tool, get_data tool, final text
        assert call_count == 3

        # Second call should have: user msg, assistant tool_use, user tool_result
        assert len(captured_histories[1]) == 3
        assert captured_histories[1][0]["role"] == "user"
        assert captured_histories[1][1]["role"] == "assistant"
        assert captured_histories[1][2]["role"] == "user"
        assert captured_histories[1][2]["content"][0]["type"] == "tool_result"

        # Third call should have 5 entries: user, asst(tool), user(result), asst(tool), user(result)
        assert len(captured_histories[2]) == 5
        assert captured_histories[2][3]["role"] == "assistant"
        assert captured_histories[2][4]["role"] == "user"
        assert captured_histories[2][4]["content"][0]["type"] == "tool_result"

    async def test_tool_result_content_blocks_correctly_formatted(self, reload_chat):
        """AC2: Tool results are correctly formatted as tool_result content blocks for Claude."""
        tool_block = _make_fake_content_block(
            "tool_use", name="search_indicators", input={"query": "GDP"}, id="toolu_fmt"
        )
        text_block = _make_fake_content_block("text", "Done.")

        stream_tool = FakeStream(tokens=[], stop_reason="tool_use", content_blocks=[tool_block])
        stream_final = FakeStream(tokens=["Done."], stop_reason="end_turn", content_blocks=[text_block])

        call_count = 0
        captured_histories = []

        def fake_stream(**kwargs):
            nonlocal call_count
            call_count += 1
            import copy

            captured_histories.append(copy.deepcopy(kwargs.get("messages", [])))
            return stream_tool if call_count == 1 else stream_final

        fake_mcp_result = MagicMock()
        fake_mcp_result.isError = False
        fake_text = MagicMock()
        fake_text.text = '{"success": true, "data": [{"id": "GDP_001"}]}'
        fake_mcp_result.content = [fake_text]

        fake_mcp_session = AsyncMock()
        fake_mcp_session.call_tool = AsyncMock(return_value=fake_mcp_result)

        tools = [{"name": "search_indicators", "description": "Search", "input_schema": {"type": "object"}}]
        msg_mock = _make_fake_cl_message()
        step_mock = AsyncMock()
        step_mock.__aenter__ = AsyncMock(return_value=step_mock)
        step_mock.__aexit__ = AsyncMock(return_value=False)
        step_mock.input = ""
        step_mock.output = ""

        with (
            patch("app.chat.cl.Message", return_value=msg_mock),
            patch(
                "app.chat.cl.user_session",
                _make_session_mock_with_history(mcp_session=fake_mcp_session, mcp_tools=tools),
            ),
            patch("app.chat.client.messages.stream", side_effect=fake_stream),
            patch("app.chat.cl.Step", return_value=step_mock),
        ):
            incoming = MagicMock()
            incoming.content = "Search GDP"
            await reload_chat.on_message(incoming)

        # Verify tool_result block structure in the second call
        tool_result_turn = captured_histories[1][-1]
        assert tool_result_turn["role"] == "user"
        tool_result_block = tool_result_turn["content"][0]
        assert tool_result_block["type"] == "tool_result"
        assert tool_result_block["tool_use_id"] == "toolu_fmt"
        assert "content" in tool_result_block
        assert '{"success": true' in tool_result_block["content"]

    async def test_history_includes_text_and_tool_use_blocks_after_chain(self, reload_chat):
        """AC1: After a multi-step chain, history includes both text and tool_use content blocks."""
        # Claude first returns a text + tool_use in one response
        text_thinking = _make_fake_content_block("text", "Let me search for that.")
        tool_block = _make_fake_content_block(
            "tool_use", name="search_indicators", input={"query": "population"}, id="toolu_mixed"
        )
        final_block = _make_fake_content_block("text", "Here is the data.")

        stream_mixed = FakeStream(
            tokens=["Let me search for that."],
            stop_reason="tool_use",
            content_blocks=[text_thinking, tool_block],
        )
        stream_final = FakeStream(tokens=["Here is the data."], stop_reason="end_turn", content_blocks=[final_block])

        call_count = 0
        captured_histories = []

        def fake_stream(**kwargs):
            nonlocal call_count
            call_count += 1
            import copy

            captured_histories.append(copy.deepcopy(kwargs.get("messages", [])))
            return stream_mixed if call_count == 1 else stream_final

        fake_mcp_result = MagicMock()
        fake_mcp_result.isError = False
        fake_text = MagicMock()
        fake_text.text = "population data"
        fake_mcp_result.content = [fake_text]

        fake_mcp_session = AsyncMock()
        fake_mcp_session.call_tool = AsyncMock(return_value=fake_mcp_result)

        tools = [{"name": "search_indicators", "description": "Search", "input_schema": {"type": "object"}}]
        msg_mock = _make_fake_cl_message()
        step_mock = AsyncMock()
        step_mock.__aenter__ = AsyncMock(return_value=step_mock)
        step_mock.__aexit__ = AsyncMock(return_value=False)
        step_mock.input = ""
        step_mock.output = ""

        with (
            patch("app.chat.cl.Message", return_value=msg_mock),
            patch(
                "app.chat.cl.user_session",
                _make_session_mock_with_history(mcp_session=fake_mcp_session, mcp_tools=tools),
            ),
            patch("app.chat.client.messages.stream", side_effect=fake_stream),
            patch("app.chat.cl.Step", return_value=step_mock),
        ):
            incoming = MagicMock()
            incoming.content = "Find population data"
            await reload_chat.on_message(incoming)

        # The assistant message in the second call's history should have mixed content blocks
        assistant_msg = captured_histories[1][1]
        assert assistant_msg["role"] == "assistant"
        assert isinstance(assistant_msg["content"], list)
        # Should contain both text and tool_use block types (from model_dump)
        block_types = {b.get("type") for b in assistant_msg["content"] if isinstance(b, dict)}
        assert "text" in block_types or "tool_use" in block_types


class TestNarrativeGeneration:
    """AC1/AC2/AC3/AC4: System prompt instructs narrative response generation."""

    def test_system_prompt_instructs_trend_narration(self):
        """AC1: System prompt must instruct trend direction narration from time-series data."""
        from app.prompts import SYSTEM_PROMPT

        # Must instruct on TIME_PERIOD-based trend analysis
        prompt_lower = SYSTEM_PROMPT.lower()
        assert "time_period" in SYSTEM_PROMPT or "time series" in prompt_lower or "trend" in prompt_lower
        # Must include trend direction vocabulary
        assert any(
            phrase in SYSTEM_PROMPT
            for phrase in ["rising", "falling", "stable", "accelerating", "decelerating", "rose", "fell", "flat"]
        )

    def test_system_prompt_instructs_multi_country_comparison(self):
        """AC2: System prompt must instruct comparison narration for multi-country data."""
        from app.prompts import SYSTEM_PROMPT

        prompt_lower = SYSTEM_PROMPT.lower()
        assert any(
            phrase in prompt_lower
            for phrase in ["multi-country", "multiple countries", "ref_area", "comparison", "compare"]
        )

    def test_system_prompt_instructs_no_data_found_response(self):
        """AC4: System prompt must instruct 'No relevant data found' response for empty results."""
        from app.prompts import SYSTEM_PROMPT

        assert "No relevant data found" in SYSTEM_PROMPT or "no relevant data" in SYSTEM_PROMPT.lower()

    def test_system_prompt_preserves_grounding_constraints(self):
        """AC1/AC2/AC3/AC4: Grounding constraints (no causal claims, no forecasts) must remain."""
        from app.prompts import SYSTEM_PROMPT

        prompt_lower = SYSTEM_PROMPT.lower()
        # No causal claims
        assert "causal" in prompt_lower or "caused" in prompt_lower
        # No forecasts
        assert "forecast" in prompt_lower or "prediction" in prompt_lower

    def test_system_prompt_instructs_data_provenance(self):
        """AC7: System prompt tells LLM that Data Sources is appended automatically."""
        from app.prompts import SYSTEM_PROMPT

        assert "Data Sources" in SYSTEM_PROMPT
        assert "appended automatically" in SYSTEM_PROMPT
        assert "[1]" not in SYSTEM_PROMPT

    def test_system_prompt_instructs_gap_flagging(self):
        """AC3: System prompt must instruct flagging of missing years/gaps in data."""
        from app.prompts import SYSTEM_PROMPT

        prompt_lower = SYSTEM_PROMPT.lower()
        assert any(phrase in prompt_lower for phrase in ["gap", "missing", "not available", "data is not available"])


class TestConfig:
    def test_config_loads_conversation_history_limit(self, monkeypatch):
        """CONVERSATION_HISTORY_LIMIT env var is read correctly."""
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
        monkeypatch.setenv("DATABASE_URL", "postgresql://user:pass@localhost:5432/db")
        monkeypatch.setenv("CONVERSATION_HISTORY_LIMIT", "5")

        from app.config import Settings

        settings = Settings(_env_file=None)
        assert settings.conversation_history_limit == 5

    def test_config_default_history_limit_is_10(self, monkeypatch):
        """Default conversation_history_limit is 10 when env var is not set."""
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
        monkeypatch.setenv("DATABASE_URL", "postgresql://user:pass@localhost:5432/db")
        monkeypatch.delenv("CONVERSATION_HISTORY_LIMIT", raising=False)

        from app.config import Settings

        settings = Settings(_env_file=None)
        assert settings.conversation_history_limit == 10

    def test_config_claude_model_default(self, monkeypatch):
        """Default claude_model is 'claude-haiku-4-5'."""
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
        monkeypatch.setenv("DATABASE_URL", "postgresql://user:pass@localhost:5432/db")
        monkeypatch.delenv("CLAUDE_MODEL", raising=False)

        from app.config import Settings

        s = Settings(_env_file=None)
        assert s.claude_model == "claude-haiku-4-5"

    def test_config_claude_model_from_env(self, monkeypatch):
        """CLAUDE_MODEL env var overrides the default."""
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
        monkeypatch.setenv("DATABASE_URL", "postgresql://user:pass@localhost:5432/db")
        monkeypatch.setenv("CLAUDE_MODEL", "claude-sonnet-4-5-20250514")

        from app.config import Settings

        s = Settings(_env_file=None)
        assert s.claude_model == "claude-sonnet-4-5-20250514"

    def test_config_claude_max_tokens_default(self, monkeypatch):
        """Default claude_max_tokens is 4096."""
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
        monkeypatch.setenv("DATABASE_URL", "postgresql://user:pass@localhost:5432/db")
        monkeypatch.delenv("CLAUDE_MAX_TOKENS", raising=False)

        from app.config import Settings

        s = Settings(_env_file=None)
        assert s.claude_max_tokens == 4096

    def test_config_claude_max_tokens_from_env(self, monkeypatch):
        """CLAUDE_MAX_TOKENS env var overrides the default."""
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
        monkeypatch.setenv("DATABASE_URL", "postgresql://user:pass@localhost:5432/db")
        monkeypatch.setenv("CLAUDE_MAX_TOKENS", "8192")

        from app.config import Settings

        s = Settings(_env_file=None)
        assert s.claude_max_tokens == 8192

    def test_config_tool_result_max_chars_default(self, monkeypatch):
        """Default tool_result_max_chars is 50000."""
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
        monkeypatch.setenv("DATABASE_URL", "postgresql://user:pass@localhost:5432/db")
        monkeypatch.delenv("TOOL_RESULT_MAX_CHARS", raising=False)

        from app.config import Settings

        s = Settings(_env_file=None)
        assert s.tool_result_max_chars == 50000

    def test_config_tool_result_max_chars_from_env(self, monkeypatch):
        """TOOL_RESULT_MAX_CHARS env var overrides the default."""
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
        monkeypatch.setenv("DATABASE_URL", "postgresql://user:pass@localhost:5432/db")
        monkeypatch.setenv("TOOL_RESULT_MAX_CHARS", "10000")

        from app.config import Settings

        s = Settings(_env_file=None)
        assert s.tool_result_max_chars == 10000


class TestModelDumpExcludeNone:
    """Verify model_dump(exclude_none=True) is used for assistant content blocks."""

    async def test_assistant_content_blocks_exclude_none_fields(self, reload_chat):
        """model_dump must be called with exclude_none=True to avoid sending null fields to API."""
        tool_block = _make_fake_content_block(
            "tool_use", name="search_indicators", input={"query": "CO2"}, id="toolu_001"
        )
        text_block = _make_fake_content_block("text", "Results.")

        stream_tool = FakeStream(tokens=[], stop_reason="tool_use", content_blocks=[tool_block])
        stream_final = FakeStream(tokens=["Results."], stop_reason="end_turn", content_blocks=[text_block])

        call_count = 0
        captured_histories = []

        def fake_stream(**kwargs):
            nonlocal call_count
            call_count += 1
            import copy

            captured_histories.append(copy.deepcopy(kwargs.get("messages", [])))
            return stream_tool if call_count == 1 else stream_final

        fake_mcp_result = MagicMock()
        fake_mcp_result.isError = False
        fake_text = MagicMock()
        fake_text.text = "data"
        fake_mcp_result.content = [fake_text]

        fake_mcp_session = AsyncMock()
        fake_mcp_session.call_tool = AsyncMock(return_value=fake_mcp_result)

        tools = [{"name": "search_indicators", "description": "Search", "input_schema": {"type": "object"}}]
        msg_mock = _make_fake_cl_message()
        step_mock = AsyncMock()
        step_mock.__aenter__ = AsyncMock(return_value=step_mock)
        step_mock.__aexit__ = AsyncMock(return_value=False)
        step_mock.input = ""
        step_mock.output = ""

        with (
            patch("app.chat.cl.Message", return_value=msg_mock),
            patch(
                "app.chat.cl.user_session",
                _make_session_mock_with_history(mcp_session=fake_mcp_session, mcp_tools=tools),
            ),
            patch("app.chat.client.messages.stream", side_effect=fake_stream),
            patch("app.chat.cl.Step", return_value=step_mock),
        ):
            incoming = MagicMock()
            incoming.content = "Search CO2"
            await reload_chat.on_message(incoming)

        # The assistant content blocks in the second call must have no None values
        assistant_msg = captured_histories[1][1]
        assert assistant_msg["role"] == "assistant"
        for block in assistant_msg["content"]:
            for value in block.values():
                assert value is not None, f"Found None value in block: {block}"


class TestToolResultTruncation:
    """Verify large tool results are truncated before feeding back to Claude."""

    async def test_large_tool_result_is_truncated(self, reload_chat):
        """Tool results exceeding max chars should be truncated with a marker."""
        from app.chat import _extract_tool_result_text

        large_text = "x" * 60000
        result = MagicMock()
        result.isError = False
        block = MagicMock()
        block.text = large_text
        result.content = [block]

        text = _extract_tool_result_text(result)
        assert len(text) < 60000
        assert "[truncated]" in text.lower() or "truncated" in text.lower()

    async def test_small_tool_result_not_truncated(self, reload_chat):
        """Tool results within limit should not be truncated."""
        from app.chat import _extract_tool_result_text

        small_text = '{"data": [1, 2, 3]}'
        result = MagicMock()
        result.isError = False
        block = MagicMock()
        block.text = small_text
        result.content = [block]

        text = _extract_tool_result_text(result)
        assert text == small_text


def _make_fake_mcp_tool():
    """Build a fake MCP tool for auto-connect tests."""
    from mcp.types import Tool

    tool = MagicMock(spec=Tool)
    tool.name = "search_indicators"
    tool.description = "Search"
    tool.inputSchema = {"type": "object", "properties": {}}
    return tool


@contextlib.asynccontextmanager
async def _fake_streamablehttp_client(url, **kwargs):
    """Fake streamablehttp_client that yields mock read/write streams."""
    yield (MagicMock(), MagicMock(), lambda: None)


class TestMcpAutoConnect:
    """Tests for MCP auto-connection on chat start."""

    async def test_on_chat_start_auto_connects_mcp(self, reload_chat):
        """on_chat_start should auto-connect to MCP and store session/tools."""
        fake_tool = _make_fake_mcp_tool()
        fake_session = AsyncMock()
        list_result = MagicMock()
        list_result.tools = [fake_tool]
        fake_session.list_tools = AsyncMock(return_value=list_result)
        fake_session.initialize = AsyncMock()

        stored = {}
        msg_mock = AsyncMock()
        msg_mock.send = AsyncMock()

        with (
            patch("app.chat.streamablehttp_client", _fake_streamablehttp_client),
            patch("app.chat.ClientSession", return_value=fake_session),
            patch("app.chat.cl.user_session") as session_mock,
            patch("app.chat.cl.Message", return_value=msg_mock),
        ):
            session_mock.set.side_effect = lambda k, v: stored.update({k: v})
            # Make ClientSession work as async context manager
            fake_session.__aenter__ = AsyncMock(return_value=fake_session)
            fake_session.__aexit__ = AsyncMock(return_value=False)

            await reload_chat.on_chat_start()

        assert stored.get("mcp_session") is fake_session
        assert len(stored.get("mcp_tools", [])) == 1
        assert stored["mcp_tools"][0]["name"] == "search_indicators"
        fake_session.initialize.assert_awaited_once()

    async def test_on_chat_start_auto_connect_failure_graceful(self, reload_chat):
        """If MCP auto-connect fails, chat start still completes without tools."""
        stored = {}
        msg_mock = AsyncMock()
        msg_mock.send = AsyncMock()

        @contextlib.asynccontextmanager
        async def failing_client(url, **kwargs):
            raise ConnectionError("MCP server not running")
            yield  # pragma: no cover

        with (
            patch("app.chat.streamablehttp_client", failing_client),
            patch("app.chat.cl.user_session") as session_mock,
            patch("app.chat.cl.Message", return_value=msg_mock),
        ):
            session_mock.set.side_effect = lambda k, v: stored.update({k: v})

            # Should not raise
            await reload_chat.on_chat_start()

        # Session should be None, tools should be empty
        assert stored.get("mcp_session") is None
        assert stored.get("mcp_tools") == []
        # Welcome message should still be sent
        msg_mock.send.assert_awaited_once()

    async def test_on_chat_end_closes_exit_stack(self, reload_chat):
        """on_chat_end should close the AsyncExitStack to clean up MCP connection."""
        mock_stack = AsyncMock()

        with patch("app.chat.cl.user_session") as session_mock:
            session_mock.get.return_value = mock_stack

            await reload_chat.on_chat_end()

        mock_stack.aclose.assert_awaited_once()

    async def test_on_chat_end_handles_no_stack(self, reload_chat):
        """on_chat_end should handle gracefully when no exit stack exists."""
        with patch("app.chat.cl.user_session") as session_mock:
            session_mock.get.return_value = None

            # Should not raise
            await reload_chat.on_chat_end()


class TestMultiTurnConversation:
    """AC1/AC2: System prompt instructs multi-turn context resolution."""

    def test_system_prompt_instructs_coreference_resolution(self):
        """AC1: Prompt must instruct resolving pronouns from previous turn context."""
        from app.prompts import SYSTEM_PROMPT

        assert any(
            phrase in SYSTEM_PROMPT.lower() for phrase in ["follow-up", "pronoun", "previous", "context", "infer"]
        )

    def test_system_prompt_instructs_no_unnecessary_clarification(self):
        """AC1: When context is unambiguous, Claude must not ask for clarification."""
        from app.prompts import SYSTEM_PROMPT

        assert "clarif" in SYSTEM_PROMPT.lower() or "unambiguous" in SYSTEM_PROMPT.lower()

    def test_system_prompt_instructs_indicator_reuse_on_comparison(self):
        """AC1: On country comparison follow-up, reuse the same indicator."""
        from app.prompts import SYSTEM_PROMPT

        assert any(
            phrase in SYSTEM_PROMPT.lower() for phrase in ["reuse", "same indicator", "previous turn", "comparison"]
        )

    async def test_multi_turn_history_passed_to_claude(self, reload_chat):
        """AC2: Full conversation history (2+ turns) is sent to Claude on follow-up."""
        import copy

        tokens = ["Here is the comparison."]
        msg_mock = _make_fake_cl_message()
        captured_messages = []

        def fake_stream(**kwargs):
            captured_messages.extend(copy.deepcopy(kwargs.get("messages", [])))
            return FakeStream(tokens)

        existing_history = [
            {"role": "user", "content": "What are CO2 emissions in Brazil?"},
            {"role": "assistant", "content": "Brazil's CO2 emissions are 500Mt. (Source: WDI, 2022)"},
        ]

        with (
            patch("app.chat.cl.Message", return_value=msg_mock),
            patch("app.chat.cl.user_session") as session_mock,
            patch("app.chat.client.messages.stream", side_effect=fake_stream),
        ):
            session_mock.get.return_value = existing_history.copy()
            session_mock.set = MagicMock()

            incoming = MagicMock()
            incoming.content = "How does that compare to Argentina?"

            await reload_chat.on_message(incoming)

        # History must include prior turns plus the new follow-up user message
        assert len(captured_messages) >= 3
        assert captured_messages[-1]["content"] == "How does that compare to Argentina?"
        # Prior assistant turn must be included
        roles = [m["role"] for m in captured_messages]
        assert "assistant" in roles


class TestConversationResume:
    """Tests for on_chat_resume handler (AC1, AC2)."""

    async def test_on_chat_resume_restores_user_and_assistant_history(self, reload_chat):
        """Test 1: on_chat_resume restores user/assistant history from thread steps."""
        thread = {
            "steps": [
                {"type": "user_message", "output": "What is the GDP of Brazil?"},
                {"type": "assistant_message", "output": "Brazil's GDP is high."},
                {"type": "user_message", "output": "And Argentina?"},
                {"type": "assistant_message", "output": "Argentina's GDP is moderate."},
            ]
        }

        stored = {}

        @contextlib.asynccontextmanager
        async def fake_mcp_client(url, **kwargs):
            raise ConnectionError("MCP not available")
            yield  # pragma: no cover

        with (
            patch("app.chat.streamablehttp_client", fake_mcp_client),
            patch("app.chat.cl.user_session") as session_mock,
        ):
            session_mock.set.side_effect = lambda k, v: stored.update({k: v})
            await reload_chat.on_chat_resume(thread)

        history = stored.get("history", [])
        assert len(history) == 4
        assert history[0] == {"role": "user", "content": "What is the GDP of Brazil?"}
        assert history[1] == {"role": "assistant", "content": "Brazil's GDP is high."}
        assert history[2] == {"role": "user", "content": "And Argentina?"}
        assert history[3] == {"role": "assistant", "content": "Argentina's GDP is moderate."}

    async def test_on_chat_resume_filters_steps_with_no_output(self, reload_chat):
        """Test 2: on_chat_resume filters out steps with no output (tool steps, empty steps)."""
        thread = {
            "steps": [
                {"type": "user_message", "output": "Hello"},
                {"type": "tool", "output": ""},  # empty output — should be skipped
                {"type": "tool", "output": None},  # None output — should be skipped
                {"type": "assistant_message", "output": ""},  # empty — should be skipped
                {"type": "assistant_message", "output": "World!"},
            ]
        }

        stored = {}

        @contextlib.asynccontextmanager
        async def fake_mcp_client(url, **kwargs):
            raise ConnectionError("MCP not available")
            yield  # pragma: no cover

        with (
            patch("app.chat.streamablehttp_client", fake_mcp_client),
            patch("app.chat.cl.user_session") as session_mock,
        ):
            session_mock.set.side_effect = lambda k, v: stored.update({k: v})
            await reload_chat.on_chat_resume(thread)

        history = stored.get("history", [])
        assert len(history) == 2
        assert history[0] == {"role": "user", "content": "Hello"}
        assert history[1] == {"role": "assistant", "content": "World!"}

    async def test_on_chat_resume_trims_history_to_limit(self, reload_chat):
        """Test 3: on_chat_resume trims history to CONVERSATION_HISTORY_LIMIT."""
        # Create 20 steps (10 user + 10 assistant)
        steps = []
        for i in range(10):
            steps.append({"type": "user_message", "output": f"User message {i}"})
            steps.append({"type": "assistant_message", "output": f"Assistant message {i}"})

        thread = {"steps": steps}
        stored = {}

        @contextlib.asynccontextmanager
        async def fake_mcp_client(url, **kwargs):
            raise ConnectionError("MCP not available")
            yield  # pragma: no cover

        with (
            patch("app.chat.streamablehttp_client", fake_mcp_client),
            patch("app.chat.cl.user_session") as session_mock,
            patch("app.chat.settings") as settings_mock,
        ):
            settings_mock.conversation_history_limit = 4
            settings_mock.mcp_server_url = "http://localhost:8001"
            session_mock.set.side_effect = lambda k, v: stored.update({k: v})
            await reload_chat.on_chat_resume(thread)

        history = stored.get("history", [])
        assert len(history) == 4
        # Should keep the last 4 messages
        assert history[0]["content"] == "User message 8"
        assert history[1]["content"] == "Assistant message 8"
        assert history[2]["content"] == "User message 9"
        assert history[3]["content"] == "Assistant message 9"

    async def test_on_chat_resume_with_empty_steps_results_in_empty_history(self, reload_chat):
        """Test 4: on_chat_resume with empty steps results in empty history."""
        thread = {"steps": []}
        stored = {}

        @contextlib.asynccontextmanager
        async def fake_mcp_client(url, **kwargs):
            raise ConnectionError("MCP not available")
            yield  # pragma: no cover

        with (
            patch("app.chat.streamablehttp_client", fake_mcp_client),
            patch("app.chat.cl.user_session") as session_mock,
        ):
            session_mock.set.side_effect = lambda k, v: stored.update({k: v})
            await reload_chat.on_chat_resume(thread)

        history = stored.get("history", [])
        assert history == []

    async def test_on_chat_resume_reconnects_mcp_session(self, reload_chat):
        """Test 5: on_chat_resume reconnects MCP session successfully."""
        thread = {"steps": []}
        stored = {}

        fake_tool = MagicMock()
        fake_tool.name = "search_indicators"
        fake_tool.description = "Search"
        fake_tool.inputSchema = {"type": "object", "properties": {}}

        fake_session = AsyncMock()
        list_result = MagicMock()
        list_result.tools = [fake_tool]
        fake_session.list_tools = AsyncMock(return_value=list_result)
        fake_session.initialize = AsyncMock()
        fake_session.__aenter__ = AsyncMock(return_value=fake_session)
        fake_session.__aexit__ = AsyncMock(return_value=False)

        with (
            patch("app.chat.streamablehttp_client", _fake_streamablehttp_client),
            patch("app.chat.ClientSession", return_value=fake_session),
            patch("app.chat.cl.user_session") as session_mock,
        ):
            session_mock.set.side_effect = lambda k, v: stored.update({k: v})
            await reload_chat.on_chat_resume(thread)

        assert stored.get("mcp_session") is fake_session
        assert len(stored.get("mcp_tools", [])) == 1
        assert stored["mcp_tools"][0]["name"] == "search_indicators"

    async def test_on_chat_resume_handles_mcp_failure_gracefully(self, reload_chat):
        """Test 5 (failure case): on_chat_resume handles MCP reconnect failure gracefully."""
        thread = {"steps": [{"type": "user_message", "output": "Hello"}]}
        stored = {}

        @contextlib.asynccontextmanager
        async def failing_client(url, **kwargs):
            raise ConnectionError("MCP server not running")
            yield  # pragma: no cover

        with (
            patch("app.chat.streamablehttp_client", failing_client),
            patch("app.chat.cl.user_session") as session_mock,
        ):
            session_mock.set.side_effect = lambda k, v: stored.update({k: v})
            # Should not raise
            await reload_chat.on_chat_resume(thread)

        # History should be restored even if MCP fails
        history = stored.get("history", [])
        assert len(history) == 1
        assert history[0] == {"role": "user", "content": "Hello"}
        # MCP session should be None
        assert stored.get("mcp_session") is None

    async def test_on_chat_resume_closes_existing_stack(self, reload_chat):
        """Test 7: on_chat_resume acloses any existing AsyncExitStack before reconnecting."""
        thread = {"steps": []}
        stored = {}

        existing_stack = AsyncMock()
        existing_stack.aclose = AsyncMock()

        with (
            patch("app.chat.streamablehttp_client", _fake_streamablehttp_client),
            patch("app.chat.ClientSession", return_value=AsyncMock()),
            patch("app.chat.cl.user_session") as session_mock,
        ):
            session_mock.get.side_effect = lambda k, default=None: existing_stack if k == "mcp_exit_stack" else default
            session_mock.set.side_effect = lambda k, v: stored.update({k: v})
            await reload_chat.on_chat_resume(thread)

        existing_stack.aclose.assert_awaited_once()

    async def test_on_chat_resume_handles_existing_stack_aclose_failure(self, reload_chat):
        """Test 8: on_chat_resume continues normally even if existing stack.aclose() raises."""
        thread = {"steps": [{"type": "user_message", "output": "Hi"}]}
        stored = {}

        failing_stack = AsyncMock()
        failing_stack.aclose = AsyncMock(side_effect=RuntimeError("already closed"))

        with (
            patch("app.chat.streamablehttp_client", _fake_streamablehttp_client),
            patch("app.chat.ClientSession", return_value=AsyncMock()),
            patch("app.chat.cl.user_session") as session_mock,
        ):
            session_mock.get.side_effect = lambda k, default=None: failing_stack if k == "mcp_exit_stack" else default
            session_mock.set.side_effect = lambda k, v: stored.update({k: v})
            # Must not raise despite aclose() failure
            await reload_chat.on_chat_resume(thread)

        failing_stack.aclose.assert_awaited_once()
        history = stored.get("history", [])
        assert history[0] == {"role": "user", "content": "Hi"}

    async def test_on_chat_resume_restores_dossier_phase_when_propose_structure_seen(self, reload_chat):
        """Resume restores dossier phase and auto-reveals the canvas when
        propose_structure appears in thread steps."""
        thread = {
            "steps": [
                {"type": "user_message", "output": "I want to investigate deforestation"},
                {"type": "assistant_message", "output": "Your dossier is ready."},
                {"name": "🔧 propose_structure", "type": "tool", "output": '{"status":"ok"}'},
            ]
        }
        stored: dict = {}

        with (
            patch("app.chat.streamablehttp_client", _fake_streamablehttp_client),
            patch("app.chat.ClientSession", return_value=AsyncMock()),
            patch("app.chat.cl.user_session") as session_mock,
            patch("app.chat.reveal_dossier_canvas", new=AsyncMock()) as reveal_mock,
        ):
            session_mock.get.side_effect = lambda k, default=None: stored.get(k, default)
            session_mock.set.side_effect = lambda k, v: stored.update({k: v})
            await reload_chat.on_chat_resume(thread)

        assert stored["dossier"]["phase"] == "dossier"
        reveal_mock.assert_awaited_once()

    async def test_on_chat_resume_investigating_phase_without_propose_structure(self, reload_chat):
        """Resume keeps investigating phase and does not auto-reveal when propose_structure is absent."""
        thread = {
            "steps": [
                {"type": "user_message", "output": "What topic?"},
                {"type": "assistant_message", "output": "Tell me more."},
            ]
        }
        stored: dict = {}

        with (
            patch("app.chat.streamablehttp_client", _fake_streamablehttp_client),
            patch("app.chat.ClientSession", return_value=AsyncMock()),
            patch("app.chat.cl.user_session") as session_mock,
            patch("app.chat.reveal_dossier_canvas", new=AsyncMock()) as reveal_mock,
        ):
            session_mock.get.side_effect = lambda k, default=None: stored.get(k, default)
            session_mock.set.side_effect = lambda k, v: stored.update({k: v})
            await reload_chat.on_chat_resume(thread)

        assert stored["dossier"]["phase"] == "investigating"
        reveal_mock.assert_not_called()

    async def test_on_chat_resume_ignores_loose_propose_structure_mentions(self, reload_chat):
        """P1 regression: a non-tool step or differently-named tool that merely
        contains 'propose_structure' must NOT flip resume into dossier phase."""
        thread = {
            "steps": [
                # Assistant prose mentioning the tool — not a tool step.
                {"type": "assistant_message", "output": "I'll call propose_structure next."},
                # A different (future) tool whose name only contains the substring.
                {"name": "🔧 propose_structure_v2", "type": "tool", "output": "{}"},
            ]
        }
        stored: dict = {}

        with (
            patch("app.chat.streamablehttp_client", _fake_streamablehttp_client),
            patch("app.chat.ClientSession", return_value=AsyncMock()),
            patch("app.chat.cl.user_session") as session_mock,
            patch("app.chat.reveal_dossier_canvas", new=AsyncMock()) as reveal_mock,
        ):
            session_mock.get.side_effect = lambda k, default=None: stored.get(k, default)
            session_mock.set.side_effect = lambda k, v: stored.update({k: v})
            await reload_chat.on_chat_resume(thread)

        assert stored["dossier"]["phase"] == "investigating"
        reveal_mock.assert_not_called()


_INVESTIGATION_KEYS = (
    "topic_definition",
    "geography_scope",
    "time_range",
    "target_audience",
    "data_sources_validation",
    "key_stats_capture",
    "narrative_structure",
    "case_studies",
    "story_pitches",
    "methodology",
)


class TestInvestigationSessionState:
    """Story 11.1: investigation checklist state, helper, and snapshot formatting."""

    async def test_on_chat_start_initializes_investigation_state(self, reload_chat):
        """AC1: on_chat_start seeds the 10-item investigation dict before sending welcome."""
        stored = {}

        @contextlib.asynccontextmanager
        async def failing_client(url, **kwargs):
            raise ConnectionError("no MCP")
            yield  # pragma: no cover

        with (
            patch("app.chat.streamablehttp_client", failing_client),
            patch("app.chat.cl.user_session") as session_mock,
            patch("app.chat.cl.Message") as msg_cls,
        ):
            session_mock.set.side_effect = lambda k, v: stored.update({k: v})
            session_mock.get.side_effect = lambda k, default=None: stored.get(k, default)
            msg_cls.return_value.send = AsyncMock()
            await reload_chat.on_chat_start()

        investigation = stored.get("investigation")
        assert isinstance(investigation, dict)
        assert tuple(investigation.keys()) == _INVESTIGATION_KEYS
        for entry in investigation.values():
            assert entry == {"done": False, "value": None}

    async def test_on_chat_resume_initializes_investigation_state(self, reload_chat):
        """AC2: on_chat_resume re-seeds the 10-item investigation dict (fresh, not persisted)."""
        stored = {}

        @contextlib.asynccontextmanager
        async def failing_client(url, **kwargs):
            raise ConnectionError("no MCP")
            yield  # pragma: no cover

        with (
            patch("app.chat.streamablehttp_client", failing_client),
            patch("app.chat.cl.user_session") as session_mock,
        ):
            session_mock.set.side_effect = lambda k, v: stored.update({k: v})
            session_mock.get.side_effect = lambda k, default=None: stored.get(k, default)
            await reload_chat.on_chat_resume({"steps": []})

        investigation = stored.get("investigation")
        assert isinstance(investigation, dict)
        assert tuple(investigation.keys()) == _INVESTIGATION_KEYS
        for entry in investigation.values():
            assert entry == {"done": False, "value": None}

    async def test_update_investigation_item_marks_done_and_returns_ok(self, reload_chat):
        """AC3: known item_id mutates state and returns the contract dict."""
        store = {"investigation": reload_chat._empty_investigation_state()}
        with patch("app.chat.cl.user_session") as session_mock:
            session_mock.get.side_effect = lambda k, default=None: store.get(k, default)
            session_mock.set.side_effect = lambda k, v: store.update({k: v})
            result = reload_chat.update_investigation_item("topic_definition", "Climate adaptation in NE Brazil")

        assert result == {
            "status": "ok",
            "item": "topic_definition",
            "items_done": 1,
            "phase_gate_reached": False,
        }
        assert store["investigation"]["topic_definition"] == {
            "done": True,
            "value": "Climate adaptation in NE Brazil",
        }

    async def test_update_investigation_item_is_idempotent(self, reload_chat):
        """AC3: calling twice for the same item still reports items_done == 1."""
        store = {"investigation": reload_chat._empty_investigation_state()}
        with patch("app.chat.cl.user_session") as session_mock:
            session_mock.get.side_effect = lambda k, default=None: store.get(k, default)
            session_mock.set.side_effect = lambda k, v: store.update({k: v})
            reload_chat.update_investigation_item("topic_definition", "v1")
            result = reload_chat.update_investigation_item("topic_definition", "v2")

        assert result["items_done"] == 1
        # Latest write wins
        assert store["investigation"]["topic_definition"]["value"] == "v2"

    async def test_update_investigation_item_counts_done_items(self, reload_chat):
        """AC3: items_done reflects the count of done == True items, not call count."""
        store = {"investigation": reload_chat._empty_investigation_state()}
        with patch("app.chat.cl.user_session") as session_mock:
            session_mock.get.side_effect = lambda k, default=None: store.get(k, default)
            session_mock.set.side_effect = lambda k, v: store.update({k: v})
            reload_chat.update_investigation_item("topic_definition", "x")
            result = reload_chat.update_investigation_item("geography_scope", "Brazil")

        assert result["items_done"] == 2
        assert result["item"] == "geography_scope"

    async def test_update_investigation_item_unknown_id_returns_error(self, reload_chat, caplog):
        """AC3: unknown item_id returns error, mutates nothing, emits no DEBUG."""
        store = {"investigation": reload_chat._empty_investigation_state()}
        snapshot = {k: dict(v) for k, v in store["investigation"].items()}

        with patch("app.chat.cl.user_session") as session_mock:
            session_mock.get.side_effect = lambda k, default=None: store.get(k, default)
            session_mock.set.side_effect = lambda k, v: store.update({k: v})
            with caplog.at_level("DEBUG", logger="app.chat"):
                result = reload_chat.update_investigation_item("bogus", "irrelevant")

        assert result == {"error": "Unknown item_id: 'bogus'"}
        assert store["investigation"] == snapshot
        assert not any("[INVESTIGATION]" in rec.message for rec in caplog.records)

    async def test_update_investigation_item_logs_debug(self, reload_chat, caplog):
        """AC3: DEBUG log is emitted with the canonical [INVESTIGATION] format."""
        store = {"investigation": reload_chat._empty_investigation_state()}
        with patch("app.chat.cl.user_session") as session_mock:
            session_mock.get.side_effect = lambda k, default=None: store.get(k, default)
            session_mock.set.side_effect = lambda k, v: store.update({k: v})
            with caplog.at_level("DEBUG", logger="app.chat"):
                reload_chat.update_investigation_item("topic_definition", "Climate")

        assert any(
            rec.levelname == "DEBUG"
            and "[INVESTIGATION] item=topic_definition status=complete value=Climate" in rec.message
            for rec in caplog.records
        )

    async def test_format_investigation_snapshot_includes_all_ten_items_in_order(self, reload_chat):
        """AC4c: snapshot lists all items in declared order, marks done with values."""
        state = reload_chat._empty_investigation_state()
        state["topic_definition"] = {"done": True, "value": "Climate adaptation"}
        state["geography_scope"] = {"done": True, "value": "Brazil"}

        snapshot = reload_chat._format_investigation_snapshot(state)

        assert snapshot.startswith("[Investigation state:")
        assert snapshot.endswith("]")

        lines = snapshot.splitlines()
        # Opener + 10 items + closer = 12 lines
        assert len(lines) == 12

        # Order preserved
        for idx, key in enumerate(_INVESTIGATION_KEYS):
            assert key in lines[idx + 1]

        # Done markers
        assert "[x] topic_definition: Climate adaptation" in snapshot
        assert "[x] geography_scope: Brazil" in snapshot
        # Not-done items rendered without value
        assert "[ ] time_range" in snapshot
        assert ": " not in lines[3]  # time_range line has no value suffix

    async def test_format_investigation_snapshot_truncates_long_values(self, reload_chat):
        """Snapshot caps value strings at 120 chars to keep prompt bounded."""
        state = reload_chat._empty_investigation_state()
        state["topic_definition"] = {"done": True, "value": "x" * 200}

        snapshot = reload_chat._format_investigation_snapshot(state)

        # 117 chars of 'x' plus the '...' suffix
        assert ("x" * 117 + "...") in snapshot
        assert ("x" * 200) not in snapshot


class TestAgenticLoopInvestigationSnapshot:
    """Story 11.1 AC4: snapshot is appended to the system prompt only in investigating phase."""

    async def test_investigation_phase_appends_snapshot_to_system_prompt(self, reload_chat):
        """AC4a: investigating-phase system prompt contains the snapshot marker."""
        from app.prompts import INVESTIGATION_SYSTEM_PROMPT

        msg_mock = _make_fake_cl_message()
        captured_call_kwargs = {}

        def fake_stream(**kwargs):
            captured_call_kwargs.update(kwargs)
            return FakeStream(["OK"])

        investigation_state = reload_chat._empty_investigation_state()
        investigation_state["topic_definition"] = {"done": True, "value": "Climate adaptation"}

        with (
            patch("app.chat.cl.Message", return_value=msg_mock),
            patch(
                "app.chat.cl.user_session",
                _make_session_mock_with_history(investigation=investigation_state),
            ),
            patch("app.chat.client.messages.stream", side_effect=fake_stream),
        ):
            incoming = MagicMock()
            incoming.content = "hi"
            await reload_chat.on_message(incoming)

        system_prompt = captured_call_kwargs.get("system", "")
        assert INVESTIGATION_SYSTEM_PROMPT in system_prompt
        assert "[Investigation state:" in system_prompt
        assert "[x] topic_definition: Climate adaptation" in system_prompt

    async def test_dossier_phase_does_not_append_investigation_snapshot(self, reload_chat):
        """AC4b: dossier-phase system prompt must NOT contain the investigation snapshot
        (regression guard for Story 10.4's [Current document (vN): ...] framing).
        """
        msg_mock = _make_fake_cl_message()
        captured_call_kwargs = {}
        doc_mock = MagicMock()
        doc_mock.props = {"content": "# Dossier", "version": 1}

        def fake_stream(**kwargs):
            captured_call_kwargs.update(kwargs)
            return FakeStream(["OK"])

        investigation_state = reload_chat._empty_investigation_state()
        investigation_state["topic_definition"] = {"done": True, "value": "ignored in dossier phase"}

        with (
            patch("app.chat.cl.Message", return_value=msg_mock),
            patch(
                "app.chat.cl.user_session",
                _make_session_mock_with_history(
                    dossier={"phase": "dossier"},
                    doc=doc_mock,
                    investigation=investigation_state,
                ),
            ),
            patch("app.chat.client.messages.stream", side_effect=fake_stream),
        ):
            incoming = MagicMock()
            incoming.content = "edit"
            await reload_chat.on_message(incoming)

        system_prompt = captured_call_kwargs.get("system", "")
        assert "[Current document (v1):" in system_prompt
        assert "[Investigation state:" not in system_prompt


class TestUpdateInvestigationItemTool:
    """Story 11.2: LLM-facing tool definition, registration, and dispatch."""

    def test_tool_definition_shape(self, reload_chat):
        """AC1: tool constant has the expected name, required fields, and item_id enum."""
        tool = reload_chat.UPDATE_INVESTIGATION_ITEM_TOOL
        assert tool["name"] == "update_investigation_item"
        assert tool["input_schema"]["required"] == ["item_id", "value"]
        item_id_prop = tool["input_schema"]["properties"]["item_id"]
        assert item_id_prop["type"] == "string"
        assert item_id_prop["enum"] == list(reload_chat._INVESTIGATION_ITEMS)
        # `value` is intentionally open-typed (no JSON "type" key) so strings and
        # structured objects are both accepted by the schema.
        assert "type" not in tool["input_schema"]["properties"]["value"]

    async def test_tool_registered_in_investigating_phase(self, reload_chat):
        """AC2a: tool is exposed to the LLM in investigating phase; apply_ops is NOT."""
        import json as _json

        msg_mock = _make_fake_cl_message()
        captured_call_kwargs = {}

        def fake_stream(**kwargs):
            captured_call_kwargs.update(kwargs)
            return FakeStream(["OK"])

        with (
            patch("app.chat.cl.Message", return_value=msg_mock),
            patch("app.chat.cl.user_session", _make_session_mock_with_history()),
            patch("app.chat.client.messages.stream", side_effect=fake_stream),
        ):
            incoming = MagicMock()
            incoming.content = "hi"
            await reload_chat.on_message(incoming)

        passed_names = [t["name"] for t in (captured_call_kwargs.get("tools") or [])]
        assert "update_investigation_item" in passed_names
        assert "apply_ops" not in passed_names
        # silence linter (json imported lazily inside the test to mirror dev style)
        del _json

    async def test_tool_registered_in_dossier_phase(self, reload_chat):
        """AC2b: tool is exposed alongside apply_ops in dossier phase."""
        msg_mock = _make_fake_cl_message()
        captured_call_kwargs = {}
        doc_mock = MagicMock()
        doc_mock.props = {"content": "# Dossier", "version": 1}

        def fake_stream(**kwargs):
            captured_call_kwargs.update(kwargs)
            return FakeStream(["OK"])

        with (
            patch("app.chat.cl.Message", return_value=msg_mock),
            patch(
                "app.chat.cl.user_session",
                _make_session_mock_with_history(dossier={"phase": "dossier"}, doc=doc_mock),
            ),
            patch("app.chat.client.messages.stream", side_effect=fake_stream),
        ):
            incoming = MagicMock()
            incoming.content = "edit"
            await reload_chat.on_message(incoming)

        passed_names = [t["name"] for t in (captured_call_kwargs.get("tools") or [])]
        assert "apply_ops" in passed_names
        assert "update_investigation_item" in passed_names

    async def test_dispatch_calls_helper_and_serializes_result(self, reload_chat):
        """AC3a/AC3b: tool_use block triggers helper; result is JSON-serialised into tool_result."""
        import json as _json

        tool_block = _make_fake_content_block(
            "tool_use",
            name="update_investigation_item",
            input={"item_id": "topic_definition", "value": "Climate adaptation"},
            id="toolu_inv_01",
        )
        text_block = _make_fake_content_block("text", "Recorded.")

        stream_with_tool = FakeStream(tokens=[], stop_reason="tool_use", content_blocks=[tool_block])
        stream_final = FakeStream(tokens=["Recorded."], stop_reason="end_turn", content_blocks=[text_block])

        call_count = 0
        captured_histories = []

        def fake_stream(**kwargs):
            nonlocal call_count
            call_count += 1
            captured_histories.append(list(kwargs.get("messages", [])))
            return stream_with_tool if call_count == 1 else stream_final

        msg_mock = _make_fake_cl_message()
        step_mock = AsyncMock()
        step_mock.__aenter__ = AsyncMock(return_value=step_mock)
        step_mock.__aexit__ = AsyncMock(return_value=False)
        step_mock.input = ""
        step_mock.output = ""

        investigation_state = reload_chat._empty_investigation_state()

        with (
            patch("app.chat.cl.Message", return_value=msg_mock),
            patch(
                "app.chat.cl.user_session",
                _make_session_mock_with_history(investigation=investigation_state),
            ),
            patch("app.chat.client.messages.stream", side_effect=fake_stream),
            patch("app.chat.cl.Step", return_value=step_mock),
        ):
            incoming = MagicMock()
            incoming.content = "the topic is climate adaptation"
            await reload_chat.on_message(incoming)

        # Second round's history must contain a tool_result block with our JSON-serialised dict.
        round_two_history = captured_histories[1]
        tool_result_msgs = [
            m for m in round_two_history if m.get("role") == "user" and isinstance(m.get("content"), list)
        ]
        assert tool_result_msgs, "expected a tool_result user-message in round 2 history"
        last_tool_results = tool_result_msgs[-1]["content"]
        tool_result_block = next(b for b in last_tool_results if b.get("type") == "tool_result")
        decoded = _json.loads(tool_result_block["content"])
        assert decoded == {
            "status": "ok",
            "item": "topic_definition",
            "items_done": 1,
            "phase_gate_reached": False,
        }

    async def test_dispatch_handles_helper_exception(self, reload_chat, caplog):
        """AC3c: helper exception is caught, surfaced as error string, and logged."""
        tool_block = _make_fake_content_block(
            "tool_use",
            name="update_investigation_item",
            input={"item_id": "topic_definition", "value": "x"},
            id="toolu_inv_02",
        )
        text_block = _make_fake_content_block("text", "ok")

        stream_with_tool = FakeStream(tokens=[], stop_reason="tool_use", content_blocks=[tool_block])
        stream_final = FakeStream(tokens=["ok"], stop_reason="end_turn", content_blocks=[text_block])

        call_count = 0
        captured_histories = []

        def fake_stream(**kwargs):
            nonlocal call_count
            call_count += 1
            captured_histories.append(list(kwargs.get("messages", [])))
            return stream_with_tool if call_count == 1 else stream_final

        msg_mock = _make_fake_cl_message()
        step_mock = AsyncMock()
        step_mock.__aenter__ = AsyncMock(return_value=step_mock)
        step_mock.__aexit__ = AsyncMock(return_value=False)
        step_mock.input = ""
        step_mock.output = ""

        with (
            patch("app.chat.cl.Message", return_value=msg_mock),
            patch("app.chat.cl.user_session", _make_session_mock_with_history()),
            patch("app.chat.client.messages.stream", side_effect=fake_stream),
            patch("app.chat.cl.Step", return_value=step_mock),
            patch("app.chat.update_investigation_item", side_effect=RuntimeError("boom")),
            caplog.at_level("ERROR", logger="app.chat"),
        ):
            incoming = MagicMock()
            incoming.content = "hi"
            await reload_chat.on_message(incoming)

        round_two_history = captured_histories[1]
        tool_result_msgs = [
            m for m in round_two_history if m.get("role") == "user" and isinstance(m.get("content"), list)
        ]
        last_tool_results = tool_result_msgs[-1]["content"]
        tool_result_block = next(b for b in last_tool_results if b.get("type") == "tool_result")
        assert tool_result_block["content"].startswith("Error calling update_investigation_item:")
        assert any("update_investigation_item failed" in rec.message for rec in caplog.records)

    async def test_dispatch_unknown_item_id_returns_structured_error(self, reload_chat):
        """AC4: unknown item_id round-trips the helper's error dict — no exception."""
        import json as _json

        tool_block = _make_fake_content_block(
            "tool_use",
            name="update_investigation_item",
            input={"item_id": "bogus", "value": "x"},
            id="toolu_inv_03",
        )
        text_block = _make_fake_content_block("text", "noted")

        stream_with_tool = FakeStream(tokens=[], stop_reason="tool_use", content_blocks=[tool_block])
        stream_final = FakeStream(tokens=["noted"], stop_reason="end_turn", content_blocks=[text_block])

        call_count = 0
        captured_histories = []

        def fake_stream(**kwargs):
            nonlocal call_count
            call_count += 1
            captured_histories.append(list(kwargs.get("messages", [])))
            return stream_with_tool if call_count == 1 else stream_final

        msg_mock = _make_fake_cl_message()
        step_mock = AsyncMock()
        step_mock.__aenter__ = AsyncMock(return_value=step_mock)
        step_mock.__aexit__ = AsyncMock(return_value=False)
        step_mock.input = ""
        step_mock.output = ""

        with (
            patch("app.chat.cl.Message", return_value=msg_mock),
            patch("app.chat.cl.user_session", _make_session_mock_with_history()),
            patch("app.chat.client.messages.stream", side_effect=fake_stream),
            patch("app.chat.cl.Step", return_value=step_mock),
        ):
            incoming = MagicMock()
            incoming.content = "hi"
            await reload_chat.on_message(incoming)

        round_two_history = captured_histories[1]
        tool_result_msgs = [
            m for m in round_two_history if m.get("role") == "user" and isinstance(m.get("content"), list)
        ]
        last_tool_results = tool_result_msgs[-1]["content"]
        tool_result_block = next(b for b in last_tool_results if b.get("type") == "tool_result")
        decoded = _json.loads(tool_result_block["content"])
        assert decoded == {"error": "Unknown item_id: 'bogus'"}

    async def test_snapshot_reflects_update_in_next_round(self, reload_chat):
        """AC5: round 2's system prompt shows the just-recorded item in the snapshot."""
        tool_block = _make_fake_content_block(
            "tool_use",
            name="update_investigation_item",
            input={"item_id": "topic_definition", "value": "Climate"},
            id="toolu_inv_04",
        )
        text_block = _make_fake_content_block("text", "Recorded.")

        stream_with_tool = FakeStream(tokens=[], stop_reason="tool_use", content_blocks=[tool_block])
        stream_final = FakeStream(tokens=["Recorded."], stop_reason="end_turn", content_blocks=[text_block])

        call_count = 0
        captured_systems = []

        def fake_stream(**kwargs):
            nonlocal call_count
            call_count += 1
            captured_systems.append(kwargs.get("system", ""))
            return stream_with_tool if call_count == 1 else stream_final

        msg_mock = _make_fake_cl_message()
        step_mock = AsyncMock()
        step_mock.__aenter__ = AsyncMock(return_value=step_mock)
        step_mock.__aexit__ = AsyncMock(return_value=False)
        step_mock.input = ""
        step_mock.output = ""

        investigation_state = reload_chat._empty_investigation_state()

        with (
            patch("app.chat.cl.Message", return_value=msg_mock),
            patch(
                "app.chat.cl.user_session",
                _make_session_mock_with_history(investigation=investigation_state),
            ),
            patch("app.chat.client.messages.stream", side_effect=fake_stream),
            patch("app.chat.cl.Step", return_value=step_mock),
        ):
            incoming = MagicMock()
            incoming.content = "the topic is climate"
            await reload_chat.on_message(incoming)

        assert call_count == 2
        # Round 1: not yet recorded
        assert "[ ] topic_definition" in captured_systems[0]
        # Round 2: recorded with the supplied value
        assert "[x] topic_definition: Climate" in captured_systems[1]


class TestPhaseGateLogic:
    """Story 11.3: phase-gate computation, phase flip, and reveal affordance."""

    def _all_gate_items_done(self, reload_chat) -> dict:
        state = reload_chat._empty_investigation_state()
        for k in reload_chat._PHASE_GATE_ITEMS:
            state[k] = {"done": True, "value": "set"}
        return state

    def test_gate_not_reached_with_partial_items(self, reload_chat):
        """AC1a: 4 of 5 gate items done → phase_gate_reached is False."""
        state = reload_chat._empty_investigation_state()
        for k in ("topic_definition", "geography_scope", "time_range", "target_audience"):
            state[k] = {"done": True, "value": "set"}
        store = {"investigation": state, "dossier": {"phase": "investigating"}}
        with patch("app.chat.cl.user_session") as session_mock:
            session_mock.get.side_effect = lambda k, default=None: store.get(k, default)
            session_mock.set.side_effect = lambda k, v: store.update({k: v})
            # Mark a non-gate item; data_sources_validation still missing
            result = reload_chat.update_investigation_item("key_stats_capture", "some stats")
        assert result["phase_gate_reached"] is False
        assert store["dossier"]["phase"] == "investigating"

    def test_gate_reached_when_all_five_items_done(self, reload_chat, caplog):
        """AC2: completing the 5th gate item flips phase_gate_reached True, phase to dossier, emits debug log."""
        state = reload_chat._empty_investigation_state()
        for k in ("topic_definition", "geography_scope", "time_range", "target_audience"):
            state[k] = {"done": True, "value": "set"}
        # _data_validation_indicators_found must be True — the gate rejects without a
        # prior successful search_indicators call (Story 12.2 AC2).
        store = {
            "investigation": state,
            "dossier": {"phase": "investigating"},
            "_data_validation_indicators_found": True,
        }
        with patch("app.chat.cl.user_session") as session_mock:
            session_mock.get.side_effect = lambda k, default=None: store.get(k, default)
            session_mock.set.side_effect = lambda k, v: store.update({k: v})
            with caplog.at_level("DEBUG", logger="app.chat"):
                result = reload_chat.update_investigation_item("data_sources_validation", "confirmed")
        assert result["phase_gate_reached"] is True
        assert store["dossier"]["phase"] == "dossier"
        assert any("phase_gate=reached, transitioning to dossier mode" in rec.message for rec in caplog.records)

    def test_gate_idempotent_when_already_dossier(self, reload_chat, caplog):
        """AC2 idempotent: re-calling a gate item already done keeps gate True, phase unchanged, log not re-emitted."""
        store = {"investigation": self._all_gate_items_done(reload_chat), "dossier": {"phase": "dossier"}}
        with patch("app.chat.cl.user_session") as session_mock:
            session_mock.get.side_effect = lambda k, default=None: store.get(k, default)
            session_mock.set.side_effect = lambda k, v: store.update({k: v})
            with caplog.at_level("DEBUG", logger="app.chat"):
                result = reload_chat.update_investigation_item("topic_definition", "re-confirmed")
        assert result["phase_gate_reached"] is True
        assert store["dossier"]["phase"] == "dossier"
        assert not any("phase_gate=reached, transitioning to dossier mode" in rec.message for rec in caplog.records)

    def test_gate_not_reached_with_non_gate_items_only(self, reload_chat):
        """AC1a: non-gate items never trigger the gate."""
        store = {"investigation": reload_chat._empty_investigation_state(), "dossier": {"phase": "investigating"}}
        with patch("app.chat.cl.user_session") as session_mock:
            session_mock.get.side_effect = lambda k, default=None: store.get(k, default)
            session_mock.set.side_effect = lambda k, v: store.update({k: v})
            result = reload_chat.update_investigation_item("methodology", "source analysis")
        assert result["phase_gate_reached"] is False

    def test_update_investigation_item_is_synchronous(self, reload_chat):
        """AC5: update_investigation_item must remain a synchronous (non-coroutine) function."""
        assert not inspect.iscoroutinefunction(reload_chat.update_investigation_item)

    async def test_dispatch_posts_affordance_on_gate_transition(self, reload_chat):
        """AC3: dispatch awaits post_dossier_reveal_affordance exactly once on investigating→dossier transition."""
        tool_block = _make_fake_content_block(
            "tool_use",
            name="update_investigation_item",
            input={"item_id": "data_sources_validation", "value": "confirmed"},
            id="toolu_gate_01",
        )
        text_block = _make_fake_content_block("text", "Dossier ready.")
        stream_with_tool = FakeStream(tokens=[], stop_reason="tool_use", content_blocks=[tool_block])
        stream_final = FakeStream(tokens=["Dossier ready."], stop_reason="end_turn", content_blocks=[text_block])
        call_count = 0

        def fake_stream(**kwargs):
            nonlocal call_count
            call_count += 1
            return stream_with_tool if call_count == 1 else stream_final

        msg_mock = _make_fake_cl_message()
        step_mock = AsyncMock()
        step_mock.__aenter__ = AsyncMock(return_value=step_mock)
        step_mock.__aexit__ = AsyncMock(return_value=False)
        step_mock.input = ""
        step_mock.output = ""

        gate_result = {"status": "ok", "item": "data_sources_validation", "items_done": 5, "phase_gate_reached": True}

        with (
            patch("app.chat.cl.Message", return_value=msg_mock),
            patch("app.chat.cl.user_session", _make_session_mock_with_history()),
            patch("app.chat.client.messages.stream", side_effect=fake_stream),
            patch("app.chat.cl.Step", return_value=step_mock),
            patch("app.chat.update_investigation_item", return_value=gate_result),
            patch("app.chat.post_dossier_reveal_affordance", new_callable=AsyncMock) as mock_reveal,
        ):
            incoming = MagicMock()
            incoming.content = "all sources validated"
            await reload_chat.on_message(incoming)

        mock_reveal.assert_awaited_once()

    async def test_dispatch_no_affordance_when_already_dossier(self, reload_chat):
        """AC4: affordance not re-posted when phase was already dossier before the call."""
        tool_block = _make_fake_content_block(
            "tool_use",
            name="update_investigation_item",
            input={"item_id": "key_stats_capture", "value": "stats"},
            id="toolu_gate_02",
        )
        text_block = _make_fake_content_block("text", "OK.")
        stream_with_tool = FakeStream(tokens=[], stop_reason="tool_use", content_blocks=[tool_block])
        stream_final = FakeStream(tokens=["OK."], stop_reason="end_turn", content_blocks=[text_block])
        call_count = 0

        def fake_stream(**kwargs):
            nonlocal call_count
            call_count += 1
            return stream_with_tool if call_count == 1 else stream_final

        msg_mock = _make_fake_cl_message()
        step_mock = AsyncMock()
        step_mock.__aenter__ = AsyncMock(return_value=step_mock)
        step_mock.__aexit__ = AsyncMock(return_value=False)
        step_mock.input = ""
        step_mock.output = ""

        gate_result = {"status": "ok", "item": "key_stats_capture", "items_done": 6, "phase_gate_reached": True}

        with (
            patch("app.chat.cl.Message", return_value=msg_mock),
            patch("app.chat.cl.user_session", _make_session_mock_with_history(dossier={"phase": "dossier"})),
            patch("app.chat.client.messages.stream", side_effect=fake_stream),
            patch("app.chat.cl.Step", return_value=step_mock),
            patch("app.chat.update_investigation_item", return_value=gate_result),
            patch("app.chat.post_dossier_reveal_affordance", new_callable=AsyncMock) as mock_reveal,
        ):
            incoming = MagicMock()
            incoming.content = "more items"
            await reload_chat.on_message(incoming)

        mock_reveal.assert_not_awaited()

    async def test_dispatch_no_affordance_when_gate_not_reached(self, reload_chat):
        """AC1/AC3: no affordance posted when phase_gate_reached is False (gate not reached)."""
        tool_block = _make_fake_content_block(
            "tool_use",
            name="update_investigation_item",
            input={"item_id": "topic_definition", "value": "Climate"},
            id="toolu_gate_03",
        )
        text_block = _make_fake_content_block("text", "Noted.")
        stream_with_tool = FakeStream(tokens=[], stop_reason="tool_use", content_blocks=[tool_block])
        stream_final = FakeStream(tokens=["Noted."], stop_reason="end_turn", content_blocks=[text_block])
        call_count = 0

        def fake_stream(**kwargs):
            nonlocal call_count
            call_count += 1
            return stream_with_tool if call_count == 1 else stream_final

        msg_mock = _make_fake_cl_message()
        step_mock = AsyncMock()
        step_mock.__aenter__ = AsyncMock(return_value=step_mock)
        step_mock.__aexit__ = AsyncMock(return_value=False)
        step_mock.input = ""
        step_mock.output = ""

        no_gate_result = {"status": "ok", "item": "topic_definition", "items_done": 1, "phase_gate_reached": False}

        with (
            patch("app.chat.cl.Message", return_value=msg_mock),
            patch("app.chat.cl.user_session", _make_session_mock_with_history()),
            patch("app.chat.client.messages.stream", side_effect=fake_stream),
            patch("app.chat.cl.Step", return_value=step_mock),
            patch("app.chat.update_investigation_item", return_value=no_gate_result),
            patch("app.chat.post_dossier_reveal_affordance", new_callable=AsyncMock) as mock_reveal,
        ):
            incoming = MagicMock()
            incoming.content = "set topic"
            await reload_chat.on_message(incoming)

        mock_reveal.assert_not_awaited()


def _make_fake_ce_factory():
    """Return (factory, created) where factory mimics cl.CustomElement(...).

    The factory captures constructor kwargs into a MagicMock with a real `.props`
    dict, a settable `.content`, and an awaitable `.update`. `created` accumulates
    every element built so tests can assert how many were constructed.
    """
    created: list = []

    def _factory(name=None, props=None, display=None, **_kwargs):
        doc = MagicMock()
        doc.props = dict(props) if props is not None else {}
        doc.content = ""
        doc.update = AsyncMock()
        doc._ce_name = name
        doc._ce_display = display
        created.append(doc)
        return doc

    return _factory, created


def _make_sidebar_mock():
    """Return a MagicMock standing in for cl.ElementSidebar with async classmethods."""
    sidebar = MagicMock()
    sidebar.set_title = AsyncMock()
    sidebar.set_elements = AsyncMock()
    return sidebar


@contextlib.asynccontextmanager
async def _failing_mcp_client(url, **kwargs):
    """streamablehttp_client stand-in that fails so on_chat_start/resume skip MCP."""
    raise ConnectionError("no MCP")
    yield  # pragma: no cover


class TestOnDemandDossierReveal:
    """Story 10.6: lazy doc creation + on-demand canvas reveal."""

    async def test_ensure_dossier_doc_creates_doc_when_absent(self, reload_chat):
        """AC2: creates a Document element with dossier-phase props when none exists."""
        stored: dict = {}
        factory, created = _make_fake_ce_factory()
        sidebar = _make_sidebar_mock()
        with (
            patch("app.chat.cl.user_session") as session_mock,
            patch("app.chat.cl.CustomElement", side_effect=factory),
            patch("app.chat.cl.ElementSidebar", sidebar),
        ):
            session_mock.set.side_effect = lambda k, v: stored.update({k: v})
            session_mock.get.side_effect = lambda k, default=None: stored.get(k, default)
            doc = reload_chat.ensure_dossier_doc()

        assert doc is stored["doc"]
        assert doc.props == {"content": "", "version": 0, "phase": "dossier"}
        assert len(created) == 1
        # AC2: creation must NOT open the sidebar.
        sidebar.set_title.assert_not_called()
        sidebar.set_elements.assert_not_called()

    async def test_ensure_dossier_doc_is_idempotent(self, reload_chat):
        """AC2: a second call returns the same element — no second CustomElement built."""
        stored: dict = {}
        factory, created = _make_fake_ce_factory()
        with (
            patch("app.chat.cl.user_session") as session_mock,
            patch("app.chat.cl.CustomElement", side_effect=factory),
        ):
            session_mock.set.side_effect = lambda k, v: stored.update({k: v})
            session_mock.get.side_effect = lambda k, default=None: stored.get(k, default)
            doc1 = reload_chat.ensure_dossier_doc()
            doc2 = reload_chat.ensure_dossier_doc()

        assert doc1 is doc2
        assert len(created) == 1

    async def test_reveal_dossier_canvas_opens_sidebar(self, reload_chat):
        """AC3: reveal opens the ElementSidebar titled 'Dossier' with the doc."""
        stored: dict = {}
        factory, created = _make_fake_ce_factory()
        sidebar = _make_sidebar_mock()
        with (
            patch("app.chat.cl.user_session") as session_mock,
            patch("app.chat.cl.CustomElement", side_effect=factory),
            patch("app.chat.cl.ElementSidebar", sidebar),
        ):
            session_mock.set.side_effect = lambda k, v: stored.update({k: v})
            session_mock.get.side_effect = lambda k, default=None: stored.get(k, default)
            await reload_chat.reveal_dossier_canvas()

        sidebar.set_title.assert_awaited_once_with("Dossier")
        sidebar.set_elements.assert_awaited_once()
        args, kwargs = sidebar.set_elements.call_args
        assert args[0] == [stored["doc"]]
        # Key includes content version + monotonic open counter (ensures close→reopen works).
        assert kwargs.get("key") == "dossier-v0-o1"
        # Reveal marks the canvas revealed so subsequent updates refresh it.
        assert stored.get("dossier_revealed") is True

    async def test_reveal_dossier_canvas_reuses_existing_doc(self, reload_chat):
        """AC3: reveal never constructs a new element when one already exists."""
        existing = MagicMock()
        existing.props = {"content": "# Hi", "version": 3, "phase": "dossier"}
        stored: dict = {"doc": existing}
        factory, created = _make_fake_ce_factory()
        sidebar = _make_sidebar_mock()
        with (
            patch("app.chat.cl.user_session") as session_mock,
            patch("app.chat.cl.CustomElement", side_effect=factory),
            patch("app.chat.cl.ElementSidebar", sidebar),
        ):
            session_mock.set.side_effect = lambda k, v: stored.update({k: v})
            session_mock.get.side_effect = lambda k, default=None: stored.get(k, default)
            await reload_chat.reveal_dossier_canvas()
            await reload_chat.reveal_dossier_canvas()

        assert len(created) == 0  # no new CustomElement built
        args, _ = sidebar.set_elements.call_args
        assert args[0] == [existing]

    async def test_post_dossier_reveal_affordance_sends_single_action(self, reload_chat):
        """AC4: posts exactly one message carrying a single 'reveal_dossier' action."""
        msg_mock = AsyncMock()
        msg_mock.send = AsyncMock()
        action_obj = MagicMock()
        with (
            patch("app.chat.cl.Message", return_value=msg_mock) as msg_cls,
            patch("app.chat.cl.Action", return_value=action_obj) as action_cls,
        ):
            await reload_chat.post_dossier_reveal_affordance()

        action_cls.assert_called_once_with(name="reveal_dossier", label="📄 Open dossier", payload={})
        _, kwargs = msg_cls.call_args
        assert kwargs.get("actions") == [action_obj]
        msg_mock.send.assert_awaited_once()

    async def test_reveal_dossier_action_callback_triggers_reveal(self, reload_chat):
        """AC4: clicking the affordance invokes reveal_dossier_canvas()."""
        action = MagicMock()
        action.remove = AsyncMock()
        with patch("app.chat.reveal_dossier_canvas", new=AsyncMock()) as reveal_mock:
            await reload_chat.on_reveal_dossier(action)

        reveal_mock.assert_awaited_once()
        action.remove.assert_awaited_once()

    async def test_on_chat_start_does_not_create_doc_or_open_sidebar(self, reload_chat):
        """AC1 regression: chat start initializes state only — no doc, no sidebar."""
        stored: dict = {}
        factory, created = _make_fake_ce_factory()
        sidebar = _make_sidebar_mock()
        with (
            patch("app.chat.streamablehttp_client", _failing_mcp_client),
            patch("app.chat.cl.user_session") as session_mock,
            patch("app.chat.cl.Message") as msg_cls,
            patch("app.chat.cl.CustomElement", side_effect=factory),
            patch("app.chat.cl.ElementSidebar", sidebar),
        ):
            session_mock.set.side_effect = lambda k, v: stored.update({k: v})
            session_mock.get.side_effect = lambda k, default=None: stored.get(k, default)
            msg_cls.return_value.send = AsyncMock()
            await reload_chat.on_chat_start()

        assert stored.get("doc") is None
        assert len(created) == 0
        sidebar.set_title.assert_not_called()
        sidebar.set_elements.assert_not_called()

    async def test_on_chat_start_welcome_message_has_no_reveal_action(self, reload_chat):
        """AC4: the welcome message carries no persistent reveal/show action."""
        stored: dict = {}
        captured: dict = {}

        def fake_message(*args, **kwargs):
            captured.update(kwargs)
            m = AsyncMock()
            m.send = AsyncMock()
            return m

        with (
            patch("app.chat.streamablehttp_client", _failing_mcp_client),
            patch("app.chat.cl.user_session") as session_mock,
            patch("app.chat.cl.Message", side_effect=fake_message),
        ):
            session_mock.set.side_effect = lambda k, v: stored.update({k: v})
            session_mock.get.side_effect = lambda k, default=None: stored.get(k, default)
            await reload_chat.on_chat_start()

        assert not captured.get("actions")

    async def test_on_chat_resume_does_not_create_doc_or_open_sidebar(self, reload_chat):
        """AC1 regression: resume re-seeds state only — no doc, no sidebar."""
        stored: dict = {}
        factory, created = _make_fake_ce_factory()
        sidebar = _make_sidebar_mock()
        with (
            patch("app.chat.streamablehttp_client", _failing_mcp_client),
            patch("app.chat.cl.user_session") as session_mock,
            patch("app.chat.cl.CustomElement", side_effect=factory),
            patch("app.chat.cl.ElementSidebar", sidebar),
        ):
            session_mock.set.side_effect = lambda k, v: stored.update({k: v})
            session_mock.get.side_effect = lambda k, default=None: stored.get(k, default)
            await reload_chat.on_chat_resume({"steps": []})

        assert stored.get("doc") is None
        assert len(created) == 0
        sidebar.set_title.assert_not_called()
        sidebar.set_elements.assert_not_called()

    async def test_apply_ops_succeeds_after_ensure_dossier_doc(self, reload_chat):
        """AC5: once a doc exists, apply_ops operates on it (no 'canvas not open')."""
        stored: dict = {"dossier": {"phase": "dossier", "content": "", "version": 0}}
        factory, created = _make_fake_ce_factory()
        sent_msg = AsyncMock()
        sent_msg.send = AsyncMock()
        with (
            patch("app.chat.cl.user_session") as session_mock,
            patch("app.chat.cl.CustomElement", side_effect=factory),
            patch("app.chat.cl.Message", return_value=sent_msg),
        ):
            session_mock.set.side_effect = lambda k, v: stored.update({k: v})
            session_mock.get.side_effect = lambda k, default=None: stored.get(k, default)
            reload_chat.ensure_dossier_doc()
            result = await reload_chat._handle_apply_ops(
                {"ops": [{"type": "append", "content": "# Hello"}], "summary": "added heading"}
            )

        assert result == "ok"
        assert stored["doc"].props["content"] == "# Hello"

    async def test_handle_apply_ops_without_doc_still_reports_not_open(self, reload_chat):
        """AC5 guard preserved: with no doc, apply_ops still returns the not-open error."""
        stored: dict = {}
        with patch("app.chat.cl.user_session") as session_mock:
            session_mock.set.side_effect = lambda k, v: stored.update({k: v})
            session_mock.get.side_effect = lambda k, default=None: stored.get(k, default)
            result = await reload_chat._handle_apply_ops({"ops": [{"type": "append", "content": "x"}], "summary": "s"})

        assert result == "Error: dossier canvas is not open"

    async def test_update_dossier_content_refreshes_sidebar_when_revealed(self, reload_chat):
        """AC6: after reveal, update_dossier_content re-renders the sidebar with a new key.

        doc.update() alone does not refresh a sidebar-hosted element, and re-running
        set_elements with the SAME key is a no-op — so the refresh must use a
        version-stamped key.
        """
        doc = MagicMock()
        doc.props = {"content": "", "version": 0, "phase": "dossier"}
        doc.update = AsyncMock()
        stored: dict = {"doc": doc, "dossier_revealed": True}
        sidebar = _make_sidebar_mock()
        with (
            patch("app.chat.cl.user_session") as session_mock,
            patch("app.chat.cl.ElementSidebar", sidebar),
        ):
            session_mock.set.side_effect = lambda k, v: stored.update({k: v})
            session_mock.get.side_effect = lambda k, default=None: stored.get(k, default)
            await reload_chat.update_dossier_content("# New content")

        assert doc.props["content"] == "# New content"
        assert doc.props["version"] == 1
        sidebar.set_elements.assert_awaited_once()
        args, kwargs = sidebar.set_elements.call_args
        assert args[0] == [doc]
        assert kwargs.get("key") == "dossier-v1-o0"  # version-stamped + open-counter → not a no-op

    async def test_update_dossier_content_no_sidebar_refresh_when_not_revealed(self, reload_chat):
        """AC4: content updates before reveal must NOT force the panel open."""
        doc = MagicMock()
        doc.props = {"content": "", "version": 0, "phase": "dossier"}
        doc.update = AsyncMock()
        stored: dict = {"doc": doc}  # dossier_revealed not set
        sidebar = _make_sidebar_mock()
        with (
            patch("app.chat.cl.user_session") as session_mock,
            patch("app.chat.cl.ElementSidebar", sidebar),
        ):
            session_mock.set.side_effect = lambda k, v: stored.update({k: v})
            session_mock.get.side_effect = lambda k, default=None: stored.get(k, default)
            await reload_chat.update_dossier_content("# Silent update")

        # Doc props still updated (so content shows once revealed), but no sidebar open.
        assert doc.props["content"] == "# Silent update"
        sidebar.set_elements.assert_not_called()
        sidebar.set_title.assert_not_called()

    async def test_refresh_dossier_canvas_is_noop_when_not_revealed(self, reload_chat):
        """_refresh_dossier_canvas does nothing until the canvas has been revealed."""
        doc = MagicMock()
        doc.props = {"content": "x", "version": 2, "phase": "dossier"}
        stored: dict = {"doc": doc}
        sidebar = _make_sidebar_mock()
        with (
            patch("app.chat.cl.user_session") as session_mock,
            patch("app.chat.cl.ElementSidebar", sidebar),
        ):
            session_mock.set.side_effect = lambda k, v: stored.update({k: v})
            session_mock.get.side_effect = lambda k, default=None: stored.get(k, default)
            await reload_chat._refresh_dossier_canvas()

        sidebar.set_elements.assert_not_called()

    async def test_apply_ops_streams_into_sidebar_per_op_when_revealed(self, reload_chat):
        """AC6: with the canvas revealed, each op refreshes the sidebar (streaming)."""
        doc = MagicMock()
        doc.props = {"content": "", "version": 0, "phase": "dossier"}
        doc.update = AsyncMock()
        stored: dict = {
            "doc": doc,
            "dossier_revealed": True,
            "dossier": {"phase": "dossier", "content": "", "version": 0},
        }
        sent_msg = AsyncMock()
        sent_msg.send = AsyncMock()
        sidebar = _make_sidebar_mock()
        with (
            patch("app.chat.cl.user_session") as session_mock,
            patch("app.chat.cl.ElementSidebar", sidebar),
            patch("app.chat.cl.Message", return_value=sent_msg),
        ):
            session_mock.set.side_effect = lambda k, v: stored.update({k: v})
            session_mock.get.side_effect = lambda k, default=None: stored.get(k, default)
            result = await reload_chat._handle_apply_ops(
                {
                    "ops": [
                        {"type": "append", "content": "## Part 1"},
                        {"type": "append", "content": "Body text."},
                    ],
                    "summary": "two appends",
                }
            )

        assert result == "ok"
        # One sidebar refresh per op (2 ops → 2 refreshes), each with a fresh key.
        assert sidebar.set_elements.await_count == 2
        keys = [c.kwargs.get("key") for c in sidebar.set_elements.await_args_list]
        assert keys == ["dossier-v1-o0", "dossier-v2-o0"]


class TestProposeStructureTool:
    """Story 11.4: propose_structure tool — skeleton generation and dossier wiring."""

    # ------------------------------------------------------------------
    # Pure-helper tests (no Chainlit mocks required)
    # ------------------------------------------------------------------

    def test_skeleton_contains_required_sections(self, reload_chat):
        """AC3: all five required headings appear in order in the skeleton markdown."""
        skeleton, sections = reload_chat._build_dossier_skeleton(None)
        assert "# Executive Summary" in skeleton
        assert "## Part 1:" in skeleton
        assert "## Case Studies" in skeleton
        assert "## Suggested Stories (Pautas Sugeridas)" in skeleton
        assert "## Methodology and Sources" in skeleton
        # Check order
        idx_exec = skeleton.index("# Executive Summary")
        idx_part1 = skeleton.index("## Part 1:")
        idx_cases = skeleton.index("## Case Studies")
        idx_stories = skeleton.index("## Suggested Stories")
        idx_method = skeleton.index("## Methodology and Sources")
        assert idx_exec < idx_part1 < idx_cases < idx_stories < idx_method
        assert len(sections) == 5

    def test_skeleton_uses_topic_from_state(self, reload_chat):
        """AC3: topic_definition value is used as Part 1 heading when no topic_area given."""
        state = {"topic_definition": {"done": True, "value": "Dengue in SE Brazil"}}
        skeleton, sections = reload_chat._build_dossier_skeleton(state)
        assert "## Part 1: Dengue in SE Brazil" in skeleton
        assert "Part 1: Dengue in SE Brazil" in sections

    def test_skeleton_topic_area_override(self, reload_chat):
        """AC3: explicit topic_area wins over state value."""
        state = {"topic_definition": {"done": True, "value": "Something long and different"}}
        skeleton, sections = reload_chat._build_dossier_skeleton(state, topic_area="Short Label")
        assert "## Part 1: Short Label" in skeleton
        assert "Part 1: Short Label" in sections
        assert "Something long" not in skeleton

    def test_skeleton_truncates_long_topic(self, reload_chat):
        """AC3: topic longer than 60 chars is truncated to <=60 chars ending with '...'."""
        long_topic = "A" * 70
        skeleton, sections = reload_chat._build_dossier_skeleton(None, topic_area=long_topic)
        part1_heading = [s for s in sections if s.startswith("Part 1:")][0]
        label = part1_heading[len("Part 1: ") :]
        assert len(label) <= 60
        assert label.endswith("...")

    def test_skeleton_fallback_when_topic_missing(self, reload_chat):
        """AC3: empty state and no topic_area falls back to 'Investigation Overview'."""
        skeleton, sections = reload_chat._build_dossier_skeleton({})
        assert "## Part 1: Investigation Overview" in skeleton
        assert "Part 1: Investigation Overview" in sections

    def test_derive_topic_label_strips_markdown_control_chars(self, reload_chat):
        """P4: Markdown control chars are stripped so the topic can't distort/escape
        the heading it's injected into; whitespace runs collapse."""
        label = reload_chat._derive_topic_label(None, topic_area="Foo `bar`  ## *baz* [x]\n# hack")
        assert "#" not in label
        assert "`" not in label
        assert "*" not in label
        assert "[" not in label and "]" not in label
        assert "\n" not in label
        # Whitespace collapsed to single spaces.
        assert "  " not in label
        assert label == "Foo bar baz x hack"

    def test_derive_topic_label_truncation_boundary(self, reload_chat):
        """P6: 60-char topic is kept verbatim; 61-char topic is truncated to <=60 with '...'."""
        exactly_60 = "A" * 60
        assert reload_chat._derive_topic_label(None, topic_area=exactly_60) == exactly_60
        over_60 = "B" * 61
        truncated = reload_chat._derive_topic_label(None, topic_area=over_60)
        assert len(truncated) <= 60
        assert truncated.endswith("...")

    # ------------------------------------------------------------------
    # Handler tests
    # ------------------------------------------------------------------

    async def test_handle_propose_structure_creates_and_populates_doc(self, reload_chat):
        """AC2: creates doc, writes skeleton, returns status:ok with 5 sections."""
        stored: dict = {}
        factory, created = _make_fake_ce_factory()
        sidebar = _make_sidebar_mock()
        with (
            patch("app.chat.cl.user_session") as session_mock,
            patch("app.chat.cl.CustomElement", side_effect=factory),
            patch("app.chat.cl.ElementSidebar", sidebar),
        ):
            session_mock.set.side_effect = lambda k, v: stored.update({k: v})
            session_mock.get.side_effect = lambda k, default=None: stored.get(k, default)
            result_json = await reload_chat._handle_propose_structure({"topic_area": "Climate Risk"})

        import json as _json

        result = _json.loads(result_json)
        assert result["status"] == "ok"
        assert len(result["sections"]) == 5
        assert len(created) == 1
        doc = stored["doc"]
        assert doc.props["phase"] == "dossier"
        assert "# Executive Summary" in doc.props["content"]
        assert "## Part 1: Climate Risk" in doc.props["content"]
        doc.update.assert_awaited()

    async def test_handle_propose_structure_does_not_open_sidebar(self, reload_chat):
        """AC4: handler does not call ElementSidebar (canvas not revealed)."""
        stored: dict = {}
        factory, _ = _make_fake_ce_factory()
        sidebar = _make_sidebar_mock()
        with (
            patch("app.chat.cl.user_session") as session_mock,
            patch("app.chat.cl.CustomElement", side_effect=factory),
            patch("app.chat.cl.ElementSidebar", sidebar),
        ):
            session_mock.set.side_effect = lambda k, v: stored.update({k: v})
            session_mock.get.side_effect = lambda k, default=None: stored.get(k, default)
            await reload_chat._handle_propose_structure({})

        sidebar.set_title.assert_not_called()
        sidebar.set_elements.assert_not_called()

    async def test_handle_propose_structure_noop_when_content_exists(self, reload_chat):
        """AC5: returns status:noop without overwriting existing content."""
        import json as _json

        existing = MagicMock()
        existing.props = {"content": "# Existing", "version": 2, "phase": "dossier"}
        existing.update = AsyncMock()
        stored: dict = {"doc": existing}
        factory, created = _make_fake_ce_factory()
        sidebar = _make_sidebar_mock()
        with (
            patch("app.chat.cl.user_session") as session_mock,
            patch("app.chat.cl.CustomElement", side_effect=factory),
            patch("app.chat.cl.ElementSidebar", sidebar),
        ):
            session_mock.set.side_effect = lambda k, v: stored.update({k: v})
            session_mock.get.side_effect = lambda k, default=None: stored.get(k, default)
            result_json = await reload_chat._handle_propose_structure({})

        result = _json.loads(result_json)
        assert result["status"] == "noop"
        assert "reason" in result
        assert existing.props["content"] == "# Existing"
        existing.update.assert_not_awaited()
        assert len(created) == 0

    async def test_handle_propose_structure_whitespace_topic_area_falls_back_to_state(self, reload_chat):
        """P6: a whitespace-only topic_area collapses to None, so the skeleton falls
        back to the investigation topic_definition value."""
        stored: dict = {"investigation": {"topic_definition": {"done": True, "value": "Floods in Bangladesh"}}}
        factory, created = _make_fake_ce_factory()
        sidebar = _make_sidebar_mock()
        with (
            patch("app.chat.cl.user_session") as session_mock,
            patch("app.chat.cl.CustomElement", side_effect=factory),
            patch("app.chat.cl.ElementSidebar", sidebar),
        ):
            session_mock.set.side_effect = lambda k, v: stored.update({k: v})
            session_mock.get.side_effect = lambda k, default=None: stored.get(k, default)
            await reload_chat._handle_propose_structure({"topic_area": "   "})

        doc = stored["doc"]
        assert "## Part 1: Floods in Bangladesh" in doc.props["content"]

    # ------------------------------------------------------------------
    # Dispatch test
    # ------------------------------------------------------------------

    async def test_dispatch_calls_propose_structure_handler(self, reload_chat):
        """AC6: dispatch awaits _handle_propose_structure when tool_use name is propose_structure."""
        import json as _json

        tool_block = _make_fake_content_block(
            "tool_use",
            name="propose_structure",
            input={"topic_area": "Climate Risk"},
            id="toolu_ps_01",
        )
        text_block = _make_fake_content_block("text", "Skeleton created.")
        stream_with_tool = FakeStream(tokens=[], stop_reason="tool_use", content_blocks=[tool_block])
        stream_final = FakeStream(tokens=["Skeleton created."], stop_reason="end_turn", content_blocks=[text_block])
        call_count = 0
        captured_calls = []

        def fake_stream(**kwargs):
            nonlocal call_count
            call_count += 1
            captured_calls.append(kwargs)
            return stream_with_tool if call_count == 1 else stream_final

        msg_mock = _make_fake_cl_message()
        step_mock = AsyncMock()
        step_mock.__aenter__ = AsyncMock(return_value=step_mock)
        step_mock.__aexit__ = AsyncMock(return_value=False)
        step_mock.input = ""
        step_mock.output = ""

        doc_mock = MagicMock()
        doc_mock.props = {"content": "", "version": 0, "phase": "dossier"}

        handler_return = _json.dumps({"status": "ok", "sections": ["Executive Summary"]})

        with (
            patch("app.chat.cl.Message", return_value=msg_mock),
            patch(
                "app.chat.cl.user_session",
                _make_session_mock_with_history(dossier={"phase": "dossier"}, doc=doc_mock),
            ),
            patch("app.chat.client.messages.stream", side_effect=fake_stream),
            patch("app.chat.cl.Step", return_value=step_mock),
            patch(
                "app.chat._handle_propose_structure", new_callable=AsyncMock, return_value=handler_return
            ) as mock_handler,
        ):
            incoming = MagicMock()
            incoming.content = "create dossier"
            await reload_chat.on_message(incoming)

        mock_handler.assert_awaited_once()
        # AC6: the handler's return value is wired back to the model as a tool_result
        # on the follow-up stream call (not just awaited and discarded).
        assert len(captured_calls) == 2
        tool_results = [
            block
            for message in captured_calls[1]["messages"]
            if isinstance(message.get("content"), list)
            for block in message["content"]
            if isinstance(block, dict) and block.get("type") == "tool_result"
        ]
        assert any(tr.get("content") == handler_return for tr in tool_results)

    async def test_dispatch_propose_structure_handler_error_is_caught(self, reload_chat):
        """P6: when _handle_propose_structure raises, the dispatch except branch
        feeds an 'Error calling propose_structure' tool_result back to the model."""
        tool_block = _make_fake_content_block(
            "tool_use",
            name="propose_structure",
            input={},
            id="toolu_ps_err",
        )
        text_block = _make_fake_content_block("text", "Recovered.")
        stream_with_tool = FakeStream(tokens=[], stop_reason="tool_use", content_blocks=[tool_block])
        stream_final = FakeStream(tokens=["Recovered."], stop_reason="end_turn", content_blocks=[text_block])
        call_count = 0
        captured_calls = []

        def fake_stream(**kwargs):
            nonlocal call_count
            call_count += 1
            captured_calls.append(kwargs)
            return stream_with_tool if call_count == 1 else stream_final

        msg_mock = _make_fake_cl_message()
        step_mock = AsyncMock()
        step_mock.__aenter__ = AsyncMock(return_value=step_mock)
        step_mock.__aexit__ = AsyncMock(return_value=False)
        step_mock.input = ""
        step_mock.output = ""

        doc_mock = MagicMock()
        doc_mock.props = {"content": "", "version": 0, "phase": "dossier"}

        with (
            patch("app.chat.cl.Message", return_value=msg_mock),
            patch(
                "app.chat.cl.user_session",
                _make_session_mock_with_history(dossier={"phase": "dossier"}, doc=doc_mock),
            ),
            patch("app.chat.client.messages.stream", side_effect=fake_stream),
            patch("app.chat.cl.Step", return_value=step_mock),
            patch(
                "app.chat._handle_propose_structure",
                new_callable=AsyncMock,
                side_effect=RuntimeError("boom"),
            ),
        ):
            incoming = MagicMock()
            incoming.content = "create dossier"
            await reload_chat.on_message(incoming)

        tool_results = [
            block
            for message in captured_calls[1]["messages"]
            if isinstance(message.get("content"), list)
            for block in message["content"]
            if isinstance(block, dict) and block.get("type") == "tool_result"
        ]
        assert any("Error calling propose_structure" in (tr.get("content") or "") for tr in tool_results)

    # ------------------------------------------------------------------
    # Registration tests
    # ------------------------------------------------------------------

    async def test_propose_structure_registered_in_dossier_phase(self, reload_chat):
        """AC1: propose_structure is in the tool list when phase is dossier."""
        msg_mock = _make_fake_cl_message()
        captured_call_kwargs = {}
        doc_mock = MagicMock()
        doc_mock.props = {"content": "", "version": 0}

        def fake_stream(**kwargs):
            captured_call_kwargs.update(kwargs)
            return FakeStream(["OK"])

        with (
            patch("app.chat.cl.Message", return_value=msg_mock),
            patch(
                "app.chat.cl.user_session",
                _make_session_mock_with_history(dossier={"phase": "dossier"}, doc=doc_mock),
            ),
            patch("app.chat.client.messages.stream", side_effect=fake_stream),
        ):
            incoming = MagicMock()
            incoming.content = "hello"
            await reload_chat.on_message(incoming)

        passed_names = [t["name"] for t in (captured_call_kwargs.get("tools") or [])]
        assert "propose_structure" in passed_names

    async def test_propose_structure_not_registered_in_investigating_phase(self, reload_chat):
        """AC1: propose_structure is NOT in the tool list during investigating phase."""
        msg_mock = _make_fake_cl_message()
        captured_call_kwargs = {}

        def fake_stream(**kwargs):
            captured_call_kwargs.update(kwargs)
            return FakeStream(["OK"])

        with (
            patch("app.chat.cl.Message", return_value=msg_mock),
            patch("app.chat.cl.user_session", _make_session_mock_with_history()),
            patch("app.chat.client.messages.stream", side_effect=fake_stream),
        ):
            incoming = MagicMock()
            incoming.content = "hello"
            await reload_chat.on_message(incoming)

        passed_names = [t["name"] for t in (captured_call_kwargs.get("tools") or [])]
        assert "propose_structure" not in passed_names


# ---------------------------------------------------------------------------
# MCP Tools in Dossier Session (Story 12.1)
# ---------------------------------------------------------------------------

_EPIC_1_MCP_TOOLS = (
    "search_indicators",
    "get_data",
    "get_metadata",
    "list_indicators",
    "get_disaggregation",
)


@pytest.mark.usefixtures("set_required_env_vars")
class TestMcpToolsInDossierSession:
    """Story 12.1: MCP tools available and dispatchable in investigating and dossier phases."""

    async def test_all_mcp_tools_present_in_investigating_phase(self, reload_chat):
        """AC1: all 5 MCP tools appear in combined_tools when phase is investigating."""
        tools = [{"name": n, "description": "x", "input_schema": {"type": "object"}} for n in _EPIC_1_MCP_TOOLS]
        msg_mock = _make_fake_cl_message()
        captured_call_kwargs = {}

        def fake_stream(**kwargs):
            captured_call_kwargs.update(kwargs)
            return FakeStream(["OK"])

        with (
            patch("app.chat.cl.Message", return_value=msg_mock),
            patch(
                "app.chat.cl.user_session",
                _make_session_mock_with_history(mcp_tools=tools, dossier={"phase": "investigating"}),
            ),
            patch("app.chat.client.messages.stream", side_effect=fake_stream),
        ):
            incoming = MagicMock()
            incoming.content = "hello"
            await reload_chat.on_message(incoming)

        passed_names = [t["name"] for t in (captured_call_kwargs.get("tools") or [])]
        assert set(_EPIC_1_MCP_TOOLS).issubset(set(passed_names))

    async def test_all_mcp_tools_present_in_dossier_phase(self, reload_chat):
        """AC1: all 5 MCP tools appear in combined_tools when phase is dossier; dossier tools also present."""
        tools = [{"name": n, "description": "x", "input_schema": {"type": "object"}} for n in _EPIC_1_MCP_TOOLS]
        msg_mock = _make_fake_cl_message()
        captured_call_kwargs = {}
        doc_mock = MagicMock()
        doc_mock.props = {"content": "", "version": 0}

        def fake_stream(**kwargs):
            captured_call_kwargs.update(kwargs)
            return FakeStream(["OK"])

        with (
            patch("app.chat.cl.Message", return_value=msg_mock),
            patch(
                "app.chat.cl.user_session",
                _make_session_mock_with_history(mcp_tools=tools, dossier={"phase": "dossier"}, doc=doc_mock),
            ),
            patch("app.chat.client.messages.stream", side_effect=fake_stream),
        ):
            incoming = MagicMock()
            incoming.content = "hello"
            await reload_chat.on_message(incoming)

        passed_names = [t["name"] for t in (captured_call_kwargs.get("tools") or [])]
        assert set(_EPIC_1_MCP_TOOLS).issubset(set(passed_names))
        assert "apply_ops" in passed_names
        assert "propose_structure" in passed_names
        assert "update_investigation_item" in passed_names

    async def test_mcp_tool_call_in_investigating_phase_routes_via_mcp_session(self, reload_chat):
        """AC2: MCP tool call routes through mcp_session.call_tool in investigating phase."""
        tool_block = _make_fake_content_block(
            "tool_use",
            name="search_indicators",
            input={"query": "deforestation"},
            id="toolu_si_01",
        )
        text_block = _make_fake_content_block("text", "Results found.")
        stream_with_tool = FakeStream(tokens=[], stop_reason="tool_use", content_blocks=[tool_block])
        stream_final = FakeStream(tokens=["Results found."], stop_reason="end_turn", content_blocks=[text_block])
        call_count = 0
        captured_calls = []

        def fake_stream(**kwargs):
            nonlocal call_count
            call_count += 1
            captured_calls.append(kwargs)
            return stream_with_tool if call_count == 1 else stream_final

        fake_mcp_result = MagicMock()
        fake_mcp_result.isError = False
        fake_text_content = MagicMock()
        fake_text_content.text = "OK_MCP_RESULT"
        fake_mcp_result.content = [fake_text_content]

        mcp_session = AsyncMock()
        mcp_session.call_tool = AsyncMock(return_value=fake_mcp_result)

        tools = [{"name": n, "description": "x", "input_schema": {"type": "object"}} for n in _EPIC_1_MCP_TOOLS]
        msg_mock = _make_fake_cl_message()
        step_mock = AsyncMock()
        step_mock.__aenter__ = AsyncMock(return_value=step_mock)
        step_mock.__aexit__ = AsyncMock(return_value=False)
        step_mock.input = ""
        step_mock.output = ""

        with (
            patch("app.chat.cl.Message", return_value=msg_mock),
            patch(
                "app.chat.cl.user_session",
                _make_session_mock_with_history(
                    mcp_session=mcp_session, mcp_tools=tools, dossier={"phase": "investigating"}
                ),
            ),
            patch("app.chat.client.messages.stream", side_effect=fake_stream),
            patch("app.chat.cl.Step", return_value=step_mock),
        ):
            incoming = MagicMock()
            incoming.content = "find deforestation data"
            await reload_chat.on_message(incoming)

        mcp_session.call_tool.assert_awaited_once_with("search_indicators", arguments={"query": "deforestation"})
        assert len(captured_calls) == 2
        tool_results = [
            block
            for message in captured_calls[1]["messages"]
            if isinstance(message.get("content"), list)
            for block in message["content"]
            if isinstance(block, dict) and block.get("type") == "tool_result"
        ]
        assert any(
            tr.get("content") == "OK_MCP_RESULT" and tr.get("tool_use_id") == "toolu_si_01" for tr in tool_results
        )

    async def test_mcp_tool_call_in_dossier_phase_routes_via_mcp_session(self, reload_chat):
        """AC2: MCP tool call routes through mcp_session.call_tool in dossier phase."""
        tool_block = _make_fake_content_block(
            "tool_use",
            name="get_data",
            input={"database_id": "WB_WDI", "indicator": "EN.ATM.CO2E.KT"},
            id="toolu_gd_01",
        )
        text_block = _make_fake_content_block("text", "Data retrieved.")
        stream_with_tool = FakeStream(tokens=[], stop_reason="tool_use", content_blocks=[tool_block])
        stream_final = FakeStream(tokens=["Data retrieved."], stop_reason="end_turn", content_blocks=[text_block])
        call_count = 0
        captured_calls = []

        def fake_stream(**kwargs):
            nonlocal call_count
            call_count += 1
            captured_calls.append(kwargs)
            return stream_with_tool if call_count == 1 else stream_final

        fake_mcp_result = MagicMock()
        fake_mcp_result.isError = False
        fake_text_content = MagicMock()
        fake_text_content.text = "OK_MCP_RESULT"
        fake_mcp_result.content = [fake_text_content]

        mcp_session = AsyncMock()
        mcp_session.call_tool = AsyncMock(return_value=fake_mcp_result)

        tools = [{"name": n, "description": "x", "input_schema": {"type": "object"}} for n in _EPIC_1_MCP_TOOLS]
        msg_mock = _make_fake_cl_message()
        doc_mock = MagicMock()
        doc_mock.props = {"content": "", "version": 0}
        step_mock = AsyncMock()
        step_mock.__aenter__ = AsyncMock(return_value=step_mock)
        step_mock.__aexit__ = AsyncMock(return_value=False)
        step_mock.input = ""
        step_mock.output = ""

        with (
            patch("app.chat.cl.Message", return_value=msg_mock),
            patch(
                "app.chat.cl.user_session",
                _make_session_mock_with_history(
                    mcp_session=mcp_session, mcp_tools=tools, dossier={"phase": "dossier"}, doc=doc_mock
                ),
            ),
            patch("app.chat.client.messages.stream", side_effect=fake_stream),
            patch("app.chat.cl.Step", return_value=step_mock),
        ):
            incoming = MagicMock()
            incoming.content = "get CO2 data"
            await reload_chat.on_message(incoming)

        mcp_session.call_tool.assert_awaited_once_with(
            "get_data", arguments={"database_id": "WB_WDI", "indicator": "EN.ATM.CO2E.KT"}
        )
        assert len(captured_calls) == 2
        tool_results = [
            block
            for message in captured_calls[1]["messages"]
            if isinstance(message.get("content"), list)
            for block in message["content"]
            if isinstance(block, dict) and block.get("type") == "tool_result"
        ]
        assert any(
            tr.get("content") == "OK_MCP_RESULT" and tr.get("tool_use_id") == "toolu_gd_01" for tr in tool_results
        )

    async def test_mcp_tool_call_with_no_session_returns_error_string(self, reload_chat):
        """AC3: when mcp_session is None, error string surfaces without crashing."""
        tool_block = _make_fake_content_block(
            "tool_use",
            name="search_indicators",
            input={"query": "deforestation"},
            id="toolu_si_02",
        )
        text_block = _make_fake_content_block("text", "Sorry, data unavailable.")
        stream_with_tool = FakeStream(tokens=[], stop_reason="tool_use", content_blocks=[tool_block])
        stream_final = FakeStream(
            tokens=["Sorry, data unavailable."], stop_reason="end_turn", content_blocks=[text_block]
        )
        call_count = 0
        captured_calls = []

        def fake_stream(**kwargs):
            nonlocal call_count
            call_count += 1
            captured_calls.append(kwargs)
            return stream_with_tool if call_count == 1 else stream_final

        tools = [{"name": n, "description": "x", "input_schema": {"type": "object"}} for n in _EPIC_1_MCP_TOOLS]
        msg_mock = _make_fake_cl_message()
        step_mock = AsyncMock()
        step_mock.__aenter__ = AsyncMock(return_value=step_mock)
        step_mock.__aexit__ = AsyncMock(return_value=False)
        step_mock.input = ""
        step_mock.output = ""

        with (
            patch("app.chat.cl.Message", return_value=msg_mock),
            patch(
                "app.chat.cl.user_session",
                _make_session_mock_with_history(mcp_session=None, mcp_tools=tools),
            ),
            patch("app.chat.client.messages.stream", side_effect=fake_stream),
            patch("app.chat.cl.Step", return_value=step_mock),
        ):
            incoming = MagicMock()
            incoming.content = "find deforestation data"
            await reload_chat.on_message(incoming)

        assert len(captured_calls) == 2
        tool_results = [
            block
            for message in captured_calls[1]["messages"]
            if isinstance(message.get("content"), list)
            for block in message["content"]
            if isinstance(block, dict) and block.get("type") == "tool_result"
        ]
        assert any(
            "Error: MCP server is not connected" in (tr.get("content") or "")
            and "search_indicators" in (tr.get("content") or "")
            for tr in tool_results
        )


# ---------------------------------------------------------------------------
# on_toggle_dossier (header toggle button)
# ---------------------------------------------------------------------------


@pytest.mark.usefixtures("set_required_env_vars")
class TestToggleDossier:
    """Tests for @cl.action_callback('toggle_dossier')."""

    @pytest.fixture
    def reload_chat(self):
        import importlib

        import app.chat as chat_module

        importlib.reload(chat_module)
        return chat_module

    async def test_toggle_closes_panel_when_revealed(self, reload_chat):
        """When dossier_revealed=True, toggle closes the sidebar and marks it closed."""
        stored: dict = {"dossier_revealed": True}
        sidebar = _make_sidebar_mock()
        action = MagicMock()

        with (
            patch("app.chat.cl.user_session") as session_mock,
            patch("app.chat.cl.ElementSidebar", sidebar),
        ):
            session_mock.get.side_effect = lambda k, default=None: stored.get(k, default)
            session_mock.set.side_effect = lambda k, v: stored.update({k: v})
            await reload_chat.on_toggle_dossier(action)

        # Close key carries the open-counter (0 when never opened in this session).
        sidebar.set_elements.assert_awaited_once_with([], key="closed-o0")
        assert stored.get("dossier_revealed") is False

    async def test_toggle_close_keys_distinct_across_open_close_cycles(self, reload_chat):
        """P2 regression: consecutive closes must use distinct keys so ElementSidebar
        (which ignores an unchanged key) does not no-op the second close."""
        stored: dict = {"dossier_revealed": True, "_sidebar_open_count": 1}
        sidebar = _make_sidebar_mock()
        action = MagicMock()

        with (
            patch("app.chat.cl.user_session") as session_mock,
            patch("app.chat.cl.ElementSidebar", sidebar),
        ):
            session_mock.get.side_effect = lambda k, default=None: stored.get(k, default)
            session_mock.set.side_effect = lambda k, v: stored.update({k: v})
            # First close at open_count=1, then simulate a reopen bumping the counter,
            # then a second close — the two close keys must differ.
            await reload_chat.on_toggle_dossier(action)
            stored["dossier_revealed"] = True
            stored["_sidebar_open_count"] = 2
            await reload_chat.on_toggle_dossier(action)

        close_keys = [c.kwargs["key"] for c in sidebar.set_elements.await_args_list]
        assert close_keys == ["closed-o1", "closed-o2"]
        assert len(set(close_keys)) == 2

    async def test_toggle_opens_panel_when_not_revealed(self, reload_chat):
        """When dossier_revealed=False, toggle calls reveal_dossier_canvas()."""
        stored: dict = {"dossier_revealed": False}
        action = MagicMock()

        with (
            patch("app.chat.cl.user_session") as session_mock,
            patch("app.chat.reveal_dossier_canvas", new=AsyncMock()) as reveal_mock,
        ):
            session_mock.get.side_effect = lambda k, default=None: stored.get(k, default)
            session_mock.set.side_effect = lambda k, v: stored.update({k: v})
            await reload_chat.on_toggle_dossier(action)

        reveal_mock.assert_awaited_once()
        # set_elements NOT called directly (reveal_dossier_canvas handles it)

    async def test_toggle_opens_panel_when_state_absent(self, reload_chat):
        """When dossier_revealed is not set (None/falsy), toggle opens the panel."""
        stored: dict = {}
        action = MagicMock()

        with (
            patch("app.chat.cl.user_session") as session_mock,
            patch("app.chat.reveal_dossier_canvas", new=AsyncMock()) as reveal_mock,
        ):
            session_mock.get.side_effect = lambda k, default=None: stored.get(k, default)
            session_mock.set.side_effect = lambda k, v: stored.update({k: v})
            await reload_chat.on_toggle_dossier(action)

        reveal_mock.assert_awaited_once()


@pytest.mark.usefixtures("set_required_env_vars")
class TestDataValidationGate:
    """Story 12.2: search_indicators gate, session flag, and prompt directives."""

    # ------------------------------------------------------------------
    # AC1: Prompt directs the LLM to call search_indicators at item 5
    # ------------------------------------------------------------------

    def test_investigation_prompt_directs_search_indicators_at_item_5(self, reload_chat):
        """AC1: INVESTIGATION_SYSTEM_PROMPT explicitly directs search_indicators call at item 5."""
        from app.prompts import INVESTIGATION_SYSTEM_PROMPT

        assert "search_indicators" in INVESTIGATION_SYSTEM_PROMPT
        assert "Found 12 relevant indicators" in INVESTIGATION_SYSTEM_PROMPT

    # ------------------------------------------------------------------
    # AC2: Gate rejects data_sources_validation without a successful search
    # ------------------------------------------------------------------

    def test_data_sources_validation_rejected_without_search(self, reload_chat):
        """AC2: update_investigation_item returns error when flag is False."""
        store = {
            "investigation": reload_chat._empty_investigation_state(),
            "dossier": {"phase": "investigating"},
            "_data_validation_indicators_found": False,
        }
        with patch("app.chat.cl.user_session") as session_mock:
            session_mock.get.side_effect = lambda k, default=None: store.get(k, default)
            session_mock.set = MagicMock(side_effect=lambda k, v: store.update({k: v}))
            result = reload_chat.update_investigation_item("data_sources_validation", "Found something")

        assert "error" in result
        assert "no indicators have been found" in result["error"]
        # State must not have been mutated (set was never called with "investigation")
        investigation_set_calls = [c for c in session_mock.set.call_args_list if c.args[0] == "investigation"]
        assert investigation_set_calls == []

    def test_data_sources_validation_accepted_with_search(self, reload_chat):
        """AC2: update_investigation_item succeeds when flag is True."""
        store = {
            "investigation": reload_chat._empty_investigation_state(),
            "dossier": {"phase": "investigating"},
            "_data_validation_indicators_found": True,
        }
        with patch("app.chat.cl.user_session") as session_mock:
            session_mock.get.side_effect = lambda k, default=None: store.get(k, default)
            session_mock.set.side_effect = lambda k, v: store.update({k: v})
            result = reload_chat.update_investigation_item("data_sources_validation", "Found 12 indicators")

        assert result.get("status") == "ok"
        assert "phase_gate_reached" in result
        # The item must actually be persisted as done — a regression that returned
        # status:ok without writing item 5 back to state would otherwise pass.
        assert store["investigation"]["data_sources_validation"] == {
            "done": True,
            "value": "Found 12 indicators",
        }

    # ------------------------------------------------------------------
    # AC3: _record_search_indicators_outcome helper unit tests
    # ------------------------------------------------------------------

    def test_record_search_indicators_outcome_sets_flag_on_success(self, reload_chat):
        """AC3: flag is set when search_indicators returns success=True and total_count>=1."""
        import json as _json

        tool_output = _json.dumps(
            {"success": True, "total_count": 12, "returned_count": 12, "data": [{"x": 1}], "truncated": False}
        )
        with patch("app.chat.cl.user_session") as session_mock:
            session_mock.set = MagicMock()
            reload_chat._record_search_indicators_outcome("search_indicators", tool_output)

        session_mock.set.assert_called_once_with(reload_chat._DATA_VALIDATION_FLAG, True)

    def test_record_search_indicators_outcome_does_not_set_flag_on_zero_count(self, reload_chat):
        """AC3: flag is NOT set when total_count is 0."""
        import json as _json

        tool_output = _json.dumps(
            {"success": True, "total_count": 0, "returned_count": 0, "data": [], "truncated": False}
        )
        with patch("app.chat.cl.user_session") as session_mock:
            session_mock.set = MagicMock()
            reload_chat._record_search_indicators_outcome("search_indicators", tool_output)

        flag = reload_chat._DATA_VALIDATION_FLAG
        flag_set_calls = [c for c in session_mock.set.call_args_list if c.args == (flag, True)]
        assert flag_set_calls == []

    def test_record_search_indicators_outcome_does_not_set_flag_on_error_response(self, reload_chat):
        """AC3: flag is NOT set when the response has success=False."""
        import json as _json

        tool_output = _json.dumps({"success": False, "error": "api_error", "error_type": "api_error"})
        with patch("app.chat.cl.user_session") as session_mock:
            session_mock.set = MagicMock()
            reload_chat._record_search_indicators_outcome("search_indicators", tool_output)

        flag = reload_chat._DATA_VALIDATION_FLAG
        flag_set_calls = [c for c in session_mock.set.call_args_list if c.args == (flag, True)]
        assert flag_set_calls == []

    def test_record_search_indicators_outcome_does_not_set_flag_on_missing_total_count(self, reload_chat):
        """AC3: a success response missing total_count defaults to 0 and does NOT set the flag."""
        import json as _json

        tool_output = _json.dumps({"success": True, "returned_count": 3, "data": [{}, {}, {}], "truncated": False})
        with patch("app.chat.cl.user_session") as session_mock:
            session_mock.set = MagicMock()
            reload_chat._record_search_indicators_outcome("search_indicators", tool_output)

        flag = reload_chat._DATA_VALIDATION_FLAG
        flag_set_calls = [c for c in session_mock.set.call_args_list if c.args == (flag, True)]
        assert flag_set_calls == []

    def test_record_search_indicators_outcome_handles_non_coercible_total_count(self, reload_chat):
        """AC3: a non-coercible total_count is swallowed (no raise) and does NOT set the flag."""
        import json as _json

        tool_output = _json.dumps({"success": True, "total_count": "not-a-number", "data": [{}], "truncated": False})
        with patch("app.chat.cl.user_session") as session_mock:
            session_mock.set = MagicMock()
            # Must not raise
            reload_chat._record_search_indicators_outcome("search_indicators", tool_output)

        flag = reload_chat._DATA_VALIDATION_FLAG
        flag_set_calls = [c for c in session_mock.set.call_args_list if c.args == (flag, True)]
        assert flag_set_calls == []

    def test_record_search_indicators_outcome_is_noop_for_other_tools(self, reload_chat):
        """AC3: tool-name guard makes the helper a no-op for non-search_indicators tools."""
        import json as _json

        tool_output = _json.dumps(
            {"success": True, "total_count": 5, "returned_count": 5, "data": [{}], "truncated": False}
        )
        with patch("app.chat.cl.user_session") as session_mock:
            session_mock.set = MagicMock()
            reload_chat._record_search_indicators_outcome("get_data", tool_output)

        session_mock.set.assert_not_called()

    def test_record_search_indicators_outcome_handles_non_json(self, reload_chat):
        """AC3: non-JSON tool output does not raise — logs at debug and returns."""
        with patch("app.chat.cl.user_session") as session_mock:
            session_mock.set = MagicMock()
            # Must not raise
            reload_chat._record_search_indicators_outcome("search_indicators", "not JSON")

        flag = reload_chat._DATA_VALIDATION_FLAG
        flag_set_calls = [c for c in session_mock.set.call_args_list if c.args == (flag, True)]
        assert flag_set_calls == []

    async def test_dispatch_loop_calls_record_helper_after_mcp_call(self, reload_chat):
        """AC3 e2e: the agentic loop sets the flag after a successful search_indicators MCP call."""
        import json as _json

        tool_block = _make_fake_content_block(
            "tool_use",
            name="search_indicators",
            input={"query": "water access", "country": "BRA"},
            id="toolu_search_01",
        )
        text_block = _make_fake_content_block("text", "Found indicators.")
        stream_with_tool = FakeStream(tokens=[], stop_reason="tool_use", content_blocks=[tool_block])
        stream_final = FakeStream(tokens=["Found indicators."], stop_reason="end_turn", content_blocks=[text_block])
        call_count = 0

        def fake_stream(**kwargs):
            nonlocal call_count
            call_count += 1
            return stream_with_tool if call_count == 1 else stream_final

        fake_mcp_content = MagicMock()
        fake_mcp_content.text = _json.dumps(
            {"success": True, "total_count": 5, "returned_count": 5, "data": [{}], "truncated": False}
        )
        fake_mcp_result = MagicMock()
        fake_mcp_result.isError = False
        fake_mcp_result.content = [fake_mcp_content]

        fake_mcp_session = AsyncMock()
        fake_mcp_session.call_tool = AsyncMock(return_value=fake_mcp_result)

        tools = [{"name": "search_indicators", "description": "Search", "input_schema": {"type": "object"}}]
        msg_mock = _make_fake_cl_message()
        step_mock = AsyncMock()
        step_mock.__aenter__ = AsyncMock(return_value=step_mock)
        step_mock.__aexit__ = AsyncMock(return_value=False)
        step_mock.input = ""
        step_mock.output = ""

        store: dict = {
            "history": [],
            "mcp_session": fake_mcp_session,
            "mcp_tools": tools,
            "dossier": {"phase": "investigating"},
            "investigation": reload_chat._empty_investigation_state(),
            "_data_validation_indicators_found": False,
        }

        with (
            patch("app.chat.cl.Message", return_value=msg_mock),
            patch("app.chat.cl.user_session") as session_mock,
            patch("app.chat.client.messages.stream", side_effect=fake_stream),
            patch("app.chat.cl.Step", return_value=step_mock),
        ):
            session_mock.get.side_effect = lambda k, default=None: store.get(k, default)
            session_mock.set.side_effect = lambda k, v: store.update({k: v})
            incoming = MagicMock()
            incoming.content = "Find water access indicators for Brazil"
            await reload_chat.on_message(incoming)

        # The flag must have been set to True after the successful MCP call
        assert store.get("_data_validation_indicators_found") is True

    def test_join_tool_result_text_does_not_truncate_large_success(self, reload_chat):
        """Regression: _join_tool_result_text returns the FULL text even when it exceeds
        tool_result_max_chars, so the data-validation recorder can json.loads it.
        (_extract_tool_result_text truncates; the recorder must not see truncated text.)"""
        import json as _json

        big_payload = _json.dumps(
            {
                "success": True,
                "total_count": 12,
                "returned_count": 4000,
                "data": [{"INDICATOR": "EN.ATM.CO2E.PC", "val": i} for i in range(4000)],
                "truncated": False,
            }
        )
        assert len(big_payload) > reload_chat.settings.tool_result_max_chars
        result = MagicMock()
        result.isError = False
        block = MagicMock()
        block.text = big_payload
        result.content = [block]

        full = reload_chat._join_tool_result_text(result)
        # Untruncated and still valid JSON.
        assert full == big_payload
        assert "[... truncated" not in full
        assert _json.loads(full)["total_count"] == 12

    async def test_dispatch_loop_sets_flag_for_large_search_result(self, reload_chat):
        """Regression (12.2 deferred HIGH): a search_indicators result large enough to be
        truncated by _extract_tool_result_text must STILL set the validation flag, so item 5
        is markable and the phase gate is reachable. Before the fix, json.loads on the
        truncated text raised → flag never set → deadlock."""
        import json as _json

        tool_block = _make_fake_content_block(
            "tool_use",
            name="search_indicators",
            input={"query": "water access", "country": "BRA"},
            id="toolu_search_big",
        )
        text_block = _make_fake_content_block("text", "Found many indicators.")
        stream_with_tool = FakeStream(tokens=[], stop_reason="tool_use", content_blocks=[tool_block])
        stream_final = FakeStream(
            tokens=["Found many indicators."], stop_reason="end_turn", content_blocks=[text_block]
        )
        call_count = 0

        def fake_stream(**kwargs):
            nonlocal call_count
            call_count += 1
            return stream_with_tool if call_count == 1 else stream_final

        big_payload = _json.dumps(
            {
                "success": True,
                "total_count": 12,
                "returned_count": 4000,
                "data": [{"INDICATOR": "EN.ATM.CO2E.PC", "val": i} for i in range(4000)],
                "truncated": False,
            }
        )
        assert len(big_payload) > reload_chat.settings.tool_result_max_chars
        fake_mcp_content = MagicMock()
        fake_mcp_content.text = big_payload
        fake_mcp_result = MagicMock()
        fake_mcp_result.isError = False
        fake_mcp_result.content = [fake_mcp_content]

        fake_mcp_session = AsyncMock()
        fake_mcp_session.call_tool = AsyncMock(return_value=fake_mcp_result)

        tools = [{"name": "search_indicators", "description": "Search", "input_schema": {"type": "object"}}]
        msg_mock = _make_fake_cl_message()
        step_mock = AsyncMock()
        step_mock.__aenter__ = AsyncMock(return_value=step_mock)
        step_mock.__aexit__ = AsyncMock(return_value=False)
        step_mock.input = ""
        step_mock.output = ""

        store: dict = {
            "history": [],
            "mcp_session": fake_mcp_session,
            "mcp_tools": tools,
            "dossier": {"phase": "investigating"},
            "investigation": reload_chat._empty_investigation_state(),
            "_data_validation_indicators_found": False,
        }

        with (
            patch("app.chat.cl.Message", return_value=msg_mock),
            patch("app.chat.cl.user_session") as session_mock,
            patch("app.chat.client.messages.stream", side_effect=fake_stream),
            patch("app.chat.cl.Step", return_value=step_mock),
        ):
            session_mock.get.side_effect = lambda k, default=None: store.get(k, default)
            session_mock.set.side_effect = lambda k, v: store.update({k: v})
            incoming = MagicMock()
            incoming.content = "Find water access indicators for Brazil"
            await reload_chat.on_message(incoming)

        # Even though the result was truncated for the model, the flag is set from the
        # un-truncated text.
        assert store.get("_data_validation_indicators_found") is True

    # ------------------------------------------------------------------
    # AC4: Prompt directs key-stats capture via update_investigation_item
    # ------------------------------------------------------------------

    def test_investigation_prompt_directs_key_stats_capture(self, reload_chat):
        """AC4: INVESTIGATION_SYSTEM_PROMPT directs get_data + update_investigation_item for key_stats_capture."""
        from app.prompts import INVESTIGATION_SYSTEM_PROMPT

        assert "key_stats_capture" in INVESTIGATION_SYSTEM_PROMPT
        assert "update_investigation_item" in INVESTIGATION_SYSTEM_PROMPT
        assert "indicator_code" in INVESTIGATION_SYSTEM_PROMPT
        assert "values_by_year" in INVESTIGATION_SYSTEM_PROMPT


# ---------------------------------------------------------------------------
# Story 12.3 helpers
# ---------------------------------------------------------------------------


def _make_api_ref(
    source="World Development Indicators",
    indicator_code="EG_ELC_ACCS_ZS",
    indicator_name="Access to electricity",
    database_id="WB_WDI",
    years="2022",
) -> dict:
    """Build a minimal deduped API reference dict as output of deduplicate_references."""
    return {
        "id": 1,
        "source": source,
        "indicator_code": indicator_code,
        "indicator_name": indicator_name,
        "database_id": database_id,
        "years": years,
        "type": "api",
    }


def _make_get_data_mcp_result_with_citation() -> str:
    """JSON string that extract_references will turn into one API ref."""
    import json

    return json.dumps(
        {
            "success": True,
            "data": [
                {
                    "CITATION_SOURCE": "World Development Indicators",
                    "INDICATOR": "WB_WDI_EG_ELC_ACCS_ZS",
                    "DATABASE_ID": "WB_WDI",
                    "TIME_PERIOD": "2022",
                    "COMMENT_TS": "Access to electricity",
                }
            ],
            "total_count": 1,
            "returned_count": 1,
            "truncated": False,
        }
    )


@pytest.mark.usefixtures("set_required_env_vars")
class TestCitationFlowIntoDossierSections:
    """Story 12.3: Inline citation format, Methodology section sync, and round-finalisation wiring."""

    # ------------------------------------------------------------------
    # AC1: DOSSIER_SYSTEM_PROMPT directive with concrete worked example
    # ------------------------------------------------------------------

    def test_dossier_prompt_directs_inline_citation_with_example(self, reload_chat):
        """AC1: DOSSIER_SYSTEM_PROMPT includes DATA_SOURCE directive, format spec, and a worked example."""
        from app.prompts import DOSSIER_SYSTEM_PROMPT

        assert "DATA_SOURCE" in DOSSIER_SYSTEM_PROMPT
        assert "(<DATA_SOURCE>, <INDICATOR>, <year or year range>)" in DOSSIER_SYSTEM_PROMPT
        # Distinctive fragment from the worked example
        assert "WB_WDI_EG_ELC_ACCS_ZS" in DOSSIER_SYSTEM_PROMPT

    # ------------------------------------------------------------------
    # AC3: Methodology-section non-edit rule in the prompt
    # ------------------------------------------------------------------

    def test_dossier_prompt_warns_against_editing_methodology_section(self, reload_chat):
        """AC3: DOSSIER_SYSTEM_PROMPT contains the three required phrases that make up the rule."""
        from app.prompts import DOSSIER_SYSTEM_PROMPT

        assert "Methodology and Sources" in DOSSIER_SYSTEM_PROMPT
        assert "automatically" in DOSSIER_SYSTEM_PROMPT
        assert "apply_ops" in DOSSIER_SYSTEM_PROMPT

    # ------------------------------------------------------------------
    # AC2: _sync_dossier_references_section helper — existing heading
    # ------------------------------------------------------------------

    async def test_sync_dossier_references_replaces_existing_methodology_section(self, reload_chat):
        """AC2: helper replaces everything from the heading to EOF with the fresh refs block."""
        import json as _json

        stale_placeholder = "[Document data sources and methodology here.]\n"
        doc = MagicMock()
        doc.props = {
            "content": f"# Exec\n\n[stuff]\n\n## Methodology and Sources\n\n{stale_placeholder}",
            "version": 1,
            "phase": "dossier",
        }
        doc.content = _json.dumps(doc.props)
        doc.update = AsyncMock()
        refs = [_make_api_ref()]

        with patch("app.chat._refresh_dossier_canvas", new_callable=AsyncMock) as mock_refresh:
            await reload_chat._sync_dossier_references_section(doc, refs)

        # Content starts correctly, ends with refs block, has exactly one heading
        assert doc.props["content"].startswith("# Exec")
        assert doc.props["content"].count("## Methodology and Sources") == 1
        assert "World Development Indicators" in doc.props["content"]
        # Version bumped
        assert doc.props["version"] == 2
        # re-sync invariant
        assert doc.content == _json.dumps(doc.props)
        # update and refresh both awaited
        doc.update.assert_awaited_once()
        mock_refresh.assert_awaited_once()

    # ------------------------------------------------------------------
    # AC2: _sync_dossier_references_section helper — heading absent
    # ------------------------------------------------------------------

    async def test_sync_dossier_references_appends_section_when_heading_absent(self, reload_chat):
        """AC2: when heading is absent, refs block is appended as a new section at the end."""
        import json as _json

        doc = MagicMock()
        doc.props = {"content": "# Exec\n\nNo methodology heading.\n", "version": 1, "phase": "dossier"}
        doc.content = _json.dumps(doc.props)
        doc.update = AsyncMock()
        refs = [_make_api_ref()]

        with patch("app.chat._refresh_dossier_canvas", new_callable=AsyncMock):
            await reload_chat._sync_dossier_references_section(doc, refs)

        content = doc.props["content"]
        assert "## Methodology and Sources" in content
        # Heading appears at the end (no content after the refs block except whitespace)
        heading_idx = content.index("## Methodology and Sources")
        assert heading_idx > content.index("# Exec")
        assert "World Development Indicators" in content[heading_idx:]

    # ------------------------------------------------------------------
    # AC2: _sync_dossier_references_section — no-op guard
    # ------------------------------------------------------------------

    async def test_sync_dossier_references_is_noop_when_content_unchanged(self, reload_chat):
        """AC2: second call with same refs is a no-op — version and update count unchanged."""
        import json as _json

        doc = MagicMock()
        doc.props = {
            "content": "# Exec\n\n[stuff]\n\n## Methodology and Sources\n\n[stale placeholder]\n",
            "version": 1,
            "phase": "dossier",
        }
        doc.content = _json.dumps(doc.props)
        doc.update = AsyncMock()
        refs = [_make_api_ref()]

        with patch("app.chat._refresh_dossier_canvas", new_callable=AsyncMock):
            # First call — should write
            await reload_chat._sync_dossier_references_section(doc, refs)
            assert doc.props["version"] == 2
            assert doc.update.await_count == 1

            # Second call with identical refs — should be a no-op
            await reload_chat._sync_dossier_references_section(doc, refs)

        assert doc.props["version"] == 2
        assert doc.update.await_count == 1  # no second update

    # ------------------------------------------------------------------
    # Code-review 2026-05-30: heading match must be line-anchored
    # ------------------------------------------------------------------

    async def test_sync_dossier_references_does_not_false_match_deeper_heading(self, reload_chat):
        """Code-review 2026-05-30 (line-anchor patch): a deeper "### Methodology and Sources"
        heading must NOT be consumed as the system-owned section. The H3 and its body survive
        intact, no orphaned "#" is left from a mid-line split, and a single fresh H2 section
        is appended at the end."""
        import json as _json

        doc = MagicMock()
        doc.props = {
            "content": "# Exec\n\n### Methodology and Sources\n\nJournalist's own notes.\n",
            "version": 1,
            "phase": "dossier",
        }
        doc.content = _json.dumps(doc.props)
        doc.update = AsyncMock()
        refs = [_make_api_ref()]

        with patch("app.chat._refresh_dossier_canvas", new_callable=AsyncMock):
            await reload_chat._sync_dossier_references_section(doc, refs)

        content = doc.props["content"]
        # The journalist's deeper heading and its body are untouched.
        assert "### Methodology and Sources" in content
        assert "Journalist's own notes." in content
        # No orphaned "#" fragment from a mid-line substring split (the pre-patch partition bug).
        assert "\n#\n" not in content
        # Exactly one real, line-anchored H2 section — the freshly appended one.
        assert len(reload_chat._METHODOLOGY_HEADING_RE.findall(content)) == 1
        # The refs block lands after the journalist's notes (appended at the end).
        assert content.index("World Development Indicators") > content.index("Journalist's own notes.")

    # ------------------------------------------------------------------
    # AC4: round-finalisation skips sync when no refs
    # ------------------------------------------------------------------

    async def test_round_finalisation_skips_dossier_sync_when_no_refs(self, reload_chat):
        """AC4: when all_tool_outputs is empty (no tool calls), _sync_dossier_references_section is not called."""
        msg_mock = _make_fake_cl_message()
        doc_mock = MagicMock()
        doc_mock.props = {"content": "# Exec\n\n## Methodology and Sources\n\n[placeholder]\n", "version": 1}

        with (
            patch("app.chat.cl.Message", return_value=msg_mock),
            patch(
                "app.chat.cl.user_session",
                _make_session_mock_with_history(dossier={"phase": "dossier"}, doc=doc_mock),
            ),
            patch("app.chat.client.messages.stream", return_value=FakeStream(["Answer."], stop_reason="end_turn")),
            patch("app.chat._sync_dossier_references_section", new_callable=AsyncMock) as mock_sync,
        ):
            incoming = MagicMock()
            incoming.content = "Just a question, no data needed."
            await reload_chat.on_message(incoming)

        mock_sync.assert_not_awaited()

    # ------------------------------------------------------------------
    # AC4: round-finalisation skips sync in investigating phase
    # ------------------------------------------------------------------

    async def test_round_finalisation_skips_dossier_sync_in_investigating_phase(self, reload_chat):
        """AC4: when in investigating phase, sync is not called even if refs exist; chat ref block fires."""
        tool_block = _make_fake_content_block(
            "tool_use",
            name="get_data",
            input={"database_id": "WB_WDI", "indicator": "EG.ELC.ACCS.ZS"},
            id="toolu_gd_inv",
        )
        text_block = _make_fake_content_block("text", "Here are the findings.")
        stream_tool = FakeStream(tokens=[], stop_reason="tool_use", content_blocks=[tool_block])
        final_tokens = ["Here are the findings."]
        stream_final = FakeStream(tokens=final_tokens, stop_reason="end_turn", content_blocks=[text_block])
        call_count = 0

        def fake_stream(**kwargs):
            nonlocal call_count
            call_count += 1
            return stream_tool if call_count == 1 else stream_final

        fake_mcp = AsyncMock()
        fake_mcp_result = MagicMock()
        fake_mcp_result.isError = False
        fake_text = MagicMock()
        fake_text.text = _make_get_data_mcp_result_with_citation()
        fake_mcp_result.content = [fake_text]
        fake_mcp.call_tool = AsyncMock(return_value=fake_mcp_result)

        tools = [{"name": n, "description": "x", "input_schema": {"type": "object"}} for n in _EPIC_1_MCP_TOOLS]
        msg_mock = _make_fake_cl_message()
        step_mock = AsyncMock()
        step_mock.__aenter__ = AsyncMock(return_value=step_mock)
        step_mock.__aexit__ = AsyncMock(return_value=False)
        step_mock.input = ""
        step_mock.output = ""

        with (
            patch("app.chat.cl.Message", return_value=msg_mock),
            patch(
                "app.chat.cl.user_session",
                _make_session_mock_with_history(
                    mcp_session=fake_mcp, mcp_tools=tools, dossier={"phase": "investigating"}
                ),
            ),
            patch("app.chat.client.messages.stream", side_effect=fake_stream),
            patch("app.chat.cl.Step", return_value=step_mock),
            patch("app.chat._sync_dossier_references_section", new_callable=AsyncMock) as mock_sync,
        ):
            incoming = MagicMock()
            incoming.content = "What electricity data is available?"
            await reload_chat.on_message(incoming)

        # Dossier sync must NOT fire in investigating phase
        mock_sync.assert_not_awaited()
        # Chat-side ref block MUST fire (existing Story 9.1 behaviour preserved)
        assert "World Development Indicators" in msg_mock.content

    # ------------------------------------------------------------------
    # AC2: round-finalisation calls sync in dossier phase
    # ------------------------------------------------------------------

    async def test_round_finalisation_calls_dossier_sync_in_dossier_phase(self, reload_chat):
        """AC2: when in dossier phase with a doc and refs present, _sync_dossier_references_section is called."""
        tool_block = _make_fake_content_block(
            "tool_use",
            name="get_data",
            input={"database_id": "WB_WDI", "indicator": "EG.ELC.ACCS.ZS"},
            id="toolu_gd_dos",
        )
        text_block = _make_fake_content_block("text", "Data added to dossier.")
        stream_tool = FakeStream(tokens=[], stop_reason="tool_use", content_blocks=[tool_block])
        stream_final = FakeStream(
            tokens=["Data added to dossier."], stop_reason="end_turn", content_blocks=[text_block]
        )
        call_count = 0

        def fake_stream(**kwargs):
            nonlocal call_count
            call_count += 1
            return stream_tool if call_count == 1 else stream_final

        fake_mcp = AsyncMock()
        fake_mcp_result = MagicMock()
        fake_mcp_result.isError = False
        fake_text = MagicMock()
        fake_text.text = _make_get_data_mcp_result_with_citation()
        fake_mcp_result.content = [fake_text]
        fake_mcp.call_tool = AsyncMock(return_value=fake_mcp_result)

        tools = [{"name": n, "description": "x", "input_schema": {"type": "object"}} for n in _EPIC_1_MCP_TOOLS]
        msg_mock = _make_fake_cl_message()
        doc_mock = MagicMock()
        doc_mock.props = {"content": "# Exec\n\n## Methodology and Sources\n\n[placeholder]\n", "version": 1}
        step_mock = AsyncMock()
        step_mock.__aenter__ = AsyncMock(return_value=step_mock)
        step_mock.__aexit__ = AsyncMock(return_value=False)
        step_mock.input = ""
        step_mock.output = ""

        with (
            patch("app.chat.cl.Message", return_value=msg_mock),
            patch(
                "app.chat.cl.user_session",
                _make_session_mock_with_history(
                    mcp_session=fake_mcp, mcp_tools=tools, dossier={"phase": "dossier"}, doc=doc_mock
                ),
            ),
            patch("app.chat.client.messages.stream", side_effect=fake_stream),
            patch("app.chat.cl.Step", return_value=step_mock),
            patch("app.chat._sync_dossier_references_section", new_callable=AsyncMock) as mock_sync,
        ):
            incoming = MagicMock()
            incoming.content = "Add electricity data to the dossier."
            await reload_chat.on_message(incoming)

        # Sync must have been called exactly once with (doc_mock, refs)
        mock_sync.assert_awaited_once()
        call_args = mock_sync.call_args
        assert call_args[0][0] is doc_mock
        refs_arg = call_args[0][1]
        assert len(refs_arg) == 1
        assert refs_arg[0]["type"] == "api"
        assert refs_arg[0]["source"] == "World Development Indicators"
        # Chat-side ref block also fires
        assert "World Development Indicators" in msg_mock.content


@pytest.mark.usefixtures("set_required_env_vars")
class TestNoDataHandling:
    """Story 12.4: no-data and API-error narration directives in investigation and dossier prompts."""

    # ------------------------------------------------------------------
    # AC1: zero-indicator copy in INVESTIGATION_SYSTEM_PROMPT
    # ------------------------------------------------------------------

    def test_investigation_prompt_handles_zero_search_results(self, reload_chat):
        """AC1: INVESTIGATION_SYSTEM_PROMPT contains the verbatim zero-indicators copy."""
        from app.prompts import INVESTIGATION_SYSTEM_PROMPT

        assert "No indicators found for [topic] in [geography]. Try broader terms" in INVESTIGATION_SYSTEM_PROMPT

    # ------------------------------------------------------------------
    # AC2: empty get_data copy + don't-capture rule in INVESTIGATION_SYSTEM_PROMPT
    # ------------------------------------------------------------------

    def test_investigation_prompt_handles_empty_get_data(self, reload_chat):
        """AC2: INVESTIGATION_SYSTEM_PROMPT contains the verbatim empty-get_data copy and don't-capture rule."""
        from app.prompts import INVESTIGATION_SYSTEM_PROMPT

        assert "No data available for [indicator] in [geography/year range]" in INVESTIGATION_SYSTEM_PROMPT
        # Don't-capture directive must be a contiguous phrase tying "Do NOT" to key_stats_capture,
        # so the test fails if the AC2 line is dropped (substring "key_stats_capture"/"Do NOT" alone
        # also match the unrelated KEY STATS CAPTURE block and the AC4 block).
        assert (
            'Do NOT include that indicator\'s stats in update_investigation_item("key_stats_capture"'
            in INVESTIGATION_SYSTEM_PROMPT
        )
        # Recovery sentence (AC2 third clause) must be present.
        assert (
            "Try a different time range or check another indicator from the search results"
            in INVESTIGATION_SYSTEM_PROMPT
        )

    # ------------------------------------------------------------------
    # AC4: API error copy distinct from zero-results in INVESTIGATION_SYSTEM_PROMPT
    # ------------------------------------------------------------------

    def test_investigation_prompt_distinguishes_api_error_from_no_data(self, reload_chat):
        """AC4: INVESTIGATION_SYSTEM_PROMPT has both verbatim strings as separate directives."""
        from app.prompts import INVESTIGATION_SYSTEM_PROMPT

        prompt = INVESTIGATION_SYSTEM_PROMPT
        assert "The data service returned an error" in prompt
        assert "No indicators found" in prompt
        # Distinctness: the two failure modes must live under separate, ordered headers — not be
        # merged into one directive. This catches a regression that lumps API errors with no-data.
        zero_idx = prompt.index("Zero indicators found")
        err_idx = prompt.index("API error response")
        assert zero_idx < err_idx
        # Each verbatim string sits under its own header.
        assert zero_idx < prompt.index("No indicators found for [topic]") < err_idx
        assert prompt.index("The data service returned an error") > err_idx

    # ------------------------------------------------------------------
    # AC3: empty-indicator rule in DOSSIER_SYSTEM_PROMPT
    # ------------------------------------------------------------------

    def test_dossier_prompt_forbids_empty_indicator_sections(self, reload_chat):
        """AC3: DOSSIER_SYSTEM_PROMPT contains the empty-indicator avoidance rule and preserves 12.3 directives."""
        from app.prompts import DOSSIER_SYSTEM_PROMPT

        # New rule from 12.4
        assert "empty data array" in DOSSIER_SYSTEM_PROMPT
        assert "DO NOT insert" in DOSSIER_SYSTEM_PROMPT
        # Regression guard: 12.3 inline-citation directive must still be present
        assert "(<DATA_SOURCE>, <INDICATOR>, <year or year range>)" in DOSSIER_SYSTEM_PROMPT
        assert "WB_WDI_EG_ELC_ACCS_ZS" in DOSSIER_SYSTEM_PROMPT
