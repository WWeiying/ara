# UVM 接入边界

UVM 是可复用的 SystemVerilog 验证框架，不是单独的黄金模型。对本项目，UVM 适合承载以下内容：

- CVXIF request/response transaction agent；
- vector backend alloc/write/done transaction monitor；
- VLSU demand/prefetch、AXI AR/R/AW/W/B monitor；
- reset、flush、backpressure、queue-full 场景的 virtual sequence；
- transaction-level protocol scoreboard 和 functional coverage collector。

不应把以下内容硬塞进 UVM 而省略现有证据链：

- Spike 的 RVV 架构参考语义；
- 向量寄存器、`vl/vtype/vstart/vcsr` 和 store memory 的逐条签名；
- QBS/AKV 的软件契约和 GGML 数值参考模型；
- Linux 的启动、虚拟内存、上下文切换和用户态长稳态。

## 接入规则

1. 先稳定 transaction 字段和 monitor 采样点，再编写 agent；
2. agent 只观察 valid/ready 成功握手，不把 speculative valid 当作提交；
3. 每个 transaction 必须携带 cycle、序号/VID、指令、shape/EEW、地址或 descriptor 版本；
4. protocol scoreboard 检查接口时序，Spike/Python scoreboard 检查架构结果，两者职责不能混淆；
5. UVM regression 的 seed、config、compile command 和 coverage database 必须进入统一 `run.json`；
6. 若 UVM 与现有 VCS 测试结果冲突，先比较采样定义，再定位 DUT，不允许修改参考结果迁就 UVM。

当前仓库的架构级检查主线仍是既有 VCS testbench、`ara_commit_monitor.sv`、Spike trace/vector comparison 和 Python runner。此目录另有可运行的 CVXIF transaction monitor/scoreboard 自检：

```bash
make -C verification uvm-smoke
```

该 smoke 验证 CVXIF/VID 的握手与 ID 生命周期，以及 Ara AXI 的
AR/R burst 长度、AW/W/B 配对、同 ID 排队、同周期握手、复位取消和
孤立响应/错误 `last` 检查；
不连接 Ara DUT，不能作为 RTL 功能通过。真实 DUT 接入使用下面的独立目标；架构级
通过仍须另行比较同一 ELF 的 commit/vector trace。

真实 DUT 的被动接入另用 `ara_cvxif_dut_bind.sv`，不修改 CVA6/Ara 数据通路。
它在实际 `ara_system.acc_req/acc_resp` 上采样 request/response 握手，
在同一时钟沿处理响应旧 ID 并重用 ID、立即响应，以及复位取消在途事务。
已有 `ara_acc_contract_monitor.sv` 同时运行，`uvm_dut.py` 要求两者的请求、
响应数一致且软件自检、UVM check/report phase、错误数均满足门禁。真实 DUT
目标还用 `ARA_UVM_TRACE_LIMIT` 和 `ARA_CONTRACT_TRACE_LIMIT` 捕获握手事件，
逐项对照事件次序、相对周期、请求/响应 ID、指令和异常位；任何一方截断时
事件数与最终计数不符，结果为 FAIL。该对照用于发现接线或采样错误，
仍不是独立架构参考模型。

```bash
make -C verification real-ara-uvm-smoke \
  REAL_UVM_OUT="$PWD/verification/out/real-ara-uvm-<run-id>"
```

编译输出目录必须是新的；每个 case 的 `work/` 目录也只能运行一次，运行前复制
ELF 到 `work/input.elf`。复用同一 simv 跑另一条已构建的 ELF 时使用
`real-ara-uvm-run REAL_UVM_OUT=... REAL_UVM_TESTCASE=...`；默认超时 300 秒，
真实模型 ELF 超过默认 1 MiB L2 时，编译镜像需传
`REAL_UVM_SIM_L2_MB=16`，与程序链接时的 `sim_l2_mb` 一致；这一参数属于
VCS 镜像，不能仅在运行时更改。
QBS/AKV-v2 测试还须在编译时显式传
`REAL_UVM_QBS=1 REAL_UVM_AKV_V2=1`，并在启动真实数据前核对
`sim/simulator.conf` 同时记录 `qbs=1`、`akv_v2=1` 及正确的 L2 容量；
缺少这些特性时，RVV 回退用例通过也不能作为专用机制通过的证据。
当前 RTL 的协议覆盖还使用单独的 `REAL_UVM_AXI_DELAY=1` 验证镜像，
仅在该镜像中插入 AXI 延迟以实际触发 AR/AW/W 反压；普通仿真镜像不变。
构建后，在同一个 `FAST_GATE_SIMV` 上运行 `rtl-quick-check` 得到
RVV/QBS/AKV 三个用例，再用 `run_real_dut_case.sh` 对同一个
`rv64uv-ara-vfredmax_boundary` ELF 分别运行 `read`、`write` 复位用例。
第六个用例为 `apps/bin/akv_column_coverage_smoke`：它复用
`akv_portability_smoke` 的数值自检与 native kernel，只执行前两轮，
用较短时间观察 AKV column 指令的分配和完成；它不取代完整的
`akv_portability_smoke`。六份 `uvm_result.json` 必须交给
`python3 -m ara_verify.uvm_coverage` 重新核验，并要求同一镜像的
24/24 个计划 bin 全部命中，随后以 `run_signoff.py --stage uvm`
独立签收。当前实例位于
`verification/out/rvv-waw-div-uvm-delay-image-20260924-01/matrix/`，
对应门禁为 `verification/out/signoff-uvm-waw-div-delay-20260924-01/`。
较长程序需显式设置 `REAL_UVM_TIMEOUT`；若握手或背压活动超过默认的
100000 条 trace 容量，还需提高 `REAL_UVM_TRACE_LIMIT`，不得接受截断证据。
每个 case 的 `uvm_result.json` 保存 UVM/contract 计数、标准化事件哈希及日志、
ELF、`simv` 和 `simv.daidir` 共享库的哈希。该接入验证 CVXIF/VID 生命周期及
Ara master 的 AXI AR/R/AW/W/B 握手配平；`uvm_dut.py --require-axi` 要求
实际非零的完整读 burst，带向量 store 的点再用 `--require-axi-write` 要求
非零且完整的写事务，两侧在结束时都必须零在途。它尚未检查读写数据数值、
请求与外部内存的端到端顺序或 MMU 翻译。
CVXIF 响应可以早于向量运算完成，
因此 `responses=requests` **不是**后端运算完成或 RVV 架构正确性的证明。
Make target 还会拒绝 VCS 的非零 UVM error/fatal summary 或零 transaction 流量；对其他
UVM/RTL stage，必须把相同的 PASS、traffic-count 和 `UVM_ERROR : 0`、`UVM_FATAL : 0`
作为 `run_stage.py --marker` 传入，不能只检查 simulator exit code。

2026-09-22 的真实 DUT UVM 检查中，`rv64uv-ara-vfredmax_boundary`、
`rv64uv-ara-sv39_state_prereq`、`rv64uv-ara-linux_vector_context` 和
`rv64uv-ara-vfredmax` 分别记录 27/27、33/33、350/350、296/296 次 UVM
请求/响应，均与独立 contract monitor 计数一致、零 UVM error/fatal，程序自检
通过。纯标量 `rv64uv-ara-stvec_readback` 程序自检虽通过，但因 CVXIF 零流量被本门禁
拒绝；不能把它计入 CVXIF UVM 覆盖。这些是接口集成证据，不是完整 UVM、标准 RVV
或 Linux signoff。新的逐事件门禁已在 `rv64uv-ara-vfredmax_boundary` 与
`rv64uv-ara-linux_vector_context` 上分别实测 27、350 个事件一致；
先前仅对比总数的运行结果不应写成逐事件通过。

后端 VID 的被动监测也已接入同一真实 DUT UVM 环境：采样 sequencer 的
`verify_vinsn_alloc`、分配 VID 和 `verify_vinsn_done`，检查重复分配、孤立完成、
复位取消和运行结束时排空。对每次分配/完成记录周期与 VID，并与独立的
`ara_commit_monitor` 向量 trace 逐事件比较；它验证生命周期和监测接线，
不能代替 Spike 的向量结果对比。UVM smoke 自检覆盖完成后同周期复用及
复位取消；故意注入孤立完成和重复分配分别触发 `VID/ORPHAN_DONE`、
`VID/DUP_ALLOC`。VCS 对 UVM_ERROR 仍返回 0，因此必须检查日志中的严重度。

2026-09-22 的新真实 DUT 运行保存在
`verification/out/real-ara-uvm-vid-20260923-01/`：
`rv64uv-ara-vfredmax_boundary` 的 CVXIF 27/27、VID 8/8、最大在飞 1，
UVM 与向量 trace 的 16 个 VID 事件一致；`rv64uv-ara-linux_vector_context`
的 CVXIF 350/350、VID 240/240、最大在飞 4，480 个 VID 事件一致。
两项均为零 UVM error/fatal，并有程序自检通过。完整后端事务结果、AXI
协议、QBS/AKV 异常及跨复位多事务覆盖仍未签收。

Ara AXI 读通道 monitor 直接采样 `ara_system.ara_axi_req/ara_axi_resp`，
即 Ara master 进入 invalidate filter 之前的握手。scoreboard 按 AXI ID
排队保存每次 AR 的 `len+1` 个预期 R beat，核对每个握手与 `last`，
允许合法的同 ID 多笔在途及同周期 AR/R。独立 smoke 的合法场景记录
6 次 AR、7 个 R beat、5 次完成和 1 次复位取消；故意注入的孤立 R 和
提前 `last` 分别触发 `AXI/ORPHAN_R`、`AXI/RLAST`。VCS 对 UVM_ERROR
仍可能返回 0，真实 DUT 的 Python 审计因此要求 AXI 摘要、零 UVM 错误、
非零完整读流量及零在途读。`rv64uv-ara-vfredmax_boundary` 在
`verification/out/real-ara-uvm-axi-20260923-01/` 实测 4 次 AR、6 个 R beat、
4 次完成、零在途，原 CVXIF/VID 与程序自检也通过。这是读协议证据，
不是写通道、数据内容、MMU 正确性或 Linux 的签收。

写通道由 AW 接受顺序、按 `last` 切分的 W burst 和按 ID 返回的 B 响应
分别记账；允许 W 先于 AW 到达，也允许同 ID 多笔在途。独立 smoke
记录 6 次 AW、6 个 W beat、5 个完成写 burst、5 次 B 和 1 次复位取消。
单独注入孤立 B 和错误 W burst 长度分别触发 `AXI/ORPHAN_B` 与
`AXI/WLAST`；其余读通道错误未随注入同时出现。此项检查的是 AXI
事务协议，不是 store 数据正确性。真实 DUT 的
`rv64uv-ara-linux_vector_context` 回归位于
`verification/out/real-ara-uvm-axi-rw-20260923-01/`：30 次 AR、1536 个 R beat、
30 次完整读；228 次 AW、3072 个 W beat、228 次匹配写 burst 和 228 次 B，
读写结束均零在途，程序自检、CVXIF 350/350 和 VID 240/240 均通过。
`uvm_result.json` 保存本次镜像、ELF 和日志哈希。此结果证明接口事务
配平与生命期检查在实际 DUT store 流量下可用，不证明读写数据、地址
顺序或 Linux 启动正确。

五个 AXI 通道还逐周期检查 `valid && !ready` 期间的完整 packed payload
与 `valid` 保持，复位取消尚未握手的保持义务；`AXI/STALL_COUNT` 分别记录
AR/R/AW/W/B 背压周期和相邻周期保持检查次数。独立 smoke 的 AW 背压
两周期、两次保持检查通过；故意改动背压中的 AW 载荷触发 `AXI/HOLD`。
另在 `verification/out/uvm-axi-hold-20260923-02/` 分别注入 AR、R、W、B
背压期间的载荷变化，每个独立负例仅触发相应通道的一次 `AXI/HOLD`；
VCS 进程退出码仍为 0，门禁必须检查 UVM 错误摘要。
`make -C verification uvm-smoke` 已固定运行五通道负例，并校验通道名、
恰好一次 UVM error 和零 fatal；新门禁运行见
`verification/out/uvm-axi-hold-regression-20260923-01/`。
真实 DUT 只有发生非零背压时，才可把对应通道计作实际背压覆盖；零计数
仅表示检查器已接入，不能证明该场景。1024-bit 扩展槽保存完整 Ara AXI
载荷；若未来增宽 AXI 结构超过该槽，必须同步增宽接口并重新编译验证。

复位中止覆盖使用验证镜像的显式 `+ARA_UVM_RESET_ON_AXI=read|write`：
testbench 在 Ara AXI 的真实 AR/AW 接受沿之后施加一次复位，随后让程序
重新启动。普通运行不接收该 plusarg，仍禁止中途复位。独立目录重放命令为：

```bash
verification/uvm/run_real_dut_case.sh <uvm-simv> <built-elf> <testcase> <new-output-dir> read
verification/uvm/run_real_dut_case.sh <uvm-simv> <built-elf> <testcase> <new-output-dir> write
```

读复位默认在第 1 笔 AR 接受后触发。设置
`ARA_UVM_RESET_READ_INDEX=2` 可选择第 2 笔；同时设置
`ARA_VCS_CODE_COVERAGE=1` 可在同一次运行生成 `code.vdb`。选择的请求序号
必须再由单项 FSM 覆盖验证具体所处阶段；见
`verification/coverage/PHASE_RESET_GAP31_20260928.md`。

QBS/AKV 状态边界的复位可设置 `ARA_UVM_RESET_STATE_TARGET` 并在命令末尾使用
`state`，例如 `qbs_validate` 或 `akv_replay_read`。该触发在目标状态仍有效的
下降沿拉复位；程序重启后的自检、UVM 审计和逐项 FSM VDB 均须通过。
18 项同镜像结果及未闭合范围见
`verification/coverage/STATE_EDGE_GAP32_20260928.md`。

专用审计要求 trigger/释放标记、UVM 只观察到一次复位、相应 AXI
`aborted` 非零、全程 CVXIF 事件与独立 contract trace 一致，并用复位后的
UVM 事件单独对照 contract monitor 最后一个 reset epoch 的计数。
独立向量 trace 记录复位边界；VID 事件按 reset epoch 分开，逐项核对
ID、顺序及该 epoch 内的相对周期，因为 trace 的周期计数在复位后归零。
`uvm_coverage.py` 只有在这类审计通过后才命中读/写复位 bin。
复位中止检查不是架构结果检查；重启后程序自检、向量结果和内存签名
仍要独立通过。当前镜像中读/写专用用例已分别 PASS：读事务 5 次 AR、
4 次完成、1 次复位取消；写事务 229 次 AW、228 次完成、1 次复位取消，
两次均无遗留在途请求。对应原始日志、向量 trace 和哈希审计分别位于
`verification/out/uvm-reset-read-20260923-03/` 与
`verification/out/uvm-reset-write-20260923-03/`。与同镜像两个普通用例
一起审计后，功能覆盖为 9/14；剩余 AR/R/AW/B 背压和 CVXIF 同周期
ID 复用未闭合，不得据此宣布 UVM 签收。

后续定向背压镜像通过 `REAL_UVM_AXI_DELAY=1` 编译，使用既有
`axi_delayer` 在 Ara AXI 边界延迟 AR/AW/W 输入侧 3 拍，R/B
返回侧直通；该宏只用于验证，普通 RTL/综合路径不变。返回侧也延迟
的诊断版本会消除原本可见的 R 背压，不用于最终覆盖汇总。真实 Qwen
数据 `decode_attn_q_qbs_ctx2` 在 QBS+AKV 输入侧延迟镜像下自检
PASS，并观察到 AR/R/AW/W 分别 765/228/545/2640 个背压周期，
4178 次载荷保持检查零错误。对应证据在
`verification/out/qbs-uvm-input-delay-case-20260923-01/`。

复位激励现在于已接受 AR/AW 后的下降沿拉低复位。旧 `#1` 与 TB
的 1 ns 时钟周期重合，曾让 UVM 与 contract monitor 对边界握手
采样不同；该失败保留于 `verification/out/uvm-delay-reset-write-20260923-01/`，
不计入覆盖。修正后的同一 QBS 启用、AKV 未启用镜像下，真实 Qwen 数据点和
标准 RVV 读/写复位点的三项哈希重审均 PASS；
`verification/out/uvm-coverage-qbs-input-delay-20260923-01.json`
按旧定义命中 12/14。静态复核发现余下两个旧 bin 与当前 Ara
边界契约不符：VSTU 在 `BVALID` 时立即置 `BREADY`，QBS/AKV 仅在
普通 VLSU 排空后接管 AXI；dispatcher 保持 CVXIF 请求直到其
响应同周期被接受。旧 bin 的零计数仍保留用于诊断，不视作已覆盖。
新口径将其替换为 `axi_b_always_ready` 和 `cvxif_atomic_req_resp`，
要求非零真实流量、零违例，并在真实 DUT bind 中逐周期断言。
覆盖审计要求新镜像的 `[DUT_BOUNDARY_CONTRACT]` 标记；旧镜像
不能按新口径签收。QBS+AKV 双启用、输入侧延迟的新镜像已在
`verification/out/real-ara-uvm-contract-20260923-01/` 编译完成。
真实 QBS context 点、读复位点和写复位点在该同一镜像下均 PASS，
`verification/out/uvm-coverage-contract-20260923-01.json` 重新审计为
14/14 bin、零错误、一个闭合镜像组。这里闭合的是该 14 项 UVM
功能覆盖清单，不代替 AXI 数据内容、完整 ISA、代码覆盖或 Linux 签收。
另在 4 MiB L2 的同源 QBS+AKV 镜像中，真实 QBS+AKV 联合程序
和标准 RVV 读、写复位用例均 PASS。联合程序记录 3532 次 CVXIF
请求/响应、3155 次 VID 分配/完成、278 次完整 AXI 读和 191 次
完整 AXI 写；读、写复位各中止 1 笔对应事务。三次运行的哈希重审
见 `verification/out/uvm-coverage-contract-combined-4m-20260923-02.json`：
同一镜像 14/14 bin、零错误。这个结果同样不证明 AXI 数据内容、
全部 RVV 指令、代码覆盖或 Linux 启动正确。
新镜像的 `rv64uv-ara-linux_vector_context` 结果位于
`verification/out/real-ara-uvm-axi-hold-20260923-01/`：W 通道实际出现
3 个背压周期，跨周期载荷保持检查执行 3 次，其他四个 AXI 通道的背压
计数为 0；原有 CVXIF、VID、AXI 读写计数和程序自检仍通过。

## 真实 Ara 接口监视器

`ara_acc_contract_monitor.sv` 通过 `bind ara_system` 观察实际的
`cva6_to_acc_t/acc_to_cva6_t`，只在显式加入 verification source 时编译。
它不修改 DUT、不进入综合，不改变普通仿真的文件列表。

| 检查对象 | 准确语义 |
| --- | --- |
| 请求保持 | 上一拍 `req_valid && !req_ready` 时，本拍 valid 不能撤销，`insn/rs1/rs2/frm/trans_id` 不得改变，包括最终握手的那拍 |
| 响应保持 | 背压期间保持 ID、异常有效位及有效的结果或异常信息；无效异常字段不参与比较 |
| ID 生命周期 | 检查重复分配、无请求的响应；同周期同 ID 区分“新请求立即应答”和“旧请求完成后 ID 复用” |
| X 检查 | 有效握手的控制和 ID 不得未知；不对所有未使用数据字段作无条件 X 检查 |
| 摘要 | 本次复位后的请求、响应、异常数、MMU 请求有效周期；结束时在途 ID、背压状态必须清零；协议错误累计跨复位保留 |

`store_pending/acc_cons_en/inval_ready` 是独立状态，不属于请求 spill register
内保持的指令。`load_complete/store_complete/fflags_valid/inval_valid` 也不能
当成响应 payload 的保持字段。这些信号虽然接入监视器，但本监视器**没有**验证
访存完成顺序、异常内容的架构正确性、MMU 翻译正确性或 invalidation 协议。
`mmu_request_cycles` 是请求有效周期数，不是 MMU 事务数。

接口响应也不等同于向量执行完成；后者仍需 backend VID、result writeback 和
commit/signature 检查。不得把这里的 `outstanding=0` 写成“所有向量执行排空”。

先验证检查器自身，再检查 DUT：

```bash
make -C verification contract-selftest
make -C verification real-ara-contract-smoke
```

第一条编译一个小型 monitor testbench，执行合法场景和故意注入的错误：重复/孤立
ID、请求/响应撤销、payload 和 `frm` 改变、异常字段改变、X、出错后复位以及未完成
请求。只有检查器正确接受合法场景、拒绝错误场景，selftest 才通过。反例日志出现
`Error` 是预期证据，不应与真实 DUT 失败混为一谈。

第二条在 `verification/out/real-ara-contract-compile/` 独立编译真实 Ara，构建
`apps/bin/rv64uv-ara-vfredmax_boundary` ELF 后执行受限 smoke。ELF 是由已跟踪源码
构建的产物，并非已入库的固定二进制。模拟器返回码、测试成功标记和严格日志检查
都必须通过：摘要恰好一条、非零且等量的请求响应、零错误、无未结束事务/背压。
即使摘要零错误，日志中存在断言错误也会拒绝，不能仅靠 grep PASS。

复用已编译的 DUT 或只重新检查日志，不必重新编译：

```bash
make -C verification real-ara-contract-run
make -C verification real-ara-contract-check
```

`REAL_CONTRACT_OUT` 可指定独立目录；`REAL_CONTRACT_APP` 和
`REAL_CONTRACT_TESTCASE` 选择已构建的其他短 ELF，日志按 testcase 保存。
同一目录不要并发运行多个 simv（hart trace 等输出名仍由现有 testbench 决定）。

需要诊断时可给 simv 加 `+ARA_CONTRACT_TRACE_LIMIT=256`，只记录至多 256 个
有活动的周期，默认关闭。采样为上升沿、DUT 非阻塞赋值更新前；记录 cycle、
insn、双方 valid/ready/fire、ID、异常位、在途位图、背压状态和错误向量。
这不是完整流水线探针，具体 bug 仍需按假设补齐相关 queue、VID、flush 等内部信号。

此 smoke 不代替完整 RVV 差分、随机覆盖、Linux 或 VCU118 签核。

## CVA6 内部生命周期探针

`cva6_acc_lifecycle_probe.sv` 通过显式 `extra_sources` 绑定真实 `acc_dispatcher`，
不进入普通 RTL 或综合文件列表。它与上面的协议检查器互补，记录 issue、队首及
push/pop、双提交口、pending/ready 当前和下一状态、flush、spill 两侧握手、
load/store 记账及响应。它是观察探针，不是架构结果 scoreboard。

每行采用同一 clocking block 的 `input #1step` 快照，避免混合时钟沿前后信号。
当前 issue PC 与寄存后的请求数据分开记录；事务关联须结合 reset epoch、周期、
握手和 ID 生命周期，不能把 ID 当成永不复用的序号，也不能把响应当成执行完成。

首次 `acc_valid_d` 后开始采样，默认最多 65536 行。
`+CVA6_ACC_LIFECYCLE_CYCLES=<1..65536>` 可缩短窗口，
`+CVA6_ACC_LIFECYCLE_FILE=<basename>` 可指定当前仿真目录内的文件名。
已有文件使用数字后缀保留。结束记录中的 `truncated=1` 表示捕获不完整，不能
将截断日志用于证明窗口外无错误；诊断晚发故障时应在运行前按假设调整触发设计。

2026-09-22 的六点新基线 VCS 回归实际编译并使用了该探针。`vfwcvt/vfncvt`
内部捕获达到上限，但自检程序和外部接口检查正常完成；其余四点内部捕获完整。
详细结果及覆盖边界见 `../RVV1_DIFFERENTIAL_VALIDATION.md` 第 102.3 节。

## Sv39 故障与重启探针

`sv39_prereq_probe.sv` 与 `cva6_state_prereq_probe.sv` 配合，在实际 CVA6/Ara
层次绑定 MMU、共享翻译路由、PTW、addrgen、VLSU、sequencer、dispatcher；
加上 CSR/FPU 共九路有界日志。只观察信号，不改变 DUT 或给故障处理程序代写结果。
具体假设、采样时刻、观察窗口与判别条件见
[sv39_probe_plan.md](../cva6/sv39_probe_plan.md)。

运行时逐项指定 `--probe-kind csr --probe-kind fpu --probe-kind mmu
--probe-kind mmu_route --probe-kind ptw --probe-kind addrgen --probe-kind vlsu
--probe-kind seq --probe-kind dispatcher`，会强制检查相应捕获。该参数不自动编译
探针，仍需通过 `verify_extra_sources` 指定冻结的源文件。

`probe_capture.json` 记录每路日志的 SHA-256、记录数、采样边界及截断状态。
缺失字段、重复日志、缺 END、活动丢失、跨模块相同周期的时间/reset 冲突均判为失败；
`audit` 重新读取原始日志，而不是只接受旧 JSON 中的 PASS。通过这一检查只代表
采集完整性，不代替故障事件覆盖、数据正确性检查或 Linux 启动验证。

## 真实 DUT 功能覆盖审计

`uvm_result.json` 是单点的检查结果；多个点的覆盖闭合用
`python3 -m ara_verify.uvm_coverage --audit <uvm_result.json> --output <report.json>`
审计。可重复传入 `--audit`。审计只接受真实 DUT 的 PASS 记录，重新核对
日志、ELF、独立向量 trace 和完整 VCS 镜像哈希，然后从原始日志重建
CVXIF、VID、AXI 读写与五通道背压计数。B 通道在当前设计中为
always-ready，不把人为制造 B 背压当作覆盖目标；CVXIF 接受与响应
为同周期原子握手，不把跨周期旧事务 ID 复用当作覆盖目标。这两项
不适用项在 `excluded_unreachable_bins` 中明示，并由新镜像中的
实时断言约束。未命中场景列在 `missing_bins`，
输出状态保持 `INCOMPLETE` 且命令退出码为 1。独立 smoke 和只生成过激励
而没有通过真实 DUT 检查的记录，不能计入这些场景。

含边界断言的新真实 DUT 镜像已有六条通过的用例：普通 smoke、
QBS Q3_K/Q5_K、读/写复位及 QBS+AKV 组合。
`verification/out/uvm-coverage-fire-closed-20260923-01.json` 从原始
证据重审得到同一镜像 24/24 个可达接口 bin，零审计错误。
`run_signoff.py --stage uvm` 可重复指定 `--uvm-audit <uvm_result.json>`
形成机器门禁；缺少审计输入或缺少覆盖 bin 均不返回 PASS。
通过的门禁和单用例负例分别保存在
`verification/out/uvm-signoff-20260923-01/` 与
`verification/out/uvm-signoff-negative-20260923-01/`。这不替代
RVV 架构正确性、RTL 代码覆盖或 Linux 系统验证。

## 异常 payload 探针

`trap_prereq_probe.sv` 绑定 `id_stage` 和 `csr_regfile`，新增 `trap_decode`、
`trap_ctrl` 两种日志，与上述九路共用 pre-edge 采样和完整性门禁。前者连接原始/
展开指令、PC、译码异常与 issue q/d；后者连接提交异常、权限/委托、M/S CSR q/d
和返回，使一轮运行可区分译码错误、传播混配、错误委托以及软件重复处理。
两路都需要通过 `verify_extra_sources` 编入镜像，再分别用 `--probe-kind` 要求
采集。纯标量 `trap-prereq` 用例不要求非零 ACC 流量；相邻 RVV 回归仍保持要求。
完整矩阵、窗口和 oracle 见 [trap_probe_plan.md](../cva6/trap_probe_plan.md)。

## 推荐迁移次序

```text
CVXIF monitor
  -> vector backend transaction monitor
  -> VLSU/AXI monitor
  -> protocol assertions and scoreboard
  -> constrained virtual sequences
  -> reuse in RVV differential and QBS/AKV campaigns
```

迁移过程中保留现有 CSV/Spike 证据，避免一次性重写验证环境造成新的不可比结果。
