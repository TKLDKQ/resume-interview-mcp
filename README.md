# Resume Interview MCP

通过逐步追问制作中文 PDF 简历的本地 MCP 服务。每轮最多三个问题，支持后续补充、更正、跳过和断点续填。重点是让用户把真实经历说清楚，并在导出前核对。

## 功能

- 官方 MCP Python SDK 的 stdio 服务，原生 `elicitation/create` 表单询问。
- 客户端不支持表单时返回相同的结构化问题，由聊天助手提问并提交回答。
- 按求职方向、个人信息、技能、逐个项目、奖项的顺序采集，已有回答不会重复询问。
- 项目按背景、个人职责、解决方案、成果和证据分别追问，支持最多三个项目。
- 取消保留当前轮，拒绝跳过当前轮，空白项可暂时跳过，缺少必填信息时不能确认导出。
- 本地原子快照、操作历史、OS 文件锁、revision 乐观并发检查，支持重启后继续。
- `classic`、`compact` 两套内置模板。AI 可根据用户偏好提出颜色、字号、边距和栏目顺序，由 `set_layout` 校验应用。
- 修改答案或布局会撤销原确认，用户重新审阅后可导出 PDF，返回真实页数和超页提示。

## 运行

Python 3.11 或更高版本。在项目目录创建本地虚拟环境后安装：

```powershell
python -m venv .venv
.venv\Scripts\python.exe -m pip install -e .
.venv\Scripts\python.exe -m resume_mcp.server
```

stdio 服务启动后等待 MCP 客户端连接。不要把普通日志写到 stdout。安装均在项目的虚拟环境内完成。

支持 stdio 的 MCP 客户端可使用以下配置，路径按实际位置替换：

```json
{
  "mcpServers": {
    "resume-interview": {
      "command": "C:/path/resume-interview-mcp/.venv/Scripts/python.exe",
      "args": ["-m", "resume_mcp.server"],
      "cwd": "C:/path/resume-interview-mcp",
      "env": {
        "RESUME_DATA_DIR": "C:/path/resume-interview-mcp/.resume-data"
      }
    }
  }
}
```

没有额外模型密钥的要求。自然语言理解和 AI 布局建议由连接 MCP 的助手提供，服务器负责提问计划、事实存储、布局校验和 PDF 渲染。

## 立即体验提问流程

终端演示客户端会连接真实 MCP 子进程，通过表单回调在终端逐项询问：

```powershell
.venv\Scripts\python.exe examples/interview_client.py
# 暂停后，用客户端输出的 session_id 继续
.venv\Scripts\python.exe examples/interview_client.py --session <session_id>
```

`/cancel` 暂停当前轮，`/decline` 跳过整轮，回车跳过单项。被跳过的必填项会在确认前要求补填。可选项可以保持为空。

生成虚构资料演示 PDF：

```powershell
.venv\Scripts\python.exe examples/demo.py
```

## 工具调用顺序

1. `start_resume` 返回 session_id、revision 和第一轮问题。
2. `interview_resume(session_id, expected_revision, ctx)` 向用户发起一轮原生表单。
3. 若返回 `mode=chat`，助手展示 `questions`，等用户回答，再调用 `submit_answers`。
4. 重复到信息完整。用户随时更正某个字段，或者增加 `project_count` 后补项目。
5. `review_resume` 展示所有已采集内容，用户确认后调用 `confirm_resume`。
6. `export_pdf` 返回本地 PDF 文件路径、页数和布局提示。

`get_resume` 可随时恢复会话。revision 必须使用最近一次工具返回的值。版本冲突时重新获取状态，核对后提交，不能盲目覆盖。

基础字段有 `name`、`target`、`template`、`project_count`、`education`、`contact`、`skills`、`experience`、`awards`、`extra`。项目字段采用 `p1_name`、`p1_role`、`p1_period`、`p1_background`、`p1_task`、`p1_solution`、`p1_result`、`p1_evidence`，第二、三个项目对应 `p2_`、`p3_`。单个答案最多 4000 字符。

## AI 模板示例

用户要求「黑白、项目在前、紧凑单栏」时，助手可以提出以下布局并调用 `set_layout`：

```json
{
  "accent": "#222222",
  "font_size": 10,
  "margin_mm": 14,
  "sections": ["skills", "projects", "education", "experience", "awards", "extra"]
}
```

布局只改变样式和顺序，所有栏目必须在配置中出现。允许的字号范围为 9.5–12 pt，边距为 12–24 mm，颜色必须是十六进制值。用户内容按文本转义处理。

第一版的「AI 模板」指受约束的版式参数设计。目前支持内置模板与此布局配置，不导入任意 Word 模板，也不生成可执行 HTML/CSS。长内容如超过一页，会返回提示，用户可缩短内容后重新确认，服务器不会承诺任意输入都能塞进一页。

## 核心设计

详见 [访谈流程与边界](DESIGN.md)。MCP 客户端需要支持 Elicitation 才会显示原生表单，服务器不能在工具调用之外自行弹窗，也不能替用户作答。聊天回退路径允许不支持表单的助手继续工作。

## 测试

```powershell
.venv\Scripts\python.exe -m unittest discover -s tests -v
```

测试覆盖分轮提问、跳过后补填、重启恢复、版本冲突、无效答案的事务回滚、动态项目数量、布局边界、中文 PDF、超页提示，以及真实 MCP stdio 下的表单接受/拒绝/取消和聊天回退。

## 本地数据

默认将会话和 PDF 写入当前目录的 `.resume-data/`，可通过 `RESUME_DATA_DIR` 改变目录。会话含原始回答与更正历史，PDF 包含用户选择展示的信息。该目录已加入 `.gitignore`。示例使用虚构姓名和示例邮箱，不含作者真实简历或密钥。

目前仅提供本地 stdio 连接，未实现多用户账号、远程服务认证、扫描件 OCR 或现有简历自动导入。

## 参考

- [MCP Python SDK v1.26.0](https://github.com/modelcontextprotocol/python-sdk/tree/v1.26.0)
- [原生 Elicitation 实现](https://github.com/modelcontextprotocol/python-sdk/blob/v1.26.0/src/mcp/server/elicitation.py)
