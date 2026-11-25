"""Stdio MCP entry point. Interview policy lives outside the transport."""
import os
from pathlib import Path

from mcp.server.fastmcp import Context, FastMCP
from pydantic import Field, create_model

from .interview import next_questions, status
from .render import Layout, TEMPLATES, render_pdf
from .store import Store

INSTRUCTIONS = """You are a resume interviewer. Ask at most 3 questions per turn.
Use start_resume, then interview_resume for native elicitation when supported.
In chat fallback, display returned questions, wait for the user's answer, and call
submit_answers with only the facts actually provided. Preserve field keys and revision.
Do not answer on the user's behalf. Do not infer dates, achievements or personal roles.
Explain skip/decline/cancel. A cancelled form keeps the pending questions for later.
Use get_resume to resume or correct existing sessions, not start_resume again.
AI may propose a layout through set_layout; it cannot execute code or add factual claims.
Before confirm_resume show the entire review_resume result and ask the user to confirm.
After corrections ask for confirmation again. Export only the confirmed revision.
"""
mcp = FastMCP("Resume Interview MCP", instructions=INSTRUCTIONS)


def store():
    return Store(os.environ.get("RESUME_DATA_DIR", str(Path.cwd() / ".resume-data")))


@mcp.tool()
def start_resume() -> dict:
    """Start a new resume. Save session_id; ask its questions before submitting answers."""
    return status(store().create())


@mcp.tool()
def get_resume(session_id: str) -> dict:
    """Resume an interview and retrieve facts, missing fields and the next question group."""
    return status(store().get(session_id))


@mcp.tool()
def submit_answers(session_id: str, expected_revision: int, answers: dict[str, str],
                   skip: list[str] | None = None) -> dict:
    """Save actual user answers or corrections. Skip optional fields explicitly; return the next questions.

    Required fields may be deferred with skip but will still block confirmation.
    Supplying an answer later clears that field's skipped state. Increasing project_count asks for more projects.
    """
    return status(store().update(session_id, expected_revision, answers, skip))


@mcp.tool()
async def interview_resume(session_id: str, expected_revision: int, ctx: Context) -> dict:
    """Ask one group of up to 3 questions using MCP form elicitation.

    Accept validates and persists answers. Decline skips this group; cancel preserves it.
    Unsupported clients receive chat questions instead. Empty accepted optional fields are skipped.
    """
    database = store()
    state = database.get(session_id)
    if state["revision"] != expected_revision:
        raise ValueError("会话已更新，请 get_resume 后重试")
    questions = next_questions(state)
    if not questions:
        return status(state)
    capabilities = ctx.session.client_params.capabilities
    if not capabilities.elicitation:
        return {**status(state), "mode": "chat", "instruction": "请向用户展示 questions，等待回答后调用 submit_answers。"}
    fields = {}
    for q in questions:
        description = q.help + (f" 可选值：{', '.join(q.choices)}" if q.choices else "")
        fields[q.key] = (str, Field(default="", title=q.title, description=description, max_length=4000))
    schema = create_model("ResumeQuestions", **fields)
    try:
        response = await ctx.elicit("请按实际情况填写。留空表示暂时跳过，取消可稍后继续。", schema=schema)
    except Exception as error:
        # A transport/client error must never count as an answer or a skipped field.
        return {**status(state), "mode": "chat", "elicitation_error": type(error).__name__,
                "instruction": "表单暂不可用。请展示 questions，等待用户回答后调用 submit_answers。"}
    if response.action == "cancel":
        return {**status(database.get(session_id)), "action": "cancel", "instruction": "本轮已取消，可稍后继续。"}
    if response.action == "decline":
        state = database.update(session_id, expected_revision, skip=[q.key for q in questions])
    else:
        values = response.data.model_dump()
        answers = {key: value.strip() for key, value in values.items() if value.strip()}
        state = database.update(session_id, expected_revision, answers,
                                [key for key in values if key not in answers])
    return {**status(state), "action": response.action, "mode": "form"}


@mcp.tool()
def list_templates() -> dict:
    """List built-in templates and the accepted schema for AI-designed layouts."""
    return {"templates": TEMPLATES, "ai_layout_schema": Layout.model_json_schema(),
            "ai_workflow": "Ask the user's style preference, propose a bounded Layout, call set_layout. No HTML or code."}


@mcp.tool()
def set_layout(session_id: str, expected_revision: int, layout: dict) -> dict:
    """Apply a user-selected or AI-proposed layout. Only style and section order can change.

    The model should explain the proposed design to the user before calling this tool.
    Changes invalidate prior confirmation. All resume sections must remain present.
    """
    validated = Layout.model_validate(layout).model_dump()
    return status(store().update(session_id, expected_revision, {"template": "ai"}, layout=validated))


@mcp.tool()
def review_resume(session_id: str) -> dict:
    """Show the exact collected facts, layout and omissions. Ask the user to review these before confirming."""
    state = store().get(session_id)
    return {**status(state), "layout": state["layout"],
            "notice": "请核对全部事实。尚未提供的成果不会被生成；项目数量减少时，旧项目保留在会话中但不导出。"}


@mcp.tool()
def confirm_resume(session_id: str, expected_revision: int, user_confirmed: bool) -> dict:
    """Record explicit user confirmation of review_resume at this exact revision. Never confirm on their behalf."""
    if not user_confirmed:
        raise ValueError("请先等待用户确认审阅内容")
    return status(store().approve(session_id, expected_revision))


@mcp.tool()
def export_pdf(session_id: str, expected_revision: int) -> dict:
    """Render a PDF of the reviewed revision. Return page count and overflow warnings without shrinking text."""
    database = store()
    state = database.get(session_id)
    if state["revision"] != expected_revision or state.get("reviewed_revision") != expected_revision:
        raise ValueError("请先审阅并确认最新版本后导出")
    return render_pdf(state, database.root / "exports")


@mcp.prompt()
def resume_interviewer() -> str:
    """Start a resumable resume interview with truthful, short follow-up questions."""
    return INSTRUCTIONS


def main():
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
