"""Deterministic question planning. Only user-confirmed fields enter a resume."""
from dataclasses import dataclass


@dataclass(frozen=True)
class Question:
    key: str
    title: str
    help: str
    required: bool = False
    choices: tuple[str, ...] = ()

    def public(self):
        return {"field": self.key, "question": self.title, "guidance": self.help,
                "required_for_export": self.required, "choices": list(self.choices)}


def groups(facts):
    yield [
        Question("target", "准备投什么岗位或使用场景？", "可写学校双选会软件开发，也可填写具体岗位。", True),
        Question("template", "选择哪种简历模板？", "classic 为经典单栏，compact 为紧凑单栏，ai 为自定义布局。", True,
                 ("classic", "compact", "ai")),
        Question("project_count", "准备写几个代表项目？", "填 0 到 3。没有项目可以填 0，稍后继续补充。", True,
                 ("0", "1", "2", "3")),
    ]
    yield [
        Question("name", "简历上使用什么姓名？", "只填写希望展示的姓名。", True),
        Question("education", "学校、学历、专业和起止时间？", "例如：示例大学｜本科｜软件工程｜2023—2027。可跳过。"),
        Question("contact", "希望公开展示哪些联系方式？", "电话、邮箱或作品链接均可，只填愿意出现在 PDF 中的信息。可跳过。"),
    ]
    yield [Question("skills", "你能用哪些技术完成什么工作？", "例如 Python 批量读取文件并导出 Excel。请写能举例说明的能力。", True),
           Question("experience", "是否有实习或工作经历？", "写公司、职位、时间和实际职责；没有可跳过。")]
    count = int(facts.get("project_count", "0"))
    for i in range(1, count + 1):
        prefix = f"p{i}_"
        yield [Question(prefix + "name", f"第 {i} 个项目叫什么？", "写项目名称。", True),
               Question(prefix + "role", "你在这个项目中负责什么？", "独立开发，或具体团队分工；不要把团队全部工作写成个人成果。", True),
               Question(prefix + "period", "项目在什么时间完成？", "写实际起止年月，不确定可跳过。")]
        project_name = facts.get(prefix + "name", f"项目 {i}")
        yield [Question(prefix + "background", f"「{project_name}」解决什么问题？", "说明使用者和需求，可跳过。"),
               Question(prefix + "task", f"「{project_name}」你实际完成了什么？", "写自己的实现内容，例如数据导入、接口联调、桌面小组件。", True),
               Question(prefix + "solution", "用了什么技术，怎么实现？", "写技术选择和实现方法；若使用 AI 辅助，也可说明你负责的设计与验证。", True)]
        yield [Question(prefix + "result", f"「{project_name}」有哪些可验证的成果？", "交付功能、获奖、用户反馈均可；没有数据就写功能，不必编造指标。"),
               Question(prefix + "evidence", "有演示、源码或其他证明吗？", "可填公开链接或证明说明，可跳过。")]
    yield [Question("awards", "有哪些值得展示的奖项或资格证书？", "注明年份、全称和等级，可跳过。"),
           Question("extra", "还有要补充或更正的信息吗？", "可补充到岗时间、作品链接或其他经历，可跳过。")]


def all_questions(facts):
    return [question for group in groups(facts) for question in group]


def next_questions(state):
    for group in groups(state["facts"]):
        remaining = [q for q in group if q.key not in state["facts"] and q.key not in state["skipped"]]
        if remaining:
            return remaining[:3]
    return []


def validate_answers(facts, answers):
    # Validate the count first so newly added project fields are accepted in the same update.
    merged = dict(facts)
    if "project_count" in answers:
        if answers["project_count"] not in ("0", "1", "2", "3"):
            raise ValueError("project_count 必须为 0、1、2 或 3")
        merged["project_count"] = answers["project_count"]
    known = {q.key: q for q in all_questions(merged)}
    # Preserve dormant projects when the project count is reduced, and permit later corrections.
    known.update({q.key: q for q in all_questions({"project_count": "3"})})
    for key, value in answers.items():
        if key not in known:
            raise ValueError(f"未知字段：{key}")
        if not isinstance(value, str) or not value.strip() or len(value) > 4000:
            raise ValueError(f"{key} 需为 1 到 4000 字符的非空文本；不填写请使用 skip")
        if known[key].choices and value not in known[key].choices:
            raise ValueError(f"{key} 可选值：{known[key].choices}")


def status(state):
    required = [q.key for q in all_questions(state["facts"]) if q.required and not state["facts"].get(q.key)]
    return {"session_id": state["id"], "revision": state["revision"],
            "facts": state["facts"], "skipped": state["skipped"],
            "questions": [q.public() for q in next_questions(state)],
            "missing_required": required, "can_review": not required,
            "reviewed_revision": state.get("reviewed_revision"),
            "next_action": "ask_user" if next_questions(state) else "review_resume"}
