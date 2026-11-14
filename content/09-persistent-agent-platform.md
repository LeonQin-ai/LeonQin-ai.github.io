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

## 怎么把接消息和干活放到两台机器上？

如果想让飞书入口和管理看板一直在线，又不希望执行任务时的 CPU、内存峰值挤占控制面，可以把部署拆成两层。下面是按现有配置可以搭建的拓扑；文末的 Linux 验证记录证明了 Docker 执行与恢复链路，不等同于一次跨主机集群验收。

```text
飞书 ──WebSocket──> A：飞书桥接 ──本地签名转发──> Go 控制面 + SQLite
                                                    │
                                           HTTPS + 独立凭据
                                                    │
                    B：Linux 执行主机 <── Rust Sandbox Manager
                           └── Docker/runc ──> 按需启动的执行 Worker
```

- **A 节点负责接消息和记状态。** 桥接与控制面按文档配置在同一台机器。任务入队、取消、执行结果都由控制面管理，SQLite 留在这一侧。看板还能发起批量会话和定时任务：例如每天给已登记的 Agent 各入队一条任务，结果分别写回各自记录。
- **B 节点负责启动和回收 Worker。** 控制面通过 `LIGHT_AGENT_SANDBOX_MANAGER_URL` 指向独立执行主机上的 Manager。非回环地址使用 HTTPS；控制面和 Manager 分别使用独立凭据。容器内的 Agent 不持有 Docker socket，也不需要知道控制面数据库的位置。
- **执行节点失联时，入口与准入是两件事。** 管理和查询服务可以继续运行，但控制面探测失败后会停止接纳对应执行请求。真实 Linux 测试验证过 Manager 停机与恢复：恢复 Manager 后，控制面不重启也能恢复执行。

这个拆法把聊天与看板、持久状态、执行资源分开。它目前是**单控制面连接一个可远程部署的执行端**：一个执行端可以运行多个 Worker，但多执行主机自动调度、故障迁移和多副本控制面的任务所有权尚未实现。增加执行节点和增加控制面副本是两项不同的工程工作，现有容量复测也没有验证它们。

部署时可从[控制面与远程 Manager 配置](https://github.com/LeonQin-ai/super-agent-bot-plantform/blob/acda0b6/README.zh-CN.md#接通真实-docker-执行)和[Docker Worker 指南](https://github.com/LeonQin-ai/super-agent-bot-plantform/blob/acda0b6/docs/docker-provider.md)开始。先验证单节点任务，再将 Manager 移到独立主机，对照任务状态、能力探测和 Worker 清理记录。

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

上一篇：[三个上手实验](08-getting-started-and-contributing.md)；返回[系列目录](README.md)。欢迎用真实部署中的容量与恢复记录，检验这套持久执行的边界。
