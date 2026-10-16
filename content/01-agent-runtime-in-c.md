# 我为什么用 C11 写一个 Agent Runtime

> 当一个 Agent 开始读文件、运行命令和协调其他角色，问题就从“模型怎么回答”扩展为“系统怎么执行”。Cognitive OS 是我沿着这条边界做的一个开源项目：把任务状态、调度、记忆、上下文和执行放进可检查的 Runtime。

项目地址：[cognitive-os-agent](https://github.com/LeonQin-ai/cognitive-os-agent)。本文是源码与实测系列的第 1 篇。

## 从“创建 note.txt”看问题

用户输入“创建 note.txt，内容为 hello”，一个有用的系统至少要回答这些问题：工作目录在哪里？模型返回的工具参数是否有效？写入失败时保留什么？前端显示完成，是否真的代表文件存在？进程重启后还能不能找到执行记录？

这些问题分布在同一条链路上，却不能只靠一段提示词解决。模型可以提出 `file_write` 动作；动作解析、策略检查、实际文件操作和状态记录仍需要确定性的程序负责。

在 Cognitive OS 中，这条链路大致是：

```mermaid
flowchart LR
    U[用户请求] --> A[HTTP / CLI]
    A --> S[任务调度器]
    S --> R[Reasoning Loop]
    R --> L[模型提出计划]
    L --> P[计划解析与策略]
    P --> T[工具与事务]
    T --> V[观察与完成校验]
    V --> R
    V --> J[任务记录与界面]
```

模型会多次参与推理，Runtime 则持续掌握任务的生命周期。一次调用返回了自然语言，并不意味着整项工作已经完成。

## C11 的选择意味着什么

我希望尽量直接地控制对象所有权、线程、文件和跨平台接口，因此用 C11 实现核心。项目通过 OS 抽象层连接线程、协程、网络、进程和文件能力；上层的调度、推理和工具接口复用这些基础设施。

这种选择会增加内存管理、错误路径和平台适配的工作量。它的价值在于系统行为比较容易从调用链追踪：谁创建任务、谁持有引用、谁写终态、哪个边界检查取消，都可以落到具体函数。

这并不自动带来更好的推理质量，也不能仅凭实现语言推导性能优势。模型质量取决于选用的模型、输入证据和任务；Runtime 的性能需要用实际负载测量。

## 把职责拆开之后

目前的核心可以从四个方向阅读：

| 层次 | 负责的事 | 入口 |
| --- | --- | --- |
| 调度与生命周期 | 排队、执行、取消、完成历史 | `runtime/scheduler.c` |
| 推理循环 | 规划、工具观察、重试与完成判断 | `cognition/reasoning.c` |
| 知识与上下文 | 记忆访问、召回、活动上下文预算 | `memory/`、`context/` |
| 动作与交互 | 工具、事务、HTTP、Web 界面 | `action/`、`tx/`、`api/` |

例如多 Agent 不必都占用一个独立进程。角色由 AgentPool 注册，任务由调度器管理；角色数量、排队任务数量和实际工作线程数量是不同指标。后面讨论百万任务测试时，这个区别非常重要。

## 一个可以核对的入口

按照仓库构建说明启动服务，默认示例端口使用 `18300`。在独立测试 workspace 中，可以发送：

```bash
curl -X POST http://localhost:18300/v1/chat \
  -H 'Content-Type: application/json' \
  -d '{"message":"创建 note.txt，内容为 hello","session":"blog-demo"}'
```

接口返回任务 `id`。随后读取 `/v1/tasks/<id>`，核对终态和工具步骤，再检查工作目录中的文件。`/v1/tasks/journal` 用于查看持久任务历史。这样的演示把“模型说完成”和“可以检查的结果”连起来了。

工具执行使用运行账户拥有的权限。策略、事务与审计可以帮助约束和追踪操作，但它们不构成对任意外部命令的安全保证；适合先在明确范围的测试工作区里体验。

## 沿着调用链阅读：请求如何变成任务

阅读入口不必从数千行的推理代码开始。我更建议先建立三个对象的关系：`runtime_ctx` 持有运行时组件，Scheduler 持有任务生命周期，Reasoning 实例负责一次会话的规划与观察。它们分别回答“系统有什么”“工作处于什么状态”“下一步做什么”。

服务在 `init()` 中装配配置、策略、工具、记忆、快照和调度器。配置具有明确的覆盖顺序：默认值、状态目录中的配置文件、`COA_` 环境变量，部分显式 CLI 配置再覆盖最终值。排查“为什么用了另一组模型或工作目录”时，应查看生效配置和启动参数，而不只看自己修改过的 JSON。

任务被接纳后获得 ID，进入 ready queue。工作线程取出任务，创建协程，执行 runner；runner 驱动推理循环，再把结果交回调度器。下面是阅读用的简化流程，省略锁、引用和错误处理：

```text
提交请求 → 分配 task / 分配 ID → 加入 ready queue
worker 取出 task → 懒创建 coroutine → runner
runner → 上下文 → 模型计划 → 工具 → 观察 → 下一轮
runner 返回 → Scheduler 记录终态 → completion callback
callback 完成 → completed 可回收 → 裁剪内存历史
```

这里存在两个不同的“结束”：runner 已返回，和完成回调已结束。回调可能还需要将结果写入 journal 或广播进度。如果任务对象在前者就被释放，回调会访问失效内存；因此源码明确要求完成回调先结束，任务才进入可回收状态。

## Ready queue 为什么使用二叉堆

`scheduler.c` 的 `queue_insert()` 和 `queue_pop()` 实现最小堆。比较规则很短，下面是源码节选：

```c
static int task_less(const task *a, const task *b) {
    if (a->priority != b->priority)
        return a->priority < b->priority;
    return a->id < b->id;
}
```

数值较小的 priority 先执行，相同优先级按 ID 排序。这提供了稳定、可解释的次序。若用有序数组，每次插入或取走队首都可能移动大量元素；堆把插入和取出降为 `O(log Q)`，其中 Q 是排队长度。

但不能因此把整个调度器描述为所有操作都是 `O(log Q)`。历史记录裁剪、任务查找和输出序列化有自己的路径。做性能分析时，需要分别看提交、出队、执行、完成通知与历史回收；优化一个容器不等于消除整个系统的瓶颈。

堆也没有自动解决饥饿。如果高优先级任务源源不断，低优先级任务可能长期等待。当前这段比较代码没有体现优先级老化；若业务要求等待时间上界，后续应设计老化策略或配额，并把它变成专门的负载测试。

## 协程很多，线程为什么不必很多

调度器在任务第一次真正运行时才调用 `coro_new()`，不会在接纳任务时为所有排队项提前分配协程栈。源码注释明确指出，这避免了为每个等待任务预付默认栈空间。

举一个只用于理解容量的估算：如果每个尚未运行的任务都提前保留 256 KiB 栈，十万项任务对应约 24.4 GiB 的地址空间。这个算式不是本项目 RSS 测量值，却能解释为什么“接纳任务”和“创建执行栈”应分开。

`scheduler_yield()` 调用协程让出接口。让出后的 continuation 会进入当前 worker 的本地队列，继续由原线程恢复，因为 Fiber/ucontext 的状态与执行线程有关。把 continuation 直接迁到任意线程，不能只修改一个队列指针就认为安全。

还要区分协程让出与阻塞 I/O。一个同步 HTTP 请求如果一直阻塞线程，即使任务由协程包装，也不会自动变成非阻塞网络调用。因此这里的 M:N 组织方式有助于管理执行单元，但真实吞吐仍受工具、模型等待和取消检查位置限制。

## C 代码里最值得看的是所有权

在 C 中，一个 JSON 输出、一段模型回答、一个 task 指针，都必须有明确的释放方。以任务查询为例：API 如果只拿到一个裸指针，调度器恰好在另一线程裁剪历史，读取输出时就可能发生 use-after-free。

项目提供 `scheduler_acquire()` / `scheduler_release()` 这样的持有接口，配合历史裁剪对 references、borrowed 等条件的检查。应重点阅读“获得引用时是否持锁”“释放引用后是否还使用字段”“回调期间是否允许回收”，而不是只检查正常路径有没有 `free()`。

| 对象或资源 | 应核对的所有权问题 | 典型失败表现 |
| --- | --- | --- |
| 模型返回的字符串 | 谁接管，重试分支是否释放 | 长任务内存逐轮增加 |
| 工具参数 JSON | 是否借用解析树内部字符串 | 释放 JSON 后路径变成乱码 |
| task 对象 | 查询与历史裁剪如何同步 | 偶发崩溃、输出损坏 |
| 完成回调 | 回调结束前对象能否回收 | journal 写入访问失效对象 |
| 部分初始化的组件 | 初始化失败怎样逆序清理 | 启动失败后句柄泄漏 |

这也是我选择 C11 后必须承担的成本：这些约束更显式，错误也更直接。工程价值来自把约束落实并验证，不能由“没有垃圾回收”直接推出低延迟或低内存。

源码阅读基线：[装配入口](https://github.com/LeonQin-ai/cognitive-os-agent/blob/cca98b6/backend/src/cognitive_os_agent.c)、[队列、worker 与回收](https://github.com/LeonQin-ai/cognitive-os-agent/blob/cca98b6/backend/src/runtime/scheduler.c)、[任务结构](https://github.com/LeonQin-ai/cognitive-os-agent/blob/cca98b6/backend/include/runtime/task.h)。这些链接固定到本文核对的提交，后续实现可能继续变化。

## 为什么值得继续看

Cognitive OS 最吸引我的部分，是把 Agent 问题拆成可验证的系统问题：讨论如何停止、依赖何时满足、上下文为什么被淘汰、恢复后能否继续执行。这个项目仍在演进，适合对 Agent 基础设施、C 系统设计和可靠执行感兴趣的开发者一起研究。

源码：[Runtime 装配](https://github.com/LeonQin-ai/cognitive-os-agent/blob/main/backend/src/cognitive_os_agent.c)、[Scheduler](https://github.com/LeonQin-ai/cognitive-os-agent/blob/main/backend/src/runtime/scheduler.c)、[Reasoning](https://github.com/LeonQin-ai/cognitive-os-agent/blob/main/backend/src/cognition/reasoning.c)。

下一篇：[让多个 Agent 真正讨论起来](02-agent-group-discussion.md)。欢迎运行项目、提出可复现的问题，或从一个小模块开始参与。
