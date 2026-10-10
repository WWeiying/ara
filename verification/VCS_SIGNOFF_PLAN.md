# Ara DSA RTL 验证与 VCS Linux 签收计划

范围：当前 `ara_dsa_verification` 工作树；标准 RVV、QBS/AKV 和 Linux/SoC 为三条独立签收线。本阶段不做 FPGA 板卡验证，也不把 QEMU、模块 smoke 或历史日志写成 RTL 签收。

## 缩短反馈时间的运行顺序

1. 先在宿主机运行静态检查、定向单元测试和 QEMU 用户态载荷，排除构建、DTB、initramfs 与软件自检错误；这些结果不能替代 RTL 签收。
2. RTL 未变时复用经输入指纹核验的同一 VCS SoC 镜像。先运行 `rvv-fast-integrity`、`linux-fast-prereq` 短门禁和 QBS/AKV 真实数据定向点，再为 Linux 准备新 payload；不要因 Image/DTB 变化重编译 RTL，也不要把跨镜像覆盖率相加。这两个 RVV 套件必须使用与当前 RTL 对应的 VCS 镜像；`--skip-build` 本身不检查 RTL 源码一致性。
3. 对已经审定的同一 Linux 载荷只启动一次完整 VCS 运行，不反复短跑再从零重跑。仅当首次改变内核启动配置、且判别点能在短时间内到达时，做一次有明确里程碑的 A/B 诊断；如果改动发生在内核初始化阶段，低于内核入口的短程里程碑没有判别力，应直接用带早停条件的完整运行。完整运行启用明确失败标志、首进度和后续停滞检查，可设置保守的最小目标周期预算判断。监控只增量读取日志，避免长日志每轮重扫。首进度/停滞/预算停止均为诊断结论，绝非 Linux PASS。
4. 超过十分钟的 VCS 放到独立后台目录，确认进程和进度后停止轮询；完成后一次性核对退出码、用户态 marker、输入/镜像哈希及签收结果。任何不具备判别力的长运行应在启动前缩成一条定向用例。

日常按改动范围选最小门禁，不对每次修改重跑全部层级：

| 改动范围 | 首轮验证 | 扩大验证的条件 |
| --- | --- | --- |
| 捕获输入、格式映射或 GGML 软件 | `host-quick-check`、输入/ELF 预检 | 输入和参考一致后，仅跑受影响格式的真实 DUT RVV/QBS 配对 |
| QBS/AKV 局部 RTL | 相关模块定向测试、`rtl-quick-check` | 数值或协议证据通过后，跑受影响格式与一项 RVV fallback 配对 |
| 通用 RVV、VLSU 或 CVXIF RTL | `rvv-fast-integrity` 与改动相关的 Spike 差分/UVM 用例 | 首错排除后再增加边界和随机种子 |
| CSR、MMU、异常或 SoC 启动路径 | `linux-fast-prereq`、QEMU 载荷检查、短周期 SoC 诊断 | 只有冻结输入且实测预算可到目标阶段，才启动一次完整 VCS Linux |

前级未通过时不启动后级。已有通过证据先做哈希/日志离线重审；只在源码、
载荷或验证需求实际变化时重跑。短门禁通过不替代相应的最终覆盖签收。

在 RTL 和 VCS 镜像已核对一致、定向 ELF 已编译时，短门禁可这样运行（每次换新输出目录）：

```bash
python3 verification/verify.py run rvv-fast-integrity \
  --simv /path/to/current/simv --skip-build --jobs 4 --timeout 300 \
  --output verification/out/rvv-fast-integrity-<run-id>
```

它同时执行四个真实 DUT 自检点，不含全量随机、QBS/AKV 或 Linux；任何一项失败都应先定位首错，再决定是否启动长回归。不要因为短门禁通过就宣称签收完成。

在相同镜像上，Linux 启动前再运行六个相互独立的定向前提检查；仅在
ELF 已按当前源码构建时使用 `--skip-build`：

```bash
python3 verification/verify.py run linux-fast-prereq \
  --simv /path/to/current/simv --skip-build --jobs 4 --timeout 300 \
  --output verification/out/linux-fast-prereq-<run-id>
```

它检查 CSR/STVEC、trap、Sv39、MMU 重定位和 RVV 上下文，不会启动 Linux，
也不证明真实内核能够进入用户态。任一项失败时先检查该项首错，不启动
数小时的完整 boot；整组通过后仍须运行原有 Linux 系统签收。

2026-09-23 在已编译的 4 MiB QBS+AKV 镜像上实测：四点并行约 48 秒，
`verification/out/rvv-fast-integrity-20260923-01/audit.json` 重审为 4/4 PASS。
这只是复用镜像时的短反馈耗时，不包含首次 VCS 编译，也不保证所有机器同速。
同一镜像的 Linux 前提门禁在
`verification/out/linux-fast-prereq-current-image-20260923-01/` 完成 6/6 PASS；
`verification/out/linux-fast-prereq-current-image-audit-20260923-01.json`
离线重审亦为 6/6 PASS。它们只检查裸机 CSR、trap、Sv39、MMU 与向量
上下文定向行为，不是 Linux 用户态标记。

Linux 运行器的相关参数为 `--linux-fail-fast`、`--linux-first-progress-timeout`、`--linux-no-progress-timeout`、`--linux-min-cycle-target` 与 `--budget-check-after`。超时值按首次有效进度和已测吞吐设置，不能靠降低超时把尚未完成的启动写成失败或通过。未开启 `--cache-tag-probe` 的运行仍将 D-cache 整字无效读告警视作失败；开启探针后，改由实际选中 byte-enable 的 `[CACHE_SELECTED_X]`、未匹配的 `[CACHE_UNMATCHED_RESPONSE]`、无效写断言和 `Fatal:` 判定失败，并要求日志出现 `[CACHE_PROBE_ACTIVE]`。整字告警本身不证明被消费字节含 X；探针也不能替代完整 Linux 启动或架构状态对比。已启动的运行使用冻结的 `run_driver.py` 副本，新代码不会改变其判定。
新运行的日志监控间隔为 5 秒，只读取新增字节；这缩短明确失败标记的发现延迟，不提升 VCS 每秒仿真的周期数。

静默 OpenSBI 的一次完整尝试保存在
`verification/out/soc-current-rtl-quiet-linux-full-20260923-01/`：约 51 万周期起出现
`a_invalid_read_data`，旧版独立审计按整字告警将其判为失败。后续检查发现
该断言检查整字，而所见 `be=f0` 仅选择已知的高四字节；因此旧版判定
不能单独证明架构可见读数据含 X。该运行在约 570 万周期、
1492 秒后人工停止，状态 `LINUX_BOOT_FAILED`；不计作 Linux boot 结果。
下一步用选中字节探针核查首次断言附近的地址、有效位和数据来源；仅软件载荷
改变时才可复用未变的编译镜像，RTL 修复则必须重编译。完成定向检查后，
只启动一次新的完整运行。
带选中字节与响应 ID 探针的独立短测
`verification/out/soc-cache-selected-probe-20260923-01/` 已按预定目标运行
至 600,000 周期并以 `LINUX_MILESTONE_REACHED` 结束。日志有 1 条探针激活、
8 条整字 `CACHE_DATA_X`、10 条整字读断言告警，但没有
`CACHE_SELECTED_X` 或 `CACHE_UNMATCHED_RESPONSE`。该结果只排除这段
窗口内探针所检测的两类错误，不能签收后续启动或整个内存系统。

2026-09-23 的 256 MiB FLATMEM 旧运行约在 1690 万周期才进入 Linux；此前
`PROGRESS` PC 样本多次落在 OpenSBI `uart8250_putc`，内核入口前 UART 已接收
约 2618 字节。串口输出是值得单独优化的启动成本，但不能仅凭 PC 采样精确
归因全部周期。精简内核与旧 RTL 编译镜像复用后的 100 万周期诊断用时约
280 秒，状态为 `LINUX_MILESTONE_REACHED`；这个里程碑仍在固件中，只证实
新载荷接入和 SoC 推进，不证明关闭 tracing 缩短 Linux 初始化。下一次完整
运行应先固定用户态 marker/错误扫描，再用实测吞吐设置预算，且不在同一
冻结载荷上重复启动短预演。

为减少上述 UART 启动成本，验证专用 OpenSBI bundle 可选
`--quiet-opensbi`（`FW_OPTIONS=0x1`）。旧运行到内核入口约输出 2618 字节；
115200 波特率、50 MHz SoC 时钟下，串行发送这些字节需要约 1136 万
时钟周期，但与其他工作是否重叠须由新运行实测。静默模式不删除 Linux
和用户态错误/通过输出：SoC monitor 与独立审计改为要求 Linux 报告
SBI 规范和实现身份，并继续检查内核、init、RVV 用户态 marker、退休、
trap 和 DDR 活动。默认非静默模式仍要求 OpenSBI 横幅。静默固件只用于
验证目录，不改部署固件或 RTL；必须先通过单元测试和 VCS 实测，不能
仅凭理论串口时间宣称整体启动加速。

## 当前证据与缺口

| 方向 | 已有证据 | 尚不能宣称 |
| --- | --- | --- |
| 标准 RVV | 定向 ELF、riscv-dv profile、Spike/RTL commit 与向量状态比较、真实 DUT CVXIF contract monitor | 全 ISA 与异常交叉覆盖闭合；所有随机 profile 和种子通过 |
| QBS/AKV | 原有十个加新增四个 Qwen2.5 真实数据 C 参考切片与捕获 golden 一致；原有六个加新增四个真实数据 QBS RTL 子系统命令通过，后四个独立重审；448 个 profile case、AKV SRAM/macro 测试及整机 handoff 自检通过；九种格式各有一项 QBS/标准 RVV 真实数据配对审计通过，RVV 无 custom-2 分配；单条 QBS+AKV 组合用例及 AKV/标准 RVV Attention 对照通过 | 全部 profile、shape、边界、异常和 fallback 的整机独立 RTL 签收；Q2_K 配对仅 4 行输出且两侧非逐位一致；切片结果不等于模型端到端覆盖或加速 |
| UVM | 真实 `ara_system` 的 CVXIF/VID/AXI monitor 与独立 contract/vector trace 逐事件对照；读写复位、背压、QBS+AKV 组合程序通过；同一 VCS 镜像的六条已审计运行命中 24/24 个可达接口功能 bin，零错误 | 接口覆盖不等于完整 RVV 架构语义、RTL 代码覆盖或 Linux 系统签收；新增需求仍须映射独立 oracle |
| 代码覆盖 | `verify.py run --code-coverage` 已在完整 Ara 的 `rvv:vadd` 上实测 PASS，编译和逐 case VDB 均生成；宿主机隔离库对同一 VDB 曾成功生成不含 line 的四项指标诊断报告 | 包含 line 的运行在 line shape 处崩溃；另一次摘要重跑在 cond shape 处崩溃。工具尚不稳定，缺 line 指标及完整 DUT 范围的稳定报告，不能签收 |
| Linux | QEMU 用户态 RVV 通过；VCS Linux 前置测试与 Cheshire/Ara SoC 编译、裸机 smoke 通过；FDT 页确定化后，2 GiB 运行到 4425 万周期因 3 小时上限停止，256 MiB 无额外探针运行到约 3210 万周期因 2 小时上限停止；FLATMEM 运行到 4760 万周期因 2.5 小时上限停止；验证专用 Image 的 QEMU 用户态检查通过 | VCS 尚无 init/用户态成功标记，更无用户态 QBS/AKV、进程切换和系统压力签收；超时和 QEMU 通过均不能代替 VCS 完成证据 |

当前 4 MiB/QBS+AKV VCS 镜像的真实 DUT UVM 接口点已重新闭合，证据为
`verification/out/uvm-coverage-current-image-6runs-20260923-01.json`：
四条真实数据 RVV/QBS/AKV 运行加当前镜像上的读、写复位两例，六份原始
日志及输入哈希重审后 24/24 个已定义 bin 命中、单一镜像组、零审计错误；
读写复位各有一次真实 AXI 事务中止。该报告不能借用旧镜像的命中量，
也不能替代 AXI 地址/数据正确性、完整 RVV ISA 或 RTL 代码覆盖。
使用相同六份原始审计输入运行 `run_signoff.py --stage uvm` 的单阶段结果为
`verification/out/uvm-current-image-signoff-20260923-01/signoff.json`，
该 UVM 门禁 PASS。它不是 `--strict` 签收：生成时工作树未清洁，
因此不得由此推断 RTL 源码已可从提交号独立重建，也不得推出整机签收。
本轮从同一六份冻结日志重审的
`verification/out/signoff-uvm-current-20260923-02/signoff.json` 仍为 PASS；
`verification/out/signoff-qbs-current-20260923-02/signoff.json` 对现有
10 个 QBS/RVV 配对点及 AKV/RVV 配对点也为 PASS，九种必需格式无缺失，
且配对镜像一致。这些是已保存证据的重新审计，不是新的仿真运行。

当前镜像的另一个严格随机 checkpoint 用例现已结束，原始运行在
`verification/out/rvv-checkpoint-current-image-seed68-20260923-01/`，
带 `--require-trace --require-vector --require-full-match` 的独立重审在
`verification/out/rvv-checkpoint-current-image-seed68-audit-20260923-01.json`，
结果为 1/1 PASS。该用例 72,243 条提交与 Spike 对齐，539 条被跟踪的
向量后端请求完成事件检查，43,540 个参考已知字节相符；另有 31,900
个参考未知字节跳过。其中 1 条 `vmv.x.s` 将结果送往标量寄存器，
没有可比较的向量目的字节，单条状态为 `UNOBSERVABLE`，不能算作
向量寄存器值匹配。
因此这项证据是已知架构状态的严格比较，而非整个 VRF 全字节相等。
它也不等于全部随机种子、所有 RVV 指令或所有内存结果已经闭合。
将该用例并入现有同镜像活动集合后，冻结矩阵为
`verification/out/rvv-activity-current-image-14cases-20260923-01.json`：
14/14 输入被接受、单一 VCS 镜像，合法 SEW×LMUL×policy 组合观察到
88/88，计划的访存模式观察到 7/7；三份有逐字节写回证据的用例累计
138,785 个参考已知字节相符。访存模式中的 strided、indexed、segment、
fault-first 目前各仅由一个用例命中，属于活动覆盖而非独立功能闭合；
跳过的未知字节也没有计入功能通过率。

同一镜像随后新增三项严格差分：checkpoint seed 69、70 以及算术
混合流 seed 71；访存流 seed 72 也独立通过。四项均以原始运行目录和
`--require-trace --require-vector --require-full-match` 重审为 1/1 PASS，
审计文件分别为
`verification/out/rvv-checkpoint-seed69-900s-audit-20260923-01.json`、
`verification/out/rvv-checkpoint-seed70-900s-audit-20260923-01.json`、
`verification/out/rvv-arithmetic-seed71-audit-20260923-01.json` 和
`verification/out/rvv-load-store-seed72-audit-20260923-01.json`。
这四份数据尚未并入上面的 14-case 冻结矩阵，不能把旧矩阵的分母
直接改成 18；随机种子通过也不代表全部 RVV 指令组合已覆盖。

QBS profile-engine 的九种格式与整机真实模型配对要分开记录：
当前九种格式各有一项真实模型数据的整机 RVV/QBS 配对：Q3_K、Q4_K、
Q5_K、Q6_K、Q8_0、Q4_0、Q5_0、IQ4_NL 和 Q2_K。Q2_K 仅选择完整
`K=4864` 的前 4 行，不能外推到全部 N、M、tail 和错误路径；448 点
profile 矩阵与这九项配对互补，仍不足以签收整机全部格式行为。
这四种格式现已各取得一份 Qwen2.5 decode `MUL_MAT` 原始输入，分别在
`verification/out/qbs-format-closure-{q2k,q4-0,q5-0,iq4-nl}-20260923-03/`。
每份均由 `verification/qbs/capture_real_format.py` 记录模型和捕获程序
哈希、命令与原始日志，并经 `--audit-existing` 离线重审为 PASS；形状依次
为 Q2_K `K=4864,N=896`，Q4_0 `K=1536,N=1536`，Q5_0 和 IQ4_NL
均为 `K=N=896`，四点均 `M=1`。这仅证明原始 F32 激活、量化权重和
llama.cpp 输出已捕获且文件结构一致；四种格式均已另有整机
RVV/QBS 定向配对，但其覆盖范围各自受实际切片形状限制。
Q2_K 模型的所选算子是 `ffn_down`，
其余三种是 `attn_q`。host 捕获工具在默认 CPU repack 路径的 Q2_K
首次运行于 `write_tensor` 段错误；关闭 repack 的判别运行通过，
后续四份封存输入均明确使用 `-nr`。捕获端 `operator.json` 的
`activation_quantization` 固定字符串不是原始激活的类型证据，实际保存
的是 F32；生成 QBS 激活时须按格式选择 Q8_K 或 Q8_0。

这些捕获还通过了独立的 QBS C 数值快筛：
`verification/out/qbs-format-closure-c-ref-20260923-01/summary.json`
记录四种格式全部 `0` mismatch；Q2_K、Q4_0、Q5_0、IQ4_NL 的最大
绝对误差分别为 `3.58e-7`、`1.91e-6`、`2.38e-7`、`2.38e-7`。
`make -C verification host-quick-check CAPTURED_QBS_OUT=<新目录>`
会先运行工具单测和原有真实数据 C 回归，再重审四份输入的哈希、格式与
GGML 输出，并运行四格式 C 参考。它用于在昂贵的 VCS 前排除输入和
软件参考错误，不能证明标准 RVV 或 QBS 的真实 DUT 行为，也不能替代
后续同镜像的整机配对。

同一四格式捕获已进一步完成真实数据的 QBS engine RTL 短测试，证据位于
`verification/out/qbs-format-rtl-sealed-20260923-02/`。测试保持完整 K，
仅取每个算子的前 16 个输出；Q2_K、Q4_0、Q5_0、IQ4_NL 分别为
3901、2916、1744、1716 周期，四点数值均 PASS，`audit.json` 独立
重算命令向量并核对捕获输入、VCS image 和日志哈希，状态为 PASS。
复现入口为 `verification/qbs/run_real_format_rtl.py --simv <engine-simv>
--output <新目录>`，完成后用同脚本 `--audit-existing --output <目录>`。
这是 QBS 子系统功能证据，不是整机 CVA6/Ara QBS/RVV 配对，不能据此
把九格式整机覆盖标记为闭合。

Q4_0 另完成一对真实 DUT RVV/QBS 测试：同一捕获的 decode `attn_q`，
`K=1536,M=1,N=32`；输入预检见
`verification/out/q4_0-pair-preflight-20260923-01.json`，两份 ELF 中
权重、F32 激活和 GGML golden 的哈希相同。QBS 使用 R4 权重布局，
RVV 使用行主序权重和 RVV Q4_0×Q8_0 点积；两侧均为 32/32 输出
零 mismatch，checksum 同为 `0x3bb4f413b20fb348`，真实 DUT UVM 审计
分别 PASS。`verification/out/q4_0-paired-evidence-20260923-01.json`
进一步核对两侧同一 VCS 镜像、原始日志和 RVV 不含 custom-2/QBS 分配，
成对结果 PASS。当前切片的 RVV/QBS 计算周期为 `298871/17402`；
这不是完整模型加速比，也不证明其余格式已配对。

Q5_0 的独立整机配对复用同一 VCS 镜像和 Qwen2.5 decode `attn_q`
捕获，`K=896,M=1,N=32`。输入预检为
`verification/out/q5_0-pair-preflight-20260923-01.json`。QBS R4 与标准
RVV 行主序两侧都通过 UVM 和 32/32 输出自检，零 mismatch，checksum
同为 `0x969367732e152945`；配对审计
`verification/out/q5_0-paired-evidence-20260923-01.json` 为 PASS，
计算周期为 RVV `152247`、QBS `10384`。这是同一切片的计算阶段数据，
不是模型级加速比。

IQ4_NL 的整机配对使用 Qwen2.5 decode `attn_q` 捕获，`K=896,M=1,N=32`，
`verification/out/iq4_nl-pair-preflight-20260923-01.json` 先检查了相同的
模型输入、golden、R4 权重变换和 ELF。QBS 与标准 RVV 均通过 UVM 和
32/32 输出自检，零 mismatch，checksum 同为 `0xa932dc518da44e1f`。
`verification/out/iq4_nl-paired-evidence-20260923-01.json` 的独立审计
为 PASS，同一 VCS 镜像且 RVV 无 custom-2 分配；计算周期为 RVV `349714`、
QBS `10314`。该值仅适用于所选的真实数据切片，不是模型级加速比。
Q2_K 的最初 `K=4864,M=1,N=8` RVV 对照在 600 秒停止时仍持续完成
向量请求，未产生数值出口；对应 QBS 8/8 输出自检通过，不能把这一对
记为 PASS。为控制验证时间，另建 `N=4` 的完整 K 切片，输入预检为
`verification/out/q2k-4r-pair-preflight-20260923-01.json`。两侧均通过
UVM 和 4/4 GGML golden 容差自检；配对审计
`verification/out/q2k-4r-paired-evidence-20260923-01.json` 为 PASS，
标准 RVV 无 custom-2 分配。RVV/QBS 计算周期为 `263516/43010`。
checksum 分别为 `0xbd6c8f8bcd55788` 与 `0x6e3cc06234cae5a9`：
两侧数值均在各自的 golden 容差内，但**不是逐位相同**，审计报告
显式标记 `bitwise_equal_output_checksum=false`。这仅闭合一个真实数据
定向点，不是 Q2_K 全尺寸或模型级性能签收。

九种格式的上述定向配对与一对 AKV-v2/标准 RVV 比较现纳入同一清单，
`verification/out/paired-campaign-nine-formats-20260923-01.json` 的
离线重审为 PASS：九格式齐全、各配对 PASS、无审计错误、十对完整 VCS
镜像组件身份一致。此报告比原五格式清单扩大了格式覆盖，但不增加
未运行的 shape、异常、随机或 Linux 用户态证据。

在不修改原九格式清单的前提下，新增 Q4_K Prefill `K=1536,N=32,M=4`
真实模型切片。`verification/out/paired-campaign-nine-formats-prefill-20260923-01.json`
重审 10 条 QBS/RVV 配对及 AKV/RVV 配对，均 PASS、完整 VCS 镜像身份一致；
RVV/QBS 计算窗口为 `134077/114061` 周期。该清单的多输入格式覆盖为
1/9（仅 Q4_K），R4 输出行尾为 0/9；代表性配对 PASS 不等于形状覆盖闭合。
`run_signoff.py --stage qbs-pairs` 对同一新清单现场重审的单阶段报告为
`verification/out/qbs-pairs-signoff-prefill-20260923-01/signoff.json`，状态 PASS。
该报告如实记录当前工作树为 dirty；它证明配对门禁可运行和证据一致，
不满足最终 `--strict` 对干净源码来源的要求。

新增真实 DUT Q3_K/Q5_K/Q8_0 单点证据分别位于
`verification/out/qbs-q3-real-dut-20260923-01/` 和
`verification/out/qbs-q5-real-dut-20260923-01/`、
`verification/out/qbs-q8-real-dut-20260923-01/`。三个程序各自比较 256 个
Qwen2.5 输出，`mismatches=0`、`qbs_status=0`；独立 UVM 审计均 PASS，
并在向量 trace 中各核对 8 次 QBS 自定义指令的分配、写回和完成。
`qbs_evidence.json` 还复核了 ELF、日志、trace、case 与两份 SHA-256 清单。
这是三种格式的独立整机单点，不是 QBS/AKV 全范围签收。

同一镜像的五种真实数据 QBS/标准 RVV 配对和 AKV-v2/标准 RVV 配对，
见 `verification/out/paired-campaign-audit-20260923-01.json`：六对逐项重审
均 PASS、镜像组件一致、缺失格式为零。新增 Q4_K 的
`K=1536, N=256, M=1` decode 切片位于
`verification/out/q4k-pair-audit-20260923-01.json`，两侧各自对捕获的
golden 自检通过，同一输入/镜像，标准 RVV 无 custom-2 分配；计算窗口
为 267429/34193 周期。这是该输入和实现的局部延迟比，不是模型级加速比。

真实 DUT UVM 的逐项观察量另存于
`verification/out/uvm-coverage-audit-20260923-02.json`，由原始日志、独立
contract/vector trace、ELF 与仿真镜像重新审计得到。该用例有 350 次 CVXIF
请求、VID 最大在飞 4、读最大在途 4、写最大在途 5、30 次完整读/1536 个
R beat、228 次完整写/3072 个 W beat；W 背压 3 周期，AR/R/AW/B 背压和
CVXIF 同周期 ID 复用均为 0。
这些是单用例命中量，不是整体验证覆盖率，更不能证明访存数据正确。

旧 UVM 功能覆盖报告在 QBS 启用、AKV 未启用的单一镜像中为 12/14。
余下两项原定义为 B 背压和 CVXIF 旧响应/新请求同周期同 ID 复用；
RTL 审核显示 VSTU 在 BVALID 时总是拉高 BREADY，QBS/AKV 只在
普通 VLSU 排空后接管 AXI，而 dispatcher 接受 CVXIF 请求时同步
交付对应响应。这两项不再作为可达背压/复用覆盖点，改由
`axi_b_always_ready` 与 `cvxif_atomic_req_resp` 的非零流量加逐周期
真实 DUT bind 断言检查。原始零计数和不适用理由仍写入覆盖报告。
新审计要求断言标记，旧 VCS 镜像不能被重新解释为新口径的 PASS。
在 QBS+AKV 双启用、1 MiB L2、输入侧延迟的同一新镜像下，真实
QBS context 点及标准 RVV 读/写复位点均通过；
`verification/out/uvm-coverage-contract-20260923-01.json` 的三份
哈希重审证据命中 14/14 bin、零错误且仅有一个闭合镜像组。
4 MiB L2 的 QBS+AKV 联合程序另在同源配置的新镜像上完成数值自检
与 UVM 审计：3532 次 CVXIF 请求/响应、3155 次 VID 分配/完成，
278 次完整 AXI 读和 191 次完整 AXI 写，均无遗留事务。再用该
**同一 VCS 镜像**运行标准 RVV 读、写复位用例，各实际取消 1 次
对应的 AXI 事务；三次运行的日志、ELF、向量轨迹和镜像哈希重审
见 `verification/out/uvm-coverage-contract-combined-4m-20260923-02.json`，
结果为 14/14 bin、零错误、一个闭合镜像组。它只闭合所列 UVM
接口功能项；AXI 数据内容/地址顺序、完整 RVV ISA、代码覆盖和
Linux 用户态仍不能据此签收。
新增标准 RVV Q8_0 真实模型切片后，四条同镜像运行的哈希重审报告
`verification/out/uvm-coverage-contract-with-rvv-q8-20260923-03.json`
仍为 14/14 个选定协议 bin、零错误、单一闭合镜像组；该增量证明
Q8_0 对照的 UVM 活动属于同一已审计镜像，不扩大这 14 项的定义。
同镜像的真实 Qwen2.5 decode Attention 单切片另完成标准 RVV 与
AKV-v2 独立运行；两侧 golden 自检与 UVM 均 PASS，输入字节和镜像
组件复核后得到 `156845/41534=3.78x` 的计算窗口周期比，证据在
`verification/out/akv-attention-pair-inputs-20260923-01/paired_evidence.json`。
这只覆盖所测 `D=128`、12 个 query head、2 个 KV head 和该次捕获
上下文，不替代其他 view/lifetime、上下文长度与模型的签收。
把上述两条 Attention 用例与联合 QBS+AKV、标准 RVV Q8_0 及读写复位
用例共同纳入同镜像报告后，
`verification/out/uvm-coverage-contract-semantic-20260923-04.json`
从原始 UVM 日志和向量后端接受事件重审 6 条运行，19/19 个选定
协议及指令活动 bin 命中、零错误、一个闭合镜像组。新增 5 项仅为
QBS M1、AKV-v2 fill/K 列、AKV V 行读取及 release 的实际指令分配；
它们证明路径被使用，不证明所有格式/shape、访存数据内容或代码
覆盖率已闭合。
后续报告 `verification/out/uvm-coverage-completion-20260923-01.json`
对同六份原始日志增加 5 个完成点：要求 QBS M1、AKV-v2 fill/K 列、
AKV V 行读取和 release 的后端 `done` 与同一复位 epoch 内的 `alloc`
按序号、VID 和指令字匹配。重审结果为同一镜像组 24/24 个选定点命中、
零审计错误；分配与完成分开统计。此处的 `PASS` 只表示该组协议和
自定义指令活动点闭合，不表示独立数值 oracle、全格式/shape、
Linux 用户态或 RTL 代码覆盖已经签收。

QBS DIRECT/CONTEXT 的冻结结果位于
`verification/out/qbs-context-real-dut-enabled-20260923-01/`。VCS 镜像配置为
`qbs=1, akv_v2=1`；两条路径的 checksum 均为
`0x71b5ea8a1468eb92`、mismatch 均为 0，两命令 activation AXI 读取
3504 B 对 1752 B，第二命令周期 2371 对 2255。两条真实 DUT UVM
检查均为 PASS，ELF、配置、VCS 镜像和输出的 SHA-256 清单复核通过。
此前误用 `qbs=0` 镜像的运行在首条自定义指令触发 Illegal Instruction，
已排除出覆盖证据；运行脚本现会在启动前拒绝这种配置。

同一 `qbs=1,akv_v2=1` DUT 镜像还运行了普通 RVV 向量上下文用例，
`verification/out/rvv-on-qbs-uvm-20260923-01/uvm_result.json` 为 PASS：
350 次 CVXIF 请求与响应、240 次 VID 分配与完成、30 次完整 AXI 读、
228 次完整 AXI 写，均无未完成事务。它证明快路径启用时该普通 RVV
用例仍可执行，不代表全部 RVV 指令和随机组合已签收。

真实模型数据组合用例位于
`verification/out/qbs-akv-combined-real-dut-20260923-01/`：程序数值
自检与 UVM 事务检查均通过，QBS 命令 1 次、AKV 命令 292 次，
`QBS_AKV_COMBINED` 报告 QBS 14117 周期、Attention 35912 周期。
初始后处理检查器误要求未启用的 `+AKV_SUMMARY`，故原运行脚本没有
产生 `RUN_SHA256SUMS`；原始 VCS 日志实际含逐命令 `AKV_PERF`。
修正后的检查器对原日志重解析为 PASS，使用
`verification/qbs/reanalyze_combined_real_dut.sh` 核对除旧检查器外的
全部原输入并生成单独的 `POSTPROCESS_SHA256SUMS`。旧 `INPUT_SHA256SUMS`
保留不改；这项重解析不能表述成原检查器哈希仍然匹配。

真实 DUT 覆盖审计命令：

```bash
PYTHONPATH=verification python3 -m ara_verify.uvm_coverage \
  --audit verification/out/real-ara-uvm-axi-hold-20260923-01/tests/rv64uv-ara-linux_vector_context/uvm_result.json \
  --audit verification/out/qbs-context-real-dut-enabled-20260923-01/llama_qwen25_decode_attn_q_qbs_direct2/uvm_result.json \
  --audit verification/out/qbs-context-real-dut-enabled-20260923-01/llama_qwen25_decode_attn_q_qbs_ctx2/uvm_result.json \
  --output verification/out/uvm-coverage-closure-20260923-03.json
```

审计重新哈希原始日志、ELF、独立向量 trace 和 VCS 镜像，再重跑事务检查；
独立 UVM smoke 不计入真实 DUT 覆盖。初始 `INCOMPLETE` 诊断中，三个真实 DUT
用例的跨镜像并集命中 8/14，但 `qbs=0` 与 `qbs=1` 两个 VCS 镜像
各只命中 7/14；签收必须以同一镜像组为准，不能拼接配置。
跨镜像未命中：CVXIF 同周期 ID 复用、AXI AR/AW/B 三通道背压、
复位中止读事务、复位中止写事务。单个计数为 0 只表示本次未观察到，
不等于该路径错误。补点需使用新 run 目录和冻结镜像，不能修改旧审计结果。

复位两项之前无法由真实 DUT 的 PASS 日志闭合：普通审计禁止任何请求后
复位，而 contract 摘要只计最后一个 reset epoch。现加入仅验证镜像启用的
AR/AW 握手触发复位，以及专用审计模式；普通运行仍保持原门禁。
专用模式对全程 UVM/contract 事件逐项比对，并把复位后的事件数与
contract 最终 epoch 单独比较；覆盖 bin 还要求目标 AXI 中止数非零。
独立向量 trace 在复位时写入边界标记，VID 事件按两个 reset epoch 分别
核对 ID、顺序和相对周期；原 trace 的周期计数会在复位后归零，不能把
整段轨迹当作单一时间轴比较。

同一真实 DUT UVM 镜像
`verification/out/real-ara-uvm-reset-epoch-20260923-02/sim/simv`
下，普通 `vfredmax_boundary`、普通 `linux_vector_context`、读复位和
写复位四次运行均通过程序自检、UVM 与独立轨迹审计。读复位在 5 次 AR
中实际取消 1 次，VID 为 9 次分配、8 次完成、1 次取消；写复位在
229 次 AW 中实际取消 1 次，VID 为 245 次分配、244 次完成、1 次
取消。审计结果分别保留于
`verification/out/uvm-reset-read-20260923-03/uvm_result.json` 和
`verification/out/uvm-reset-write-20260923-03/uvm_result.json`。
四次运行的同镜像覆盖汇总为
`verification/out/uvm-coverage-reset-20260923-01.json`：无证据错误，
命中 9/14；仍缺 AXI AR/R/AW/B 背压和 CVXIF 同周期 ID 复用。背压
计数为零不能解释为检查器未接入，也不能标为已覆盖。

针对真实 DUT 背压，在 `ARA_VERIFY_AXI_DELAY` 验证镜像中于 Ara AXI
边界插入现有 `axi_delayer`。输入侧固定延迟 3 拍，R/B 返回侧直通；
普通 RTL 编译和综合不启用此宏。先前五通道均延迟的 QBS 用例虽然
PASS，却使原本可观察的 R 背压消失，因此该旧镜像仅用于诊断，不能
代替最终覆盖证据。输入侧延迟的 QBS+AKV 镜像
`verification/out/qbs-akv-uvm-input-delay-20260923-01/sim/simv`
上，真实 Qwen 数据 `decode_attn_q_qbs_ctx2` 自检 PASS，AR/R/AW/W
分别出现 765/228/545/2640 个背压周期，4178 次跨周期载荷保持
检查零 UVM 错误。

复位激励原先使用 `#1`，而 TB 时钟周期也为 1 ns，导致复位与下一
上升沿竞争：UVM 的 `#1step` 采样多记录一次 CVXIF 握手，独立
contract monitor 在复位分支跳过该握手。失败原始记录保留于
`verification/out/uvm-delay-reset-write-20260923-01/`。改在已接受
AR/AW 后的下降沿拉低复位，重跑的写用例 UVM/contract 全程逐事件
对齐，程序自检及 AXI/VID 中止账本均 PASS。

上述 QBS+AKV 输入侧延迟镜像再运行标准 RVV 读复位和写复位，三项
完整证据的单镜像审计结果为
`verification/out/uvm-coverage-qbs-input-delay-20260923-01.json`：
零证据错误、命中 **12/14**。只剩 AXI B 背压和 CVXIF 旧响应与新请求
同周期同 ID 复用；这两项仍为 `INCOMPLETE`，需先审查 RTL 可达性，
若不可达须提供带源码约束与复核证据的 waiver，不能把零计数写成 PASS。
初步结构审查显示，普通 `vstu` 收到 `axi_b_valid_i` 时立即拉高
`axi_b_ready_o`；QBS/AKV 只在 `normal_vlsu_idle` 后接管 AXI，
而 `vstu_idle` 要求 store commit 队列为空。故合法普通 store 的
`B.valid && !B.ready` 是 waiver 候选，不是需要伪造的背压场景；
仍需独立断言或形式化复核及明确适用配置。三项同镜像用例分别记录
742、30、375 次 CVXIF 请求，均为当拍响应且同 ID 旧响应复用为零；
这只是已测路径的事实，不能据此豁免尚未覆盖的非当拍响应路径。

本次同镜像重审命令：

```bash
PYTHONPATH=verification python3 -m ara_verify.uvm_coverage \
  --audit verification/out/qbs-uvm-input-delay-case-20260923-01/uvm_result.json \
  --audit verification/out/qbs-input-delay-reset-read-20260923-01/uvm_result.json \
  --audit verification/out/qbs-input-delay-reset-write-20260923-01/uvm_result.json \
  --output verification/out/uvm-coverage-qbs-input-delay-20260923-01.json
```

将上述两条 QBS 上下文用例与普通 RVV 用例限定在同一 QBS+AKV
VCS 镜像后，`verification/out/uvm-coverage-same-qbs-image-20260923-01.json`
无证据错误、命中 8/14；仍缺 CVXIF 同周期 ID 复用、AXI AR/AW/B
背压以及复位中止读写事务。后续须用真实 DUT 定向激励补齐，不能以
独立 agent smoke 或跨镜像并集替代。

SLDU 结果队列读指针修复后，在新的同配置 UVM 镜像上重新运行普通 RVV
上下文与 QBS DIRECT/CONTEXT，三者自检和 UVM 均通过；load/store
随机 seed 51 的原失败 ELF 严格重放通过，seed 52 也在修复镜像上通过。
`verification/out/uvm-coverage-sldu-fixed-20260923-02.json` 对新镜像
重新审计仍为 8/14；修复没有扩大上述功能覆盖范围。

标准 RVV 的 `ara_dsa_rvv1_mixed_control` 两个固定种子严格回归已通过：
`verification/out/rvv-mixed-strict-20260923-02/summary.json` 记录两条 PASS；
Spike/RTL 分别匹配 852、854 条提交记录，向量状态为 `PREFIX` 匹配。
这只是两个随机样本，不代表 V2 全矩阵闭合。
两例的严格逐条对比分别停在索引 851 的 `vcpop.m`（PC
`0x80001a2e`）和索引 853 的 `vmv.x.s`（PC `0x80002ec2`）：
源向量含尾部/掩码策略允许的未定义位，标量结果因而不可独立观察。
比较器保留此前的严格匹配前缀，不能把后续程序自检 PASS 改写为
完整 Spike/RTL 逐条一致。下文 seed 101 已提供另一条确定性随机流
的全程严格差分；mixed-control 若要达到同等级证据，须在标量读取前
使相应源元素/掩码位架构确定。原 mixed-control 随机流仍保留为
未定义位传播及出口自检的边界用例，不靠忽略差异取得全程匹配。
对冻结轨迹离线重放逐位已知性后，seed 0 在索引 851 的
`vcpop.m s10,v22,v0.t` 前，v22 的低 33 位均被标为不确定，而 v0
的相应谓词位确定，其中 25 位允许参与计数。不确定性先后经过
`vmseq.vv v22,v31,v4,v0.t` 与 `vmulh.vv v22,v25,v21,v0.t` 传播。
seed 1 在索引 853 的 `vmv.x.s t1,v16` 前，v16 第 0 元素不确定；
最近的写者为 `vwredsumu.vs v16,v20,v7`，归约输入 v20 的低 64 位
已被标为不确定。这两处均是标量结果依赖未定义向量源的具体路径，
不是仅凭最终 GPR 不一致作出的推测。新的完整严格 mixed-control
样本必须在产生这种标量读取前建立已定义源，且仍保留原程序的
控制流、掩码与归约覆盖；不能把未知结果直接白名单化。
这两例的最终生成汇编覆盖另有执行侧交叉检查：
`verification/out/rvv-mixed-strict-20260923-02/retired_activity.json` 使用
冻结 ELF 的反汇编与 DUT 退休轨迹逐条核对 PC/编码，只对实际退休的
RVV 指令统计 mnemonic、访存类型、已知 SEW/LMUL 及 mask 使用。
复现命令为 `PYTHONPATH=verification python3 -m ara_verify.dynamic_coverage
--case <case0> --case <case1> --objdump install/riscv-gcc/bin/riscv64-unknown-elf-objdump
--output <new-report.json>`；输入 SHA-256 写入报告。两例合计 6792 条
实际退休 RVV 指令，但 Spike/RTL 逐条匹配分别止于 852/854 条
**全部类型**提交记录；后续指令只具有该 PASS 用例的出口自检证据，
不能说成全部逐条比对通过。此报告也不等于 RTL 代码覆盖。
在这两条样本中，实际退休的访存仅见 unit-stride 64 条和
whole-register 64 条；已知运行配置仅有 e64/m1、e8/mf2、e8/m4。
因此 strided/indexed/segment、e16/e32 等必测维度仍须从独立
定向或随机用例取得可审计的执行证据，不能用生成侧直方图补齐。
一条已通过的 `ara_dsa_rvv1_load_store_1` 样本另提供 1473 条实际
退休 RVV 指令，其中 strided 8、indexed 3、mask 3、fault-first 1，
且出现 e16/mf2；该例 Spike/RTL 逐条比对仅到 400 条全部类型提交。
三例合并的执行侧活动报告为
`verification/out/rvv-retired-activity-20260923-01.json`，共 8265 条
实际退休 RVV 指令。segment、e32 及其余配置/异常交叉仍未据此闭合。
新增 `rvv:vsegment_emul_edges` 在同一冻结 VCS 镜像上完成程序自检，
`verification/out/rvv-segment-e32-20260923-03/` 的定向运行与 trace
审计均 PASS：147 次 CVXIF 请求、972 次后端分配/完成。
`verification/out/rvv-retired-activity-with-segment-20260923-01.json`
重审四条 PASS 用例共 8393 条实际退休 RVV 指令，其中这条定向程序
有 16 条 segment 访存，并实际执行 e32/m1、m2、m4、mf2。
这项新增证据由程序内存结果自检、ELF/镜像哈希和退休轨迹支撑，
没有 Spike 逐条对比；其他 SEW/LMUL、异常与重启交叉仍未闭合。
同源 `vsegment_emul_edges.c` 又按 `apps/riscv-tests/isa/Makefile` 的
`rv64uv-p-*` 规则链接 Spike 专用 `crt.S/syscalls.c`，
`verification/out/rvv-segment-e32-spike-runtime-20260923-01/spike.elf`
在 `--isa=rv64gcv_zvl1024b` 下独立运行并输出 `PASSED`，日志在
`verification/out/rvv-segment-e32-spike-runtime-20260923-02/`。
源码 SHA-256 为 `efe14d4e37b47282d550a1d91fb6e2607caa9c576e50a7787ffdd83c722f11d1`；
VCS/Spike ELF 分别为 `5215419134fe6c6a9c5b97762d0fe040d1a3f0f1672807ffdd67722b432e2ebf` 和
`700fbb7a471675b0a0d51dd90d3b8754e1c97db7c0c575e7310ccdf7c97c068a`。
这证明同一测试逻辑在两个运行时均通过，**不是同一 ELF 的逐条差分**；
直接把已 strip、无 `tohost/fromhost` 的 VCS ELF 交给 Spike 会停在
不兼容的退出协议处，旧超时诊断保留于
`verification/out/rvv-segment-e32-spike-20260923-01/`。
统计脚本同时修正了 `vlseg` 被 `vlse` 前缀误分类为 strided 的问题，
新报告另存，旧报告不追改。首次定向运行的 FAIL 是 runner 将
`UVM_FATAL : 0` 汇总行误判为 fatal；修正判定并加测试后，
相同 ELF/镜像的确认运行才计入上述 PASS 证据。
另在同一冻结镜像上运行 `vindexed_vstart_edges` 和
`vstore_mask_tail_edges`，见
`verification/out/rvv-lmul-extremes-20260923-01/`：两条程序自检 PASS，
trace 审计 2/2 PASS。执行侧六例汇总
`verification/out/rvv-retired-activity-lmul-20260923-01.json`
包含 8440 条实际退休 RVV 指令；新增 `e64/m8` 4 条、`e8/mf8` 3 条，
七个 LMUL 值均至少在实际执行的向量指令上出现。
这是单维活动命中，不代表全部合法 SEW×LMUL、mask/tail policy、
非零 vstart、异常重启或架构状态逐条比对已经闭合。
从相同六条 PASS 轨迹另生成
`verification/out/rvv-retired-activity-policy-20260923-01.json`：
8440 条退休 RVV 指令中，56 条是配置指令；其余 8384 条按最近一次
已退休且可静态解码的 `vsetvli/vsetivli` 分组，`tu/mu` 8379 条、
`ta/ma` 5 条、未知 0 条。这是指令指定策略的执行侧活动统计，
不是直接读取 RTL `vtype` 的独立核对，也不是策略交叉覆盖签收。
当前没有 `ta/mu`、`tu/ma` 的退休活动证据；动态 `vsetvl` 无法由
反汇编确定其策略时，后续指令会单独计入未知而非推断。
补充的 `vmask_logical_matrix` 在冻结 VCS 镜像上程序自检及 trace 审计
均 PASS；七例合计 8824 条退休 RVV 指令，四种 policy 配置均有活动。
但该 mask-logical 程序的 `ma/mu` 编码并不意味着 masked-off 目的元素
受到检查：它没有带 `v0.t` 的向量指令，报告将两者分开列出。
为验证这一差别，新增 `vpolicy_masked_edges`：四种 policy 下各执行
一条带 `v0.t` 的 `vadd.vv`，以标量参考值检查选中元素，并仅在
`tu`/`mu` 规定保留时检查尾元素/未选中元素。
`verification/out/rvv-masked-policy-20260923-01/` 在相同冻结镜像上
程序自检 PASS、trace 审计 1/1 PASS；
`verification/out/rvv-masked-policy-retired-20260923-01.json`
显示四种组合各有 1 条 `v0.t` 指令退休。这仍是定向程序自检，
不是同 ELF 的 Spike 逐条比对，也不证明其他 SEW/LMUL 与异常交叉。
八例合并统计见
`verification/out/rvv-retired-activity-policy-8case-20260923-01.json`：
8860 条 RVV 指令退休，`v0.t` 对应的四种配置各有活动；
这只是策略组合活动和上述定向结果自检，不等于全矩阵语义覆盖。
相同源码另用 Spike 专用 `crt.S/syscalls.c` 链接并在
`--isa=rv64gcv_zvl1024b` 下运行，输出 `PASSED`；ELF 和 commit 日志保存在
`verification/out/rvv-masked-policy-spike-20260923-01/`。
源码 SHA-256 为 `b0a098004a91a1808e6ba7564f5ae8640af3db13320d0c9dfd4033eca72997ac`；
VCS ELF 为 `ef15cc625b713d040ca5a82dc9710b24add36abaae59fceba7eafd1ff9798df7`，
Spike ELF 为 `252e5522338b3a51f84dc5e03fc4051d88eb08cd1c17a2d798f1538cffbfae2f`。
Spike 构建时将 `RISCV_LLVM` 指向本仓库的 RISC-V LLVM clang，并执行
`make -C apps/riscv-tests/isa rv64uv-p-vpolicy_masked_edges`；两侧 ELF 不同，证据限于同源
程序各自完成结果自检，不能据此声称逐条架构状态匹配。
Q8_0 的真实数据标准 RVV/QBS 成对证据已在
`verification/out/qbs-rvv-q8-pair-20260923-02/` 通过数值和 UVM 审计；
配对检查要求相同捕获输入、golden 和完整 VCS 镜像。
审计器现进一步要求 RVV 对照的后端实际分配指令中无任何 QBS/AKV
共用的 `custom-2` opcode，而非只排除某一个固定 QBS 指令字。
`verification/out/qbs-rvv-q8-pair-custom2-audit-20260923-01.json`
对原始文件重新哈希审计仍 PASS，RVV 路径 `custom-2` 分配为 0，
周期与加速比未变；这仍只是 Q8_0 单点，不代表全部量化格式。
Q3_K/Q5_K 的标准 RVV 真实数据对照第一次独立重跑分别报告
`REAL_BENCH result=PASS`、`mismatches=0`，但 UVM 审计均为 FAIL：
`ARA_CONTRACT_TRACE_LIMIT=500000` 时 `ARA_UVM_TRACE_LIMIT` 仍采用
100000 默认值，截断了 148593/154113 次 CVXIF 请求及
142174/153164 次后端分配对应的 UVM 事件。旧运行保留在
`verification/out/qbs-rvv-q{3,5}-pair-20260923-02/`，不得作为
配对签收。两项以两个事件上限均为 500000 的命令另起
`verification/out/qbs-rvv-q{3,5}-pair-20260923-03/` 重跑后，程序仍分别
报告 `REAL_BENCH PASS`、`mismatches=0`，UVM summary 均为零 error/fatal，
但独立审计仍拒绝：旧 VCS 镜像在 `fire=0` 的等待周期也打印
`ARA_CONTRACT_TRACE`，各自 500000 条原始记录先达到上限，只有
97912/62000 条实际事件进入审计，低于 148593/154113 次 CVXIF
请求。当前监视器源码已仅在握手时打印；旧镜像的实际日志证明
它未包含这一改动，不能靠放宽门禁或再次提高日志上限签收。
独立的新 UVM 镜像已编译完成，输出到
`verification/out/real-ara-uvm-contract-fire-4m-20260923-01/`，
保持 4 MiB L2、QBS/AKV 和 AXI 延迟配置。
`verification/out/real-ara-uvm-fire-smoke-20260923-01/` 的真实 DUT
短测已通过，37 条 UVM 事件与 37 条独立 contract 事件一致，
没有 `fire=0` 空闲记录。Q3_K/Q5_K 的 QBS 侧已分别在
`verification/out/qbs-q{3,5}-fire-pair-20260923-01/` 通过真实数据
自检、UVM 和 QBS 证据审计。相同新镜像的标准 RVV 对照位于
`verification/out/qbs-rvv-q{3,5}-fire-pair-20260923-01/`。两点均已
完成逐事件 UVM 审计与成对证据检查：Q3_K 的 RVV/QBS 分别为
`955389/33281` 周期（`28.71x`），Q5_K 分别为 `1493614/37143`
周期（`40.21x`）。捕获输入、结果和镜像哈希一致，标准 RVV 路径
均无 custom-2 指令分配。这仅是两个真实数据切片的配对结论，
不是模型端到端加速比。审计器现把 contract trace 中双方均未握手的
空闲记录视为失败，而不再静默忽略；历史 Q3_K RVV 日志中有
402088 条此类记录，新镜像的 Q3_K QBS 日志无此类记录。该规则
用于尽早发现旧镜像先耗尽原始日志上限的问题，不能代替事件总数
及逐事件摘要的独立比对。
同一镜像上的 Q6_K QBS 与标准 RVV 对照均完成真实数据自检和 UVM。
`verification/out/q6-qbs-real-pair-20260923-01/qbs_evidence.json`
复核了 8 条 QBS 命令的分配与完成；
`verification/out/q6-paired-evidence-20260923-01.json` 进一步核对两侧
捕获输入、golden、ELF、完整 VCS 镜像、日志与向量分配：QBS/RVV 均为
零 mismatch，标准 RVV 无 custom-2 分配，RVV/QBS 分别为
`1478066/40561` 周期（`36.44x`）。该数值只适用于所测 Qwen2.5-1.5B
`decode attn_q` 切片的计算窗口，不代表模型整体加速比。
Q3_K/Q5_K/Q6_K/Q8_0 和 AKV-v2/标准 RVV Attention 对照的 VCS `simv`
哈希均为 `9a8dbe29d9f2ba325feed39da104d1c4f1884b3c75822dde12e6756be55e36d3`。
新镜像的 Q8_0 配对审计见
`verification/out/qbs-rvv-q8-fire-pair-20260923-01/paired_evidence.json`：
RVV/QBS 为 `173026/38782` 周期（`4.46x`），两侧数值自检通过，
RVV 无 custom-2 分配。AKV-v2 的冻结 ELF 新镜像配对报告为
`verification/out/akv-attention-pair-inputs-20260923-01/paired_evidence_fire_20260923.json`，
RVV/AKV-v2 为 `156845/41534` 周期（`3.78x`），两侧自检及 UVM
均通过，标准 RVV 无 custom-2 分配。
`verification/qbs/audit_paired_campaign.py` 使用
`verification/qbs/paired_campaign_20260923.json` 重新调用每个成对
审计，并强制检查代表格式和完整镜像身份；结果
`verification/out/paired-campaign-20260923-04.json` 为 PASS：
五项各自 PASS、零证据错误、无缺失格式，且完整镜像组件身份一致。
这只是代表性真实数据切片的配对门禁，不是全部 QBS profile 或
端到端模型签收。

复用上述同一镜像和已有短程序，普通 smoke、QBS Q3_K/Q5_K、
读/写复位及 QBS+AKV 组合六条运行均通过原始日志重审；报告
`verification/out/uvm-coverage-fire-closed-20260923-01.json` 的
24/24 个可达接口功能 bin 在同一镜像组闭合，零审计错误。这不是
RVV 指令功能、RTL 代码覆盖或 Linux 启动的签收。后续不为这些
已命中的 bin 重复仿真；新增运行须先说明缺少的证据和最早可判别周期。
`run_signoff.py --stage uvm` 对相同六条原始审计重算的门禁结果为
`verification/out/uvm-signoff-20260923-01/signoff.json`，状态 PASS；
只提供普通 smoke 的负例为 INCOMPLETE。门禁不会把旧汇总 JSON
中的 PASS 直接当作可用证据。

QBS profile-engine 的独立矩阵审计见
`verification/out/qbs-profile-matrix-audit-20260923-01.json`：原始 VCS
日志中 448/448 个预定组合恰好命中一次（九格式、M=1..4、rows=1..4、
三个模式，Q8_0 额外 16 个极值点）。真实模型数据 RTL 子系统六点在
`verification/out/qbs-real-rtl-sealed-20260923-01/` 重跑，输入、VCS
镜像、命令向量、日志和汇总均有可复核哈希，结果与旧汇总一致。
这两组是子系统级证据，彼此互补；其中六点真实数据只含 Q4_K/Q6_K。
整机真实数据格式覆盖另见上面的九格式配对清单，不得将子系统结果
代替整机 QBS+AKV 数值或 Linux 用户态签收。

## 里程碑与通过条件

| 阶段 | 实施内容 | 可审计出口 |
| --- | --- | --- |
| V0 输入冻结 | 锁定 RTL/依赖补丁、编译器、Spike、QEMU、VCS、配置、模型数据、ELF、Image/DTB/rootfs 的提交与 SHA-256；每次改动另起 run 目录 | manifest、完整命令、种子、工具版本齐全；不得复用旧结果冒充新版本 |
| V1 真实 DUT UVM | 已接入真实 CVXIF、sequencer VID 和 Ara AXI 五通道的被动 monitor 与协议 scoreboard；下一步补访存数据/顺序检查、flush/reset 和可达通道背压的真实 DUT 激励，并把功能覆盖命中量映射到需求；B always-ready 与 CVXIF 原子握手按接口不变量检查 | UVM monitor 与独立 contract/vector trace 在同一 ELF 上事务数/ID/时序一致；故意注入错误能被检查器捕获；真实 DUT 场景有非零命中量且架构结果另行比对，零 UVM error/fatal 本身不足以 PASS |
| V2 标准 RVV | 定向边界、ISA 测试和分层随机；Spike 对比标量提交、逐条向量写回/可见状态、CSR 与 store 后内存签名；覆盖 `vset`、SEW/LMUL、mask/tail、`vstart`、FP 归约/转换、各访存模式、异常与重启 | 最早分歧可定位到动态指令/VID；所有必测点通过，多种固定种子可复现；失败种子保留原始与缩减版本 |
| V3 QBS/AKV | 用真实 GGUF 捕获数据覆盖支持的格式/profile、M/N/K 与尾块、生命周期/view、资源冲突、非法描述符、flush/reset 和标准 RVV fallback；比较独立软件数值参考、内存保护及完成事件，不以同源 QEMU 模型作为唯一 oracle | 每个受支持组合有数值容差/精确比较规则、硬件路径命中证据和 fallback 证据；新机制关闭时普通 RVV 不退化为错误结果 |
| V4 覆盖闭合 | 需求-测试-功能 bin 双向矩阵；功能 covergroup 只在接受/完成/退休等定义清楚的事件采样。VCS line/branch/condition/FSM/toggle 覆盖限定到 DUT，排除 TB/库模型；审查交叉 bin 和断言非空触发 | 必测功能 bin 100% 达成或逐项审核 waiver；关键模块初始量化目标：可达 line/branch/condition/FSM 至少 95%，合格 toggle 至少 90%；剩余每个未覆盖点分类和签字，不以总百分比掩盖关键路径 |
| V5 VCS SoC/Linux | 使用真正含中断、MMU、UART 与外部内存的 SoC VCS top，先裸机/IRQ/MMU，再加载同源 OpenSBI、Linux、DTB、rootfs；用户态执行标准 RVV、QBS/AKV、禁用扩展 fallback、页故障/信号返回与多进程抢占 | 全启动到 init/用户态；输出自检签名、进程退出码、内核错误扫描和 payload hash；QEMU 结果单列，不能替代 VCS |
| V6 签收 | 分别审核 RVV、QBS/AKV、Linux 三条线；失败/超时/不可观测和工具故障不得转为 PASS | 每条线独立证据包、需求覆盖表、代码覆盖与 waiver、未关闭 bug 列表、可重放命令；任一线未闭合则整机结论仍为未签收 |

## 规模与回归节奏

- 每次 RTL 修改：相关定向首错回归 + 代表性普通 RVV/QBS/AKV 正反路径；通过后再扩到完整矩阵。标准 RVV 随机建议日常 10 个固定种子、夜间 50 个、最终签收 200 个，种子数量不能代替功能覆盖。
- VCS Linux 不停在几条 bare-metal 指令。先完成可启动 SoC；关键回归以单次 **1–2 小时墙钟时间**为目标，使用 2–4 个用户进程/线程、实际计数的 256–1024 次抢占或上下文切换、16–64 MiB 跨页工作集、反复 RVV/快速路径与 fallback 切换。具体负载按仿真吞吐率校准，达不到预定事件数即未完成，而不是把超时当通过。
- 当前 `rvv_linux_smoke` 只承担整机启动、基本 RVV、一次父子进程状态隔离和故障/信号返回的第一阶段门禁；即使该程序在 VCS 上通过，也不能代替上一条的压力回归。Linux 压力阶段需分别记录进程切换、定时器中断、缺页/权限故障、实际触达页数、RVV 状态签名、QBS/AKV 接受与完成数及 fallback 次数。开始前用实测 VCS 吞吐率估算事件预算；若 1–2 小时不足以达到目标，可拆为多个各自有冻结输入和独立出口的运行，但不能合并不等价的状态或把未执行的覆盖点算作完成。
- Linux 专项至少分别覆盖标准 RVV 状态、Sv39 页故障/权限恢复、信号返回、QBS/AKV 合法与非法请求、共享内存/访存顺序及负载期间 IRQ。自检须写明成功/失败 marker；同时检查内核 oops/panic、无响应和 VCS assertion。
- 超过十分钟的运行放到独立后台目录，启动后只确认进程、日志增长和输入哈希；完成后统一收集。诊断错误时先确定首错与周期信号假设，再跑一次有界波形，不凭多次换参数猜测。

## 覆盖率与工具门禁

随机用例的生成侧 `stimulus_coverage.json` 没有 PASS 字段；审计通过重算
原始 ASM 的直方图验证其完整性。该直方图仍不等于动态指令/功能覆盖。
此前记录在 ASM 改写前，seed 53–55 的旧直方图与最终编译源不一致；
旧文件保留为生成器侧诊断，不计入签收。新运行在改写和编译后记录最终 ASM。
`verify.py audit --require-full-match` 进一步要求所有 RTL 非 trap commit
被比较，并具备完整向量状态证据。`MATCH`、显式配置的退出 PC 上
最后一条 trap-marked `ecall` 被核对后的 `TERMINAL_MATCH`，以及
ELF/命令/成功写入一致的 `TERMINAL_TOHOST_MATCH` 可满足架构匹配条件；
普通 `PREFIX`（包括中途截断和架构值不可观测）只保留为诊断，
不可用于签收。后者允许 Spike 继续执行测试退出后的 trap handler，
但不把这些未在 RTL 中执行的指令混入共同执行区间。

现有严格随机激励 seed 101 的长时重放完成：共同执行区间的 319107 条
非 trap 提交逐条一致，末尾 RTL 退出记录为 `0x80003e70` 的 `ecall`，
526 个向量目标写请求逐条比较 PASS，36973 个已知字节一致。离线复算
得到 `TERMINAL_MATCH`，原重放目录的历史 JSON 仍保留旧版 `PREFIX`；
该重放目录不具备完整原始 run 元数据，不能仅凭此例宣布随机主线签收。

使用当前比较与审计逻辑重新运行的 seed 101 证据位于
`verification/out/rvv-checkpoint-strict-4m-20260923-02/`：RTL 和 Spike 均
正常结束，319107 条非 trap 提交逐条匹配，最后的 trap-marked `ecall`
在指定退出 PC 精确匹配，526 条向量目标写请求的 36973 个已知字节匹配，
16/16 个完整向量状态检查点通过。运行目录保留 `run.json`、原始日志和
`summary.json`；对该目录执行
`verify.py audit --require-trace --require-vector --require-full-match`
得到 `verification_audit.json`，结果 PASS。未知写入字节未被误报为已比较
字节；此结果是单种子证据，不替代多种子、需求和代码覆盖闭合。

对已完成的 load/store seed 53–55，仅重审原始 ELF、Spike/RTL
轨迹与命令而不重跑 VCS。seed 53 在 2667 条非 trap 提交后由已配置
的 `tohost=0x80003000` 成功写入值 `1` 结束；Spike 下一条继续执行
退出循环，而 RTL 测试台按契约停止。新的严格终端判定同时核对
ELF 符号、命令 plusarg、最后一条匹配 store、RTL SUCCESS marker 和
完整向量目的请求与已知字节。独立报告
`verification/out/rvv-seed53-terminal-audit-20260923-01.json` 为 PASS，
2667/2667 条非 trap 提交匹配。原比较器在架构未定义的向量转标量
结果处总是截断，即使本次 RTL 与 Spike 的实际标量值相同。现仅当
该值相同且 RTL 值可知时继续逐条比较；若不同或未知，仍在该点停止，
不把未定义值的偶然一致解释为架构正确性。用未改变的原始日志重审，
seed 54 和 55 分别为 2647/2647、2682/2682 条非 trap 提交匹配，
完整向量目的请求数分别为 1361、1462，已知字节分别比较 14955、
30629；报告见 `verification/out/rvv-seed54-terminal-audit-20260923-02.json`
和 `verification/out/rvv-seed55-terminal-audit-20260923-02.json`，均为 PASS。
其余未定义向量字节仍按既有规则跳过，不能声称所有向量位逐位一致。
seed 54 的旧负例报告只代表旧比较器口径，保留作为诊断历史。这三条
短随机用例没有覆盖完整 ISA，也不代替多 profile/需求/代码覆盖闭合。
另用同一已编译 DUT 和生成器镜像执行 arithmetic profile 的 seed 61：
`verification/out/rvv-arithmetic-strict-seed61-20260923-01/` 的 RTL
运行约 54 秒，2498/2498 条非 trap 提交与 1028/1028 个向量目的请求
比较通过；包含生成侧覆盖检查的严格报告
`verification/out/rvv-arithmetic-strict-seed61-audit-20260923-01.json`
为 1/1 PASS。动态退休报告
`verification/out/rvv-arithmetic-seed61-retired-coverage-20260923-01.json`
记录 1077 条向量类指令，其中浮点 154、widening 103；581 条非配置
指令的 policy 无法由静态 `vsetvl` 推定，不能当作 policy 覆盖。
vtype-churn profile 的 seed 62 使用相同镜像在约 155 秒 RTL 仿真后通过：
`verification/out/rvv-vtype-strict-seed62-audit-20260923-01.json` 为 1/1
严格 PASS，3327/3327 条非 trap 提交及 2794/2794 个向量目的请求匹配。
`verification/out/rvv-vtype-seed62-retired-coverage-20260923-01.json`
记录 2973 条实际退休的向量类指令、84 次配置及多种 SEW/LMUL；
其中 28 次配置是动态 `vsetvl`，不能从静态反汇编推定其 policy。
更重要的是，严格随机流会由 `rewrite_deterministic_vector_policies()`
把 agnostic policy 归一成 `tu/mu`，因此不能拿这个 profile 宣称
`ta/ma` 等 policy 已被随机覆盖。单独的
`rvv:vpolicy_masked_edges` 程序在真实 DUT 自检 PASS；退休活动报告
`verification/out/rvv-policy-matrix-retired-coverage-20260923-01.json`
逐项观察到 `tu/mu`、`tu/ma`、`ta/mu`、`ta/ma` 下各一条 masked
`vadd`。该用例检查架构定义的 active/undisturbed 元素，不要求
agnostic 字节与参考模型逐位相同；它是定向 policy 证据，不是完整
随机 policy 交叉或代码覆盖签收。
浮点 profile 另在同一 DUT/生成器镜像上各执行一个种子：FP32 seed 63
和 FP64 seed 64 的 RTL 耗时分别为 164.303 秒和 154.282 秒。
`verification/out/rvv-fp32-strict-seed63-audit-20260923-01.json` 与
`verification/out/rvv-fp64-strict-seed64-audit-20260923-01.json` 均为
严格审计 1/1 PASS；非 trap 提交分别匹配 3504/3504、3495/3495，
向量目的请求分别匹配 2850/2850、2580/2580。已知向量字节分别比较
19044、13309 个，不可观察字节分别跳过 510697、457462 个，故不能称为
整寄存器逐位相等。两例冻结 RTL 退休轨迹的合并报告
`verification/out/rvv-fp-seeds63-64-retired-coverage-20260923-01.json`
为 PASS，合计 5950 条向量类指令，其中浮点类 569 条；这些计数是已退休
活动，不代表每个浮点子操作、SEW/LMUL/policy 交叉都闭合。
整数压力 seed 65 初次生成后处理在 `vsetvl t4,s3,s3` 处停止，未进入 RTL；
原归一化器不能同时改写作为 AVL 和 vtype 的 `s3`。修复仅在 `rd` 非零且
与 `rs1/rs2` 不同时借用本条即将被覆盖的目的寄存器承载新 vtype，不改变
AVL；三重别名仍拒绝。原生成 ASM 全量静态归一化和 42 项相关单元测试通过。
独立重跑的整数压力 seed 65 与 slide 访存 seed 66 分别用时 228.817、
399.053 秒，完整提交匹配 5386、8719 条，向量目的请求分别匹配 4434、
4141 条；严格审计报告
`verification/out/rvv-integer-stress-strict-seed65-audit-20260923-01.json`
和 `verification/out/rvv-load-store-slide-strict-seed66-audit-20260923-01.json`
各为 1/1 PASS。两例是不同 profile 的单种子证据，不代表 profile
多种子稳定性已闭合。
`verification/out/rvv-activity-matrix-10cases-20260923-04.json` 从冻结
ELF 与 DUT 退休轨迹重算 10 条已通过用例；其中历史 load/store 三例
在纳入之前重新执行严格 tohost/向量目的请求审计，而非直接信任旧的
`PREFIX` 字段。报告保留输入用例清单、反汇编/ELF 工具路径、计划及原始证据
哈希，不覆盖已有报告。计划中的 SEW 4/4、LMUL 7/7、访存模式 7/7、policy
组合 4/4 均有退休活动。访存模式分别为 unit-stride 632、strided 25、
indexed 18、segment 21、mask 4、whole-register 6、fault-first 3 条；
`ta/ma`、`ta/mu`、`tu/ma` 各仅在同一定向用例中出现 1 条，随机流的
agnostic policy 仍被归一化为 `tu/mu`。静态反汇编无法推定 147 次
`vsetvl` 的 SEW/LMUL；现在依据同一提交轨迹中此前已提交的标量寄存器值
还原了这 147 次配置，相关非配置指令的 policy 均已解析，剩余未解析数为 0。
该还原只提高退休活动统计的准确度，不替代 Spike 差分或 RTL 功能检查。
矩阵的 `ACTIVITY_OBSERVED` 只表示各一维 bin 至少出现过，**不**是
SEW×LMUL×指令×policy/异常的功能交叉、RTL 代码覆盖或标准 RVV 签收。
`ara_dsa_rvv1_mixed_control` 的新 seed 41 已在定义向量到标量读取源的
改写流上完整匹配 11198 条提交，退出向量签名及目的写回比对通过；
其结果在 `verification/out/rvv-mixed-defined-seed41-20260923-01/`。
但该版本只覆盖 `main` 中的读取，不能据此说所有随机子程序的读取
都被显式定义。seed 42 的首次同类运行在生成阶段只注入 1 处，
而最终汇编的 `main` 与 `sub_1` 至 `sub_5` 共含 58 条向量到标量读取；
该运行已主动停止，不计入完整严格通过。生成器现对实际执行的
`main` 和子程序做独立计数门禁，漏注入会在 VCS 前报错；
`verification/out/rvv-mixed-defined-seed42-fixed-20260923-01/` 是使用
包含当前 SLDU 修复的真实 DUT 镜像的回归；新生成清单
`defined_scalar_source_reads=58`，与独立汇编助记符计数一致。该运行最终
`PASS`：共同区间 36441 条提交匹配，17262 条向量目的请求的写回检查
状态为 `PASS`，其中实际比较 83661 字节、7883167 字节因参考值未知而
跳过；不能把请求数理解为逐字节全量比较。RTL 运行耗时约 2261 秒，
因此日常修改不重复运行该长用例，保留其结果用于冻结候选的回归证据。
两条 mixed-control seed 也不等于全部随机 profile 签收。
将该通过用例加入原 11 例的离线重审后，独立报告
`verification/out/rvv-activity-legal-cross-matrix-12cases-20260923-01.json`
接受 12/12 例，88/88 个合法 SEW/LMUL/policy 组合有 DUT 退休活动；
8 例具有写回证据，共比较 1565875 字节，因参考值未知跳过
10899409 字节。报告不将这些活动计数解释为完整功能交叉或代码覆盖。
上述 12 例跨多个 VCS 镜像，不能直接作为单一当前 RTL 镜像的闭合证据。
`verification/out/rvv-activity-legal-cross-matrix-12cases-provenance-20260923-01.json`
按 `simv`、生成共享库和 `simulator.conf` 的内容将它们分成 9/1/2 例
三组；对同一清单启用 `--require-same-image` 已如预期拒绝。旧随机回归的
镜像身份是依据启动命令路径事后重新哈希，并无运行时输入清单，故该分组
用于阻止跨镜像误汇总，不单独充当历史镜像未变化的充分证明。
仅用哈希为 `9a8dbe29d9f2ba325feed39da104d1c4f1884b3c75822dde12e6756be55e36d3`
的当前镜像上已通过的 `vpolicy_type_matrix` 与 mixed-control seed 42 重算，
`verification/out/rvv-activity-current-image-2cases-20260923-01.json`
显示合法 SEW/LMUL/policy 仍为 88/88，但访存模式仅 3/7；缺 strided、
indexed、segment 和 fault-first。定向自检套件 `rvv-memory-gap` 只选
`vls`、`vluxei`、`vlseg`、`vlff` 四例，复用同一镜像在独立目录
`verification/out/rvv-memory-gap-current-image-20260923-01/` 执行，
原始输入、日志和提交轨迹重审报告
`verification/out/rvv-memory-gap-audit-20260923-01.json` 为 4/4 PASS。
与前述两例合并后，严格同镜像报告
`verification/out/rvv-activity-current-image-6cases-20260923-01.json`
接受 6/6 例、一个完整 VCS 镜像组，合法 SEW/LMUL/policy 为 88/88，
访存模式为 7/7；补缺的 strided、indexed、segment、fault-first 分别有
14、22、18、8 条 DUT 退休指令。各缺口目前仅由一条定向用例命中，
这些退休活动与程序自检仍不是完整 RVV 功能交叉或 RTL 代码覆盖签收。
同一镜像另运行 `vindexed_vstart_edges`，程序自检与冻结输入/提交轨迹
重审均 PASS，证据分别在
`verification/out/rvv-indexed-restart-current-image-20260923-01/` 和
`verification/out/rvv-indexed-restart-audit-20260923-01.json`。
`verification/out/rvv-indexed-restart-vstart-activity-20260923-01.json`
把已提交的显式 `vstart` 写与下一条非配置 RVV 指令按 PC 对齐，观察到
6 个非零值 `63,63,7,11,17,68`，分别作用于 indexed load/store；
报告绑定同一 VCS 镜像指纹及 ELF/trace 哈希。它提供所测非零重启路径
的定向功能证据，不能代替非法 `vstart`、异常恢复及跨模式全矩阵测试。
为补足这部分边界，新增定向套件 `rvv-state-layout-gap`，只运行
`villegal_vstart_ops`、`vwiden_overlap_edges`、`vnclip_edges` 三个已有
自检程序，复用当前 4 MiB/QBS+AKV VCS 镜像，在
`verification/out/rvv-state-layout-gap-current-image-20260923-01/`
执行。`verification/out/rvv-state-layout-gap-audit-20260923-01.json`
对冻结输入与提交轨迹重审后为 3/3 PASS；严格同镜像活动报告
`verification/out/rvv-activity-current-image-9cases-20260923-01.json`
接受 9/9 例且只有一个完整 VCS 镜像组。新重算报告
`verification/out/rvv-state-layout-gap-exception-activity-20260923-01.json`
统计三例共 126 条退休 RVV 指令；非法 `vstart` 一例的八种操作产生
8 次 CVXIF 异常响应，程序逐例自检 `mcause=2` 与 `vstart=1`；这八条
非法操作并未退休，不能从退休指令直方图寻找它们。Widening 与
narrowing 两例分别退休 64 与 61 条 RVV 指令，均无异常响应。
该计数仅证明所测接口异常活动，异常原因由程序自检限定；它不是逐条
Spike 异常比较，也不构成完整 RTL 代码覆盖闭合。
同一镜像另复用 `vpolicy_masked_edges`，独立结果目录
`verification/out/rvv-masked-policy-current-image-20260923-01/` 的程序
自检为 PASS，冻结输入与提交轨迹重审见
`verification/out/rvv-masked-policy-current-image-audit-20260923-01.json`
（1/1 PASS）。活动重算报告
`verification/out/rvv-masked-policy-current-image-activity-20260923-01.json`
观察到 36 条退休 RVV 指令，四种 policy 下各有非配置业务指令。
更新后的严格同镜像报告
`verification/out/rvv-activity-current-image-10cases-20260923-01.json`
接受 10/10 例、一个完整镜像组；合法 SEW/LMUL/policy 活动仍为
88/88，四种 policy 现在各至少由两例观察到。分数 LMUL 与
strided/indexed/segment/fault-first 等仍主要由单个定向程序支撑；
88/88 是已退休配置活动，不是每种指令族、掩码、异常组合的功能闭合。
同一镜像进一步运行 `vunit_vstart_edges`、`vwhole_vstart_edges`，并重测
`vindexed_vstart_edges`；三例的程序自检和冻结输入审计见
`verification/out/rvv-vstart-memory-trio-20260923-01/audit.json`（3/3 PASS）。
该目录下三个 `*_vstart_activity.json` 从退休轨迹中分别关联 indexed、
unit-stride、whole-register 的 6、2、5 次已知非零 `vstart` 写入与后续
非配置向量指令，镜像组件指纹相同。新增两例后的严格同镜像报告
`verification/out/rvv-activity-current-image-12cases-20260923-01.json`
接受 12/12 例、一个镜像组，合法 SEW/LMUL/policy 为 88/88，访存
模式为 7/7；其中 strided、indexed、segment、fault-first 与分数 LMUL
仍为单例活动，不能据此宣称相应功能交叉或 RTL 代码覆盖已闭合。
同一镜像上的 arithmetic 随机 seed 67 另有完整严格差分：
`verification/out/rvv-arithmetic-current-image-seed67-audit-20260923-01.json`
为 1/1 PASS，2467 条非 trap 提交完整匹配，1040 个向量目的请求比较
PASS。实际可与 Spike 已定义值比较 11584 字节，另有 129205 字节因
参考值不可观察而跳过；898 个请求没有可比较的已定义字节，不能把
此例表述成全 VRF 逐位一致。退休活动重算见
`verification/out/rvv-arithmetic-current-image-seed67-activity-20260923-01.json`，
共 1122 条向量类指令。加入该例后的严格同镜像矩阵
`verification/out/rvv-activity-current-image-13cases-20260923-01.json`
接受 13/13 例，合法配置活动 88/88、访存模式 7/7；四种非规则访存
模式仍各只有一个定向用例支撑。为提高已定义向量字节的独立检查比例，
另启动当前镜像的短流逐指令检查点任务；未完成前不计入本报告。
为把配置活动与具体受检指令区分，`dynamic_coverage.py` 现额外记录
`retired_mnemonic_type_policy` 和 `retired_masked_mnemonic_type_policy`。
对原 `vpolicy_type_matrix` PASS 用例的冻结 ELF、提交轨迹和输入清单离线
重审见 `verification/out/rvv-policy-functional-activity-20260923-01.json`：
88 个合法 SEW/LMUL/policy 组合各有两次带 `v0.t` 的 `vadd.vv` 退休，
总计 176 次，未解析配置为零。程序源码对两轮执行后的已定义元素逐个
比对，原始 VCS 日志为 PASSED。因此可将它作为**带掩码 `vadd.vv`
已定义元素**在这 88 个配置组合上的定向自检证据；agnostic 元素、
其他指令族、逐条独立 Spike 状态比较及 RTL 代码覆盖均未由此闭合。
同镜像严格门禁的报告
`verification/out/rvv-activity-current-image-2cases-provenance-20260923-01.json`
记录 67 个 VCS 镜像组件和单一指纹；本次 2/2 用例的镜像路径与组件
哈希一致，但仍保留上述随机运行缺少原始镜像清单的证据边界。
严格门禁可显式从冻结原始轨迹重算，而不修改旧的 `result.json` 或
`summary.json`：

```bash
PYTHONPATH=verification python3 verification/verify.py audit \
  --run verification/out/sldu-fix-load-store-seeds53-55-20260923-01 \
  --require-trace --require-vector --require-full-match \
  --recompute-terminal-tohost \
  --output verification/out/rvv-load-store-seeds53-55-strict-reaudit-20260923-01.json
```

该报告为 `PASS`、3/3 cases；每例内嵌 ELF、Spike 命令与可执行文件、
VCS 启动文件及动态库、原始轨迹的 SHA-256。此选项仅用于完整匹配审计，
默认审计仍读取历史比较结果，不会静默改变旧报告。
同三条原始 commit trace 的动态活动报告位于
`verification/out/rvv-load-store-seeds53-55-retired-coverage-20260923-01.json`；
其逐例 commit-trace SHA-256 与上述严格审计相同。实际退休 4469 条
向量类指令（含 50 条配置、230 条访存），其中 1521 条带 `v0.t`；
访存已观察到 unit-stride、strided、indexed、segment、mask、
whole-register 和 fault-first。该脚本读取未覆盖写的历史 `result.json`，
因此逐例仍标 `PREFIX`；完整正确性由独立严格审计报告证明，不能把
活动报告自身称为完整比较。三例的静态可识别 policy 均为 `tu/mu`，
`ta/ma` 等 policy 与更多 SEW/LMUL 组合仍待独立激励和动态闭合。

原安装文件保持不变；宿主机通过 `LD_LIBRARY_PATH` 优先加载用户准备的
隔离补丁库。完整 Ara 的 `rvv:vadd` 仪表化仿真 PASS（174 秒），编译和
运行 VDB 均存在。包含五项指标的第一次 URG 汇总在 `line.verilog.shape.xml`
处发生 `URG-LTFF`/段错误，日志在
`verification/out/code-coverage-vadd-20260923-01/urg.launcher.log`。
随后一次明确选择 `branch+cond+fsm+tgl` 的运行成功，原始 HTML/XML
诊断报告保留于
`verification/out/code-coverage-vadd-20260923-01/urg-no-line-diagnostic/`；
`session.xml` 记录了工具版本、VDB 路径和完整命令。该单一 `vadd` 用例的
`ara_tb` 总计条件 37.91%、toggle 14.22%、FSM 5.86%、branch 38.33%，
但分母包含 testbench、依赖及未专门筛选的层级，**不是 DUT 覆盖率**。
尝试 `-show summary 4 -format both` 复现时又在 `cond.verilog.shape.xml`
处崩溃，退出码 255。当前有一份可供定位未覆盖点的诊断报告，但没有
稳定的完整五项指标报告，不可签收或据此做 waiver。后续须先在同源
VDB 上稳定复现并限定 DUT 层级，再汇总多个 PASS 用例，审查未覆盖点。

宿主机命令形态如下，不修改 VCS 安装目录，也不在 EDA 容器中运行：

```bash
V=/home/wangwy/software/synopsys/install/vcs/V-2023.12-SP1
P=/home/wangwy/patch/urg_isolated_V-2023.12-SP1_dATrByZI/active_candidate
LD_LIBRARY_PATH="$P:$V/linux64/lib" "$V/linux64/bin/urg1" -full64 \
  -metric branch+cond+fsm+tgl -dir <compile.vdb> <case.vdb> -report <new-report-dir>
```

`verify.py run --code-coverage` 已将 VCS 覆盖采集设为显式选项：编译使用 `line+cond+fsm+tgl+branch`，每个并发 case 写自己的 `code.vdb`；默认仿真不增加开销。独立 UVM smoke 验证了工具选项和 VDB 结构，但还没有完整 Ara 代码覆盖报告。VCS 数据库存在只表示采样发生，**不表示覆盖达标**。签收还需用 URG 合并同源设计的 VDB，限定 DUT 实例，生成逐模块百分比和未覆盖点清单，做版本哈希绑定与 waiver 审核。现有 `audit --require-coverage` 只检查随机激励的语义覆盖报告，不能用于替代 RTL 代码覆盖签收。
完整 Ara 的五个 `.shape.xml` 文件均通过 gzip 校验与 XML 语法解析；
这只排除了明显的压缩流截断和 XML 语法损坏，不能排除数据库语义错误
或 URG 解析器问题，也不能把偶发成功的报告视为稳定覆盖率签收。
同一 VDB 的独立 `-strict -metric line -format text` 诊断保存在
`verification/out/urg-line-strict-20260923-01.log`，仍于 line shape
装载阶段报 `URG-LTFF` 和 segmentation fault，未生成任何报告文件。
该次 `urg1` 的 systemd 退出码却为 0；因此覆盖率门禁不得仅依据进程
退出码判 PASS，必须同时拒绝错误日志、要求 `session.xml` 和全部请求指标
的可解析报告，并确认 DUT 层级与运行 VDB 对齐。
`python3 -m ara_verify.urg_report --report <urg-report> --log <urg-log>
--compile-vdb <compile.vdb> --test-vdb <case.vdb>
--metrics line,cond,fsm,tgl,branch --output <audit.json>` 检查致命日志、
报告结构、请求指标与 VDB 路径；DUT 层级仍需另行审核。
在上述单指标失败记录上已返回 `INVALID` 与非零退出码。其
`REPORT_VALID` 只表示报告结构与原始 VDB 对齐，不表示 DUT 覆盖率达标。

首次完整 Ara 仪表化 `linux_vector_context` 在默认 300 秒预算下超时，
`verification/out/code-coverage-rvv-context-20260923-02/` 虽生成编译和
运行 VDB，但该用例未 PASS，数据不能用于签收。较短的真实 DUT
`rvv:vadd` 在独立目录通过并生成 VDB，证明完整 Ara 的 VCS 采集链路
可用；上述单次 URG 诊断报告不代表目标覆盖率达成。
`~/Makefile` 中的 2016 EDA 容器可启动 URG L-2016.06，但它读取上述
VCS V-2023.12-SP1 的小型 VDB 时，在 `fsm.verilog.shape.xml` 装载处
报 `UCAPI-FLF`、`UCAPI-DESCORR` 和 `URG-LTF`，未生成可用报告。
这是跨版本数据库兼容性失败，不能据此判定设计覆盖率，也不能将
2016 URG 的运行状态当作 2023 VDB 的覆盖签收。
进一步用同一容器的 VCS L-2016.06 对
`verification/coverage/verilator_coverage_smoke.sv` 做最小编译：带 `-cm` 和不带
`-cm` 均在语义检查后段于工具自身 `get_proc_stat()` 发生 SIGSEGV；
容器默认用户与工作区 UID 运行结果相同。因未生成 `simv` 或 VDB，
目前无法在该环境完成“2016 VCS 采集、2016 URG 汇总”的同版本链路；
这不是 Ara RTL 的编译或覆盖率结论。

Linux 源头探针运行已结束，摘要为 `LINUX_BOOT_FAILED`；封存证据在
`verification/out/soc-linux-cache-source-20260923-02/`。最后一次相关
DDR AR 于周期 17,290,221 请求 `0x801007c0`，随后四个 R beat
从周期 17,290,222 起含 X，其中首 beat 为 `xxxxxx0070616d2d`。
周期 17,290,286 的首个被选中 D-cache X 与这个首 beat 一致：
`hit=0010`、`refill=0`、`wbuf_be=00`，说明当次 load 从 cache
数据阵列取到了先前的未知 DDR 字节，既不是当次 refill 旁路，
也不是 write-buffer 覆盖产生的。封存 `memory.hex` 对 DTB
仅预装 1770 (`0x6ea`) 字节，从 `0x80100000` 到 `0x801006e9`；
`0x801007c0` 不在预装 DTB 范围内。外部 `axi_sim_mem` 默认对
未初始化字节返回 X，且本 testbench 设置了 `WarnUninitialized(0)`。
这解释了 X 的直接来源，但**尚不能判断**内核读取该地址是否合法、
运行期间是否应由软件完整初始化，以及是否有更早的地址/长度损坏。
下一步只针对该地址范围核查 DDR 写入及 byte strobe、DTB 运行时
长度/位置、触发读取的内核指令；在证明原因前不把整个 DDR 强制清零，
也不修改 CVA6/cache RTL 或屏蔽末端 SRAM fatal。

后续独立运行 `verification/out/soc-linux-dtb-tail-20260923-03/` 已结束，
摘要仍为 `LINUX_BOOT_FAILED`。其周期 6,543,627 的探针表明运行时 FDT 头部的
`totalsize` 由预装的 `0x6ea` 增至 `0xb0a`；在 DDR AR 到达
`0x801007c0` 时，`0x7c0..0x7c4` 五个字节已经写入，组成
`-map\0`，其后字节尚未在稀疏 DDR 模型中建立。先前 D-cache 探针的
`req_addr=0x7c5`、`req_be=0x20`、`req_size=0` 表明确有一次对
空洞首字节的单字节读取。冻结 Linux Image 在相应 PC 附近的反汇编
是逐字节 `lbu`、查表、左移的 CRC 循环，与 Linux `crc32_be` 实现
一致；Linux 的 `early_init_dt_verify` 和后期 FDT 校验都会按
`fdt_totalsize` 扫描 blob。此次探针在周期 17,290,221 再次测得
`present=0000001f`、`contents=xxxxxx0070616d2d`，17,290,286 的
`CACHE_SELECTED_X` 精确选择 `0x7c5`，四个周期后索引变为 X，
下一周期 SRAM fatal。该链条证明稀疏 DRAM 模型的 X 直接导致此次
仿真停止；并不证明系统其余部分正确。独立对照实验仅为 FDT 所在
4 KiB 页的空闲区提供确定的初值，其他 DDR 地址继续保留 X，
且不修改 CVA6/cache RTL。该运行在周期 19,050,000 仍处于
`LINUX_RUNNING`，已越过旧运行的 17,290,221 周期 DDR 故障点；
这只证明原故障没有在相同位置重现。后续同一运行推进至约
25,250,000 周期，未见新 fatal。期间进度采样 PC 反复位于
`0xffffffff801cc1xx` 与 `0xffffffff80505xxx`；封存 Linux Image
对应偏移的反汇编显示后者存在比较回调和分段迭代，而非此前的
FDT CRC 逐字节路径。后续逐字节比对确认两段热点分别对应当前
Linux 源中的 `jump_label_swap` 和 `__sort_r`；这说明重复 PC 有
启动期排序路径的解释，仍不能单凭 PC 判定整个启动会正常完成。
该次运行最终在 10800 秒墙钟上限处停止，摘要为
`LINUX_BOOT_FAILED`、`simulation.timeout=true`；末次进度为
44,250,000 周期、24,127,298 次提交，PC 在
`0xffffffff80b870d8..0xffffffff80b87154` 范围反复出现。
对该运行封存的精确 Linux Image 用仓库 RISC-V objdump 反汇编可见：
`0xffffffff80b87074` 开始是 `memset` 形态的字节填充例程，
`0xffffffff80b870d4..80b87150` 展开为 32 条连续 8 字节 store，
`0xffffffff80b87154` 将目的地址推进 256 字节，随后按末端地址
回跳。因此重复 PC 是正在执行填充循环的证据，本身不是死循环
证据；但未捕获目的地址和末端地址，仍无法断定该填充范围是否合理
以及何时结束。UART 已打印 Linux 6.19.6 启动信息，未见用户态
成功标记。
封存 DTB 的 `/memory@80000000/reg` 声明从 `0x80000000` 起的
2 GiB RAM，initramfs 位于 `0x88000000`；大范围内存初始化可能
影响 VCS 启动耗时，但本次没有捕获 `memset` 的目的地址和长度，
不能据此把超时全部归因于内存容量。若做较小内存的仿真对照，
必须同时重建外部 DTB 与 OpenSBI 内嵌 DTB，并保持内核和 initramfs
装载区域在声明范围内，原 2 GiB 启动包仍作为独立基线保留。
为检验启动耗时是否主要受 2 GiB 内存几何影响，另用
`prepare_linux_bundle.py --sim-ram-mib 256` 在
`verification/out/fpga-linux-sim256-20260923-01/` 生成仿真专用包；
其内存范围为 `0x80000000..0x90000000`，Image 与 initramfs 仍在
原地址，外部/内嵌 DTB 哈希一致。当前工作树的候选包重建因审核过的
`cva6-local-fixes.patch` 固定哈希不匹配而停止，未放宽该门禁；改由
`derive_sim_linux_candidate.py` 从此前完整封存的候选包仅替换四个
Linux 工件并重新封存，得到
`verification/out/soc-sim256-derived-20260923-01/package`。
派生包的全部 RTL 文件哈希与基底相同，seal 和 Linux 装载几何
检查均通过。独立的 VCS 运行目录为
`verification/out/soc-linux-sim256-20260923-01/`。这路任务在确认
编译成功及早期执行到 350,000 周期后主动停止：原 2 GiB 运行
3 小时仅到 44,250,000 周期，而需要区分的填充路径出现在后段，
按当前 VCS 吞吐率，预设 2 小时上限很可能在到达判定点前耗尽。
因此该短运行**不**提供缩小内存后启动加速或通过的证据；保留
编译产物和早期日志，但不把外部停止后的 `summary.json` 中间状态
解释为完成。后续先制定可在预定时间内观察到的判定点，不能再
仅靠延长看门狗重复全程仿真。即使 256 MiB 启动通过，也只证明
该仿真几何下的系统行为，不能代替 2 GiB 部署几何的签收。
为量化诊断探针的仿真开销，使用上述已编译的 256 MiB 镜像和同一
`memory.hex` 分别做 90 秒短测：带 `CACHE_TAG_PROBE`/`DTB_TAIL_PROBE`
推进至 126437 周期，不带两项探针推进至 192137 周期，早期窗口
为 `1.52x`。两次均由外部限时停止，只是吞吐测量，不是 Linux
启动结果；不能假定中后期也有相同比值。基于此在独立目录
`verification/out/soc-linux-sim256-fast-20260923-01/` 进行了无额外探针的
封存包 VCS 运行，上限 7200 秒。该运行最终因墙钟超时停止，末次进度
约 3210 万周期、19695434 次提交，UART 已输出 Linux 启动信息，
未到 init/用户态成功标记，不能算 Linux 通过。冻结 Image 的两段热点
指令字节分别对应 Linux 源码中的 `__sort_r` 和 `jump_label_swap`；
`jump_label_init()` 会调用排序，冻结构建配置启用了 `CONFIG_JUMP_LABEL`。
当前 SDK `vmlinux` 的 jump table 约有 8995 个 entry，但它与冻结 Image
并非同一镜像，所以该数只用于估计排序规模。重复 PC 有明确的软件
启动期路径解释；尚不能据此断言关闭 jump label 后会在预算内到达用户态。
为缩短验证反馈，`verification/linux/build_fast_kernel.sh` 可在独立 Kbuild
输出目录生成**验证专用** Image，仅关闭 `CONFIG_JUMP_LABEL`，保留 RVV、
MMU、64 位与现有 SMP 配置，不改原 SDK 内核或已有启动包。先用
`run_userspace_qemu.py --kernel <Image>` 的 180 秒用户态检查确认软件
可启动，再将该 Image 与匹配 DTB/OpenSBI/initramfs 封存，按短程进度
预算做 VCS 对照；部署内核的最终验证仍须另行完成。未通过 QEMU 或
未证实缩短启动时，不应进行新的多小时 VCS 全启动。
该独立 Image 的配置差异为 `JUMP_LABEL=y→n` 及依赖它的自测项关闭；
已有 Linux 用户态 payload 在 QEMU 7.754 秒内通过全部要求的标记。
这不是 RTL Linux 通过。SoC runner 的 `--reuse-compiled-from` 已用相同
256 MiB 封存包做短程自检：逐项核对编译相关输入后，在新目录复制已有
VCS image，并推进至 10 万周期，超过 5 万周期诊断里程碑后主动停止，
状态为 `LINUX_MILESTONE_REACHED`。之后仅变更 Linux 载荷时可复用
该编译镜像，避免再次编译 RTL；真正的新内核 VCS 启动速度尚未测量。
新 Image 已与原用户态 initramfs、匹配的 256 MiB DTB 和 OpenSBI 固件
封存于 `verification/out/fpga-linux-fast-jl-off-20260923-01/`，派生 SoC 包
为 `verification/out/soc-fast-jl-off-derived-20260923-01/package/`；
派生报告确认 RTL 文件哈希未变。该包在
`verification/out/soc-linux-fast-jl-off-20260923-01/` 通过编译输入逐项
比对复用旧 VCS image。独立 VCS 运行使用 `--run-timeout 7200
--linux-fail-fast --linux-no-progress-timeout 600`。它在约 25 分钟内推进到
615 万 SoC 周期，日志尚无 Linux kernel/用户态通过标记。由于下述
封存 RTL 与当前源码不一致，这条旧候选运行已主动停止，以免继续消耗
两小时预算；保留 `sim/console.log`，但 `summary.json` 中的 `RUNNING`
是停止前状态，不是最终通过状态。该运行只证明旧候选的启动进度，
不能以周期增长或 QEMU 结果替代当前 RTL 的用户态签收。
本次复用镜像是冻结的旧 SoC 候选，不是当前工作树的最终 RTL：逐文件
比较 `hardware/src/*.sv` 的对应包内副本，有 3 个差异，分别在
`sldu/sldu.sv`、`vlsu/qbs/qbs_engine.sv` 和
`vlsu/akv/akv_engine.sv`。其中 SLDU 读指针修复是功能差异；
QBS/AKV 两处为包内 FPGA 专用写法与当前通用写法的差别。
所以该运行即使到达用户态，也只可用于 Linux 载荷/启动耗时诊断，
不得作为当前 RTL 的系统签收。最终签收需要从当前 RTL 重新封存
SoC 候选、编译 VCS，并重新执行相同的用户态检查。
为推进当前 Ara RTL 的 VCS SoC 签收，新增
`verification/fpga/derive_current_rtl_candidate.py`，在核对旧包封印和完整
`hardware/src` 文件清单后，只允许替换 `sldu.sv`、`qbs_engine.sv`、
`akv_engine.sv` 三处差异；额外源码漂移会阻止派生。独立新包位于
`verification/out/soc-current-rtl-fast-jl-off-20260923-01/package/`，
`derivation.json` 记录旧/新哈希并重新封印。它保留 256 MiB 验证专用
Linux 载荷，且只用于 VCS，不是 FPGA 包或 Linux 通过证据。
`verification/out/soc-current-rtl-fast-compile-20260923-01/` 的独立 VCS
编译已通过，技术模型检查 PASS，编译耗时 167.713 秒，`simv` 哈希为
`8968805ee7d1b522b45471afcf61f0b0ef496de5d88641c0e6b622359eea6b67`。
同一镜像随后仅推进至 100000 周期诊断里程碑，耗时 60.406 秒，状态
`LINUX_MILESTONE_REACHED`；它不是内核启动或用户态通过。
同一已核对的编译镜像已复制到独立目录
`verification/out/soc-current-rtl-fast-linux-20260923-01/`，并执行完整
Linux VCS 回归，带 7200 秒墙钟上限、明确失败标记早停和 600 秒无进展
早停。运行在 7200 秒时超时，最终推进到 3175 万 SoC 周期，状态为
`LINUX_BOOT_FAILED`，`simulation.timeout=true`；UART 没有 init/用户态
标记，因此这不是 Linux 签收，也不能当成已发现 RTL 功能错误。只有最终
`summary.json` 的用户态检查通过才可计作当前 RTL 的 VCS Linux 签收。
运行中约 2715 万周期的重复 PC `0xffffffff80b97ac0` 至
`0xffffffff80b97b34` 已用与封存 Image SHA-256 完全相同的
`verification/out/linux-fast-kernel-20260923-02/build/vmlinux` 定位到
内核 `memset` 的展开存储循环。此时总提交持续增加，但 UART 尚无
init/用户态标记；该 PC 片段不能单独证明死循环或 Linux 已通过，
不据此更改现有回归的看门狗或判定口径。

本次与封存 Image 相同的 QEMU 诊断，在 `__memset` 中断下发现
`sparse_init -> __memblock_alloc_or_panic -> memset` 的 16 MiB 清零调用。
这说明内核早期初始化包含大块线性写入，与 VCS 中持续提交且 PC 重复的
现象相符；QEMU 的调用栈不能直接证明 VCS 中每次重复 PC 的调用者。
在取得 VCS 寄存器/地址探针或更快的系统级验证方式之前，不再对同一
冻结 RTL 和 Linux 载荷盲目重复完整 7200 秒运行。

为缩短日常验证耗时，按以下顺序推进，前级失败即停止后级：

1. QBS 输入或参考实现变更时，先执行
   `make -C verification host-quick-check CAPTURED_QBS_OUT=out/<新目录>`；
   这一步不用 VCS，先排除捕获文件损坏、格式不符和数值错误。
2. 再执行 `make -C verification rtl-quick-check FAST_GATE_SIMV=... FAST_GATE_OUT=...`，
   使用当前 RTL 已编译的 VCS image 并为每次运行创建独立输出目录。
   它并行检查标准 RVV、QBS、AKV 的代表点，不能代替覆盖闭合。
3. 只运行改动所触及的严格 Spike 差分、UVM interface/协议和 Linux
   关键代码提取测试；通过后再扩大随机种子。先使用已有日志和离线审核，
   不为重新生成同一证据重复仿真。
4. SoC/Linux 改动先复用已核对 image 做最早相关周期的
   `--linux-cycle-milestone` 诊断，限制在 10--15 分钟的吞吐测量内。
   从这段实测估计达到所需阶段的墙钟时间；超过任务预算时只保留
   诊断结果，不启动整段 Linux。里程碑到达不是启动通过。
5. 源码和载荷冻结且预算可行时才启动一次完整 Linux，保留
   `--linux-fail-fast`、`--linux-no-progress-timeout` 和绝对墙钟上限。
   对同一包已知的最低目标周期，可额外使用 `--linux-min-cycle-target`
   提前识别预算不足；超时和预算不足均不计作通过。

这次 256 MiB、JUMP_LABEL-off 镜像的 7200 秒实测平均约 4410
SoC 周期/秒，到 3175 万周期仍未出现用户态标记。该数字只用于当前
封存配置的资源预算，不能外推为其他内核、内存配置或 RTL 的速度。

验证提速候选可用 `build_fast_kernel.sh --memory-model flat` 复现；它仅在
原 JUMP_LABEL-off 配置上将 sparse memory 改为 FLATMEM，其他内核
配置差异由 Kconfig 依赖自动生成，不改变 Ara RTL。独立 Image 位于
`verification/out/linux-flatmem-kernel-20260923-01/build/arch/riscv/boot/Image`。
同一用户态 initramfs 在 256 MiB QEMU 中通过全部检查标记，报告为
`verification/out/linux-flatmem-qemu-256m-20260923-01/userspace_check.json`；
这只证明该内核配置可运行，不证明 Cheshire SoC 或硬件正确。新 SoC 包
`verification/out/soc-current-rtl-flatmem-256m-20260923-01/package` 的 RTL
文件未变，复用旧 VCS 镜像的 SHA-256 为
`8968805ee7d1b522b45471afcf61f0b0ef496de5d88641c0e6b622359eea6b67`。
同镜像短运行在 60.407 秒到达 10 万周期，状态
`LINUX_MILESTONE_REACHED`，不是用户态通过；只有后续经过 `sparse_init`
对应阶段且实际出现用户态标记，才能确认 VCS Linux 签收及提速效果。
独立完整运行 `ara-dsa-flatmem-linux-20260923.service` 已结束，
输出为 `verification/out/soc-current-rtl-flatmem-full-20260923-01/`。
`summary.json` 记录 `LINUX_BOOT_FAILED`、`timeout=true`，墙钟 9000 秒；
末条进度为 4760 万 SoC 周期，尚无 init/用户态通过标记。这是预算耗尽，
不是已定位的 RTL 功能首错，不能签收 Linux。冻结同一 RTL、Image 和
内存配置下不要再直接重跑完整启动；先使用已有日志确定阶段与阻塞条件，
并测量任何新候选是否足以改变剩余周期预算。
末段进度的 PC 分散在 Linux `trace_event_raw_init`、页释放代码和
OpenSBI 入口附近，提交计数持续增长；仅凭这些采样既不能判定死循环，
也不能宣称启动即将完成。该 FLATMEM 配置实测平均约 5290 SoC 周期/秒，
因此下一次 Linux 候选应先用 QEMU 验证载荷，再用短里程碑测量本机
吞吐与阶段变化，不能重复消耗 9000 秒等待同一出口。

为避免再次把整段墙钟预算耗在已知到不了的判定点，SoC runner 现在支持
可选的 `--linux-min-cycle-target N --budget-check-after 900`。`N` 必须是
**同一封存包、内存几何和启动路径**已有证据支持的最低判定周期；不能把
2 GiB 运行的 4425 万周期直接用作 256 MiB 运行的下界。runner 在
900 秒后按实际 `[SOC_PROGRESS]` 周期/秒估计，额外给 1.5 倍速度余量；
即便如此仍不能在 `--run-timeout` 内达到 `N` 时，提前结束并报告
`LINUX_BUDGET_INCOMPLETE`，保留日志、已达周期和目标周期。这是预算
不足而非 RTL 功能失败，也不是 Linux 通过。未指定该选项时运行行为
不变。日常 RTL 修改优先复用
同一 VCS image 运行短 bare-metal/UVM/差分门禁；完整 Linux 只在
源码与载荷冻结后跑一次，并先用 10–15 分钟实测吞吐判断预算是否现实。
可选 `--linux-fail-fast --linux-no-progress-timeout 900` 在明确的 Linux
失败标记出现时结束，或在已观察到周期进展后连续 900 秒无进展时结束；
分别报告 `LINUX_EARLY_FAILURE`、`LINUX_STALLED`，均不计作通过。
这两项和周期预算早停只对新启动的 `--mode linux` 运行生效。已有
`COMPILED_NOT_RUN` 目录可用 `--run-only` 复用镜像，避免重复综合；
早停或超时的运行目录不能原地重启，需另建目录保存证据。
针对定位特定阶段的新运行，可选 `--linux-cycle-milestone N --linux-fail-fast`；
观察到进度日志中周期达到 `N` 即停止，结果明确标记为
`LINUX_MILESTONE_REACHED`，运行器返回非零，不作为 Linux 启动或用户态签收。
`N` 应按待验证故障的最早相关周期选择，而不是一律跑到最终启动；失败标记
优先于里程碑。此选项只改变新启动的诊断运行，不能作用于已经在跑的任务。
例如先对短 bare-metal/UVM/严格 Spike 差分做日常门禁，仅在 SoC 相关改动时
复用已编译镜像进行带阶段目标的 Linux 诊断；完整 Linux 仍在候选冻结后单独运行。
前 7 条 `CACHE_DATA_X` 与原 2 GiB 运行按周期、PC、数据和请求地址
逐条相同；缩小内存声明未改变这段早期行为。原运行的 8 条
`CACHE_DATA_X` 均为整字探针，记录的 `be=f0` 只选高 32 位，
而 X 位于低 32 位；按所记录的 byte-enable，它们不是被选中
字节含 X 的证据。完整日志没有更严格的 `CACHE_SELECTED_X` 记录。
另有 10 次 CVA6 D-cache `a_invalid_read_data` 告警，其断言检查
整字归约结果而非选中字节，单凭该告警不能证明架构可见数据有 X；
但也未逐次确认对应 byte-enable，不能直接忽略。尚无证据证明这些
早期告警与末段 PC 行为有因果关系。这路 Linux 测试没有逐条 Spike/QEMU 对比，
因此既不能报告“对比错误”，也不能以未报告 mismatch 签收启动。
复核证据位于 `verification/out/soc-linux-fdt-page-20260923-02/`。

功能覆盖需另外定义：RVV 指令族×SEW/LMUL×mask/tail×`vstart`，访存模式×跨页/异常，QBS 格式/profile×shape/tail×fallback，AKV view/lifetime×更新/切换，CVXIF/AXI 的背压×flush/reset×ID 重用。交叉组合按规格剔除非法项，不能简单要求所有笛卡尔积命中。每个覆盖点对应至少一个真实通过的检查；仅生成过指令、仅出现 valid、或检查器没有报错都不计为功能闭合。

已有 10 个 PASS case 的离线审计见
`verification/out/rvv-activity-writeback-matrix-10cases-20260923-02.json`：
计划的 SEW、LMUL、policy pair 和访存模式活动 bin 分别为 4/4、7/7、
4/4、7/7；其中 7 个 case 带完整的向量目的寄存器写回比对记录，
有至少一位参与比较的写回字节位置为 1,482,214 个，另有 3,016,242
个字节位置因未知值或不可观察范围跳过；前者不一定整字节的 8 位均被比较。
其余 3 个 case 不能据此声称有逐写回比对。审计器还按
ELF 的 PC/指令字核对每条写回记录，并按 mnemonic 保存比较和跳过量。
这些数量不是“正确率”：跳过的字节没有被证明正确，vector store 的
目标内存也不在这组写回统计内；活动矩阵的状态仍为
旧报告的顶层状态为 `ACTIVITY_OBSERVED`，只反映单轴命中，不能当作
RVV 功能或 RTL 代码覆盖签收。
同一批原始证据重新按每条退休指令的 SEW×LMUL×policy 交叉计数，见
`verification/out/rvv-activity-cross-matrix-10cases-20260923-02.json`。
单轴虽各自有活动，112 个笛卡尔积诊断组合仅 25 个实际命中，其中
22 个是 `tu/mu`，另外三种 policy 各仅命中一个组合；交叉项明确为
`INCOMPLETE`。进一步对照 `ara_dispatcher.sv` 的 `LMUL >= SEW/ELEN`
检查，当前 ELEN=64 时有 24 个组合不受支持；112 只是未过滤的笛卡尔积，
不是应闭合的合法目标。
按修正后的状态口径重新审计同一批冻结输入，得到
`verification/out/rvv-activity-cross-matrix-10cases-20260923-03.json`：
10 个 case 全被接受，单轴状态仍是 `ACTIVITY_OBSERVED`，但顶层状态
仍是 `INCOMPLETE`。该报告按旧的 112 格配置生成，仅作历史对照。
新 `vpolicy_type_matrix` 定向程序使用两遍活动长度，分别检查尾部
undisturbed 和 mask undisturbed 语义，覆盖全部受支持 SEW/LMUL/policy
组合；同一现有 VCS 镜像运行 140.52 秒、程序自检 PASS。包含原 10 个
PASS case 的新审计文件为
`verification/out/rvv-activity-legal-cross-matrix-11cases-20260923-01.json`：
11 个 case 均接受，合法交叉活动 88/88，24 个非法组合单列排除。
这只闭合**该四维配置上的退休活动与此定向算术自检**，不代表每个
指令族×配置的功能闭合；其余功能交叉仍需 Spike/独立参考、定向
访存/异常检查和代码覆盖证据，不能由随机指令数量推断。
同一 `vpolicy_type_matrix.c` 源码另经 riscv-tests 的 Spike CRT 独立编译，
使用 `spike --isa=rv64gcv_zvl1024b` 在 30 秒上限内报告 `PASSED`；
冻结输出在 `verification/out/vpolicy-type-matrix-spike-20260923-01/spike.log`。
VCS 与 Spike ELF 的运行时及指令布局不同，因此这是一项双实现的
程序自检，不是同一 ELF 的逐指令差分。源码 SHA256 为
`dd85f6768363c57210c7f346acea6615d80a4ffcb52c2f12b5c84f2ac21cd759`；
VCS 输入 ELF 和 Spike ELF 的 SHA256 分别为
`7973e1e2bb942caec0a51c860d4e2ab6a9c942e93df8004c621c7b3d32a60714`、
`de9d0e82d19d14d1b18d8d2892e4345f0ab6a5c1665d821288fed22119a4a433`。

### 当前 RTL 的 Linux 首个内核标记

`verification/out/soc-linux-version-probe-20260923-01/` 使用当前 RTL 的
封存 SoC 包、256 MiB FLATMEM/lean 内核及 quiet OpenSBI，复用核对过的
VCS 镜像。`summary.json` 的终态为 `LINUX_UART_MILESTONE_REACHED`：
7,250,000 SoC 周期、约 1876 秒，UART 恰好一次输出 `Linux version
6.19.6`。`milestone_audit.json` 由 `check_soc_milestone.py` 重新核对
691 条封存输入、VCS launcher/动态库、运行驱动、命令和 UART 原始日志，
结果 `PASS`。同一 Image 的 SHA-256 为
`1933f6f65e17fbc0de40b80d0bc58388d91da40989c7afa94d6e8d6d8d4a9e29`；
独立 QEMU 用户态检查也为 `PASS`。这些证据只证明当前 RTL 已进入内核
打印阶段，**不**证明 init、用户态或完整 Linux 启动。

完整 VCS 启动另在
`verification/out/soc-linux-full-quiet-noprobe-20260924-01/` 执行，
使用同一封存包，但不启用额外 cache 探针，设 10800 秒运行上限、
显式失败早停及无进展早停。任务使用
`verification/tools/soc-venv/bin/python`；系统 Python 缺少 `pyelftools`，
首次准备命令因此在创建运行目录前退出，未进入仿真。该新任务的
`summary.json` 取得完整用户态标记并经 `check_soc_linux.py` 独立审计
之前，不计作 Linux 通过。

上述不带 cache 探针的完整运行在启动早期被 `a_invalid_read_data`
标记早停，`summary.json` 为 `LINUX_EARLY_FAILURE`，不是内核崩溃。
同一封存输入的带探针里程碑运行在相同时间点记录的是整字包含 X，
但没有 `CACHE_SELECTED_X`；整字断言本身不足以证明选中读取字节有 X。
因此不把无探针运行改判为 PASS，也不简单屏蔽该标记。新目录
`verification/out/soc-linux-full-quiet-cacheprobe-20260924-01/` 经
`--reuse-compiled-from` 核对并复制已编译 VCS 镜像；该选项只产生
`COMPILED_NOT_RUN`。随后显式使用 `--run-only --cache-tag-probe`
启动带选中字节检查的完整 Linux 运行，设 14400 秒绝对上限和
失败/无进展早停，独立保存原始日志。只有最终用户态标记及独立审计
通过，才可认定 Linux 签收。

将后来独立通过并审计的随机 seed 69、70、71、72 加入原 14 点后，
`verification/out/rvv-activity-current-image-18cases-20260924-01.json`
由冻结退休轨迹重算：18 个用例均接受、0 排除，完整 VCS 镜像指纹
分组为 1。SEW、LMUL、policy pair、访存模式的单轴活动分别为
4/4、7/7、4/4、7/7，合法 SEW×LMUL×policy 交叉仍为 88/88。
有完整向量写回比对证据的用例从 3 增至 5，至少一位参与比较的
字节位置从 138,785 增至 168,854；另有 8,285,752 个字节位置
因未知值或不可观察范围跳过。报告状态仍为 `ACTIVITY_OBSERVED`，
不能将 88/88 活动或上述字节数表述为所有 RVV 指令的功能通过率。
