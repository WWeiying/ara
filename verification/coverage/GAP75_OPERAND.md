# 操作数队列定向覆盖补充

本轮复用已通过故障布局修复验收的 VCS coverage 镜像，不修改 RTL，
不再编译 VCS，也不启动完整 Linux。输出目录：

`verification/out/gap75-operand-20261005-04`

## 激励与静态依据

旧 654 项正式报告中，operand_queue 的 4/8 倍扩展转换、选择索引推进、
FP16/32/64 归约中性值构造仍有零点。源码已确认 ALU operand queues
启用了 SupportIntExt2/4/8；不是为关闭参数构造无效测试。此批覆盖：

| 新测试 | 核心组合 | 独立检查 |
| --- | --- | --- |
| vgap75_ext16_f2 | 8→16 位，有符号/零扩展 | 逐元素扩展、保留元素及后继 RAW 加法 |
| vgap75_ext32_f4 | 8→32 位，有符号/零扩展 | 同上 |
| vgap75_ext64_f2 | 32→64 位，有符号/零扩展 | 同上 |
| vgap75_ext64_f4 | 16→64 位，有符号/零扩展 | 同上 |
| vgap75_ext64_f8 | 8→64 位，有符号/零扩展 | 同上 |
| vgap75_red16 | FP16 min/max 归约 | 精确位模式、fflags、目的寄存器尾部保留 |
| vgap75_red32 | FP32 min/max 归约 | 同上 |
| vgap75_red64 | FP64 min/max 归约 | 同上 |

各测试包含 LMUL=1/2/4；短 VL、非整 packet 长度、接近 VLMAX、
全掩码关闭和交错掩码。每项有 36 次主要转换/归约组合，不复制 seed
充数。归约源值按已知数值顺序排列，使用原始 IEEE 位模式和整数索引
构造 oracle，不让相同向量归约充当自己的黄金结果。源和初始数据只
初始化一次；每次从相同初始目的值重装，以缩短仿真而保持检查范围。

## 执行和准入

1. LLVM 构建八个 ELF，固定 VLEN=1024、四 lane，禁用标量循环自动
   向量化。共享 header 的目标依赖已补齐。
2. 使用不访问 SoC 专有 CTRL MMIO 的 HTIF 启动入口，同一 ELF 用于
   Spike 和 VCS。每项先通过冻结 Spike；检查 `g75_result` 中完整自检
   计数、零错误和 `tohost=1`，才启动 VCS。禁用打印，不禁用自检。
   专用 linker 显式放置 rodata，并断言 `_start=0x80000000`，与 VCS
   固定启动地址一致；脚本同时检查 ELF entry。
3. 八路并行，独立目录、trace 和 VDB。每项 VCS 上限 1,800 秒。
4. VCS 结束后核验自检、CVXIF protocol、完整 scalar commit 对比、
   逐指令 VRF writeback 对比及请求/退休 trace。PREFIX 不算 PASS。
5. 只将全部检查通过的 VDB 与同镜像的五项修复回归 VDB 汇总。
   原始 DVE 报告分别保存于 `baseline-report` 和 `combined-report`。

本轮 scalar checker 显式选 `rvfi_store_data_layout=unshifted`，对应
当前 CVA6 STORE writeback 的实际接口。默认 lane_aligned 行为保留给
历史调用方；参数出现在检查结果中，不自动猜测或跳过 store 数据。
上半字 store 的正确/损坏值和错误 layout 均有单元测试。

## 增量解释

旧 654 项 VDB 属于修复前 RTL，不能和新 RTL 合并宣称全局覆盖率上升。
本批比较同镜像五项基线与新增 PASS 后的 DVE 百分比，并给出
`raw-bitmap-delta.json`。

另外，`historical-target-hits.json` 仅诊断新测试是否命中了旧 654 项
报告中 operand_queue/sequencer 的零点。逐项核验 RTL 内容哈希及
coverage width/checksum 不变，拒绝不兼容点；不比较已修改 dispatcher，
不将不同镜像百分比相加，也不把 raw bit 数当作 DVE 百分点。

## 查看进度

在唯一验证 worktree 中：

```bash
./vstatus jobs gap75
./vstatus log gap75
```

状态中的 PASS 是逐项独立验收结果；只有 coverage_status=COMPLETE
和实际 DVE CSV 才表示该批汇总完成。TIMEOUT/FAIL 保留首错，不计入
verified coverage。覆盖探索期间不自动修改 RTL，也不放宽检查条件。

首批 `gap75-operand-20261005-01` 的普通应用启动入口会访问 SoC CTRL
MMIO，不能直接用于独立 Spike，已在 VCS 启动前停止。此问题不属于
RTL 首错；后续采用上述共同入口，不通过放大超时掩盖启动异常。
第二批普通 linker 未显式放置 rodata，归约测试入口被推后，已停止；
归约常量被 VCS 当作启动指令的 trace 作为启动布局问题证据保留。

## 第三批失败根因与启动修复

第三批八项均未通过严格验收，没有新增 verified coverage。该结果不能
解释成八个 RTL bug；已经确认下列两处测试启动/装载契约错误。

### 未清零的静态变量

`ara_soc.sv` 中宿主机 VCS 的 SRAM 初始化方式为 `random`。
DPI ELF loader 只登记 `p_filesz>0` 的 PT_LOAD；本批 `.bss` 是
`p_filesz=0` 的独立段，因而不会被预装载清零。原专用入口没有执行
C runtime 所需的 BSS 清零。Spike 装载后的 BSS 为零，两个环境的
静态变量初值因此不同。

在 `vgap75_ext16_f2` 第 2676 条对比首错处，PC `0x800021ae` 的
`lw` 读取地址 `0x80002d08`。ELF 符号表明确该地址是 `checks`：
Spike 返回 0，RTL 返回 `0x1967e609`。主程序仅重置 `num_failed`
和 `test_case`，没有重置这个静态计数器。

修复：linker 明确定义八字节对齐的 `__bss_start/__bss_end`；入口
在调用 main 前逐八字节清零整个 BSS。它恢复 C 程序的初始化契约，
不关闭 SRAM 随机初始化，不改 RTL，也不跳过计数器对比。

### 未对齐的文件段覆盖代码

四 lane 镜像的 AXI 宽口为 128 bit，即 16 byte。TB 的装载循环按
完整宽口 word 写入 SRAM，使用地址右移索引，要求段起始地址对齐；
它不支持非对齐段的 byte-lane 拼接。第三批 linker 未对齐 rodata。

| 测试 | 错误 PT_LOAD 地址 | 实际影响 |
| --- | --- | --- |
| vgap75_ext64_f4 | 0x80002ae8 | 常量向下写入 0x80002ae0，覆盖函数返回指令 |
| vgap75_red16 | 0x800029c8 | 常量向下写入 0x800029c0，覆盖恢复寄存器和返回指令 |
| vgap75_red32 | 0x800029f8 | 常量向下写入 0x800029f0，覆盖函数尾部 |

FP16 trace 在 `0x800029c0` 退休的指令是 `0xc800`，而 ELF 的原
指令是 `0x6ac2`。前者正好来自浮点常量表，随后错误指令导致低地址
访问及 load-unit 断言。按 TB 装载算法离线重建内存也能重现这些
文件字节的覆盖，因此不能将该断言直接归因于 LSU RTL。

修复：text/rodata/data/sdata 的文件段采用 128 byte 对齐，兼容
当前 16 byte 宽口，保留原代码和常量内容；编译后逐项检查每个
文件支持的 PT_LOAD 的物理起始地址。入口另记录异常的 mcause、
mepc、mtval 到 `g75_trap`，便于定位真正的后续异常。

八项重编译后的 ELF 已通过段对齐检查和 Spike 自检。先在
`verification/out/gap75-startup-focused-20261005-01` 运行 FP16 归约
判别测试，必须严格通过后才恢复整批 RTL 验收。该点同时覆盖旧批的
BSS 初值差异和函数尾部覆盖，避免直接重跑八项再猜测原因。

该判别测试现已严格 PASS：41,584 条 scalar commit 对齐，180 条
vector writeback 检查通过（16,176 byte），2,340 次自检且零错误，
402 对 CVXIF 请求/响应且 protocol_errors=0。只修改上述启动和
链接文件，沿用同一 RTL 镜像，原来的函数尾部异常消失。证据为该
目录中的 `scalar-comparison.json`、`vector-comparison.json` 和
`audit.json`。八项重新验收目录为上面的 `...-04`，其余项必须独立
验收，不能由该判别点推定全部通过。
