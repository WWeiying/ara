# NF7 indexed 历史失败的复现边界

原程序 `rvv_fault_replay_segment_nf7_indexed_e32_mf2` 在板上完成，
96配置、72次信号、1个累计检查错误。它不是已证明的卡死或已定位的RTL根因。
归档入口为 campaign 的 `rvv_recovery12_indexed_failure01/evidence.json`。

`prepare.py` 已核对原ELF及汇编哈希，并确认现有生成器产生的目标汇编
与归档逐字节一致。`geometry01.json` 保存96个配置、72个预期故障的
地址/索引/掩码/字段及来源哈希。当前C oracle单独绑定哈希，不能仅凭
汇编相同就声称它与原ELF中编译的C完全一致。

## 必须保留的条件

- e32/mf2、VL8、NF7、索引EEW32；目标寄存器v24至v30，索引v16。
- 有序indexed段load/store；不能换成普通unit-stride段访问。
- 边界1/3/5，全开/交替/稀疏/全关四种掩码；跨页字段分界0或3。
- 各索引是独立排列，不重叠；字段地址按base+index[i]+4*f形成。
- 首故障的vstart是元素编号，不是字段编号。原oracle允许该元素中
  位于保护页的任一字段地址，不能无依据收紧成必须报告最小字段。
- handler检查故障前完整元素，并修改已完成有效前缀的内存；从原PC和
  原vstart重试后，前缀不能被重新执行。不要要求故障元素的所有字段
  都保持未执行状态。

## 下一次复现的分阶段检查

| 阶段 | 独立记录 |
| --- | --- |
| 准备 | trial、模式、基址、全部索引、mask、VL/vtype、寄存器初值 |
| 异常进入 | cause、PC、tval、vstart、VL/vtype，以及预期可接受地址集合 |
| 重启前 | 每个已完成元素/字段的寄存器或内存，保护页恢复结果 |
| 重试 | 保持原PC/vstart，执行SFENCE，前缀内存注入与后继目标指令 |
| 完成 | vstart清零、异常次数、完整结果、所有内存及两侧guard |

首先使用真实Sv39和同一组语义做有界重放，逐阶段输出首错；这能定位
RTL的地址、字段、mask或异常收尾问题，但不替代Linux信号帧与sigreturn
验收。原始Linux ELF仍保留未闭环，不能将几何生成器通过计入硬件PASS。
