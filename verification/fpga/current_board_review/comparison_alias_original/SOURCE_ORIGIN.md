# 比较源读取与压缩结果的起点错位

## 原始场景和当前复现

程序来自板测归档的 `rvv_small_masks_cmp_alias_restart_e8_m2`，不是新构造
的替代反例。来源、汇编和原始 oracle 见 [SELECTION.md](SELECTION.md)，
移植差异见 `prepared01/prepared/rvv_small_masks_cmp_alias_restart_e8_m2/wrapper.diff`。
SoC 移植只替换运行环境；源数组生成、目标汇编和完整结果检查保留。
原 Linux ELF 未在裸机环境直接执行。

目标：`vmseq.vv v8,v8,v16,v0.t`，e8/m2，VL128、vstart64，全一谓词，
目的与源 v8 同基址重叠。SoC PC 为 `0x80000508`，编码 `0x60880457`。
输入 ELF SHA256：
`7a49da58f5e84da62acd671bd2f3d064ff2b876c99c0e6d54da4857c77ee625d`。

candidate03 的普通运行和单独探针运行均报告：

```text
RVV_MASK_BIT seed=0 op=0 vl=128 mask=0 vstart=64 element=84 active=1 old=0 expected=0 actual=1
```

Spike 使用相同刺激和独立软件结果检查通过。该实测是当前 RTL 的活动位
错误，不仅是旧板测中 prestart 位被覆盖的症状。

## 周期证据

探针没有强制任何 DUT 状态。捕获窗口为18000..20500ns；实测数据见
`failure_capture01/cycle/raw_cycles.json` 和 CSV，原 FSDB 保留在对应测试的
`work/failed.fsdb`。这里只列关键周期，信号值取时钟上升沿之前的状态。

| 周期 | 测量 | 意义 |
| ---: | --- | --- |
| 19205 | lane0 AluA/B 请求 `vl=32, vstart=16, eew=EW8`，源 v16/v8 | 请求仍按架构起点偏移，但长度是完整 lane VL |
| 19206 | v8/v16 requester 地址分别34/66；VALU `issue_cnt=32` | 两个源的基地址32/64均加2个lane字；VALU尚未扣除前缀 |
| 19209 | VALU 首次有效计算，`issue_cnt=32` | 第一组结果被视为结果元素0起点 |
| 19211 | MASKU接收第一组结果，`vrf_pnt=0` | 压缩目的起点也是0，不是64 |
| 19213 | MASKU接收第三组结果，`vrf_pnt=64` | 后移的源数据被放入活动结果区 |

源数组的原始 xorshift 生成规则给出：

| 元素 | a | b | 相等结果 |
| ---: | ---: | ---: | ---: |
| 84 | 228 | 172 | 0 |
| 148 | 231 | 231 | 1 |

每 lane 的 e8 字包含8个元素，四 lane 的两个字偏移相当于全局64元素。
因此第84个结果使用了第148个源元素，准确解释实测的错误1。
这不是对 oracle 的修改，也不是依据最终错误值猜测：请求起点、完整
消费计数、压缩位置和输入数据共同支持同一条因果链。

## 修复范围

在 `hardware/src/lane/lane_sequencer.sv` 中，整数比较的 AluA/B 源请求
从零开始；carry 已采用这一约定。只调整 `[VMSEQ:VMSBC]`，不改变共享
外层分支中的 gather 索引读取。

浮点比较的 MulFPUA/B 存在相同的静态契约：VMFPU从完整lane VL开始，
MASKU从位零压缩比较结果和NV标签。因此也将这两个专用请求起点置零。
另外使用[非周期性有限输入控制](../comparison_source_controls/README.md)
验证：candidate03的e16/m1、VL32/vstart16的`.vv`和`.vf`均实际报告
`FP_SOURCE_FAIL ... errors=10 flags=1 start_after=0`；零起点控制PASS。
这些是明确标注的新定向测试，不冒充板测原始程序。candidate04的同ELF
对照已独立完成3/3 PASS；两项旧失败均从10错变为0错，零起点控制保持
PASS且含周期的完整提交CSV逐字节一致。三项均保持fflags=1和返回vstart0，
1177项pin无漂移，见[独立A/B报告](../comparison_source_controls/AB_REPORT.md)。

另外用[八项NaN控制](../comparison_source_controls/nv_successor/DUT_REPORT.md)
检查源起点改变后的异常资格化。候选04全部完整PASS，701项pin匹配。
所有测试e16/m1、VL32/vstart16、原sticky NX=1；prestart/屏蔽/tail的
sNaN保持flags1，活动sNaN EQ和活动qNaN LT为flags17，活动qNaN EQ/NE
仍为flags1。独立非周期性数值oracle同时检查数据位置，不能仅靠正确
flags掩盖错位。该tail用例的NaN位于元素37、完整VL32之外，验证没有
错误后移读取，不声称覆盖了最后一个部分消费字内的tail资格化。

保留执行请求和架构CSR的vstart、VL、EEW、谓词以及hazard字段。
MASKU继续限定真正活动的 `[vstart,vl)` 位，保护prestart和屏蔽位，
并按有效元素提交浮点异常。普通访存、slide和gather的请求约定不变。

现有零vstart比较请求的字段不变；是否保持实际周期仍以新镜像的相同
ELF回归为准，不仅凭静态推断宣称性能不变。

## 验收状态

candidate03 的 FAIL 和首错后取消的其余测试均保留原状态。
后继candidate04仅增加上述lane请求修改，独立冻结和构建，不覆盖旧镜像。
冻结清单SHA256为
`b8dcc5d0efc55af13b1e194866135ac2d7370bbcc75276e37d402c5235ea545d`。
VCS构建完成，耗时118.10秒；构建本身不是功能通过证据。

原失败e8/m2程序在candidate04已完整PASS/exit0，模拟73.08秒。
记录见 `candidate04_01/first/status.json` 与同目录的原控制台/提交CSV。
逐周期后验 `candidate04_01/first/cycle/gate.json` 为
`PASS_ORIGIN0_BIT84_ZERO`：四lane的源请求从零读取，源地址范围与完整VL
一致；实际第84个比较使用ac/e4，压缩位和最终VRF写回位均为0。
目标接受前的周期事件与对照相同。

三项浮点控制已完成上文的独立A/B验收。19个原来源single和16项
代表性RVV/QBS/AKV控制也已全部完整PASS/exit0，
[独立终态审计](candidate04_audit02/README.md)逐项核对原始成员、输入ELF、
完整oracle、失败标记否决和退出；1859项计划pin、1144项原测量pin及107项
原来源pin全部匹配。

16项控制的完整提交CSV均已解析检查，15份与candidate03逐字节一致。
`restart_compare`的18975行中有1374行仅cycle字段增加1，首个变化是
`vmseq.vx`完成事件27644变27645；程序结束30318变30319。
所有非周期字段一致。因此不能称16项周期全部不变，也不能将墙钟用时
当作性能周期。差异细节见[周期对照](../comparison_source_controls/RESTART_COMPARE_CYCLES.md)。

这些19项是归档的首错single，不是全部4032配置父矩阵或Linux信号ABI验收。
