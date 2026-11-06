# 输出驻留：真实 GGML 图接入验证

## 1. 结论与范围

独立图测试已通过，证明 output-tile 能通过实际 GGML CPU graph dispatch 进入
native QBS 的 Decode Attention 路径，而不是测试程序直接调用 SDK 冒充图执行。

固定交付 llama.cpp 源码加上默认关闭的候选补丁，全部重新构建 GGML 静态库，
再由 `ggml_graph_compute_with_ctx` 执行。SDK 从固定 Git 提交提取，AKV 汇编
核对为交付版本；没有使用本机未提交的 AKV 汇编或 llama.cpp 修改。

| 真实捕获 | Query heads / KV heads | D / 可见历史 | K 类型 | 每次 native 命令 | 三次调用 |
| --- | --- | --- | --- | ---: | --- |
| Qwen2.5 | 12 / 2，GQA6 | 128 / 128 | Q8_0 | 16 | baseline、candidate、candidate |
| Qwen2.5 | 12 / 2，GQA6 | 128 / 128 | Q4_0 | 16 | 同上 |
| Qwen3 | 16 / 8，GQA2 | 128 / 20 | Q8_0 | 8 | 同上 |
| Qwen3 | 16 / 8，GQA2 | 128 / 20 | Q4_0 | 8 | 同上 |

V 均为 Q8_0。Qwen3 使用原 Prefill 捕获中的第 19 个 query 的真实 view，包含
全部 16 个 query head、8 个 KV head；没有将几个 token 重复拼接为长上下文。
Qwen2.5 使用已有真实 Decode 捕获，包含全部 heads。

## 2. 实际检查

- 共 12 次 native 图调用、144 条 native QBS 命令，逐调用顺序与工作量核对通过。
- 每个 profile 的两次 candidate 与 Register-PV baseline 输出逐位相同。
- 所有输入张量保持原字节不变，输出在每次调用前重新置毒。
- 最终 FCSR 与 baseline 一致，并保留初始 DZ sticky 位；VCSR 保持 5。
- 与真实捕获 golden 的逐元素误差检查通过，没有更改原定容差。
- 8 次拒绝测试覆盖两种加速选项互斥冲突和缺少 NORMAL_MEMORY 许可，输出与
  单线程普通 GGML graph bitwise 一致；这不是线程、mask-hole 等所有 fallback
  的本轮验收。

| Profile | 最终 FCSR | 与捕获 golden 的最大绝对误差 |
| --- | ---: | ---: |
| Qwen2.5 / Q8_0 K | 9 | 1.40070915e-6 |
| Qwen2.5 / Q4_0 K | 11 | 9.65595245e-6 |
| Qwen3 / Q8_0 K | 9 | 2.47731805e-7 |
| Qwen3 / Q4_0 K | 9 | 2.99885869e-7 |

各行的三次调用均为同样的 flags 和误差。Qwen2.5/Q4_0 的 11 包含初始 DZ、
UF 与 NX，baseline 同样如此，不能强行要求所有 profile 的 flags 都等于 9。

独立解析器还要求每个 BEGIN/END 之间恰有一个完整 dispatch 汇总、正确的
Register-PV/output-tile 选择记录及完整命令数。不接受只有末尾 PASS 标记的日志。
工具测试现为 19 项，包括漏掉命令、误选路径、额外派发、标志变化和未完成测试
的拒绝检查。这些工具测试数量不是硬件激励覆盖率。

## 3. 构建与运行记录

原始构建：唯一验证工作树 `verification/out/e2e_output_graph_20261106_01/`。
其 GGML 库、测试程序与 initramfs 均已构建，但第一次运行使用没有开启 QBS 的
QEMU CPU 配置，在 `qbs_native_info` 的 0x0005155b 指令触发 SIGILL。
该 FAIL 保留，不重新标记为 PASS，也不将它归类为硬件功能 bug。

后继运行 `e2e_output_graph_replay_20261106_01/` 使用同一个 ELF 和 initramfs，
没有重新编译。改用已审计的 native-QBS QEMU，并显式指定 `xaraqbs=true`。
运行前后核对 QEMU 模型源码、配置、构建日志、可执行文件与原始输入 pin。

回执状态：`GRAPH_FUNCTIONAL_AND_DISPATCH_PASS`。
仓库摘要：`verification/performance/evidence/output_graph_20261106_01/result.json`。
原始失败和后继通过分属不同目录，不能合并为一次原始成功运行。

相关实现：

- `ggml/CMakeLists.txt` / `ggml/test.cpp`：隔离真实 GGML 图测试。
- `run_output_graph.py`：保留的初始构建/错误环境运行记录所对应脚本，**不要将其
  默认 QEMU 参数当作可执行 QBS 的主线入口**。
- `replay_output_graph.py`：以正确 native-QBS 环境重放未变化 ELF。
- `check_output_graph.py`：独立有序活动检查。

这些文件均在 `verification/performance/end_to_end_baseline/` 下。正式后续流水线
应从开始就使用 native-QBS 模型及能力检查，不重复初次错误的环境步骤。

## 4. 尚未证明的事项

QEMU 不提供真实 RTL 周期。本轮 GQA6/128-token 的数值和调度通过，不能证明
该形状也具有 GQA2/20-token 在 VCS 中约 1.25x..1.27x 的完整调用收益。

默认生产 checkout 与 FPGA 位流没有替换。隔离源码中的完整 llama.cpp 模型
配对已经执行，状态见第 5 节；仍须根据真实时间占比决定适用形状。吞吐和
token/s 由 RTL/板测获得，不从 QEMU 时间换算。

此外，普通 RVV、F16 Attention、线程和 mask-hole 等 fallback 应继续回归。
这些工作完成前，不将本轮图级通过作为整个 LLM 软硬件优化目标完成。

## 5. 完整模型 A/B 与后验核验

后继 `run_output_model.py` 使用上面的固定交付树及归档 SDK，完整构建 llama.cpp
的 `llama` 静态库与模型测试程序，不复用未核对的本地库。生产模型目录和位流不改。
测试源码从已验收的 `register_model_test.cpp` 生成，只改变两侧选择、日志标签
和大量的调试打印：

| 项目 | 两侧共同设置 / 差异 |
| --- | --- |
| 模型 | Qwen3-1.7B Q4_K_M，同一只读模型磁盘 |
| 对照 | baseline=Register-PV；candidate=output-tile |
| ISA / 运行时 | 同一个静态 ELF、相同 QBS/native opt-in、单 worker |
| Prefill | 两侧均启用已存在的 grouped Prefill，不把其收益归入新方案 |
| KV 格式 | 分别 Q8_0 K 和 Q4_0 K；V 均 Q8_0 |
| 上下文 | n_ctx=128，n_batch=n_ubatch=64；固定自然语言 prompt，实际分词数 40 |
| 执行规模 | 每种 KV 格式一次 prompt Prefill，加两次单 token Decode，得到三组 logits |
| 数值检查 | 六组完整 151936 维 logits 逐位比较，共 911616 个配对值；token 和最终 CSR 一致 |
| 状态隔离 | 父进程不初始化 GGML，两侧分别 fork，避免缓存的环境选择互相影响 |
| 覆盖检查 | 每侧应有 56 次成功 Prefill、112 次成功 Decode，并核对新旧选择互斥及工作量一致 |

这是一轮完整模型的短生成数值回归，不是长对话、质量基准或性能基准。
QEMU 使用显式 `xaraqbs=true`，执行前核对 native 模型源码、配置、构建及磁盘身份。

运行目录：唯一验证工作树 `verification/out/e2e_output_model_20261106_01/`。
完整库、测试 ELF 和 initramfs 已重新构建，QEMU 已正常关机，guest 退出码为 0。
独立日志解析确认每侧 56 次 Prefill、112 次 Decode，911616 个 logits 逐位一致，
token、最终 CSR 及 native 工作量相同。最终 VCSR 不要求保持入口的 5；完整模型
内部允许改变向量定点配置，检查的是新旧软件路径的最终状态一致，不能将其与
前面直接图调用的 VCSR 保持测试混为一谈。

原 worker 有意保持 `MODEL_EXECUTED_PENDING_INDEPENDENT_AUDIT` 状态，不因
guest 返回 0 就宣告全部输入闭合。后继 `collect_output_model.py` 正在独立核对
输入 pin、ELF/日志和实际执行命令，并对 native QBS QEMU 的源码、配置与构建
身份做运行后的检查。目录为 `e2e_output_model_audit_20261106_01/`，检查完成
后才形成正式审计回执。不会修改原运行的状态或覆盖其日志。

`check_output_model.py` 是独立的顺序检查器，不仅读取最终 PASS。工具单元测试
所在实验工具集合现为 30 项通过，包括误选后端、漏掉 Decode、改变 token、输入许可错误与失败
guest 退出码。模型测试的最终结果须同时满足程序内比较和这些独立活动检查。

查看任务：

```sh
systemctl --user status ara-e2e-output-model-audit-20261106-01.service --no-pager
cat /home/wangwy/openproject/ara_dsa_signoff_integration/verification/out/e2e_output_model_audit_20261106_01/status.json
```
