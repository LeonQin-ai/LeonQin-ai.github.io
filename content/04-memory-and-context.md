# 记忆与上下文分开管理：Cognitive OS 的 Memory Service 与 Context MMU

> 一段信息值得长期保留，并不代表每次请求都应把它加载进模型窗口。做 Agent 时，我发现“存什么”和“当前读什么”需要两套相互配合的机制。

这是 [Cognitive OS](https://github.com/LeonQin-ai/cognitive-os-agent) 技术系列第 4 篇。本文关注任务之外仍然存在的知识，以及一次推理实际使用的工作集。

## Memory 回答“保留什么”

项目通过 Memory Service 接口访问四类记忆：

| 类型 | 用途 |
| --- | --- |
| Working | 当前短期工作信息 |
| Episodic | 任务与结果形成的经验 |
| Semantic | 长期事实 |
| Procedural | 操作方法与过程知识 |

接口暴露 remember、forget、按键和按查询 recall 等操作，底层通过 vtable 接入实现。当前默认后端委托给项目自己的 memory facade；接口留下了替换空间，但不能把这种设计可能性写成已经完成的所有数据库集成。

更重要的是写入条件。一个任务只输出了计划、卡在工具失败或被取消，其内容不应该被当成成功经验共享给其他会话。Runtime 将完成证据和长期记忆更新联系起来，避免“我准备创建文件”逐渐变成系统记忆中的“文件已创建”。

## Context 回答“这次加载什么”

模型上下文的容量与使用成本有限。即使长期记录全部保存，当前推理也只能读取一个经过选择的集合。

Context MMU 中有两个互相独立的维度：

| 维度 | 取值 | 含义 |
| --- | --- | --- |
| 表示粒度 | L0 / L1 / L2 | 摘要索引、概览、细节 |
| 驻留状态 | HOT / WARM / COLD | 细节已加载、概览已加载、主要保留元信息 |

因此，“冷”不等于“内容被永久删掉”，“概览”也不等于“原文”。原始规范记录由记录存储保留，当前活动表示可以按预算被驱逐或重新物化。

## 一次召回的路径

```text
查询
 → 候选记录
 → 相关性及其他因素排序
 → WARM / L1 概览
 → 再排序
 → 部分记录提升到 HOT / L2
 → 超预算时淘汰
```

排序会记录 relevance、importance、confidence、utility、recency、salience、scope 等因素。与只输出一个“相关度分数”相比，这能帮助定位为什么某条记录进入或离开工作集。

表示通过内容 hash 缓存，正文变化后才需要重新派生。被选中的页面并不都能无限提升到 HOT，预算约束需要同时覆盖活动表示和缓存，避免某个未计费的细节副本绕过管理。

## “Context 预算”为什么不能等同于进程内存

这里很容易产生宣传上的误解。MMU 管理的 token 预算，针对的是被物化的上下文表示；整个进程还可能持有规范原文、索引、序列化缓冲、调度对象和系统分配器空间。

所以一个 1 GiB 原文压力实验，可能占用更多 RSS。项目保存的 768/128/128 MiB 布局实验中，峰值 RSS 约为 3197.01 MiB。这说明测试确实有额外内存成本，不能只展示缩小后的概览字节数，就把它描述为整个系统的常驻内存。

概览是有损的。测试核对的“完整恢复”，指从规范记录重新加载正文后，原始长度和内容 hash 一致；它不表示可以从有损概览单独重建全部原文，也不代表向远程模型发送过 GiB 级输入。

## Service 接口的价值，在于约束调用方

`memory_service_ops` 将 remember、forget、recall_key、recall_query、stats 和 destroy 放到同一个后端契约中。调用方先说明记忆类型，再调用统一接口；默认实现负责把这些请求映射到现有 memory facade。

这个设计减少了认知层对某个存储实现的直接依赖，但没有自动解决存储一致性、跨进程并发和数据迁移。切换到远程后端时，还要重新明确超时、重试、查询排序、删除语义和输出所有权。一个 vtable 是扩展接缝，不是这些工程问题的完成证明。

在 C 接口里还要留意 `char **text` 这类输出参数。接口约定返回文本由堆分配，调用者释放；默认后端借用原有 memory 对象，其析构又不能顺手释放不属于自己的资源。先读头文件的所有权说明，通常比直接钻进存储算法更快理解组件边界。

## L0、L1、L2 与 HOT、WARM、COLD 为什么是两套维度

L0/L1/L2 表示内容粒度，HOT/WARM/COLD 表示当前驻留方式。把它们混成同一个枚举，会让“内容可以有哪些表示”和“现在占用了哪些资源”难以分别演进。

一个页面可能保留稳定的 record ID、重要度和访问统计，同时释放派生正文。后续查询需要这条记录时，再从规范内容物化表示。这里的 ID 和元信息承担寻址作用，不能因为正文不在活动缓存里，就认为原始知识已经被忘记。

当前 `derive_l2()` 复制规范内容，L1 则通过确定性规则派生概览。它不是每次调用大模型生成摘要的服务。所谓 Context MMU 是软件层的工作集管理类比，也没有借助 CPU 页表替模型提供透明的虚拟内存。

## 打开 `ctx_mmu_recall()`，看一次具体查询

召回首先同步规范记录与页面元信息，再根据查询获取候选相关性。源码会为各页面计算多个因子，将加权分数归一化。可以用下面的形式理解 `factor_score()`：

```text
score = clamp01(Σ(weight_i × factor_i) / Σ(weight_i))

factor = relevance、importance、confidence、utility、
         recency、salience、scope
```

其中 recency 按半衰期衰减，源码使用 `exp2(-age / half_life)`。如果半衰期为 H，其他条件相同，距离上次访问 H 时间的记录对应时间因子约为 0.5。这使“多久以前”可以与其他因子一起解释，而不是把新记录一律置顶。

随后按分数排序，先尝试将 COLD 页面提升到 WARM/L1，再选择部分页面提升到 HOT/L2。L2 的数量受 `l2_top_k` 等配置约束，提升还需要通过剩余 token 预算检查。候选排名高，不等于一定能加载全文。

一个值得继续优化的细节是排序范围。当前实现对页面集合做排序，使用插入排序；当集合很大时，不能因为向量检索只取 top-k，就假定后续所有处理都只有 k 项。评估扩展性应查看实际扫描与排序对象，再考虑局部候选、堆选择或其他策略。

## 预算核算最容易漏掉哪个分支

正常路径容易测试，拒绝提升的路径更容易藏内存问题。假设 L1 文本已经生成，随后发现预算不足：如果仅保持 COLD 状态，却没有释放新生成的文本，这个页面就留下了一份未计入活动预算的副本。

当前实现会在拒绝提升时释放该 L1 表示并清零其 token 数。下面是核心节选：

```c
if (tok > mmu->token_budget ||
    mmu->token_used > mmu->token_budget - tok) {
    free(pg->repr[CTX_L1]);
    pg->repr[CTX_L1] = NULL;
    pg->tok[CTX_L1] = 0;
    mmu->rejected_promotions++;
    continue;
}
```

第一项检查先处理 `tok > budget`，再使用减法形式，避免直接相加带来的无符号溢出风险。这样的细节连接了“策略正确”和“实现正确”：文字上写不超过预算，远不如错误分支也真的释放资源。

另外，pin 会影响驱逐。`evict_to_budget()` 跳过 pinned 页面；如果所有候选都被固定，就可能无法满足预算。pin 应被视为带成本的保留承诺，需要控制使用范围，而不是免费提高命中率的开关。

## 缓存失效与事实更新

`materialize()` 会计算规范内容 hash，发现正文变化后释放旧的各级表示，再按需派生新的内容。因此缓存 key 不应只用 record ID：同一个 ID 下的事实可能被修正，继续使用旧概览会把“更新成功”变成“模型仍看到旧版本”。

还要注意，正文 hash 只覆盖对应内容变化。若未来概览算法、提示词或派生配置改变，也应考虑将表示版本纳入缓存有效性判断。这里是从现有实现推导的演进需求，不表示当前已经拥有完整的跨版本缓存协议。

对长期记忆而言，更新与遗忘也应保留来源。一个低置信度推断若反复被召回，可能看起来越来越像事实；单纯增加访问频次不能证明内容正确。系统最好能区分用户明确提供的事实、工具观察和模型归纳，并让错误记忆可定位、可删除。

## 怎样设计“完整恢复”的实验

实验至少应保留三类独立观测：规范内容的长度与 hash，活动表示的大小与驻留状态，进程 RSS。只展示一个概览比例，无法判断正文究竟保存在哪里。

```text
写入三条规范记录，记录 length/hash
→ 物化为 HOT，确认有完整表示
→ 压低预算并驱逐，确认活动正文释放
→ 提升为 WARM，记录概览字节数
→ 再提升为 HOT，核对 length/hash
→ 从磁盘重新加载规范记录，再核对 length/hash
```

如果最后仅比较字符串前缀，就不能排除末段被截断；如果复用同一个内存对象，又不能证明磁盘恢复成功。因此测试把持久加载与缓存重建分开，并对内容长度与 hash 都做核对。

这里使用的 hash 用于测试内容一致性，不应直接扩展成安全领域的防篡改声明。要抵抗恶意修改，还需要另外的威胁模型与完整性机制。

## 面试追问：与普通 RAG 有什么关系

**向量检索已经选了候选，为什么还需要预算管理？** 相关性回答优先看谁，预算回答最多能加载多少以及以什么粒度加载。一条高相关记录可能很大，不能只按条数限制。

**把预算设为 8k，就能保证请求只有 8k token 吗？** 不能。当前 Context 使用估算口径，最终请求还包括系统提示、工具定义、会话历史与附件等内容；真实 Provider token 应另行计量。

**为什么驱逐而不直接删除？** 驱逐释放可重建的活动表示，遗忘删除或改变长期知识，两者生命周期不同。把它们混淆会让内存优化意外丢失事实。

**什么指标最能帮助调优？** 先看候选命中、提升与拒绝数量、物化字节、驱逐和重新物化延迟，再结合任务是否真的使用了正确证据。缓存命中率高，仍可能持续命中无用内容。

源码阅读基线：[MMU 召回、评分、物化与驱逐](https://github.com/LeonQin-ai/cognitive-os-agent/blob/cca98b6/backend/src/context/mmu.c)、[Service 契约](https://github.com/LeonQin-ai/cognitive-os-agent/blob/cca98b6/backend/include/memory/service.h)、[Service 默认后端](https://github.com/LeonQin-ai/cognitive-os-agent/blob/cca98b6/backend/src/memory/service.c)。

## 怎样检查这套实现

先构建 `runtime-bench`，再运行：

```bash
cd backend
python tests/test_runtime_benchmark.py
```

其中的小规模测试会执行真实 MMU 的 HOT 分配、驱逐、概览加载、重新物化和磁盘校验。CI 使用较小的数据检查正确性；历史大内存数据与运行条件保存在基准报告中。

源码：[Memory Service](https://github.com/LeonQin-ai/cognitive-os-agent/blob/main/backend/include/memory/service.h)、[Context MMU](https://github.com/LeonQin-ai/cognitive-os-agent/blob/main/backend/src/context/mmu.c)、[记录存储](https://github.com/LeonQin-ai/cognitive-os-agent/blob/main/backend/src/memory/record.c)。数据：[扩展基准报告](https://github.com/LeonQin-ai/cognitive-os-agent/blob/main/backend/docs/runtime-benchmark-expanded.md)。

上一篇：[Flow 依赖](03-flow-dependencies.md)；下一篇：[工具协议与执行证据](05-tool-protocol-and-evidence.md)。如果你正在处理长任务和大型代码库，欢迎从“规范内容与活动表示分离”这个边界一起讨论。
