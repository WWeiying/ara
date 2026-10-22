# 两项原来源 MIN 输入审查

结论：**无阻断，接受封存的 call1292/call1232 两项 source-single SoC 输入。不是 DUT PASS，不是新独立 full-raw reference 验收，也不是已存在 VCS worker/plan 的批准。** 未读 reference raw、未跑 Host/参考/编译/DUT、未改任何 producer 或 sealed 文件。

生产目录：`../nan_min_soc_prepare01`。global READY SHA256：`2183b27009b1a9891346b99c753719908192905bb093f6090ec251753dac6ee2`。case READY：call1292 `486d74ae354c128352d4df785aa530da7e0b210b8de02f2b5b99d1a318e5d997`；call1232 `5dbf2fb9fc38d0f78ef38c28bdd8cef60f00929ecb8deff8c7fa25d1d9656910`。

## 来源与实际操作

Canonical 为归档 `ara_hw_campaign_20261007_01/rvv_fp_redspecial03` 的 e32/m1 C、输入、fixture、assembly 和 Linux ELF。原 C SHA `f92ffb3af070febf3dfebb85b0a25f6c5612b95044e2aa1262d600687926eb4f`，原 Linux ELF SHA `6bdf00a1600f10ebfc7a8b519bfea655d31e6b6b2b62d89f9e459d266eb597bc`。

原循环顺序是 scenario/l/mode/rm/op/sticky；每 fixture 两个 sticky 调用。独立枚举该顺序确认下表为 **zero-based** call，fixture bank1、row 均 zero-based；不是 MIN 的新人工 shape。

| Single | 原 tuple | Fixture row | VL / CAP | Mask | Expected / flags / vstart |
| --- | --- | --- | --- | --- | --- |
| call1292 | [1,3,3,0,1,0] | 646 | 3 / 32 | 0x24，仅元素2 active | 0x7fc00000 / 0 / 0 |
| call1232 | [1,3,1,0,1,0] | 616 | 3 / 32 | 0，全 off | 0x7fc12345 / 0 / 0 |

删除唯一 selector 精确还原原 C；两项 adapted case.c 与对应已审 MAX case 的差异仅 runtime identity 和 selector 的 op2→op1。物理输入512 word、seed64 word、mask64 byte、output144 byte 不变。原输入/seed八个 scenario 初始化、3360 fixture-row traversal/6720 field reads 和215040 mask-byte fills 保留；但仅执行一次 selected helper，**未保留/验收其前序 helper-call history**。

直接读取实际 ELF PT_LOAD 字节，独立比较两项 × SoC/Spike × op0/op1/op2 的全部12个21指令窗口与原 Linux ELF，全部一致；四个 capacity 窗口的3条编码也一致。实际 selected target 为 `0x14881c57`（vfredmin.vs），不是 MAX `0x1c881c57`。extractor 选 op1、禁止 op0/op2 的任意内部 PC，contiguous21、实际 capacity32/vlenb128及完整参数均检查。

两个 selected quiet-NaN 结果与 MAX 相同，不能单凭 canonical/payload 值证明 MIN。这里同时核了实际目标编码、op1 fixture/source identity，以及独立 MIN oracle 的 numeric-order、signed-zero、NaN/sNaN 位语义。oracle 不从 fixture/result 取值；已产 Host truth-table 报告11 pairs+4 reduction tests，通过，未重跑。call1232 实际 seed/input 是 **qNaN**，不是额外 sNaN/NV coverage。

## 完整 Oracle 与 CSR Delta 链

checker 对照已审 MAX `observer_recovery01/checker.py`：只切换 op1/unused op0+op2、wrong-op negative、GPR unknown 初始化。CSR delta/state 链、全 byte oracle、capacity/boot/source loops、tail/guards/退出/诊断否决均未删减。GPR 初态用 None、x0=0，不假定 ISA 默认清零。

只读结构化 ledger 独立核两项各21条 ordered helper、实际参数、selected fixture 地址/值、全144 ordered LBU 值、全128 byte v24 结果和完整 store32。目标4字节结果以外124字节 tail及前后8字节 guards 都保持0x5b。mask helper 在 CAP32 下消费4字节，不是仅按 target VL3 加载1字节；setup 的64物理 mask 字节全保留。

两项实际 ledger 均为：index10 显式 fflags=0 且 source a7=0；index11 只有 vstart=0，**没有 fflags event**；index12/13 实际 readback vstart0/fflags0。缺目标 event 仅承接紧邻、精确 PC/encoding/ordinal 绑定的 clear0，不补默认零。链从未知 CSR 状态开始，检查 frm/fflags 保存、请求、完整 helper CSR whitelist、fcsr alias 一致性及实际 restore operands/writes；突发 NV、未知/冲突 alias、缺 clear/readback 都拒绝。没有在 target 与 readback 间允许额外 clear。结构化 annotation 在 validate 重建，不能代替 raw event。

producer 的一次 full extraction 产每项12个 captured-effect negatives及33个完整-ledger negatives；其执行代码、记录数量和 pins 已核，未重跑或再读 raw。structured ledger 核查不是第二次完整退休流审计。

## 实际终态与身份

| Single | Spike PID / actual rc / seconds | Parser PID / actual rc / seconds | SoC ELF SHA256 |
| --- | --- | --- | --- |
| call1292 | 1735967 / int0 / 2.974705 | 1736080 / int0 / 42.168349 | `86b198a47a06426b0a4b127a14c446a8495652407b8fb722729e78e7c7e68c0f` |
| call1232 | 1736602 / int0 / 3.074609 | 1736637 / int0 / 49.437805 | `0ab53076d2ed4adc3d3a8cecefe19ca07c006219cbb477fd4db432e54c824674` |

两项 timeout=false，唯一参考各一次；实际 outcome 在后验前 durable 写入，parser 的 numeric wait 也单独保存。receipt 的 validated=false 是低层未后验标签，不是退出失败；这里只据实际 int0及随后 bound result 交叉核查，不推断 service/GC 状态。

两项各1,857,014 firmware退休至 HTIF、1,860,000总退休、2,981 park；额外5条是 boot。raw 各120,821,104B。profile `rv64gcv_zfh_zvfh_zvl1024b`、3M/120s/256MiB未改。result/execution/READY/raw-pin 摘要一致且 stat 符合 bounds，**未独立重新散列/解析 raw**。原 MAX 的 STOPPED/checker/READY 均在 lineage 中保留不变。

case pins union142项：138非 raw 文件前后重散列一致，4个 reference raw 文件（两 commits.log及两个空 spike.log）仅 stat/摘要链。另核 global READY 与两 case READY。sourceproof/helper/ledger/actualexit/admission pins 完整绑定。最终 metadata/ELF验证命令 actual exit0，chunk `cd655d`；最终 pin复核 actual exit0，chunk `1628f0`。它们不是新 Host/reference 执行。

## 准入边界

可复用且只复用上述两项现有 SoC ELF；未来单独 VCS plan 仍须绑定实际 M6 image、checker、worker、完整 oracle、durable monitor结果和 fail-stop。本审查不启动或接受 DUT，不替代原 MIN module84，也不关闭完整 Linux parent、前序调用或所有 MIN/MAX 数值/flag 类型。需要这两项 SoC points 正是因为原 module84 不含同一完整软件/SoC执行链；MAX PASS 也不替代 op1。

关键 checker SHA：`973a5776d4692553aabf079c6b5e2e7debd12ad5af126f5e3203b67b6632a168`；MIN oracle SHA：`f2a94cb15dc82716bf654436d109a4c3140f4269244b7f596ccb6f8d295bb407`。
