"""Interactive terminal MCP host for demonstrating native form elicitation."""
import argparse
import asyncio
import json
import os
import sys
from pathlib import Path

from mcp import ClientSession, StdioServerParameters, types
from mcp.client.stdio import stdio_client


def result_data(result):
    if result.isError:
        raise RuntimeError(result.content[0].text)
    return json.loads(result.content[0].text)


async def ask_user(context, params):
    print("\n" + params.message)
    print("输入 /cancel 暂停，/decline 跳过本轮。")
    values = {}
    for key, spec in params.requestedSchema["properties"].items():
        print(spec.get("description", ""))
        value = input(spec.get("title", key) + " > ").strip()
        if value == "/cancel":
            return types.ElicitResult(action="cancel")
        if value == "/decline":
            return types.ElicitResult(action="decline")
        values[key] = value
    return types.ElicitResult(action="accept", content=values)


async def run(session_id):
    params = StdioServerParameters(command=sys.executable, args=["-m", "resume_mcp.server"],
                                  cwd=str(Path(__file__).resolve().parents[1]), env=dict(os.environ))
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write, elicitation_callback=ask_user) as client:
            await client.initialize()
            state = result_data(await client.call_tool("get_resume" if session_id else "start_resume",
                                                       {"session_id": session_id} if session_id else {}))
            print("续填用 session_id：", state["session_id"])
            while state["questions"]:
                state = result_data(await client.call_tool("interview_resume", {
                    "session_id": state["session_id"], "expected_revision": state["revision"]}))
                if state.get("action") == "cancel":
                    return
                if state.get("mode") == "chat":
                    print(json.dumps(state["questions"], ensure_ascii=False, indent=2))
                    print("本轮请通过支持表单的客户端或 submit_answers 继续。")
                    return
            if state["missing_required"]:
                print("以下必填项被跳过，请补填。回车可暂停。")
                answers = {}
                for key in state["missing_required"]:
                    value = input(key + " > ").strip()
                    if not value:
                        return
                    answers[key] = value
                state = result_data(await client.call_tool("submit_answers", {
                    "session_id": state["session_id"], "expected_revision": state["revision"], "answers": answers}))
                if state["questions"] or state["missing_required"]:
                    print("已保存，请用 session_id 继续补充新增问题。")
                    return
            review = result_data(await client.call_tool("review_resume", {"session_id": state["session_id"]}))
            print(json.dumps(review["facts"], ensure_ascii=False, indent=2))
            if input("确认以上内容并生成 PDF？输入 yes > ").strip().lower() != "yes":
                print("已保存，可通过 session_id 继续修改。")
                return
            arguments = {"session_id": state["session_id"], "expected_revision": state["revision"]}
            result_data(await client.call_tool("confirm_resume", {**arguments, "user_confirmed": True}))
            output = result_data(await client.call_tool("export_pdf", arguments))
            print(json.dumps(output, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--session", help="已有 session_id，可断点续填")
    asyncio.run(run(parser.parse_args().session))
