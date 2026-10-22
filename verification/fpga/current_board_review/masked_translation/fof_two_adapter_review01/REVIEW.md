# 两项 FOF 封存 Adapter 静态审查

结论：**无阻断，接受两项静态 source/adapter 和已产 reference 元数据绑定。** 本审查未读 reference raw，未独立重算其执行 trace，不是 DUT PASS 或 DUT 启动授权。后续 Main 决定 reference/DUT 准入。

生产目录：`verification/fpga/current_board_review/masked_translation/fof_original_two_singles01`。READY SHA256：`502c78d6d3466258f3452d28738c155eaa6c4701029f6a70ab677b2b58fa6f7d`。来源审查复用 `fof_two_source_review01/SOURCE_REVIEW.md`，SHA256 `9806f23e631e6b11debd03467bc6d935edb98b105f96b1c9c1e97c06c7569fe3`。

## 实际核查

- 静态读取 fixture.c/S/h、原/修正 observer、prepare/recovery/seal、Host negatives 和实际退出元数据；未执行这些脚本或任何 Host/编译/Spike/DUT。
- 118 READY pins 中116个非 raw 文件重新散列均一致。两个 raw 仅 stat 尺寸，未打开或重新散列；其摘要在 READY、reference result、input pins 和 startup-prefix 记录中一致。五个 input_pins 链的所有条目与 READY 相符，READY 前后 SHA 一致。
- 独立从实际 ELF 的 PT_LOAD 字节读取指令，核对两项各 SoC/Spike 的 load_0、load_1 各11条及 capacity 3条，与对应历史 failed ELF 完全一致。归档 S 与 prepared original.S 相同，prepared fixture 与封存 fixture 相同。这不是整个 Linux ELF 字节等价：Sv39/ABI/退出软件确实是 adapter。
- 14个已有编译/Host/反汇编 command execution 记录均 numeric0。已有两份 Host 测试退出记录0，边界测试包含 e8 不定区域两种不同数据及严格区域/缺字节/CSR/boot 分类负例；未重跑。

## Oracle 与实际 Scope

e8/scenario0：真实 S-mode Sv39 的 base `0x40000ffc`，first leaf 有效、second leaf 无效；VL8、mask0xff、四个输入11/48/85/122。保留130物理输出、16物理 mask、原 oldvd preload8和 store8。原结果 out[1..4] 和 guards out[0]/out[9] 严格；**最终 out[5..8] 在 C 和独立 byte expected 中全部排除**。初始阶段仍检查其原初始化。helper 在第5/6条取得 VL4/vstart0，恢复 VL8 后 completion CSR 应为8。checker 严格检查4个 target read 地址、一次 helper、原8项输出 store 地址以及返回 pack，而非仅检查最终 VL。

e64/scenario5：base `0x40001000`，VL8、mask0、uint64 oldvd 值0x5b，而非 memset5b。8项结果和原 guards0/9完整保留；返回 VL8/vstart0；checker 的 target data-read 列表为空。不是 VL0 shortcut。capacity 实际检查128/e8、16/e64；vlenb 实际检查128。vlm 逻辑消费1字节，但物理16字节原初始化/检查保留。

两项只允许一次 completion S-ECALL；目标 fault/trap、普通 load_0 执行、default trap 和 oracle mismatch 均拒绝。handler 不 repair/remap/retry target；任何非 completion trap 增加 unexpected 并由 C/observer 拒绝，返回 M continuation 不会把目标失败伪装成正常。CSR snapshot、packed return、marker、完整保存/恢复、HTIF1和原 parking都被核查。额外完整8KiB数据、12KiB页表、外层 guards/未使用 output storage 及 fcsr/vcsr 检查明确属于 supplementary，不改变 e8 不定许可。

## 已产 Reference 元数据（非再次 Raw 审核）

| 项目 | e8/scenario0 | e64/scenario5 |
| --- | --- | --- |
| SoC ELF SHA256 | `40cfaa6efb389fba0d5a55d8e7d58d67b7c927b0ff499ae3e5d0d77337a4a674` | `9e9e8da2ace6b0965f1c5989e4ac03ddcb4b16bed54d61ac795ad5cf4a213ecd` |
| Result SHA256 | `a42b0225e7cd2ce788d821060b84a4b46cd47ea08f70fecb0a66b181390726c9` | `ee4da22ab24d1abba8ef62b400043284bdb26b894350e7eb7ff797dc1b3e105c` |
| Persisted actual Spike rc / timeout | int0 / false | int0 / false |
| Spike elapsed / raw bytes | 2.974493s / 20,376,118 | 3.024279s / 20,918,270 |
| Firmware records / scalar checks | 169885 / 5477 | 172547 / 5481 |
| Target attempts / helper entries | 1 / 1 | 1 / 1 |

两项 result 均为 `REFERENCE_CHECKER_PASS_NOT_DUT`，命令精确绑定各自 Spike ELF；一次/项，120s、1.5M instruction、256MiB cap 未增加。result checker SHA 为 `aaf353ca41989df625f8d6d60721a223176a843cad1b94dc09f97b06c81bd2f3`。executor-session actual exit 已单独保存在 EXECUTOR_WAITS.json，不来自 missing PID/GC 推断。

e8 原 `reference_e8_01/not_completed.json` 的 `REFERENCE_NOT_ACCEPTED_NO_RETRY` 和实际 postcheck exit1 保留，精确错误为 `ValueError: Complete saved CSR set`。原程序 Spike 实际rc0不等于原 postcheck PASS。修正 diff 只改 utility 相对路径及 pre-main BSS zero-store/final DONE 分类；独立 oracle、helper、数值/count/bounds 不变。e8 successor 是同一 raw 离线重核，不是第二次 Spike；e64 是唯一一次已产参考。

`startup_prefix.json` SHA `4cecf30dc6e4c1b777d6da1155de1c84e2700473793a71b4d104fe65a0349a76` 记录两项完整有序 BSS clear、completion zero 各一次，止于 main。静态核其代码只允许 M-mode exact startup PC/insn/zero，有序地址等于完整 BSS 范围。运行时 observer 本身**未累计 boot 次数**，不能宣称其单独拒绝未来任意重复 boot 写；这次参考的实际 prefix 由该单独封存记录覆盖。后续 DUT checker 若复用，须明确采用何种启动证据，不能默默把本次 prefix 当作未来 trace 的事实。

## 限制

本次只读审查未解析、重新散列或验证 raw 内容。producer 已产 raw 后验和 prefix 结果的身份/代码/元数据在这里受审，不是新独立 full-reference PASS。e64 的 Spike 无 target read 不证明 DUT 无 MMU/AR；DUT 若声称此微架构性质须绑定 target VID，并排除 preload/mask/store/completion 访问。

不关闭 Linux clone/wait/signal/PROT_NONE 编码、完整96调用 parent、8历史 ELF/20 reduced singles、e16 H/I 的 M6 重放或全 FOF。无新 RTL identity/build、DUT、Host 或参考执行；无原 producer 修改。
