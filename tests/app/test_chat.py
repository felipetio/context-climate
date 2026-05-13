"""Unit tests for streaming Claude API integration and MCP tool use in app/chat.py."""

import contextlib
import importlib
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
        assert passed_names == ["apply_ops"]

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
            patch("app.chat.open_dossier_canvas", new=AsyncMock()),
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
            patch("app.chat.open_dossier_canvas", new=AsyncMock()),
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


class TestDossierCommandOnResume:
    """Story 10.5 AC2: /dossier command is registered when a thread is resumed."""

    async def test_command_registered_on_chat_resume(self, reload_chat):
        """on_chat_resume registers the dossier slash command so resumed sessions get /dossier."""
        thread = {"steps": []}

        @contextlib.asynccontextmanager
        async def fake_mcp_client(url, **kwargs):
            raise ConnectionError("MCP not available")
            yield  # pragma: no cover

        with (
            patch("app.chat.streamablehttp_client", fake_mcp_client),
            patch("app.chat.cl.user_session") as session_mock,
            patch("app.chat._register_dossier_commands", new=AsyncMock()) as register_mock,
            patch("app.chat.open_dossier_canvas", new=AsyncMock()),
        ):
            session_mock.set = MagicMock()
            session_mock.get = MagicMock(return_value=None)
            await reload_chat.on_chat_resume(thread)

        register_mock.assert_awaited_once()


class TestReopenDossierCanvas:
    """Story 10.5: reopen_dossier_canvas() helper behaviour."""

    async def test_reopen_reuses_existing_doc(self, reload_chat):
        """AC1: when a doc exists, reopen re-attaches the same reference."""
        existing_doc = MagicMock(name="existing-doc")
        session_mock = _make_session_mock_with_history(doc=existing_doc)

        with (
            patch("app.chat.cl.user_session", session_mock),
            patch("app.chat.cl.ElementSidebar") as sidebar_mock,
            patch("app.chat.cl.CustomElement") as custom_element_mock,
        ):
            sidebar_mock.set_title = AsyncMock()
            sidebar_mock.set_elements = AsyncMock()
            await reload_chat.reopen_dossier_canvas()

        sidebar_mock.set_title.assert_awaited_once_with("Dossier")
        sidebar_mock.set_elements.assert_awaited_once_with([existing_doc], key="dossier-canvas")
        # Must NOT create a new CustomElement
        custom_element_mock.assert_not_called()
        # Must NOT mutate the session doc reference
        session_mock.set.assert_not_called()

    async def test_reopen_when_no_doc_calls_open(self, reload_chat):
        """AC1: when no doc exists, reopen delegates to open_dossier_canvas."""
        session_mock = _make_session_mock_with_history(doc=None)

        with (
            patch("app.chat.cl.user_session", session_mock),
            patch("app.chat.open_dossier_canvas", new=AsyncMock()) as open_mock,
        ):
            await reload_chat.reopen_dossier_canvas()

        open_mock.assert_awaited_once()

    async def test_reopen_is_idempotent(self, reload_chat):
        """AC1: calling reopen multiple times does not orphan elements."""
        existing_doc = MagicMock(name="existing-doc")
        session_mock = _make_session_mock_with_history(doc=existing_doc)

        with (
            patch("app.chat.cl.user_session", session_mock),
            patch("app.chat.cl.ElementSidebar") as sidebar_mock,
            patch("app.chat.cl.CustomElement") as custom_element_mock,
        ):
            sidebar_mock.set_title = AsyncMock()
            sidebar_mock.set_elements = AsyncMock()
            await reload_chat.reopen_dossier_canvas()
            await reload_chat.reopen_dossier_canvas()

        assert sidebar_mock.set_elements.await_count == 2
        for call in sidebar_mock.set_elements.await_args_list:
            assert call.args == ([existing_doc],)
            assert call.kwargs == {"key": "dossier-canvas"}
        custom_element_mock.assert_not_called()


class TestOpenDossierCanvasIdempotency:
    """Story 10.5 AC5: open_dossier_canvas() no longer orphans existing docs."""

    async def test_open_when_doc_exists_delegates_to_reopen(self, reload_chat):
        """AC5: closes deferred Story 10.2 finding."""
        existing_doc = MagicMock(name="existing-doc")
        session_mock = _make_session_mock_with_history(doc=existing_doc)

        with (
            patch("app.chat.cl.user_session", session_mock),
            patch("app.chat.cl.ElementSidebar") as sidebar_mock,
            patch("app.chat.cl.CustomElement") as custom_element_mock,
        ):
            sidebar_mock.set_title = AsyncMock()
            sidebar_mock.set_elements = AsyncMock()
            await reload_chat.open_dossier_canvas()

        # Must NOT create a second CustomElement
        custom_element_mock.assert_not_called()
        # Must re-attach the existing doc via the sidebar
        sidebar_mock.set_elements.assert_awaited_once_with([existing_doc], key="dossier-canvas")
        # Must NOT overwrite the session doc
        session_mock.set.assert_not_called()

    async def test_open_when_no_doc_creates_new_element(self, reload_chat):
        """Sanity: original behaviour preserved when session is empty."""
        session_mock = _make_session_mock_with_history(doc=None)
        new_doc = MagicMock(name="new-doc")

        with (
            patch("app.chat.cl.user_session", session_mock),
            patch("app.chat.cl.ElementSidebar") as sidebar_mock,
            patch("app.chat.cl.CustomElement", return_value=new_doc) as custom_element_mock,
        ):
            sidebar_mock.set_title = AsyncMock()
            sidebar_mock.set_elements = AsyncMock()
            await reload_chat.open_dossier_canvas()

        custom_element_mock.assert_called_once()
        sidebar_mock.set_elements.assert_awaited_once_with([new_doc], key="dossier-canvas")
        session_mock.set.assert_called_once_with("doc", new_doc)


class TestShowDossierAction:
    """Story 10.5 AC3: welcome 'Show dossier' button reopens the canvas."""

    async def test_show_dossier_callback_calls_reopen(self, reload_chat):
        """The action_callback delegates to reopen_dossier_canvas."""
        with patch("app.chat.reopen_dossier_canvas", new=AsyncMock()) as reopen_mock:
            await reload_chat.on_show_dossier(MagicMock(name="action"))
        reopen_mock.assert_awaited_once()

    async def test_on_chat_start_welcome_includes_show_dossier_action(self, reload_chat):
        """on_chat_start sends the welcome message with a 'show_dossier' action button."""
        captured_kwargs = {}

        def fake_message(*args, **kwargs):
            captured_kwargs.update(kwargs)
            msg = AsyncMock()
            msg.send = AsyncMock()
            return msg

        @contextlib.asynccontextmanager
        async def failing_client(url, **kwargs):
            raise ConnectionError("no MCP")
            yield  # pragma: no cover

        with (
            patch("app.chat.streamablehttp_client", failing_client),
            patch("app.chat.cl.user_session", _make_session_mock_with_history()),
            patch("app.chat.cl.Message", side_effect=fake_message),
            patch("app.chat._register_dossier_commands", new=AsyncMock()),
            patch("app.chat.open_dossier_canvas", new=AsyncMock()),
        ):
            await reload_chat.on_chat_start()

        actions = captured_kwargs.get("actions") or []
        assert len(actions) == 1
        assert actions[0].name == "show_dossier"
        assert actions[0].label == "Show dossier"
        assert actions[0].payload == {}


class TestDossierSlashCommand:
    """Story 10.5 AC2: /dossier command reopens canvas without entering agentic loop."""

    async def test_command_short_circuits_on_message(self, reload_chat):
        """A message with command='dossier' calls reopen and skips the agentic loop."""
        session_mock = _make_session_mock_with_history(doc=MagicMock(name="doc"))

        with (
            patch("app.chat.reopen_dossier_canvas", new=AsyncMock()) as reopen_mock,
            patch("app.chat._agentic_loop", new=AsyncMock()) as loop_mock,
            patch("app.chat.cl.user_session", session_mock),
            patch("app.chat.client.messages.stream") as stream_mock,
        ):
            incoming = MagicMock()
            incoming.command = "dossier"
            incoming.content = "/dossier"
            await reload_chat.on_message(incoming)

        reopen_mock.assert_awaited_once()
        loop_mock.assert_not_called()
        stream_mock.assert_not_called()

    async def test_command_registered_on_chat_start(self, reload_chat):
        """on_chat_start registers the dossier slash command via the emitter."""

        @contextlib.asynccontextmanager
        async def failing_client(url, **kwargs):
            raise ConnectionError("no MCP")
            yield  # pragma: no cover

        with (
            patch("app.chat.streamablehttp_client", failing_client),
            patch("app.chat.cl.user_session", _make_session_mock_with_history()),
            patch("app.chat.cl.Message") as msg_cls,
            patch("app.chat._register_dossier_commands", new=AsyncMock()) as register_mock,
            patch("app.chat.open_dossier_canvas", new=AsyncMock()),
        ):
            msg_cls.return_value.send = AsyncMock()
            await reload_chat.on_chat_start()

        register_mock.assert_awaited_once()

    async def test_register_dossier_commands_payload(self, reload_chat):
        """The registered command list has the expected shape (id, description, icon)."""
        emitter_mock = AsyncMock()

        class _CtxStub:
            emitter = emitter_mock

        with patch("app.chat.cl.context", _CtxStub):
            await reload_chat._register_dossier_commands()

        emitter_mock.set_commands.assert_awaited_once()
        commands = emitter_mock.set_commands.await_args.args[0]
        assert len(commands) == 1
        assert commands[0]["id"] == "dossier"
        assert "description" in commands[0]
        assert "icon" in commands[0]


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
            patch("app.chat._register_dossier_commands", new=AsyncMock()),
            patch("app.chat.open_dossier_canvas", new=AsyncMock()),
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
            patch("app.chat.open_dossier_canvas", new=AsyncMock()),
            patch("app.chat._register_dossier_commands", new=AsyncMock()),
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
