"""Generate a fictional resume, with no credentials or external LLM calls."""
import json
import os
from pathlib import Path

from resume_mcp.interview import status
from resume_mcp.render import render_pdf
from resume_mcp.store import Store

database = Store(os.environ.get("RESUME_DEMO_DIR", ".resume-data/demo"))
state = database.create()
answers = {
    "target": "软件开发实习", "template": "classic", "project_count": "1",
    "name": "示例同学", "education": "示例大学｜软件工程｜2023—2027",
    "contact": "example@example.com", "skills": "Python 文件批处理、JSON 数据校验、MCP 工具开发。",
    "p1_name": "文档整理工具", "p1_role": "独立开发", "p1_period": "2026.09—2026.10",
    "p1_background": "需要把多份文档中的条目整理成统一格式。",
    "p1_task": "实现文件读取、字段整理和表格导出。",
    "p1_solution": "使用 Python 解析文档，校验字段后导出 Excel。",
    "p1_result": "完成文件导入到表格导出的流程。",
}
state = database.update(state["id"], 0, answers,
                        skip=["experience", "p1_evidence", "awards", "extra"])
state = database.approve(state["id"], state["revision"])
result = render_pdf(state, database.root / "exports")
print(json.dumps(result, ensure_ascii=False))
