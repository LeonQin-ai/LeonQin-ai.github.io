# 一个 Agent 一直记得你，却不必一直运行

上午，你在飞书里请 Agent 整理一份资料。下午再问一句「继续刚才那个任务」，你希望它还是上午那个 Agent。可如果每个用户的 Agent 都要常驻一个进程，光是等待消息也会占用机器资源。

**这个项目想做到的是：一直保留 Agent 的身份，只在有活时分配执行资源。** [super-agent-bot-plantform](https://github.com/LeonQin-ai/super-agent-bot-plantform) 用 Go 和 SQLite 保存身份与任务，用 Rust 管理执行 Worker，把推理和工具调用交给 [light-agent](https://github.com/LeonQin-ai/light-agent)。飞书私聊和按需启动 Docker Worker 已在真实 Linux 虚拟机上验证；完整的生产唤醒与休眠调度仍在建设中。上面的对话是设计想解决的场景，不是已完成的连续记忆演示。

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

## 一台 4 核机器，能同时跑多少 Agent？

如果只报「启动了多少个容器」，读者仍不知道这些 Agent 真干活时会怎样。于是复测给每个实例独立的容器、状态目录和工作区，让文件工具写入唯一标记，再核对文件内容。

| 4 vCPU、3655 MiB RAM 的 Linux VM | 完成任务 | 错误 | P95 |
| --- | ---: | ---: | ---: |
| 72 个文件工具实例，120.5 秒 | 17,113 | 0 | 315 ms |
| 80 个文件工具实例，120.5 秒 | 18,052 | 1 | 711 ms |

72 个实例达到约 **142 个文件任务/秒**，通过复测门槛。80 个实例虽然完成更多任务，却出现错误，没有达标。这比单报一个最大并发数更能说明问题：增加执行实例后，尾延迟先变差，吞吐没有按实例数同比增长。

数据来自[容量复测报告](https://github.com/LeonQin-ai/super-agent-bot-plantform/blob/acda0b6/docs/agent-capacity-followup-2026-11-07.md)。模型使用内置 Mock，文件操作是真实执行；这一测试衡量独立 Worker 的执行容量，不代表真实模型或飞书端到端吞吐。休眠身份可以存多少，也要单独测量。

## 已验证的能力与待完成的工作

项目文档记录了真实 Linux 虚拟机上的飞书私聊回复和按需 Docker Worker 验证。独立的唤醒、休眠状态机已有基础，生产驱动仍待接线。Firecracker 有 Jailer、vsock 和 Guest RPC 等基础工作，KVM 启动仍待验证；gVisor 和 WASM 有策略及能力检测框架，执行 Provider 尚未实现。容器容量测试和端到端消息吞吐需要分别读，不能互相代替。

想从源码开始，可以先看[平台架构](https://github.com/LeonQin-ai/super-agent-bot-plantform/blob/acda0b6/docs/architecture.md)，再看[持久执行](https://github.com/LeonQin-ai/super-agent-bot-plantform/blob/acda0b6/docs/durable-execution.md)与[Linux 验证记录](https://github.com/LeonQin-ai/super-agent-bot-plantform/blob/acda0b6/docs/linux-validation-2026-11-06.md)。如果想理解 Worker 里的模型和工具如何协作，可以接着读[用 C11 写 Agent Runtime](01-agent-runtime-in-c.md)。

如果只看三个入口：[项目源码](https://github.com/LeonQin-ai/super-agent-bot-plantform)看架构，[Linux 验证记录](https://github.com/LeonQin-ai/super-agent-bot-plantform/blob/acda0b6/docs/linux-validation-2026-11-06.md)看真实执行与恢复，[容量复测](https://github.com/LeonQin-ai/super-agent-bot-plantform/blob/acda0b6/docs/agent-capacity-followup-2026-11-07.md)看实例增加后系统如何变化。
