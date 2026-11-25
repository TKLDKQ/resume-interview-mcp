"""Render validated data with bounded layout options; never execute AI-provided HTML."""
import re
from io import BytesIO
from pathlib import Path
from uuid import uuid4
from xml.sax.saxutils import escape

from pydantic import BaseModel, ConfigDict, Field, field_validator
from pypdf import PdfReader
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.pagesizes import A4
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.cidfonts import UnicodeCIDFont
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer


class Layout(BaseModel):
    model_config = ConfigDict(extra="forbid")
    accent: str = "#315B78"
    font_size: float = Field(default=10.5, ge=9.5, le=12)
    margin_mm: float = Field(default=16, ge=12, le=24)
    sections: list[str] = Field(default_factory=lambda: ["education", "skills", "experience", "projects", "awards", "extra"])

    @field_validator("accent")
    @classmethod
    def hex_color(cls, value):
        if not re.fullmatch(r"#[0-9a-fA-F]{6}", value):
            raise ValueError("accent 必须为 #RRGGBB")
        return value

    @field_validator("sections")
    @classmethod
    def section_order(cls, value):
        expected = {"education", "skills", "experience", "projects", "awards", "extra"}
        if set(value) != expected or len(value) != len(expected):
            raise ValueError("sections 必须为六个栏目的完整排列")
        return value


TEMPLATES = {
    "classic": Layout().model_dump(),
    "compact": Layout(font_size=10, margin_mm=14, accent="#222222").model_dump(),
}


def render_pdf(state, output_directory):
    facts = state["facts"]
    layout = Layout.model_validate(state["layout"] if facts["template"] == "ai"
                                   else TEMPLATES[facts["template"]])
    pdfmetrics.registerFont(UnicodeCIDFont("STSong-Light"))
    base = ParagraphStyle("body", fontName="STSong-Light", fontSize=layout.font_size,
                          leading=layout.font_size * 1.45, spaceAfter=4, wordWrap="CJK")
    heading = ParagraphStyle("heading", parent=base, fontSize=12, leading=17,
                             textColor=colors.HexColor(layout.accent), spaceBefore=7, spaceAfter=4)
    title = ParagraphStyle("name", parent=base, alignment=TA_CENTER, fontSize=21, leading=27)
    subtitle = ParagraphStyle("target", parent=base, alignment=TA_CENTER)
    story = []

    def paragraph(text, style=base):
        story.append(Paragraph(escape(text).replace("\n", "<br/>"), style))

    paragraph(facts["name"], title)
    paragraph(facts["target"], subtitle)
    if facts.get("contact"):
        paragraph(facts["contact"], subtitle)
    story.append(Spacer(1, 5))
    labels = {"education": "教育经历", "skills": "专业技能", "experience": "实习与工作经历",
              "projects": "项目经历", "awards": "荣誉与证书", "extra": "补充信息"}
    for section in layout.sections:
        if section == "projects":
            count = int(facts["project_count"])
            if count:
                paragraph(labels[section], heading)
            for i in range(1, count + 1):
                prefix = f"p{i}_"
                title_text = "｜".join(facts.get(prefix + key, "") for key in ("name", "role", "period")
                                      if facts.get(prefix + key))
                project_style = ParagraphStyle(f"project{i}", parent=base, keepWithNext=True,
                                               spaceBefore=5, textColor=colors.HexColor(layout.accent))
                paragraph(title_text, project_style)
                for key, label in (("background", "项目背景"), ("task", "核心任务"),
                                   ("solution", "解决方案"), ("result", "项目成果"), ("evidence", "作品证明")):
                    if facts.get(prefix + key):
                        paragraph(f"{label}：{facts[prefix + key]}")
        elif facts.get(section):
            paragraph(labels[section], heading)
            paragraph(facts[section])
    memory = BytesIO()
    margin = layout.margin_mm * 72 / 25.4
    document = SimpleDocTemplate(memory, pagesize=A4, leftMargin=margin, rightMargin=margin,
                                 topMargin=margin, bottomMargin=margin,
                                 title=f"{facts['name']} 个人简历", author=facts["name"])
    document.build(story)
    data = memory.getvalue()
    pages = len(PdfReader(BytesIO(data)).pages)
    folder = Path(output_directory)
    folder.mkdir(parents=True, exist_ok=True)
    target = folder / f"resume-{state['id'][:8]}-r{state['revision']}-{uuid4().hex[:8]}.pdf"
    target.write_bytes(data)
    return {"pdf_path": str(target.resolve()), "pages": pages,
            "warnings": ["超过一页。请缩短长段落或减少项目后重新审阅导出。"] if pages > 1 else [],
            "revision": state["revision"]}
