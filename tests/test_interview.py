import os
import tempfile
import unittest
from pathlib import Path

from resume_mcp.interview import next_questions, status
from resume_mcp.render import Layout, render_pdf
from resume_mcp.store import Conflict, Store


def test_directory():
    root = os.environ.get("RESUME_TEST_DIR")
    if root:
        Path(root).mkdir(parents=True, exist_ok=True)
    return tempfile.mkdtemp(prefix="resume-test-", dir=root)


BASE = {"name": "示例同学", "target": "软件开发", "template": "classic",
        "project_count": "1", "skills": "Python 文件批处理", "p1_name": "文档工具",
        "p1_role": "独立开发", "p1_task": "实现 PDF 文本导出", "p1_solution": "Python 与 PyMuPDF"}


class InterviewTests(unittest.TestCase):
    def setUp(self):
        self.root = test_directory()
        self.store = Store(self.root)
        self.state = self.store.create()
        self.sid = self.state["id"]

    def test_incremental_questions_and_no_repeat(self):
        self.assertEqual(len(next_questions(self.state)), 3)
        state = self.store.update(self.sid, 0, {"target": "Android 开发"})
        self.assertEqual([q.key for q in next_questions(state)], ["template", "project_count"])

    def test_resume_from_disk_and_version_conflict(self):
        self.store.update(self.sid, 0, {"name": "示例同学"})
        self.assertEqual(Store(self.root).get(self.sid)["facts"]["name"], "示例同学")
        with self.assertRaises(Conflict):
            self.store.update(self.sid, 0, {"name": "过期更新"})

    def test_skip_required_blocks_confirmation_and_can_be_answered_later(self):
        state = self.store.update(self.sid, 0, skip=["name"])
        self.assertIn("name", status(state)["missing_required"])
        with self.assertRaises(ValueError):
            self.store.approve(self.sid, 1)
        state = self.store.update(self.sid, 1, {"name": "示例同学"})
        self.assertNotIn("name", state["skipped"])

    def test_invalid_answer_does_not_partially_write(self):
        with self.assertRaises(ValueError):
            self.store.update(self.sid, 0, {"name": "应当回滚", "template": "unknown"})
        self.assertEqual(self.store.get(self.sid)["facts"], {})

    def test_project_count_preserves_dormant_facts_and_correction_invalidates_review(self):
        state = self.store.update(self.sid, 0, BASE)
        self.store.approve(self.sid, 1)
        state = self.store.update(self.sid, 1, {"project_count": "0"})
        self.assertEqual(state["facts"]["p1_name"], "文档工具")
        self.assertIsNone(state["reviewed_revision"])
        state = self.store.update(self.sid, 2, {"project_count": "2"})
        self.assertIn("p2_name", status(state)["missing_required"])

    def test_unsafe_layout_and_path_rejected(self):
        with self.assertRaises(ValueError):
            Layout(accent="javascript:alert(1)")
        with self.assertRaises(ValueError):
            Layout(sections=["skills"])
        with self.assertRaises(ValueError):
            self.store.get("../../escape")

    def test_pdf_export_and_literal_markup(self):
        answers = {**BASE, "p1_result": "<b>用户原文 & 字符</b>"}
        state = self.store.update(self.sid, 0, answers)
        self.store.approve(self.sid, 1)
        output = render_pdf(state, Path(self.root) / "exports")
        self.assertEqual(output["pages"], 1)
        self.assertTrue(Path(output["pdf_path"]).read_bytes().startswith(b"%PDF"))

    def test_overflow_reports_page_count(self):
        state = self.store.update(self.sid, 0, {**BASE, "extra": "中文项目经历。" * 500})
        output = render_pdf(state, Path(self.root) / "exports")
        self.assertGreater(output["pages"], 1)
        self.assertTrue(output["warnings"])


if __name__ == "__main__":
    unittest.main()
