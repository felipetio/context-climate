import asyncio
import json
import logging
import os
from contextlib import AsyncExitStack
from typing import Any

import anthropic
import chainlit as cl
from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client

import app.data  # noqa: F401  # registers Chainlit data layer
from app.citations import deduplicate_references, extract_references, format_reference_list
from app.config import settings
from app.prompts import get_system_prompt

# ---------------------------------------------------------------------------
# RAG upload constants (used only when DATA360_RAG_ENABLED=true)
# ---------------------------------------------------------------------------

_ACCEPTED_MIME_TYPES = {
    "application/pdf",
    "text/plain",
    "text/markdown",
    "text/csv",
}

# ---------------------------------------------------------------------------
# Authentication
# ---------------------------------------------------------------------------

# Demo credentials — override via env vars for non-default setups.
# Defaults: demo / demo (suitable for local development only).
_AUTH_USERNAME = os.getenv("CHAINLIT_DEMO_USERNAME", "demo")
_AUTH_PASSWORD = os.getenv("CHAINLIT_DEMO_PASSWORD", "demo")


@cl.password_auth_callback
def auth_callback(username: str, password: str):
    """Password auth using credentials from env vars (CHAINLIT_DEMO_USERNAME / CHAINLIT_DEMO_PASSWORD).

    Defaults to demo/demo for local development.
    Set these env vars to change credentials without modifying code.
    """
    if username == _AUTH_USERNAME and password == _AUTH_PASSWORD:
        return cl.User(identifier=username, metadata={"role": "user"})
    return None


logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Dossier canvas (Epic 10)
# ---------------------------------------------------------------------------


async def open_dossier_canvas() -> None:
    doc = cl.CustomElement(
        name="Document",
        props={"content": "", "version": 0, "phase": "investigating"},
        display="inline",
    )
    await cl.ElementSidebar.set_title("Dossier")
    await cl.ElementSidebar.set_elements([doc], key="dossier-canvas")
    cl.user_session.set("doc", doc)


async def update_dossier_content(content: str) -> None:
    doc = cl.user_session.get("doc")
    if doc is None:
        return
    doc.props["content"] = content
    doc.props["version"] += 1
    await doc.update()


# ---------------------------------------------------------------------------
# apply_ops patch engine (Story 10.3)
# ---------------------------------------------------------------------------


APPLY_OPS_TOOL: dict[str, Any] = {
    "name": "apply_ops",
    "description": (
        "Apply a sequence of ops to the dossier document. "
        "Each op references exact existing text where applicable. "
        "Use small, surgical ops. Quote anchor text exactly as it appears."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "ops": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "type": {
                            "enum": [
                                "replace",
                                "insert_after",
                                "insert_before",
                                "delete",
                                "append",
                                "prepend",
                            ]
                        },
                        "find": {
                            "type": "string",
                            "description": ("Exact text to locate. Required for replace, delete."),
                        },
                        "anchor": {
                            "type": "string",
                            "description": ("Exact text to locate. Required for insert_after, insert_before."),
                        },
                        "content": {
                            "type": "string",
                            "description": ("New text. Required for replace, insert_*, append, prepend."),
                        },
                    },
                    "required": ["type"],
                },
            },
            "summary": {
                "type": "string",
                "description": "One-line explanation of what changed, shown in chat.",
            },
        },
        "required": ["ops", "summary"],
    },
}


def apply_single_op(content: str, op: dict) -> tuple[str, str | None]:
    """Apply a single op to `content` and return `(new_content, error | None)`.

    Pure string transform — no Chainlit session access so it can be unit-tested.
    On error, returns the input content unchanged plus an error message.
    """
    op_type = op["type"]

    if op_type in ("replace", "delete"):
        find = op.get("find", "")
        count = content.count(find)
        if count == 0:
            return content, f"Text not found: '{find}'"
        if count > 1:
            return content, f"Ambiguous match for '{find}' — found {count} times, be more specific"
        if op_type == "replace":
            return content.replace(find, op.get("content", ""), 1), None
        return content.replace(find, "", 1), None

    if op_type in ("insert_after", "insert_before"):
        anchor = op.get("anchor", "")
        count = content.count(anchor)
        if count == 0:
            return content, f"Anchor not found: '{anchor}'"
        if count > 1:
            return content, f"Ambiguous anchor '{anchor}' — found {count} times, be more specific"
        new_text = op.get("content", "")
        if op_type == "insert_after":
            return content.replace(anchor, anchor + "\n\n" + new_text, 1), None
        return content.replace(anchor, new_text + "\n\n" + anchor, 1), None

    if op_type == "append":
        new_text = op.get("content", "")
        return (content + "\n\n" + new_text).strip(), None

    if op_type == "prepend":
        new_text = op.get("content", "")
        return (new_text + "\n\n" + content).strip(), None

    return content, f"Unknown op type: '{op_type}'"


async def _handle_apply_ops(tool_input: dict) -> str:
    """Apply a list of ops to the dossier document, streaming updates per-op.

    Returns "ok" on success, or an error string on the first op that fails.
    """
    doc = cl.user_session.get("doc")
    if doc is None:
        return "Error: dossier canvas is not open"

    current_content: str = doc.props.get("content", "")
    ops: list[dict] = tool_input.get("ops", [])

    for op in ops:
        new_content, err = apply_single_op(current_content, op)
        if err is not None:
            return err
        current_content = new_content
        doc.props["content"] = current_content
        doc.props["version"] = int(doc.props.get("version", 0)) + 1
        await doc.update()
        await asyncio.sleep(0.03)

    dossier = cl.user_session.get("dossier")
    if isinstance(dossier, dict):
        dossier["content"] = current_content
        dossier["version"] = doc.props.get("version", 0)

    summary = tool_input.get("summary", "")
    if summary:
        await cl.Message(content=summary).send()
    return "ok"


# ---------------------------------------------------------------------------
# RAG upload helper
# ---------------------------------------------------------------------------


async def _process_upload_element(element: cl.File) -> str | None:  # type: ignore[name-defined]
    """Process a single uploaded file element via the RAG pipeline.

    Sends status messages to the user and calls process_upload().
    Returns a context string to inject into the LLM history on success,
    or an error string prefixed with 'ERROR:' so on_message can include
    it as context, or None if processing should be silently skipped.

    This function is only called when DATA360_RAG_ENABLED=true.
    """
    # Lazy imports — avoids loading asyncpg / sentence-transformers when RAG is off.
    import app.db as _app_db  # noqa: PLC0415
    from mcp_server.rag.processor import process_upload  # noqa: PLC0415

    filename = element.name or "uploaded_file"
    mime_type = element.mime or ""
    file_path = element.path  # Chainlit writes the file to a temp path

    # --- MIME type check ---
    if mime_type not in _ACCEPTED_MIME_TYPES:
        msg = f"Unsupported file type '{mime_type}'. Please upload a PDF, TXT, MD, or CSV file."
        await cl.Message(content=f"⚠️ {msg}").send()
        return f"ERROR: {msg}"

    # --- Size check ---
    limit_mb = settings.rag_max_upload_mb
    try:
        size_bytes = os.path.getsize(file_path)
    except OSError:
        size_bytes = 0
    size_mb = size_bytes / (1024 * 1024)
    if size_mb > limit_mb:
        msg = f"File '{filename}' is too large ({size_mb:.1f} MB). Maximum allowed size is {limit_mb} MB."
        await cl.Message(content=f"⚠️ {msg}").send()
        return f"ERROR: {msg}"

    # --- Pool availability check ---
    if _app_db.pool is None:
        msg = "RAG database is not available. The document could not be processed and is not searchable."
        await cl.Message(content=f"❌ {msg}").send()
        return f"ERROR: {msg}"

    # --- Processing ---
    await cl.Message(content="⏳ Processing document...").send()
    try:

        def _read_file() -> bytes:
            with open(file_path, "rb") as fh:  # noqa: ASYNC230
                return fh.read()

        file_bytes = await asyncio.to_thread(_read_file)
        async with _app_db.pool.acquire() as conn:
            result = await process_upload(
                conn=conn,
                filename=filename,
                mime_type=mime_type,
                file_bytes=file_bytes,
            )

        if isinstance(result, dict) and not result.get("success", True):
            error_msg = result.get("error", "Unknown error")
            await cl.Message(content=f"❌ Failed to process document: {error_msg}.").send()
            return f"ERROR: Failed to process document '{filename}': {error_msg}"

        n_chunks = result.get("chunk_count", "?") if isinstance(result, dict) else "?"
        await cl.Message(
            content=f"✅ Document ready for search ({n_chunks} chunks). You can now ask questions about it."
        ).send()
        return (
            f"Document '{filename}' successfully processed and indexed ({n_chunks} chunks)."
            " It is now available for semantic search via the search_documents tool."
        )

    except Exception as exc:
        logger.error("Upload processing failed for '%s': %s", filename, exc)
        msg = str(exc)
        await cl.Message(content=f"❌ Failed to process document: {msg}.").send()
        return f"ERROR: Upload processing failed for '{filename}': {msg}"


# MCP session key used in cl.user_session
_MCP_SESSION_KEY = "mcp_session"
_MCP_TOOLS_KEY = "mcp_tools"
_MCP_EXIT_STACK_KEY = "mcp_exit_stack"


def _make_client():
    return anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)


client = _make_client()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _mcp_tools_to_anthropic(mcp_tools: list) -> list[dict[str, Any]]:
    """Convert MCP Tool objects to the Anthropic tools parameter format."""
    result = []
    for tool in mcp_tools:
        result.append(
            {
                "name": tool.name,
                "description": tool.description or "",
                "input_schema": tool.inputSchema,
            }
        )
    return result


def _extract_tool_result_text(call_result) -> str:
    """Extract text from an MCP CallToolResult, handling errors."""
    if call_result.isError:
        # Surface the error to Claude so it can narrate gracefully
        parts = []
        for block in call_result.content:
            if hasattr(block, "text"):
                parts.append(block.text)
        return "Error: " + (" ".join(parts) if parts else "Unknown MCP tool error")

    parts = []
    for block in call_result.content:
        if hasattr(block, "text"):
            parts.append(block.text)
    text = "\n".join(parts) if parts else ""

    max_chars = settings.tool_result_max_chars
    if len(text) > max_chars:
        text = text[:max_chars] + "\n\n[... truncated, results too large ...]"
    return text


# ---------------------------------------------------------------------------
# Chainlit handlers
# ---------------------------------------------------------------------------


@cl.on_chat_resume
async def on_chat_resume(thread: dict) -> None:
    """Restore conversation history when a user resumes a previous thread."""
    history: list[dict[str, Any]] = []
    steps = thread.get("steps", [])
    for step in steps:
        step_type = step.get("type", "")
        output = step.get("output", "")
        if not output:
            continue
        if step_type == "user_message":
            history.append({"role": "user", "content": output})
        elif step_type == "assistant_message":
            history.append({"role": "assistant", "content": output})
    # Trim to the configured history limit
    max_msgs = settings.conversation_history_limit
    history = history[-max_msgs:]
    cl.user_session.set("history", history)

    # Close any existing MCP stack before reconnecting (prevents connection leaks)
    existing_stack = cl.user_session.get(_MCP_EXIT_STACK_KEY)
    if existing_stack:
        try:
            await existing_stack.aclose()
        except Exception:
            logger.warning("Failed to close existing MCP stack on resume", exc_info=True)

    cl.user_session.set(_MCP_SESSION_KEY, None)
    cl.user_session.set(_MCP_TOOLS_KEY, [])
    cl.user_session.set(_MCP_EXIT_STACK_KEY, None)

    stack = AsyncExitStack()
    try:
        read, write, _ = await stack.enter_async_context(streamablehttp_client(url=settings.mcp_server_url))
        session = await stack.enter_async_context(ClientSession(read, write))
        await session.initialize()
        result = await session.list_tools()
        tools = _mcp_tools_to_anthropic(result.tools)

        cl.user_session.set(_MCP_SESSION_KEY, session)
        cl.user_session.set(_MCP_TOOLS_KEY, tools)
        cl.user_session.set(_MCP_EXIT_STACK_KEY, stack)
        logger.info("MCP reconnected on resume: %d tools available", len(tools))
    except Exception:
        logger.warning("MCP reconnect failed on resume, continuing without tools", exc_info=True)
        await stack.aclose()


@cl.on_chat_start
async def on_chat_start():
    cl.user_session.set("dossier", {"phase": "investigating", "content": "", "version": 0})
    await open_dossier_canvas()

    cl.user_session.set("history", [])
    cl.user_session.set(_MCP_SESSION_KEY, None)
    cl.user_session.set(_MCP_TOOLS_KEY, [])
    cl.user_session.set(_MCP_EXIT_STACK_KEY, None)

    # Initialise the asyncpg pool for RAG uploads when running via `chainlit run`.
    # (The FastAPI lifespan in app/main.py handles this when running via uvicorn,
    # but chainlit run bypasses that lifespan entirely.)
    if settings.rag_enabled:
        import asyncpg as _asyncpg  # noqa: PLC0415

        import app.db as _app_db_init  # noqa: PLC0415

        if _app_db_init.pool is None:
            try:
                _app_db_init.pool = await _asyncpg.create_pool(settings.database_url, min_size=1, max_size=5)
                logger.info("RAG asyncpg pool initialised (chainlit-run path)")
            except Exception:
                logger.warning("RAG asyncpg pool init failed — uploads will be unavailable", exc_info=True)

    # Auto-connect to MCP server
    stack = AsyncExitStack()
    try:
        read, write, _ = await stack.enter_async_context(streamablehttp_client(url=settings.mcp_server_url))
        session = await stack.enter_async_context(ClientSession(read, write))
        await session.initialize()
        result = await session.list_tools()
        tools = _mcp_tools_to_anthropic(result.tools)

        cl.user_session.set(_MCP_SESSION_KEY, session)
        cl.user_session.set(_MCP_TOOLS_KEY, tools)
        cl.user_session.set(_MCP_EXIT_STACK_KEY, stack)
        logger.info("MCP auto-connected: %d tools available", len(tools))
    except Exception:
        logger.warning("MCP auto-connect failed, continuing without tools", exc_info=True)
        await stack.aclose()

    await cl.Message(content="Welcome to Context Climate! Ask me about World Bank climate and development data.").send()


@cl.on_chat_end
async def on_chat_end():
    stack: AsyncExitStack | None = cl.user_session.get(_MCP_EXIT_STACK_KEY)
    if stack:
        try:
            await stack.aclose()
        except Exception:
            logger.warning("Error closing MCP connection", exc_info=True)


@cl.on_message
async def on_message(message: cl.Message):
    # --- RAG upload handling (only when RAG is enabled) ---
    upload_context_parts: list[str] = []
    if settings.rag_enabled and message.elements:
        for element in message.elements:
            if isinstance(element, cl.File):
                result = await _process_upload_element(element)
                if result:
                    upload_context_parts.append(result)

    # If message has ONLY attachments and no text, skip the agentic loop
    # (applies regardless of RAG setting — empty content causes API errors)
    if not message.content.strip():
        return

    # Retrieve conversation history and append new user turn.
    # Prepend any upload results so Claude knows what happened before answering.
    history = cl.user_session.get("history", [])
    user_content = message.content
    if upload_context_parts:
        context_block = "[Upload results]\n" + "\n".join(upload_context_parts)
        user_content = f"{context_block}\n\n{user_content}"
    history.append({"role": "user", "content": user_content})

    # Trim to the last N messages in the conversation history
    max_msgs = settings.conversation_history_limit
    history = history[-max_msgs:]

    # Persist trimmed history immediately
    cl.user_session.set("history", history)

    # Get MCP tools and session (may be None/empty if MCP not connected)
    mcp_session: ClientSession | None = cl.user_session.get(_MCP_SESSION_KEY)
    tools: list[dict[str, Any]] = cl.user_session.get(_MCP_TOOLS_KEY) or []

    msg = cl.Message(content="")
    await msg.send()

    try:
        # Mutable copy of history for the agentic loop
        loop_history = list(history)

        await _agentic_loop(loop_history, tools, mcp_session, msg)

        await msg.update()

        # Append assistant reply to persistent history (use msg.content for consistency
        # with what was actually streamed to the user)
        history.append({"role": "assistant", "content": msg.content})
        cl.user_session.set("history", history)

    except Exception as e:
        logger.exception("Error during message handling: %s", e)
        await msg.remove()
        await cl.Message(content="⚠️ Sorry, I couldn't reach the AI service. Please try again.").send()


async def _agentic_loop(
    history: list[dict[str, Any]],
    tools: list[dict[str, Any]],
    mcp_session: ClientSession | None,
    msg: cl.Message,
) -> str:
    """
    Drive the Claude agentic loop:
      1. Call Claude (with tools if available).
      2. If Claude returns tool_use blocks, execute them via MCP and append results.
      3. Repeat until Claude returns a final text response (stop_reason != "tool_use").
      4. Stream the final text response token by token.

    Returns the final assembled text.
    """
    call_kwargs: dict[str, Any] = {
        "model": settings.claude_model,
        "max_tokens": settings.claude_max_tokens,
        "system": get_system_prompt(
            rag_enabled=settings.rag_enabled,
            staleness_threshold_years=settings.staleness_threshold_years,
        ),
    }
    # Always register the local apply_ops tool alongside MCP tools.
    # Story 10.4 will gate it on dossier phase via the system prompt.
    combined_tools = list(tools) + [APPLY_OPS_TOOL]
    call_kwargs["tools"] = combined_tools

    max_rounds = settings.max_tool_rounds
    tool_round = 0
    all_tool_outputs: list[str] = []

    while True:
        tool_round += 1
        if tool_round > max_rounds:
            logger.error("Exceeded maximum tool rounds (%d), aborting agentic loop.", max_rounds)
            return (
                "I'm sorry, but I had to stop because I exceeded the maximum number "
                "of tool calls. Please try rephrasing or simplifying your request."
            )
        call_kwargs["messages"] = history

        async with client.messages.stream(**call_kwargs) as stream:
            tokens: list[str] = []
            async for text_token in stream.text_stream:
                tokens.append(text_token)
                await msg.stream_token(text_token)

            final_message = await stream.get_final_message()

        stop_reason = final_message.stop_reason

        if stop_reason != "tool_use":
            final_text = "".join(tokens)

            # Build deterministic Data Sources block from collected tool outputs (Story 9.1)
            raw_refs = extract_references(all_tool_outputs)
            if raw_refs:
                refs = deduplicate_references(raw_refs)
                ref_block = "\n\n" + format_reference_list(refs)
                await msg.stream_token(ref_block)
                final_text += ref_block
                # Attach structured references to message metadata for Story 9.2/9.3
                msg.metadata = {"references": refs}

            return final_text

        # Reset the UI message for the next iteration so intermediate
        # "thinking" text from tool-use rounds doesn't leak to the user.
        msg.content = ""

        # --- Handle tool_use blocks ---
        # Append assistant response (may contain both text and tool_use blocks)
        assistant_content = final_message.content  # list of content blocks
        history.append({"role": "assistant", "content": [b.model_dump(exclude_none=True) for b in assistant_content]})

        # Process each tool_use block
        tool_results = []
        for block in assistant_content:
            if block.type != "tool_use":
                continue

            tool_name = block.name
            tool_input = block.input
            tool_use_id = block.id

            # Show intermediate step in UI
            async with cl.Step(name=f"🔧 {tool_name}", type="tool") as step:
                step.input = json.dumps(tool_input, indent=2)

                if tool_name == "apply_ops":
                    try:
                        tool_output = await _handle_apply_ops(tool_input)
                    except Exception as exc:
                        logger.error("apply_ops failed: %s", exc)
                        tool_output = f"Error applying ops: {exc}"
                elif mcp_session is not None:
                    try:
                        call_result = await mcp_session.call_tool(tool_name, arguments=tool_input)
                        tool_output = _extract_tool_result_text(call_result)
                    except Exception as exc:
                        logger.error("MCP tool call failed for %s: %s", tool_name, exc)
                        tool_output = f"Error calling tool '{tool_name}': {exc}"
                else:
                    tool_output = (
                        f"Error: MCP server is not connected. Cannot call tool '{tool_name}'. "
                        "The Data360 API is currently unavailable."
                    )

                step.output = tool_output[:500] + "…" if len(tool_output) > 500 else tool_output
                all_tool_outputs.append(tool_output)

            tool_results.append(
                {
                    "type": "tool_result",
                    "tool_use_id": tool_use_id,
                    "content": tool_output,
                }
            )

        # Append tool results to history and loop
        history.append({"role": "user", "content": tool_results})
