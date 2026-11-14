# Agent 关掉执行进程后，怎么接着工作？

我在 [light-agent](https://github.com/LeonQin-ai/light-agent) 之外做了一个上层项目：[super-agent-bot-plantform](https://github.com/LeonQin-ai/super-agent-bot-plantform)。前者负责 Agent 的推理和执行过程；后者关心一个跨进程的问题：用户隔一段时间回来继续对话时，怎样找到原来的 Agent，又不必为每个 Agent 一直保留一个执行进程？

## 持久化的到底是哪一部分？

假设一个用户在飞书私聊里提交任务，稍后再追问进展。平台需要保留 Agent 身份、任务状态、收件箱和记忆引用。Worker 的进程号、容器以及当次执行使用的系统资源则可以随执行生命周期结束。两类对象通过任务与运行时记录关联，执行器更换后不必重新分配用户的 Agent 身份。

| 对象 | 生命周期 | 负责组件 |
| --- | --- | --- |
| Agent 身份、任务、收件箱 | 跨进程保留 | Go 控制面与 SQLite |
| 主机能力与准入条件 | 定期刷新，过期后重新探测 | 控制面与 Rust 主机代理 |
| Worker 及内部命令 | 随执行需要创建和回收 | Docker/runc 与 Worker 内的 cos-execd |

## 从一条消息到一次执行

飞书桥接进程通过 WebSocket 接收私聊消息，将允许的请求转给 Go 控制面。控制面先处理身份关联与持久化去重，再选择执行路径；配置 C11 Worker 后，普通 API 消息和飞书私聊都可交给 light-agent 执行。受信命令队列是另一条入口，不能把飞书回复成功当作所有命令执行流程都已验收。

配置写着“使用某后端”只是意图。准入还需要检查主机能力记录是否有效，以及该后端是否真的接入调度器。当前可用的执行路径是 Docker；主机探测失败时停止接纳对应执行请求，避免把未知能力当成可用能力。

## 崩溃之后，为什么不默认重放？

如果 Worker 已经执行了操作，但控制面还没写入任务终态，此时直接重跑可能重复产生副作用。项目在启动 Worker 前记录其标识；控制面重启后清理有记录的 Worker，并将中断任务标记为失败，不自动重放。幂等提交可以帮助处理重复请求，但它不能证明外部动作已经执行了几次。

复核这条路径时，可以在独立测试环境中对照任务记录、Worker 标识和执行输出：正常完成时三者应能对应；中断时重点看是否留下可诊断的任务状态，以及后续请求是否还能进入系统。这里的验收对象是可观察的恢复行为，而不是模型在回答里声称“已经恢复”。

## 已验证的能力与待完成的工作

项目文档记录了真实 Linux 虚拟机上的飞书私聊回复和按需 Docker Worker 验证。独立的唤醒、休眠状态机已有基础，生产驱动仍待接线。Firecracker 有 Jailer、vsock 和 Guest RPC 等基础工作，KVM 启动仍待验证；gVisor 和 WASM 有策略及能力检测框架，执行 Provider 尚未实现。容器容量测试和端到端消息吞吐需要分别读，不能互相代替。

想从源码开始，可以先看[平台架构](https://github.com/LeonQin-ai/super-agent-bot-plantform/blob/acda0b6/docs/architecture.md)，再看[持久执行](https://github.com/LeonQin-ai/super-agent-bot-plantform/blob/acda0b6/docs/durable-execution.md)与[Linux 验证记录](https://github.com/LeonQin-ai/super-agent-bot-plantform/blob/acda0b6/docs/linux-validation-2026-11-06.md)。如果想理解 Worker 里的模型和工具如何协作，可以接着读[用 C11 写 Agent Runtime](01-agent-runtime-in-c.md)。
