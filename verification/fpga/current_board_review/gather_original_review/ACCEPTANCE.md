# Gather 八单点独立验收

独立结果：`acceptance_audit01/audit.json` 为
`PASS_8_SOURCE_FULLORACLE_IDENTITY_AUDIT`。证据与输入 SHA256 见
`acceptance_audit01/pins.json`；审计实现为 `audit_accepted8.py`。

candidate04 封存镜像上验收的是下列八个 **source port 精确单点**：一次已通过的
control 被继承，余七项新跑，worker exit0；control 未重跑。
原 candidate03 的 TIMEOUT/CANCELLED 和 successor01 首次 wrapper 的 NOT_ACCEPTED
保持原记录，不覆盖或改判。

| case 后缀 | op | full capacity | gather 退休 PC | cycle | 秒 |
| --- | ---: | ---: | --- | ---: | ---: |
| e16_m1_ops0，继承 control | 0 | 64 | 0x800005ae | 13083 | 29.31 |
| e8_mf8 | 0 | 16 | 0x8000059a | 7637 | 23.58 |
| e16_mf4 | 0 | 16 | 0x800005a6 | 9992 | 27.60 |
| e16_m1_ops1 | 1 | 64 | 0x80000596 | 12057 | 30.52 |
| e32_m1_ops2 | 2 | 32 | 0x800005bc | 14552 | 33.03 |
| e64_m1_ops3 | 3 | 16 | 0x800005f2 | 22843 | 48.87 |
| e32_m8_ops20 | 20 | 256 | 0x80000934 | 28161 | 53.90 |
| e64_m8_ops0 | 0 | 128 | 0x800005a6 | 30864 | 62.55 |

共同 stimulus 为 seed0、scalar0、VL2、mask mode0（全开）、trial0/vstart1、
tu/mu、旧 destination 91；完整 capacity RNG/setup、indices、predicate、原 asm、
full-cap scalar oracle、两端 guards、返回 vstart 与 cases/errors 统计保留。
每项只缩六层空循环边界，原 tuple filter 保留；不是移除 oracle 的微测试。

审计从原始 commit trace 独立检查了八次目标指令身份、实际 VL/vstart 与返回
vstart0，以及全部 592 个输出元素和 16 个 guard 读取。每项原 asm target routine
包含 ret 共 **13 条指令**，与剥符号的归档 reduced Linux ELF 中唯一连续指令窗口
逐编码相同。完整 PASS markers 各一次、failure marker veto、退出0和输入身份均通过。
完整原始来源、原 Linux ELF、reduced ELF、port ELF 的不同哈希详列于 audit.json，
不能混称为原 Linux ELF 回放。

## 83 来源与未覆盖边界

83 是归档确认过的 **83 个 shape/op 来源记录**：80 个 opcode partition 的 first-failing
single，加三个未拆分 fractional parent 的 op0 single；不是83种不同标量数值 tuple。
共同首错 tuple 字段相同，但 SEW/LMUL/op、原 ELF、indices 类型和数值宽度属于身份。
19 个 shape 的父矩阵与它们的 partition/归档副本均不能重复计为新覆盖。

目前仅 8/83 单点通过，75 未通过；已覆盖 7/19 shape、全部五种 archived gather op。
这不关闭 parent 的 56448 配置、partition 的 2688 配置、非平凡 mask、其它 VL/vstart/
seed/scalar、原 Linux ABI/板级运行、另外的 gather stall 条目或整组83。

下一步仅准备 `remainder12_01`，取另外12个 shape 各一个真实 archived single。
ledger 将严格区分 accepted8、prepared-not-DUT12、not-prepared63，保留来源、父子映射
和已核验重复文件身份。即使未来12项通过，也仅为20/83，不能声明父矩阵闭合。
