# 我测了百万任务，但没有测百万次模型推理：Cognitive OS 的 Runtime 实测

> “百万任务”只有与工作负载一起解释才有意义。这次我测的是实际 Scheduler、AgentPool 和本地确定性任务的执行路径，目的是观察 Runtime 的规模行为，而不是宣称远程模型具有同样的吞吐。

这是 [Cognitive OS](https://github.com/LeonQin-ai/cognitive-os-agent) 技术系列第 7 篇。数据来自仓库保存的扩展基准，以下按原报告口径解读。

## 测试到底运行了什么

机器为 Windows 11 build 26200、Intel Family 6 Model 142，约 8 GiB 内存，使用 Zig cc 0.14.1、`-O1` 构建。规模负载使用 8 个工作线程，每任务执行 64 次 Context 探测，聚合上下文缓冲为 8 MiB；原始 JSON 还记录了 8 个空闲的辅助 Runtime Worker，不能遗漏这部分进程开销。

Agent 数量指注册的角色数。1000 个角色不等于 1000 个进程，也不等于同时向模型发起 1000 次请求。任务主体使用本地确定性工作负载，不包含生产模型推理与网络延迟。

每个规模组合执行 3 次独立运行；耗时、吞吐和各次运行的延迟分位数按报告取中位值，峰值 RSS 使用组内最大值。

## 把数字与范围一起展示

| 注册角色 | 完成任务 | 耗时中位值 | 吞吐 | 排队 P99 | 峰值 RSS |
| --- | --- | --- | --- | --- | --- |
| 100 | 100,000 | 5748.495 ms | 17,396 task/s | 0.422 ms | 22.48 MiB |
| 1000 | 100,000 | 5771.132 ms | 17,328 task/s | 0.376 ms | 22.57 MiB |
| 100 | 1,000,000 | 65971.943 ms | 15,158 task/s | 2.039 ms | 78.65 MiB |
| 1000 | 1,000,000 | 72279.054 ms | 13,835 task/s | 14.790 ms | 77.92 MiB |

百万任务扩展包含 100/1000 角色各 3 轮，共实际完成 600 万项任务。报告记录所有提交任务被接纳并完成，失败与拒绝为零，结束时活动数和队列数为零；完成历史保留上限为 64 条。

RSS 还包含基准自身保留的验证数组，不能把它全部归因于调度器，也不能根据长任务测试的 RSS 增加就直接判断历史泄漏。

## 平均吞吐不能盖住排队突增

1000 角色下，百万任务的吞吐约比已有十万任务基准下降 20%，排队 P99 上升到 14.790 ms，采样队列峰值达到 6201。这个结果值得展示，因为它明确告诉我们：长时间运行时，平均值之外还存在突发排队。

这组数据不能证明线性扩展，也没有建立生产延迟 SLO。若只保留最好的吞吐数字，读者反而无法判断系统在较长负载下的行为。

“累计完成百万任务”也不等于“百万任务同时积压”。项目另外设置 backlog gate，在十万任务提交完成前阻塞 Worker，观察到 99,992 条真实排队任务。这是独立负载，不能与普通吞吐结果混为一个场景。

## 如何复现，而不是只看表格

先按照仓库说明构建 `runtime-bench`：Windows 使用 `build.ps1 -Target runtime-bench`，POSIX 可使用 `make build/bench-runtime`。进入 backend 后：

```bash
python tests/test_runtime_benchmark.py
python tests/run_runtime_measurements.py --million \
  --compiler "实际编译器/版本/参数" --output docs
```

第一条是小规模正确性 smoke，覆盖任务完成、MMU、积压与回滚。第二条重新运行百万任务组合并保存数据；它需要实际承担测试负载，结果会随机器、编译参数和系统负载变化。

本篇引用的是已保存的历史测量，不代表每次 CI 都重新执行百万任务，也不代表后续每个版本都已经重新建立同样的性能基线。

## 先拆开 benchmark runner，避免测到空循环

`bench_runtime.c` 中的 runner 不请求远程模型，但也不是只递增一个计数器。它记录从提交到 runner 开始的时间，按角色名调用 `agent_pool_task_prompt()` 组织任务输入，对共享上下文做 64 次探测，再设置任务状态和输出。

核心路径可以简化为：

```text
submitted_us → 进入 Scheduler → runner 开始
    → 记录 latency_us
    → 按 bench-N 找角色并构建 prompt
    → 64 次 context 字节访问与校验
    → 设置 DONE / FAILED、生成 output
    → Scheduler 完成与历史裁剪
```

这意味着数据包含实际队列、工作线程、角色提示组织和完成处理的成本。它仍然是很轻的本地工作，不包含生产模型的 token 生成、真实文档解析或慢速网络工具。理解这条路径后，读者才能判断自己的工作负载与它有多远。

还要看提交端是否主动控制压力。如果提交方节奏较慢，系统可能持续排空队列，此时累计百万项并未制造百万项积压。独立 backlog gate 才是刻意压住 worker、让队列真实增长的实验；两个场景回答的问题不同。

## 吞吐、排队延迟和端到端时间是三种指标

吞吐用完成任务数除以总耗时，适合观察单位时间处理量。排队延迟从提交到 runner 开始，反映任务启动前的等待。端到端任务延迟还包括 runner 工作、工具、模型、完成处理及可能的重试。

```text
T_end_to_end = T_queue + T_execution + T_finalization
T_execution ≈ T_model + T_tools + T_local_control
```

这里的分解是分析模型，不表示当前所有字段都逐项测量了上述每部分。尤其 `scheduler_latency_p99_ms` 不能被改写为“真实 Agent 请求 P99”。把排队分位数误当端到端指标，会大幅低估远程模型应用的等待。

如果某业务平均每项任务需要 2 秒模型时间，仅凭本地 runner 的每秒一万多项完成量，不能估算该业务可承载多少并发。还要加入 API 并发上限、token 配额、工具延迟以及请求间依赖。

## 用原始 JSON 复算，而不是复制截图

下面的脚本在项目根目录运行，读取仓库保存的百万任务数据，检查数量守恒，再按角色规模打印中位耗时、吞吐、运行内 P99 的中位值与最大峰值 RSS：

```python
import json
from pathlib import Path
from statistics import median

path = Path("backend/docs/runtime-million-2026-10-14.json")
report = json.loads(path.read_text(encoding="utf-8"))
for agents in (100, 1000):
    runs = [r for r in report["runs"] if r["agents"] == agents]
    assert len(runs) == 3
    for r in runs:
        assert r["tasks_submitted"] == r["tasks_admitted"] == r["tasks_completed"]
        assert r["tasks_failed"] == r["tasks_rejected"] == 0
        assert r["queue_at_end"] == r["active_at_end"] == 0
        assert r["retained_tasks"] <= 64
    print({
        "agents": agents,
        "elapsed_ms_median": round(median(r["elapsed_ms"] for r in runs), 3),
        "tasks_s_median": round(median(r["tasks_per_second"] for r in runs)),
        "queue_p99_ms_median": median(r["scheduler_latency_p99_ms"] for r in runs),
        "peak_rss_mib_max": round(max(r["peak_rss_bytes"] for r in runs) / 2**20, 2),
    })
```

聚合规则需要说清：三次运行的 P99 取中位数，不等于把三百万条原始延迟样本合并后重新计算 P99。前者反映三次实验各自尾部的典型值，后者需要完整样本或可合并直方图。报告采用前者，文章不能悄悄把它改称全体任务的 P99。

同理，峰值 RSS 取组内最大值，不能与耗时的中位值拼成一次实际存在的“最佳运行”。表格每列可能采用不同聚合策略，应保持标注一致。

## 尾延迟上升说明什么，又没有说明什么

1000 角色时，百万任务排队 P99 达到 14.790 ms，而十万任务的对应值为 0.376 ms。这说明该环境和负载下，较长测试存在更明显的排队尾部。它没有直接证明是哪一个锁、分配器或操作系统调度事件造成了退化。

要定位原因，下一步应对照提交采样、活跃数、队列长度与 RSS 时间线，再做单变量实验：固定任务总数，改变 worker 数；固定 worker 数，改变提交压力；固定上下文访问方式，改变角色数。没有这些对照，仅凭“角色变多了”就归因注册表查找，是证据不足的。

三次重复也不足以建立稳定的生产 SLO。机器温度、电源模式、后台程序和运行顺序都可能影响结果。当前数据适合暴露规模行为并形成后续假设，不能替代长期线上分布。

## 为什么内存必须分账

峰值 RSS 包括 Runtime 组件、上下文缓冲、任务对象、线程栈、分配器以及 benchmark 自己保存的验证数据。百万任务负载中的 work 结构和延迟记录数组也随着任务数增长，即使调度器完成历史始终只留 64 条，进程峰值仍可能升高。

因此判断历史泄漏，至少要同时看 retained_tasks、retained_bytes、结束活跃数与队列数，而不能只看一次最高 RSS。更强的长期检验可以在同一进程重复等量批次，观察排空后的内存是否持续阶梯增长；本篇没有用现有表格宣称完成了所有长期泄漏验证。

| 内存口径 | 包含什么 | 适合回答的问题 |
| --- | --- | --- |
| Context materialized bytes | 当前物化表示 | 工作集是否按预期驱逐 |
| retained task bytes | 保留的任务数据 | 完成历史是否有界 |
| 规范内容大小 | 保留下来的完整记录 | 恢复的数据量是多少 |
| RSS / Peak RSS | 整个进程驻留及其峰值 | 测试实际占用多少系统内存 |

在大 Context 实验里，1 GiB 规范内容对应约 3.12 GiB 峰值 RSS，进一步说明规范原文、复制、缓存和序列化会叠加。只给出 3900 字节 WARM 概览，容易隐藏主要成本。

## 正确性 gate 为什么先于跑分

负载程序必须先证明完成的是提交的那些任务，而不是漏做工作后获得高吞吐。报告检查 submitted、admitted、completed 相等，failed、rejected 为零，结束 active 与 queued 为零，并验证回滚结果。

这些检查仍不是万能的性能正确性证明。若 runner 中真正的业务计算被错误删掉，数量守恒也可能继续通过。因此文章同时公开 runner 路径、上下文探测数和原始数据，让读者知道“完成一次”具体包含什么。

小规模 smoke 不设置某个固定 tasks/s 阈值，避免共享 CI 机器的抖动被当作功能失败；它检查实际工作、状态和恢复。性能回归可以另设固定机器上的多次基线比较，并保留波动范围。

## 下一轮实验的控制变量

生产模型测试需要与 Runtime 局部测量配合。远程限流和生成时间可能掩盖本地开销，分层测量有助于定位，最后仍需组合成端到端评估。

现有吞吐下降值得调查，但不能直接证明某段实现存在缺陷。应固定任务数、上下文工作量和提交压力，分别改变 worker 数与角色数，再结合热点与时间线分析。

复测必须记录代码提交、编译器与参数、机器和系统、工作负载、重复次数、采样方法及聚合规则。先确认这些条件，数字才具备比较基础；累计百万任务也不能直接换算成百万并发用户。

源码阅读基线：[runner 与测量字段](https://github.com/LeonQin-ai/cognitive-os-agent/blob/cca98b6/backend/tests/bench_runtime.c)、[测量组合与断言](https://github.com/LeonQin-ai/cognitive-os-agent/blob/cca98b6/backend/tests/run_runtime_measurements.py)。

## 这些测试对项目有什么帮助

它们把“Agent 很多时会不会出问题”拆成可测的问题：注册表查找是否退化？排队延迟如何变化？历史保留是否有界？结束时任务数量是否守恒？积压放行之后能否排空？

这是一组系统工程证据。对于实际业务 Agent，还要继续测模型延迟、限流、工具 I/O、外部失败和具体任务完成率。

数据：[完整报告](https://github.com/LeonQin-ai/cognitive-os-agent/blob/main/backend/docs/runtime-benchmark-expanded.md)、[百万任务原始 JSON](https://github.com/LeonQin-ai/cognitive-os-agent/blob/main/backend/docs/runtime-million-2026-10-14.json)。源码：[基准程序](https://github.com/LeonQin-ai/cognitive-os-agent/blob/main/backend/tests/bench_runtime.c)。

上一篇：[可靠性与恢复](06-reliability-and-recovery.md)；下一篇：[三个上手实验](08-getting-started-and-contributing.md)。欢迎提交带机器、编译参数和原始结果的复测，让不同平台的数据能在相同口径下讨论。
