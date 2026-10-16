# 用实验读懂 Cognitive OS，并准备一次技术面试

> 介绍一个 Agent 项目，最有说服力的方式是给读者一条能跑、能观察、能核对的路径。这篇用三个小实验，把前面讨论的 Runtime 能力串起来。

这是 [Cognitive OS](https://github.com/LeonQin-ai/cognitive-os-agent) 技术系列第 8 篇，也是整组文章的实践入口。

## 准备一个独立工作区

按照仓库构建文档生成 CLI。Windows 示例：

```powershell
cd backend
.\build.ps1 -Target cli
New-Item -ItemType Directory -Force state-blog-demo,workspace-blog-demo | Out-Null
.\build\cognitive-os-agent.exe --state state-blog-demo --workspace workspace-blog-demo serve 18300
```

在启动前创建测试目录，并在所选 state 中配置模型；也可以先用项目的 mock 模式理解调用链。mock 用于确定性离线验证，不能用它的固定回答评价真实模型的理解质量。

服务启动后打开 `http://localhost:18300`，在模型页面配置你使用的接口和模型；配置项与本地模型接入方式见文末运行文档。密钥保留在本地配置中，不要放进准备公开的文章、截图或 issue。

Linux/macOS 按仓库 `make` 或 CMake 构建说明执行，对应二进制通常不带 `.exe`。下面的 HTTP 示例使用同一个 `18300` 端口。

## 实验一：让文件结果说话

向 `POST /v1/chat` 发送：

```json
{"message":"创建 note.txt，内容为 hello","session":"blog-files"}
```

拿到 `id` 后，查询 `GET /v1/tasks/<id>`。不要只停在最终自然语言答案：检查任务状态、工具步骤、测试 workspace 中的文件和实际内容。

再读取 `/v1/tasks/journal`，观察持久任务记录。这一步把“可以执行动作”的演示升级成“可以核对动作与记录”的演示。

如果所用模型不按工具协议提出动作，Runtime 可能要求继续规划或报告未完成。遇到失败应保留模型协议、错误和步骤，而不是为了演示好看把失败当成成功。

## 实验二：让架构师与评审互相回答

先注册两位角色：

```bash
curl -X POST http://localhost:18300/v1/agents \
  -H 'Content-Type: application/json' \
  -d '{"name":"architect","role":"提出方案，并回应评审的问题"}'
curl -X POST http://localhost:18300/v1/agents \
  -H 'Content-Type: application/json' \
  -d '{"name":"reviewer","role":"检查边界条件，提出具体问题并核对回答"}'
```

创建群聊并记录返回的房间 `id`：

```json
{
  "name":"方案讨论",
  "kind":"group",
  "members":["architect","reviewer"],
  "discussion_rounds":3
}
```

向 `POST /v1/im/sessions/<id>/messages` 提交：

```json
{"content":"讨论如何给源码阅读任务设计完整性验证。请互相提问，并说明各自观点需要哪些证据。"}
```

重点观察第二轮：架构师是否真的回答了评审的具体问题？评审是否针对回答更新意见？单纯重复角色介绍不算有深度的讨论。轮数和输入管道由 Runtime 提供，观点质量仍需读者判断。

界面左侧可以看到当前角色和轮次，也可以停止。讨论期间发送新的用户消息，旧任务会被接管，迟到回复不能继续进入房间。尝试一次这样的补充要求，比只看一段顺畅的最终回答更能理解调度边界。

## 实验三：用测试观察失败

构建 CLI 与测试程序后，另开终端，从仓库根目录运行以下回归：

```bash
cd backend
python tests/test_im_discussion_e2e.py
python tests/test_completion_recovery_e2e.py
python tests/test_crash_recovery_e2e.py
```

它们使用自己的临时状态与测试进程：讨论测试检查互相引用、停止、接管和失败；阅读测试检查未到 EOF 的任务如何继续；崩溃测试终止其创建的 Runtime，核对中断识别与显式恢复。

这些用例使用本地 fixture，便于反复复现控制流。它们不会证明所有生产模型行为和所有外部命令都已被覆盖。

## 把实验一变成可重复的验收脚本

界面适合观察过程，脚本适合固定成功标准。下面用 Python 标准库提交请求、等待终态，再检查工作区文件。先按前面的命令启动服务；脚本从 `backend` 目录运行，对应 `workspace-blog-demo`。它使用真实配置的模型，可能产生模型调用费用。

```python
import json
import time
import urllib.request
from pathlib import Path

BASE = "http://127.0.0.1:18300"

def request(path, body=None):
    data = None if body is None else json.dumps(body, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(BASE + path, data=data,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=10) as response:
        return json.load(response)

def wait_task(task_id, seconds=180):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        task = request(f"/v1/tasks/{task_id}")
        if task["status"] in {"DONE", "FAILED", "CANCELLED", "TIMEOUT"}:
            return task
        time.sleep(0.25)
    raise TimeoutError("本地轮询到期，请继续检查任务状态")

target = Path("workspace-blog-demo/note.txt")
if target.exists():
    raise RuntimeError("note.txt 已存在，请为本次实验使用全新的工作区")
created = request("/v1/chat", {
    "message": "创建 note.txt，内容为 hello",
    "session": "blog-files",
})
task = wait_task(created["id"])
print("状态:", task["status"])
print("答复:", task.get("output", ""))
assert task["status"] == "DONE", task
assert target.exists(), "模型或状态声称完成，但文件不存在"
assert target.read_text(encoding="utf-8").strip() == "hello"
print("PASS：本次新工作区中的文件与任务结果一致")
```

为什么先拒绝已有 `note.txt`？否则上次遗留的文件可能让本次实验假通过。相同逻辑适用于 PPT：打开一个已经存在的旧文件，不能证明刚提交的任务完成了新版本。

上面本地轮询超时只代表脚本停止等待，不会自动取消后端任务。如果要停止任务，需要对该任务 ID 发取消请求。若服务启用 API 认证，request 还需按运行文档增加 Authorization；不要把真实令牌写进准备提交的脚本。

## 给群聊一个能检验深度的题目

“讨论架构”范围过大，很容易得到两段泛泛的介绍。可以把题目改成：

```text
我们用字节偏移和 EOF 判断源码是否读完。
architect：提出一个可实现的最小方案，列出依赖的假设。
reviewer：至少给出一个会推翻该方案的反例。
第二轮必须回答对方上一轮的问题；第三轮列出已验证、未验证和仍有分歧的结论。
```

接着用一张记录表评价结果，而不只看是否产生六条消息：

| 检查项 | 你应保存的证据 |
| --- | --- |
| reviewer 是否针对方案提问 | 对应的原句与问题 |
| architect 第二轮是否回应 | 回答具体覆盖了哪个问题 |
| 是否出现方案修正 | 修正前后有哪些不同 |
| 是否承认验证缺口 | 结论对应工具证据还是推断 |
| 新消息是否接管 | 旧任务结束方式与迟到回复情况 |

可以再做一个对照：轮数设为 1 与 3，使用同一道题，记录耗时、模型调用数以及未回答问题数。这样你得到的是交互机制的观察，而不是仅凭一次感觉评价“多 Agent 更聪明”。真实模型存在随机性，比较质量时还需要多次运行。

## 加一个 DAG 实验：让总结等待证据

先通过前文接口注册 reader 和 reviewer（或把下面名字换成你已注册的角色），在 `workspace-blog-demo` 创建 `evidence.txt`，内容为一个你知道答案的小样本。随后向 `POST /v1/flows` 提交：

```json
{
  "nodes": [
    {
      "id": "read",
      "agent": "reader",
      "task": "读取 evidence.txt，准确摘录其中的证据，不要修改文件"
    },
    {
      "id": "review",
      "agent": "reviewer",
      "task": "只做文字核对：根据上游 {{read}}，列出事实、推断和缺失证据"
    }
  ],
  "edges": []
}
```

返回任务 ID 后，查询 `/v1/tasks/<id>`，查看 `flow_nodes`。`{{read}}` 会形成依赖；review 在 read 成功前应保持 queued。真实模型可能回复很快，手工轮询未必捕捉得到中间态，所以确定性验证仍应使用仓库的 `test_flow_dependencies_e2e.py`：它通过 fixture 阻塞上游，使“下游未启动”成为稳定可测的窗口。

再把上游文件名换成不存在的路径。预期不是 reviewer 猜测文件内容，而是上游失败、下游 blocked。这个实验把协作从角色名称提升到执行条件，适合用来讲解为什么群聊和 DAG 提供不同能力。

## 为面试准备一条 15 分钟讲解路线

面试演示不宜从模块清单开始，更适合围绕“怎样让一次 Agent 操作可信”组织：

| 时间 | 内容 | 具体证据 |
| --- | --- | --- |
| 0–2 分钟 | 用户问题与系统边界 | 创建文件、完成状态与实际内容 |
| 2–5 分钟 | 一条调用链 | API → Scheduler → Reasoning → Tool → Journal |
| 5–8 分钟 | 一个困难的并发点 | 群聊接管时迟到结果被拒绝 |
| 8–11 分钟 | 一个失败与恢复案例 | 依赖阻断或进程重启识别中断 |
| 11–13 分钟 | 一组测量 | 百万任务负载、P99 与 RSS 口径 |
| 13–15 分钟 | 设计取舍与未完成工作 | 层式屏障、同步 I/O、产物验证边界 |

提前准备“如果网络不可用怎么办”：保留本地 fixture 回归和原始数据，明确说明正在演示控制流而非真实模型质量。现场演示若失败，就沿日志解释失败层次；把失败改称成功，比失败本身更影响技术可信度。

你还可以按三个深度准备答案：30 秒描述问题，2 分钟解释设计，5 分钟打开关键函数和测试。面对追问，优先给函数入口、状态不变量与证据，不必背诵所有目录名。

## 常见故障先从哪一层看

| 现象 | 优先核对 | 下一步 |
| --- | --- | --- |
| HTTP 400 | 字段名与 JSON | `/v1/chat` 使用 message，检查响应错误正文 |
| HTTP 409 模型未配置 | 生效 state、路由与模型配置 | 按模型配置提示补齐，再重试 |
| 连接不到服务 | 端口、监听进程、启动日志 | 确认实际是 18300 且服务未退出 |
| 群聊没有角色 | 注册表与 members | 先注册，再检查房间成员 |
| 显示完成但无文件 | 工具步骤与新产物 | 判断是否只读、只检查环境或计划未解析 |
| 源码反复从头读 | 返回的 next_offset_bytes | 保留真实分页记录，检查是否忽略连续前沿 |
| 旧 bug 仍能复现 | 实际运行二进制 | 对照安装路径、构建来源，确认已更新并重启 |

这里最容易混淆的是“我已经拉了最新源码”和“桌面程序已经运行最新代码”。桌面启动器通常启动安装目录下的可执行文件，未必使用你刚编译的 build 目录。排错记录应指向实际进程。

## 从一个小而完整的贡献开始

一个可审阅的改动可以只解决一个失败条件，例如中文页尾的偏移处理。但它应包含触发输入、预期结果、修复、相邻反例和测试命令。无需为了一个小 bug 重构所有模块；也不要只新增一条永远返回成功的 mock 断言。

建议按这个顺序准备贡献材料：

1. 固定一个最小复现，说明当前实际状态和预期状态。
2. 指出失败发生在解析、执行、状态还是展示层。
3. 在正确层修复，保留与上下游的接口语义。
4. 用真实文件、状态或请求记录证明行为改变。
5. 在提交说明中记录测试范围与仍未覆盖的情况。

这套流程也能直接变成面试素材：你不仅说明加了什么功能，还能说明为什么这样定位、怎样证明修复有效，以及哪些保证目前还没有建立。

源码阅读基线：[HTTP 字段与任务入口](https://github.com/LeonQin-ai/cognitive-os-agent/blob/cca98b6/backend/src/api/api_rest.c)、[依赖端到端用例](https://github.com/LeonQin-ai/cognitive-os-agent/blob/cca98b6/backend/tests/test_flow_dependencies_e2e.py)、[CLI 配置和启动](https://github.com/LeonQin-ai/cognitive-os-agent/blob/cca98b6/backend/cli/main.c)。

## 可以从哪里参与

如果你喜欢 C 系统编程，可以阅读调度器的生命周期、引用和取消边界；如果关注 Agent 行为，可以增加真实失败的最小回归；如果熟悉文档、多模态或不同模型协议，可以提供带脱敏输入、格式与错误阶段的兼容性案例。

一个有帮助的 issue 通常包含：使用版本、操作系统、模型与接口类型、最小触发步骤、预期行为、实际任务状态、展开后的工具结果。不要提交密钥、SSH 密码或不希望公开的文件。

项目仍有很多值得探索的地方，例如多轮讨论的质量评估、更细的 Context 选择、外部动作的幂等设计和跨平台性能复测。欢迎先跑一个小实验，再带着观察参与讨论。

项目：[GitHub 仓库](https://github.com/LeonQin-ai/cognitive-os-agent)、[中文 README](https://github.com/LeonQin-ai/cognitive-os-agent/blob/main/README.zh-CN.md)、[运行与 API 文档](https://github.com/LeonQin-ai/cognitive-os-agent/blob/main/backend/README.md)。演示：[真实操作录像](https://github.com/LeonQin-ai/cognitive-os-agent/blob/main/backend/docs/runtime-demo.mp4)。

上一篇：[百万任务实测](07-million-task-benchmark.md)；返回[系列目录](README.md)。如果这些工程问题也是你正在解决的，欢迎关注、试用或贡献 Cognitive OS。
