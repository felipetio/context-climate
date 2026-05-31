import asyncio
import base64
import json
import logging
import os
import re
from contextlib import AsyncExitStack
from typing import Any

import anthropic
import chainlit as cl
import markdown
from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client

import app.data  # noqa: F401  # registers Chainlit data layer
from app.citations import deduplicate_references, extract_references, format_reference_list
from app.config import settings
from app.prompts import DOSSIER_SYSTEM_PROMPT, INVESTIGATION_SYSTEM_PROMPT

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

# Optional PDF export (Story 14.4). weasyprint needs system libs (pango/cairo);
# if it (or they) are unavailable, degrade gracefully — the "⬇ PDF" button just
# hides and the rest of the dossier keeps working.
try:
    from weasyprint import HTML as WeasyHTML

    WEASYPRINT_AVAILABLE = True
except Exception as exc:  # pragma: no cover - depends on system libs
    WeasyHTML = None
    WEASYPRINT_AVAILABLE = False
    logger.warning("weasyprint unavailable; PDF export disabled: %s", exc)


# ---------------------------------------------------------------------------
# Dossier canvas (Epic 10)
# ---------------------------------------------------------------------------


_INVESTIGATION_ITEMS: tuple[str, ...] = (
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

_PHASE_GATE_ITEMS: frozenset[str] = frozenset(
    ["topic_definition", "geography_scope", "time_range", "target_audience", "data_sources_validation"]
)


def _empty_investigation_state() -> dict[str, dict[str, Any]]:
    return {item: {"done": False, "value": None} for item in _INVESTIGATION_ITEMS}


def _format_investigation_snapshot(state: dict[str, dict[str, Any]]) -> str:
    """Render a deterministic, ordered snapshot of the investigation checklist
    for inclusion in the system prompt. Order follows `_INVESTIGATION_ITEMS`.
    """
    lines = ["[Investigation state:"]
    for item in _INVESTIGATION_ITEMS:
        entry = state.get(item) if isinstance(state, dict) else None
        done = bool(entry.get("done")) if isinstance(entry, dict) else False
        marker = "x" if done else " "
        value_repr = ""
        if done and isinstance(entry, dict) and entry.get("value") is not None:
            # Collapse newlines so each item stays on exactly one line, then cap
            # length to keep the snapshot bounded (Story 11.1 Dev Notes).
            value_repr = str(entry.get("value")).replace("\r", " ").replace("\n", " ").strip()
            if len(value_repr) > 120:
                value_repr = value_repr[:117] + "..."
        if value_repr:
            lines.append(f"  [{marker}] {item}: {value_repr}")
        else:
            lines.append(f"  [{marker}] {item}")
    lines.append("]")
    return "\n".join(lines)


def update_investigation_item(item_id: str, value: Any) -> dict[str, Any]:
    """Mark an investigation checklist item as complete and return status."""
    if item_id not in _INVESTIGATION_ITEMS:
        return {"error": f"Unknown item_id: '{item_id}'"}

    if item_id == "data_sources_validation":
        if not cl.user_session.get(_DATA_VALIDATION_FLAG, False):
            return {
                "error": (
                    "data_sources_validation cannot be marked done — no indicators "
                    "have been found this session. Call search_indicators first."
                )
            }

    state = cl.user_session.get("investigation")
    if not isinstance(state, dict):
        state = _empty_investigation_state()
        cl.user_session.set("investigation", state)

    state[item_id] = {"done": True, "value": value}
    # Write back unconditionally — do not rely on cl.user_session.get() returning a
    # live mutable reference (robust if a session backend ever returns a copy).
    cl.user_session.set("investigation", state)
    logger.debug("[INVESTIGATION] item=%s status=complete value=%s", item_id, value)

    items_done = sum(1 for v in state.values() if isinstance(v, dict) and v.get("done"))
    gate_reached = all(isinstance(state.get(k), dict) and bool(state[k].get("done")) for k in _PHASE_GATE_ITEMS)
    if gate_reached:
        dossier = cl.user_session.get("dossier")
        if not isinstance(dossier, dict):
            logger.warning("[INVESTIGATION] phase_gate=reached but dossier key is not a dict — phase not flipped")
        elif dossier.get("phase") != "dossier":
            dossier["phase"] = "dossier"
            cl.user_session.set("dossier", dossier)
            logger.debug("[INVESTIGATION] phase_gate=reached, transitioning to dossier mode")
    return {
        "status": "ok",
        "item": item_id,
        "items_done": items_done,
        "phase_gate_reached": gate_reached,
    }


async def update_dossier_content(content: str) -> None:
    doc = cl.user_session.get("doc")
    if doc is None:
        return
    doc.props["content"] = content
    # html_content (Story 14.1) and pdf_data_url (Story 14.4) are derived display
    # props. Raw Markdown in doc.props["content"] stays the source of truth for
    # edits/downloads. Both are recomputed from content via _apply_derived_props.
    await _apply_derived_props(doc, content)
    doc.props["version"] += 1
    doc.content = json.dumps(doc.props)  # re-sync: CustomElement.content is set only once
    await doc.update()
    await _refresh_dossier_canvas()


async def _apply_derived_props(doc: cl.CustomElement, content: str, *, render_pdf: bool = True) -> None:
    """Recompute the derived display props (``html_content``, ``pdf_data_url``) from
    raw Markdown ``content`` and set them on ``doc.props``.

    Centralizes the Story 14.1/14.4 derivation so every content-mutation path keeps
    the rendered preview and PDF export in sync with ``doc.props["content"]``. Does
    NOT bump version, re-serialize ``doc.content``, or refresh — the caller owns
    that ordering (the props must be set BEFORE ``doc.content = json.dumps(...)``).

    ``render_pdf=False`` skips the (~0.5s) PDF render and clears ``pdf_data_url`` —
    used for intermediate streaming frames so the button hides mid-edit and the
    per-frame payload stays small; the final frame renders the PDF.
    """
    html_content = markdown.markdown(content, extensions=["tables", "fenced_code"])
    doc.props["html_content"] = html_content
    doc.props["pdf_data_url"] = await _render_pdf_data_url(html_content) if render_pdf else None


async def _render_pdf_data_url(html_content: str) -> str | None:
    """Render dossier HTML to a base64 ``data:application/pdf`` URL, or None.

    Returns None (so ``Document.jsx`` hides the PDF button) when weasyprint is
    unavailable or rendering raises — PDF export is best-effort and must never
    break the dossier update (Story 14.4 AC5). The render runs in a worker thread
    so the synchronous, CPU-bound weasyprint call never blocks the event loop.
    """
    if not WEASYPRINT_AVAILABLE:
        return None
    try:
        full_html = (
            f"<html><body style='font-family:sans-serif;max-width:800px;margin:2cm auto'>{html_content}</body></html>"
        )
        pdf_bytes = await asyncio.to_thread(WeasyHTML(string=full_html).write_pdf)
        return "data:application/pdf;base64," + base64.b64encode(pdf_bytes).decode()
    except Exception as exc:
        logger.warning("PDF generation failed; hiding PDF export: %s", exc)
        return None


# ---------------------------------------------------------------------------
# On-demand canvas reveal (Story 10.6)
# ---------------------------------------------------------------------------
# The dossier canvas is created lazily and revealed only via an explicit
# affordance once the session enters dossier phase. It is never opened at chat
# start/resume (PR #64 removed the always-open canvas as poor UX). Creation
# (`ensure_dossier_doc`) and reveal (`reveal_dossier_canvas`) are deliberately
# separate concerns. The decision to *post* the reveal affordance lives in the
# phase gate (Story 11.3), not here.


def ensure_dossier_doc() -> cl.CustomElement:
    """Lazily create the dossier ``Document`` element, or return the existing one.

    Idempotent: reuses ``cl.user_session["doc"]`` when present so we never orphan a
    ``CustomElement`` (which would lose prop sync). Creates the element with
    ``phase="dossier"`` so ``Document.jsx`` renders the editable view, not the
    investigating placeholder. Does NOT open the sidebar.
    """
    doc = cl.user_session.get("doc")
    if doc is not None:
        return doc
    doc = cl.CustomElement(
        name="Document",
        props={"content": "", "version": 0, "phase": "dossier"},
        display="inline",
    )
    cl.user_session.set("doc", doc)
    return doc


async def reveal_dossier_canvas() -> None:
    """Open the dossier canvas in the right-side ``ElementSidebar``.

    Ensures a ``doc`` exists first, then reveals it. Idempotent: reuses the same
    element reference, so repeated reveals never orphan elements.
    """
    doc = ensure_dossier_doc()
    cl.user_session.set("dossier_revealed", True)
    # Monotonic open-counter ensures the key is unique across close → reopen
    # cycles.  ElementSidebar silently ignores set_elements when the key hasn't
    # changed, so re-using "dossier-v0" after a close would leave the panel shut.
    open_count = (cl.user_session.get("_sidebar_open_count") or 0) + 1
    cl.user_session.set("_sidebar_open_count", open_count)
    await cl.ElementSidebar.set_title("Dossier")
    await cl.ElementSidebar.set_elements([doc], key=f"dossier-v{doc.props.get('version', 0)}-o{open_count}")


async def _refresh_dossier_canvas() -> None:
    """Re-render the revealed dossier canvas with the current ``doc`` state.

    Chainlit's ``ElementSidebar`` renders from its own snapshot taken at
    ``set_elements`` time: ``doc.update()`` does NOT refresh a sidebar-hosted
    element, and ``set_elements`` with an unchanged key is a no-op. So we re-run
    ``set_elements`` with a version-stamped key to force the sidebar to replace
    its snapshot. No-op until the canvas has been revealed, so content updates
    never force the panel open (AC4; Story 11.4 ``propose_structure`` populates
    the doc silently before the journalist opens it).
    """
    if not cl.user_session.get("dossier_revealed"):
        return
    doc = cl.user_session.get("doc")
    if doc is None:
        return
    open_count = cl.user_session.get("_sidebar_open_count") or 0
    await cl.ElementSidebar.set_elements([doc], key=f"dossier-v{doc.props.get('version', 0)}-o{open_count}")


async def post_dossier_reveal_affordance() -> None:
    """Post the one-click "Open dossier" affordance to chat.

    Called by the phase gate (Story 11.3) when the session transitions to dossier
    phase. Renders a single ``cl.Action``; the canvas is NOT auto-opened. There is
    no ``/dossier`` command and no persistent welcome button.
    """
    await cl.Message(
        content="Your dossier is ready.",
        actions=[cl.Action(name="reveal_dossier", label="📄 Open dossier", payload={})],
    ).send()


@cl.action_callback("reveal_dossier")
async def on_reveal_dossier(action: cl.Action) -> None:
    """Reveal the dossier canvas when the journalist clicks "Open dossier"."""
    await reveal_dossier_canvas()
    # One-shot affordance: remove it after use so it doesn't linger in chat.
    await action.remove()


@cl.action_callback("toggle_dossier")
async def on_toggle_dossier(action: cl.Action) -> None:
    """Toggle the dossier panel open/closed via the header button."""
    if cl.user_session.get("dossier_revealed"):
        # Stamp the close key with the open-counter too. ElementSidebar ignores
        # set_elements when the key is unchanged, so a fixed "closed" key would be
        # a no-op on the second close of an open → close → open → close cycle,
        # leaving the panel stuck open.
        open_count = cl.user_session.get("_sidebar_open_count") or 0
        await cl.ElementSidebar.set_elements([], key=f"closed-o{open_count}")
        cl.user_session.set("dossier_revealed", False)
    else:
        await reveal_dossier_canvas()


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


UPDATE_INVESTIGATION_ITEM_TOOL: dict[str, Any] = {
    "name": "update_investigation_item",
    "description": (
        "Record the journalist's answer for one investigation checklist item. "
        "Call this exactly once per item, after you have gathered enough context "
        "to summarise the answer in `value`. Do not call it speculatively. "
        "Items 1-5 (topic_definition, geography_scope, time_range, target_audience, "
        "data_sources_validation) are gathered during the interview phase; items 6-10 "
        "(key_stats_capture, narrative_structure, case_studies, story_pitches, methodology) "
        "are gathered while building the dossier."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "item_id": {
                "type": "string",
                "enum": list(_INVESTIGATION_ITEMS),
                "description": "The checklist item being recorded.",
            },
            "value": {
                "description": (
                    "The journalist's answer for this item. "
                    "Use a concise string for free-text items (topic_definition, geography_scope, etc.) "
                    "or a structured object for items that summarise multiple data points "
                    "(e.g. key_stats_capture, data_sources_validation)."
                ),
            },
        },
        "required": ["item_id", "value"],
    },
}


PROPOSE_STRUCTURE_TOOL: dict[str, Any] = {
    "name": "propose_structure",
    "description": (
        "Generate the initial dossier skeleton once the investigation phase gate has "
        "been reached. Call this EXACTLY ONCE, when the journalist is ready to start "
        "building the document and the document is still empty. Python builds a "
        "fixed-section markdown skeleton from the recorded investigation state; you "
        "only optionally supply a concise topic label for the headings. After the "
        "skeleton exists, use apply_ops (NOT this tool) for all structural changes."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "topic_area": {
                "type": "string",
                "description": (
                    "Optional concise, heading-friendly label (<= 60 chars) for the "
                    "investigation topic, e.g. 'Dengue and Climate in SE Brazil'. If "
                    "omitted, the skeleton derives the label from the recorded "
                    "topic_definition value."
                ),
            },
        },
        "required": [],
    },
}


# Markdown control characters stripped from topic labels so a topic can't distort
# or escape the heading it is injected into (nested "#" heading, "`" code span,
# "*"/"_" emphasis, "[" / "]" link/anchor brackets).
_MARKDOWN_CTRL = str.maketrans("", "", "`*_[]#")


def _derive_topic_label(state: dict[str, dict[str, Any]] | None, topic_area: str | None) -> str:
    """Pick a concise heading label: explicit topic_area, else topic_definition value, else fallback."""
    if topic_area:
        label = topic_area
    else:
        entry = state.get("topic_definition") if isinstance(state, dict) else None
        raw = entry.get("value") if isinstance(entry, dict) else None
        label = str(raw) if raw else ""
    # Strip newlines + Markdown control chars, then collapse whitespace runs so the
    # label renders cleanly inside the "## Part 1: <label>" heading.
    label = label.replace("\r", " ").replace("\n", " ").translate(_MARKDOWN_CTRL)
    label = " ".join(label.split())
    if len(label) > 60:
        label = label[:57].rstrip() + "..."
    return label or "Investigation Overview"


def _build_dossier_skeleton(
    state: dict[str, dict[str, Any]] | None, topic_area: str | None = None
) -> tuple[str, list[str]]:
    """Build the fixed-section dossier skeleton. Returns (markdown, section_headings).

    Pure function — no Chainlit access — so it can be unit-tested directly.
    """
    topic = _derive_topic_label(state, topic_area)
    sections = [
        "Executive Summary",
        f"Part 1: {topic}",
        "Case Studies",
        "Suggested Stories (Pautas Sugeridas)",
        "Methodology and Sources",
    ]
    skeleton = (
        "# Executive Summary\n\n"
        "[Add key statistics and headline findings here.]\n\n"
        f"## Part 1: {topic}\n\n"
        "[Add analysis here.]\n\n"
        "## Case Studies\n\n"
        "[Profile specific entities here.]\n\n"
        "## Suggested Stories (Pautas Sugeridas)\n\n"
        "[Add investigative angles here.]\n\n"
        "## Methodology and Sources\n\n"
        "[Document data sources and methodology here.]\n"
    )
    return skeleton, sections


def apply_single_op(content: str, op: dict) -> tuple[str, str | None]:
    """Apply a single op to `content` and return `(new_content, error | None)`.

    Pure string transform — no Chainlit session access so it can be unit-tested.
    On error, returns the input content unchanged plus an error message.
    """
    op_type = op["type"]

    if op_type in ("replace", "delete"):
        find = op.get("find", "")
        if not find:
            return content, f"Missing required 'find' for {op_type} op"
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
        if not anchor:
            return content, f"Missing required 'anchor' for {op_type} op"
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
        if not new_text:
            return content, "Missing required 'content' for append op"
        return (content + "\n\n" + new_text).strip(), None

    if op_type == "prepend":
        new_text = op.get("content", "")
        if not new_text:
            return content, "Missing required 'content' for prepend op"
        return (new_text + "\n\n" + content).strip(), None

    return content, f"Unknown op type: '{op_type}'"


async def _handle_apply_ops(tool_input: dict) -> str:
    """Apply a list of ops to the dossier document, streaming updates per-op.

    Returns "ok" on success, or an error string on the first op that fails.
    """
    doc = cl.user_session.get("doc")
    if doc is None:
        return "Error: dossier canvas is not open"

    ops = tool_input.get("ops", [])
    # Guard against double-encoded JSON: model sometimes passes ops as a JSON string
    # instead of an array, causing "string indices must be integers" on op["type"].
    if isinstance(ops, str):
        try:
            ops = json.loads(ops)
        except (json.JSONDecodeError, TypeError):
            return "Error: 'ops' could not be parsed — pass a JSON array, not a string"
    if not ops or not isinstance(ops, list):
        return "Error: 'ops' must be a non-empty list"

    # Snapshot for rollback on partial failure — keeps doc.props and the
    # `dossier` session dict consistent if any op in the batch fails. Includes the
    # derived display props (html_content/pdf_data_url) so a mid-batch failure
    # restores the rendered preview/PDF too, not just the raw content.
    original_content: str = doc.props.get("content", "")
    original_version: int = int(doc.props.get("version", 0))
    original_html: str = doc.props.get("html_content", "")
    original_pdf: str | None = doc.props.get("pdf_data_url")
    current_content = original_content
    last_idx = len(ops) - 1

    for idx, op in enumerate(ops):
        new_content, err = apply_single_op(current_content, op)
        if err is not None:
            doc.props["content"] = original_content
            doc.props["version"] = original_version
            doc.props["html_content"] = original_html
            doc.props["pdf_data_url"] = original_pdf
            doc.content = json.dumps(doc.props)  # re-sync before update (CustomElement.content is set only once)
            await doc.update()
            await _refresh_dossier_canvas()
            return err
        current_content = new_content
        doc.props["content"] = current_content
        # Refresh the formatted preview every op (cheap Markdown parse); render the
        # PDF only on the final op so the export reflects the settled content
        # without paying the ~0.5s render N times during streaming (Story 14.4 AC4).
        await _apply_derived_props(doc, current_content, render_pdf=(idx == last_idx))
        doc.props["version"] = int(doc.props.get("version", 0)) + 1
        doc.content = json.dumps(doc.props)  # re-sync before update
        await doc.update()
        await _refresh_dossier_canvas()
        await asyncio.sleep(0.03)

    dossier = cl.user_session.get("dossier")
    if isinstance(dossier, dict):
        dossier["content"] = current_content
        dossier["version"] = doc.props.get("version", 0)

    summary = tool_input.get("summary", "")
    if summary:
        await cl.Message(content=summary).send()
    return "ok"


_METHODOLOGY_HEADING = "## Methodology and Sources"
# Match the heading only as a standalone line (optional trailing whitespace) so that
# deeper headings (e.g. "### Methodology and Sources") or the phrase appearing in prose
# or a code fence never false-match and corrupt the document. See code-review 2026-05-30.
_METHODOLOGY_HEADING_RE = re.compile(r"^## Methodology and Sources[ \t]*$", re.MULTILINE)


async def _sync_dossier_references_section(doc: cl.CustomElement, refs: list[dict[str, Any]]) -> None:
    """Replace the contents of the dossier's "Methodology and Sources" section with
    the deterministic references block built from collected tool outputs.

    The section is the LAST section of the propose_structure skeleton. If the user
    has restructured the dossier and the heading is absent, the references block is
    appended as a fresh section at the end of the document.
    """
    from app.citations import format_reference_list  # local import to keep cycle-free

    block = format_reference_list(refs)
    content: str = doc.props.get("content", "")
    match = _METHODOLOGY_HEADING_RE.search(content)
    if match is not None:
        # Replace EVERYTHING from the heading line to end-of-document (the section is
        # system-owned and the last section of the skeleton — documented tradeoff).
        before = content[: match.start()]
        new_content = before.rstrip() + "\n\n" + _METHODOLOGY_HEADING + "\n\n" + block + "\n"
    else:
        new_content = content.rstrip() + "\n\n" + _METHODOLOGY_HEADING + "\n\n" + block + "\n"
    if new_content == content:
        return
    doc.props["content"] = new_content
    await _apply_derived_props(doc, new_content)
    doc.props["version"] = int(doc.props.get("version", 0)) + 1
    doc.content = json.dumps(doc.props)
    await doc.update()
    await _refresh_dossier_canvas()


async def _handle_propose_structure(tool_input: dict) -> str:
    """Create the dossier skeleton and populate the lazily-created doc.

    Returns a JSON string. Does NOT open the sidebar — the journalist reveals the
    canvas via the Story 10.6 affordance. Refuses to overwrite existing content.
    """
    doc = ensure_dossier_doc()
    existing = (doc.props.get("content") or "").strip()
    if existing:
        return json.dumps({"status": "noop", "reason": "skeleton already exists"})

    state = cl.user_session.get("investigation")
    topic_area = (tool_input.get("topic_area") or "").strip() or None
    skeleton, sections = _build_dossier_skeleton(state, topic_area)
    doc.props["phase"] = "dossier"
    await update_dossier_content(skeleton)
    return json.dumps({"status": "ok", "sections": sections})


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


# MCP session keys used in cl.user_session
_MCP_SESSION_KEY = "mcp_session"
_MCP_TOOLS_KEY = "mcp_tools"
# The MCP streamablehttp client must be opened AND closed in the same asyncio
# task — anyio's cancel scope forbids exiting it from a different task. We drive
# its lifecycle from a single long-lived task (see _open_mcp_connection): it
# opens the connection, parks on a close event, and tears the connection down
# in-task when signalled. We therefore store the close event and the task handle
# (not the AsyncExitStack) so on_chat_end / on_chat_resume can signal shutdown
# without ever touching the context manager from a foreign task.
_MCP_CLOSE_EVENT_KEY = "mcp_close_event"
_MCP_TASK_KEY = "mcp_task"
_DATA_VALIDATION_FLAG = "_data_validation_indicators_found"


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


def _join_tool_result_text(call_result) -> str:
    """Join the text blocks of an MCP CallToolResult WITHOUT truncation.

    Error results are prefixed with 'Error:'. This un-truncated form is used both by
    _extract_tool_result_text (which then truncates for the model) and by
    _record_search_indicators_outcome, which needs the full JSON: truncating first
    would break json.loads → the data-validation flag is never set → the investigation
    deadlocks at the phase gate for large (>tool_result_max_chars) search_indicators
    results.
    """
    parts = [block.text for block in call_result.content if hasattr(block, "text")]
    if call_result.isError:
        # Surface the error to Claude so it can narrate gracefully
        return "Error: " + (" ".join(parts) if parts else "Unknown MCP tool error")
    return "\n".join(parts) if parts else ""


def _extract_tool_result_text(call_result) -> str:
    """Extract text from an MCP CallToolResult, truncating oversized output for the model."""
    text = _join_tool_result_text(call_result)
    max_chars = settings.tool_result_max_chars
    if len(text) > max_chars:
        text = text[:max_chars] + "\n\n[... truncated, results too large ...]"
    return text


def _record_search_indicators_outcome(tool_name: str, tool_output: str) -> None:
    """Set the indicators-found session flag when a search_indicators call succeeded.

    Called from the agentic loop right after _extract_tool_result_text. Cheap
    no-op for any other tool. JSON-parse failures are logged at debug and ignored
    (the loop must not crash on a malformed MCP payload).

    Also fires for search_local_indicators (offline tool from Epic 5) which can
    satisfy data_sources_validation when it finds matches.
    """
    if tool_name not in ("search_indicators", "search_local_indicators"):
        return
    try:
        parsed = json.loads(tool_output)
    except (json.JSONDecodeError, TypeError):
        logger.debug("[DATA_VALIDATION] search_indicators output is not JSON; skipping flag set")
        return
    if not isinstance(parsed, dict) or not parsed.get("success"):
        return
    # search_indicators uses total_count; search_local_indicators uses total_matches
    count_raw = parsed.get("total_count") if tool_name == "search_indicators" else parsed.get("total_matches")
    try:
        total_count = int(count_raw or 0)
    except (TypeError, ValueError):
        return
    if total_count >= 1:
        cl.user_session.set(_DATA_VALIDATION_FLAG, True)
        logger.debug("[DATA_VALIDATION] %s returned count=%d; flag set", tool_name, total_count)


async def _open_mcp_connection() -> tuple[
    ClientSession | None, list[dict[str, Any]], asyncio.Event | None, asyncio.Task | None
]:
    """Open an MCP connection inside a single, dedicated, long-lived task.

    The streamablehttp client context is both entered and exited inside the
    returned task, which satisfies anyio's rule that a cancel scope must be
    exited in the same task it was entered. (The previous approach entered the
    context in ``on_chat_start`` and closed it from ``on_chat_end`` — a different
    task — which made anyio emit a noisy ``RuntimeError: Attempted to exit cancel
    scope in a different task`` traceback on every chat end, even though the
    error was caught for control flow.)

    Returns ``(session, tools, close_event, task)``. On failure ``session`` is
    ``None`` and ``tools`` is empty, so callers continue without MCP tools.
    Signal ``close_event`` and await ``task`` via :func:`_close_mcp_connection`
    to tear the connection down cleanly in its own task.
    """
    ready = asyncio.Event()
    close_event = asyncio.Event()
    holder: dict[str, Any] = {}

    async def _lifecycle() -> None:
        try:
            async with AsyncExitStack() as stack:
                read, write, _ = await stack.enter_async_context(streamablehttp_client(url=settings.mcp_server_url))
                session = await stack.enter_async_context(ClientSession(read, write))
                await session.initialize()
                result = await session.list_tools()
                holder["session"] = session
                holder["tools"] = _mcp_tools_to_anthropic(result.tools)
                ready.set()
                # Keep the connection open until chat end signals close_event.
                # Exiting this `async with` (here, in this task) tears down the
                # streamablehttp client in the same task that entered it.
                await close_event.wait()
        except Exception:
            logger.warning("MCP connection failed, continuing without tools", exc_info=True)
        finally:
            # Always unblock the opener below, even on early failure.
            ready.set()

    task = asyncio.create_task(_lifecycle())
    await ready.wait()

    session = holder.get("session")
    if session is None:
        # Connection never became ready; ensure the lifecycle task can finish.
        close_event.set()
        return None, [], None, None
    return session, holder.get("tools", []), close_event, task


async def _close_mcp_connection(close_event: asyncio.Event | None, task: asyncio.Task | None) -> None:
    """Signal the MCP lifecycle task to tear down and wait for it to finish.

    The teardown runs inside ``task`` itself, so awaiting it here never exits the
    anyio cancel scope from a foreign task — this is what keeps the cancel-scope
    RuntimeError out of the logs.
    """
    if task is None:
        return
    if close_event is not None:
        close_event.set()
    try:
        await asyncio.wait_for(task, timeout=10.0)
    except asyncio.TimeoutError:
        logger.warning("Error closing MCP connection: lifecycle task did not finish within timeout")
    except Exception:
        logger.warning("Error closing MCP connection", exc_info=True)


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

    # Re-initialise dossier session state on resume.
    # If propose_structure was previously called in this thread the session was in
    # dossier phase — restore the phase flag and auto-reveal the canvas so the
    # user immediately sees their dossier (the one-shot "Open dossier" action is
    # gone after first use; auto-reveal avoids a dead end on resume).
    # Tool steps are persisted as cl.Step(name="🔧 {tool_name}", type="tool") by
    # the agentic loop. Match the exact tool step — type AND full name — so resume
    # is not tripped by an error message, assistant prose mentioning the tool, or a
    # future tool whose name merely contains "propose_structure".
    is_dossier = any(
        step.get("type") == "tool" and (step.get("name") or "") == "🔧 propose_structure" for step in steps
    )
    dossier_phase = "dossier" if is_dossier else "investigating"
    cl.user_session.set("dossier", {"phase": dossier_phase, "content": "", "version": 0})
    cl.user_session.set("investigation", _empty_investigation_state())
    cl.user_session.set(_DATA_VALIDATION_FLAG, False)
    if is_dossier:
        await reveal_dossier_canvas()

    # Close any existing MCP connection before reconnecting (prevents leaks).
    await _close_mcp_connection(
        cl.user_session.get(_MCP_CLOSE_EVENT_KEY),
        cl.user_session.get(_MCP_TASK_KEY),
    )

    cl.user_session.set(_MCP_SESSION_KEY, None)
    cl.user_session.set(_MCP_TOOLS_KEY, [])
    cl.user_session.set(_MCP_CLOSE_EVENT_KEY, None)
    cl.user_session.set(_MCP_TASK_KEY, None)

    session, tools, close_event, task = await _open_mcp_connection()
    cl.user_session.set(_MCP_SESSION_KEY, session)
    cl.user_session.set(_MCP_TOOLS_KEY, tools)
    cl.user_session.set(_MCP_CLOSE_EVENT_KEY, close_event)
    cl.user_session.set(_MCP_TASK_KEY, task)
    if session is not None:
        logger.info("MCP reconnected on resume: %d tools available", len(tools))
    else:
        logger.warning("MCP reconnect failed on resume, continuing without tools")


@cl.on_chat_start
async def on_chat_start():
    cl.user_session.set("dossier", {"phase": "investigating", "content": "", "version": 0})
    cl.user_session.set("investigation", _empty_investigation_state())
    cl.user_session.set(_DATA_VALIDATION_FLAG, False)

    cl.user_session.set("history", [])
    cl.user_session.set(_MCP_SESSION_KEY, None)
    cl.user_session.set(_MCP_TOOLS_KEY, [])
    cl.user_session.set(_MCP_CLOSE_EVENT_KEY, None)
    cl.user_session.set(_MCP_TASK_KEY, None)

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

    # Auto-connect to MCP server (driven by a dedicated lifecycle task so the
    # connection is opened and closed in the same task — see _open_mcp_connection).
    session, tools, close_event, task = await _open_mcp_connection()
    cl.user_session.set(_MCP_SESSION_KEY, session)
    cl.user_session.set(_MCP_TOOLS_KEY, tools)
    cl.user_session.set(_MCP_CLOSE_EVENT_KEY, close_event)
    cl.user_session.set(_MCP_TASK_KEY, task)
    if session is not None:
        logger.info("MCP auto-connected: %d tools available", len(tools))
    else:
        logger.warning("MCP auto-connect failed, continuing without tools")

    await cl.Message(
        content="Welcome to Context Climate! Ask me about World Bank climate and development data.",
    ).send()


@cl.on_chat_end
async def on_chat_end():
    # Signal the lifecycle task to close the MCP connection in its own task.
    await _close_mcp_connection(
        cl.user_session.get(_MCP_CLOSE_EVENT_KEY),
        cl.user_session.get(_MCP_TASK_KEY),
    )


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

    def _build_call_kwargs() -> dict[str, Any]:
        # Rebuilt each round so `apply_ops` mutations to the doc are reflected
        # in the system prompt's `[Current document (vN): ...]` snapshot.
        dossier_state = cl.user_session.get("dossier")
        phase = dossier_state.get("phase", "investigating") if isinstance(dossier_state, dict) else "investigating"
        if phase == "dossier":
            doc = cl.user_session.get("doc")
            version = doc.props.get("version", 0) if doc is not None else 0
            content = doc.props.get("content", "") if doc is not None else ""
            doc_note = f"[Current document (v{version}):\n{content}\n]\n\n"
            system_prompt = doc_note + DOSSIER_SYSTEM_PROMPT
        else:
            investigation_state = cl.user_session.get("investigation")
            if isinstance(investigation_state, dict):
                snapshot = _format_investigation_snapshot(investigation_state)
                system_prompt = INVESTIGATION_SYSTEM_PROMPT + "\n\n" + snapshot
            else:
                system_prompt = INVESTIGATION_SYSTEM_PROMPT

        combined_tools = list(tools)
        combined_tools.append(UPDATE_INVESTIGATION_ITEM_TOOL)
        if phase == "dossier":
            combined_tools.append(APPLY_OPS_TOOL)
            combined_tools.append(PROPOSE_STRUCTURE_TOOL)
        return {
            "model": settings.claude_model,
            "max_tokens": settings.claude_max_tokens,
            "system": system_prompt,
            "tools": combined_tools,
        }

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
        call_kwargs = _build_call_kwargs()
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

                # Story 12.3: also flow the same references into the dossier doc's
                # "Methodology and Sources" section when in dossier phase.
                dossier_state = cl.user_session.get("dossier")
                if (
                    isinstance(dossier_state, dict)
                    and dossier_state.get("phase") == "dossier"
                    and (doc := cl.user_session.get("doc")) is not None
                ):
                    await _sync_dossier_references_section(doc, refs)

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
                elif tool_name == "update_investigation_item":
                    try:
                        _dossier_pre = cl.user_session.get("dossier") or {}
                        _phase_before = _dossier_pre.get("phase", "investigating")
                        result = update_investigation_item(
                            tool_input.get("item_id", ""),
                            tool_input.get("value"),
                        )
                        tool_output = json.dumps(result)
                        if result.get("phase_gate_reached") and _phase_before == "investigating":
                            await post_dossier_reveal_affordance()
                    except Exception as exc:
                        logger.error("update_investigation_item failed: %s", exc)
                        tool_output = f"Error calling update_investigation_item: {exc}"
                elif tool_name == "propose_structure":
                    try:
                        tool_output = await _handle_propose_structure(tool_input)
                    except Exception as exc:
                        logger.error("propose_structure failed: %s", exc)
                        tool_output = f"Error calling propose_structure: {exc}"
                elif mcp_session is not None:
                    try:
                        call_result = await mcp_session.call_tool(tool_name, arguments=tool_input)
                        tool_output = _extract_tool_result_text(call_result)
                        # Record the data-validation outcome from the UN-truncated text.
                        # tool_output may be truncated for the model; feeding that to the
                        # recorder would break json.loads → the validation flag would never
                        # be set → the phase gate would deadlock on large search results.
                        _record_search_indicators_outcome(tool_name, _join_tool_result_text(call_result))
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
