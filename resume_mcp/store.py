"""Atomic local snapshots, revision checks and OS locks for safe resume updates."""
import json
import os
import re
from contextlib import contextmanager
from pathlib import Path
from uuid import uuid4

from .interview import all_questions, status, validate_answers


class Conflict(ValueError):
    pass


class Store:
    def __init__(self, root):
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def path(self, session_id):
        if not re.fullmatch(r"[a-f0-9]{32}", session_id):
            raise ValueError("无效的 session_id")
        return self.root / f"{session_id}.json"

    @contextmanager
    def locked(self, session_id):
        path = self.path(session_id).with_suffix(".lock")
        with open(path, "a+b") as handle:
            handle.seek(0)
            if not handle.read(1):
                handle.write(b"0")
                handle.flush()
            handle.seek(0)
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(handle.fileno(), msvcrt.LK_LOCK, 1)
            else:
                import fcntl
                fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
            try:
                yield
            finally:
                handle.seek(0)
                if os.name == "nt":
                    msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
                else:
                    fcntl.flock(handle.fileno(), fcntl.LOCK_UN)

    def write(self, state):
        target = self.path(state["id"])
        temp = target.with_suffix(f".{uuid4().hex}.tmp")
        with open(temp, "w", encoding="utf-8") as handle:
            json.dump(state, handle, ensure_ascii=False, indent=2)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp, target)

    def get(self, session_id):
        try:
            return json.loads(self.path(session_id).read_text(encoding="utf-8"))
        except FileNotFoundError as error:
            raise ValueError("会话不存在，请先 start_resume") from error

    def create(self):
        state = {"id": uuid4().hex, "revision": 0, "facts": {}, "skipped": [],
                 "history": [], "reviewed_revision": None, "layout": {}}
        self.write(state)
        return state

    def update(self, session_id, expected_revision, answers=None, skip=None, layout=None):
        answers, skip = answers or {}, skip or []
        with self.locked(session_id):
            state = self.get(session_id)
            if state["revision"] != expected_revision:
                raise Conflict("会话已更新，请 get_resume 后按最新 revision 重试")
            if set(answers) & set(skip):
                raise ValueError("同一字段不能同时回答和跳过")
            validate_answers(state["facts"], answers)
            valid_keys = {q.key for q in all_questions({"project_count": "3"})}
            if set(skip) - valid_keys:
                raise ValueError("skip 包含未知字段")
            if not answers and not skip and layout is None:
                return state
            previous = {key: state["facts"].get(key) for key in set(answers) | set(skip)}
            for key in skip:
                state["facts"].pop(key, None)
            state["facts"].update({key: value.strip() for key, value in answers.items()})
            state["skipped"] = sorted((set(state["skipped"]) | set(skip)) - set(answers))
            if layout is not None:
                state["layout"] = layout
            state["revision"] += 1
            state["reviewed_revision"] = None
            state["history"].append({"revision": state["revision"], "previous": previous,
                                     "answers": answers, "skip": skip, "layout": layout})
            self.write(state)
            return state

    def approve(self, session_id, expected_revision):
        with self.locked(session_id):
            state = self.get(session_id)
            if state["revision"] != expected_revision:
                raise Conflict("内容已改变，请重新审阅")
            if status(state)["missing_required"]:
                raise ValueError("仍有必填信息缺失，补充后才能确认")
            state["reviewed_revision"] = expected_revision
            self.write(state)
            return state
