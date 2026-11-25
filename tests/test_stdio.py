"""Exercise actual MCP JSON-RPC and native elicitation over a subprocess stdio connection."""
import json
import os
import sys
import unittest
from pathlib import Path

from mcp import ClientSession, StdioServerParameters, types
from mcp.client.stdio import stdio_client

from test_interview import BASE, test_directory


def payload(result):
    if result.isError:
        raise AssertionError(result.content)
    return json.loads(result.content[0].text)


class StdioTests(unittest.IsolatedAsyncioTestCase):
    async def connect_and_run(self, callback, operation):
        root = test_directory()
        params = StdioServerParameters(command=sys.executable, args=["-m", "resume_mcp.server"],
                                      cwd=str(Path(__file__).resolve().parents[1]),
                                      env={**os.environ, "RESUME_DATA_DIR": root})
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write, elicitation_callback=callback) as client:
                await client.initialize()
                tools = await client.list_tools()
                self.assertIn("interview_resume", [tool.name for tool in tools.tools])
                await operation(client)

    async def test_chat_fallback(self):
        async def operation(client):
            state = payload(await client.call_tool("start_resume", {}))
            result = payload(await client.call_tool("interview_resume", {
                "session_id": state["session_id"], "expected_revision": 0}))
            self.assertEqual(result["mode"], "chat")
            self.assertEqual(result["revision"], 0)
        await self.connect_and_run(None, operation)

    async def test_native_accept_cancel_decline_and_export(self):
        actions = iter(["cancel", "decline", "accept"])

        async def callback(context, params):
            action = next(actions)
            if action != "accept":
                return types.ElicitResult(action=action)
            keys = params.requestedSchema["properties"]
            values = {key: BASE.get(key, "") for key in keys}
            return types.ElicitResult(action="accept", content=values)

        async def operation(client):
            state = payload(await client.call_tool("start_resume", {}))
            sid = state["session_id"]
            result = payload(await client.call_tool("interview_resume", {"session_id": sid, "expected_revision": 0}))
            self.assertEqual(result["action"], "cancel")
            self.assertEqual(result["revision"], 0)
            result = payload(await client.call_tool("interview_resume", {"session_id": sid, "expected_revision": 0}))
            self.assertEqual(result["action"], "decline")
            self.assertEqual(result["revision"], 1)
            result = payload(await client.call_tool("interview_resume", {"session_id": sid, "expected_revision": 1}))
            self.assertEqual(result["mode"], "form")
            self.assertEqual(result["facts"]["name"], BASE["name"])
            result = payload(await client.call_tool("submit_answers", {
                "session_id": sid, "expected_revision": result["revision"], "answers": BASE}))
            revision = result["revision"]
            error = await client.call_tool("export_pdf", {"session_id": sid, "expected_revision": revision})
            self.assertTrue(error.isError)
            await client.call_tool("review_resume", {"session_id": sid})
            payload(await client.call_tool("confirm_resume", {"session_id": sid,
                          "expected_revision": revision, "user_confirmed": True}))
            output = payload(await client.call_tool("export_pdf", {"session_id": sid, "expected_revision": revision}))
            self.assertTrue(Path(output["pdf_path"]).exists())
            self.assertEqual(output["pages"], 1)
            updated = payload(await client.call_tool("submit_answers", {
                "session_id": sid, "expected_revision": revision, "answers": {"name": "更正后的姓名"}}))
            stale = await client.call_tool("export_pdf", {"session_id": sid, "expected_revision": updated["revision"]})
            self.assertTrue(stale.isError)
        await self.connect_and_run(callback, operation)
