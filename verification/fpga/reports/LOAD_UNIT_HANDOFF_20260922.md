# Load Unit FPGA 导出差异审核交接记录

日期：2026-09-22。

状态：静态只读审核已完成；当前目标尚未执行本报告所列实验，未签核。

后续说明：本文保留静态审核时的范围。之后已完成真实bypass/load/WT控制器加
受控翻译边界的15组局部实测，见
[LOAD_CONTRACT_MEASURED_20260922.md](../../cva6/LOAD_CONTRACT_MEASURED_20260922.md)。
本文提出的真实MMU/PTW/scoreboard完整组合实验仍未执行，不追改为整机通过。

## 1. 范围与证据边界

本报告归档此前的只读审核，不引入 RTL 修复，也不执行实验。审核所在 worktree 为 `/home/wangwy/openproject/ara_dsa_verification`，比较对象如下：

| 角色 | 相对 worktree 根目录的路径 | 审核快照 SHA-256 |
| --- | --- | --- |
| deps 基线 | `hardware/deps/cva6/core/load_unit.sv` | `2c2b71a94f8dbdceda0e46b2c8ca23e1a2e3d2d3621bbd39cf87c87ee591a72c` |
| FPGA 导出 | `hardware/fpga/ara_dsa_vcu118/rtl/cva6/core/load_unit.sv` | `042db6cbcfdba16f6810a49de010eeb52105829e444a348df5fc7ec89f3ac7dd` |

归档前只读复核上述哈希，与此前审核快照一致。下文行号对应此快照，不保证后续版本行号不变。

已完整阅读两份 `load_unit.sv`，并沿相关路径检查 `load_store_unit.sv`、`lsu_bypass.sv`、MMU/PTW、PMP、store buffer、WT cache 及 scoreboard 的请求、依赖、接受、返回、异常和 flush 语义。相关配置与源文件选择也已静态核对。

- 当前 FPGA 导出使用 MMU、WT cache、两项 load buffer、一级 load 返回流水。
- 源文件选择依据为 `hardware/fpga/ara_dsa_vcu118/scripts/sources.tcl`；配置基础为 `cv64a6_imafdcv_sv39_config_pkg.sv`，SoC 还通过 Cheshire 的 `gen_cva6_cfg` 设置非幂等区域。
- `NI` 在本文特指 `CVA6Cfg.NonIdemPotenceEn`，不是 cache 的 `stall_i`，也不是运行时某条指令是否落入非幂等区域。
- **`MmuPresent=0 && NonIdemPotenceEn=0` 的丢完成是静态可构造的缺陷，当前 FPGA 配置不触发。** “MMU 参数存在但运行时地址翻译关闭”也不等于 `MmuPresent=0`。
- **当前目标尚未测。保留已有导出适配不代表通过回归、完成 SoC 验证或获得签核。**

审核及本次归档均未运行 EDA、仿真、综合或板卡操作，未修改 RTL、依赖或参数。本次唯一写入文件为本报告。

## 2. 结论与问题分级

### 2.1 P1：跨配置丢完成，静态可构造，当前配置不触发

FPGA 新增等待态分支在 `ex_i.valid && !data_rvalid` 时会产生 `pop_ld_o=1`，但异常结果输出仍受 `MmuPresent || NonIdemPotenceEn` 限制。两参数皆为 0 时，可以弹出队头而不产生完成。

一个无需假设异常握手的静态反例为：

| 周期 | 条件与行为 | 结果 |
| --- | --- | --- |
| C0 | `MmuPresent=0`、`NonIdemPotenceEn=0`；有效未对齐 load；无 page-offset 冲突；cache 不 grant | `IDLE` 发请求后进入 `WAIT_GNT`；no-MMU 路径寄存未对齐异常 |
| C1 | `WAIT_GNT` 收到该异常；没有旧 `data_rvalid` | FPGA 分支撤下 `data_req`、产生 pop、转 `IDLE`，但配置门控使 `valid_o=0` |
| C2 及以后 | 原队头已被移除，且本次没有 cache 接受 | 原 load 没有后续完成来源 |

这是 RTL 逻辑直接支持的跨配置缺陷，不是本次仿真复现结果，也不能表述为当前 FPGA 已出现的故障。当前目标有 MMU，该参数组合不成立。

### 2.2 P2：绕过地址冲突的异常完成能力不完整

`WAIT_PAGE_OFFSET` 不保持翻译请求，也不锁存异常。若异常与旧 load 的 `data_rvalid` 同拍出现，新增分支选择旧返回、不 pop；下一拍异常可以消失，队头仍要等待地址冲突解除。

已确认的是“异常早退机会可能丢失”，不是“请求被丢弃”或“新 SoC 必然死锁”。队头没有被弹出，冲突解除后仍可能正常重新翻译并报告异常。冲突是否最终解除、是否产生不可接受的延迟，需要系统条件和实验判别。这也不是相对 deps 已确认的新架构回归。

### 2.3 当前配置的安全性结论

在已检查的当前 MMU/WT cache/bypass 契约下，未发现这两个 hunk 新增的确定组合环、丢请求或双完成反例。但没有执行当前目标实验、组合环工具检查或回归，因此此结论仅限静态审核。

建议将两个 hunk 作为**成对、目标配置受限、待验证的 FPGA 导出适配**保留，不用 deps 文件盲目覆盖。不能直接将其升级为所有 CVA6 配置通用的异常修复，也不能因此将新完整 SoC 标为已签核。

## 3. 逐 hunk 安全性分析

默认 `diff -u` 有两个文本 hunk：`@@ -286,35 +286,53 @@` 和 `@@ -446,7 +464,9 @@`。第一个 hunk 内含两个状态修改，以下分别分析。行号默认指 FPGA 导出版本。

### 3.1 Hunk 1a：WAIT_PAGE_OFFSET 异常优先

位置：`load_unit.sv:288`。

新增行为：优先检查 `ex_i.valid`；没有 `data_rvalid` 时转 `IDLE` 并 pop，有返回时保持状态；没有异常时保留原来的等待 page-offset 冲突解除逻辑。

安全性依据：

- 当前队头尚未向 cache 成功发出本次请求，异常直接完成不需要为本次请求发送 kill，也不需要等待 store 地址冲突解除。
- `ex && !data_rvalid` 的 pop 必须与异常输出同时发生，才能结束队头生命周期。
- `ex && data_rvalid` 时保持队头，让旧返回先占用结果口，避免异常覆盖已在途 load 的结果。
- 不发 cache 请求，因此不会绕过正常 load/store 内存排序而执行异常 load 的访存。

限制与证据：

- 本状态仍使用默认 `translation_req_o=0`，并未新增异常 pending 寄存器。
- `cva6_mmu.sv:521` 将 `misaligned_ex_n.valid` 限定为 `misaligned_ex_i.valid & lsu_req_i`；DTLB 命中异常依赖寄存的请求，PTW fault 也不是持续到 LSU 确认的握手。
- `cva6_ptw.sv:575`、`:583` 的错误传播状态随后进入 `LATENCY`，不能假设错误一直保持。

最小判别序列：C0 发翻译并遇地址冲突；C1 异常与旧返回同拍，未 pop；C2 异常消失而冲突仍在。此时保留了请求，没有保留异常，早退机会丢失。

结论：可条件保留，但不能宣称所有异常均能独立于 store-buffer 冲突完成。若产品要求这种活性保证，当前实现不足，需要后续证据驱动的设计处理；本报告不修改设计。

### 3.2 Hunk 1b：WAIT_GNT 异常优先

位置：`load_unit.sv:302`。

新增行为：保持 `translation_req_o=1`；异常时不再保持 `data_req`，没有旧返回时直接 pop 并回 `IDLE`；无异常时保留原 grant、DTLB 和 NI 分支。

组合依赖与握手判断：

- **`translation_req_o=1` 必须保持在异常判断之外。** 它不依赖 `ex_i`，因此本修改没有引入 `ex -> 撤翻译请求 -> ex` 的组合反馈。不能因想减少翻译活动而把该赋值移入 `else`。
- MMU 中存在请求参与异常判断的组合逻辑，例如 `canonical_addr_check`；不能笼统假设全部异常都完全由寄存器产生。
- 异常时 `data_req=0`，所以 `ldbuf_w=data_req & data_gnt=0`，不会分配本次 cache 尝试的 load-buffer slot。
- WT cache 的 `data_gnt` 是当拍接受，不是上一拍接受的延迟通知。`wt_dcache_ctrl.sv:141` 的 IDLE 接受路径及 READ 命中后的连续接受路径均检查当前请求。撤下尚未授权的请求本身不丢失已接受事务。
- 本状态没有本次尚待发送的 tag。若同一逻辑 load 此前经历 TLB/NI abort，在当前 WT 契约下，该尝试已走过 kill 应答；必须把被取消的 cache 尝试与逻辑指令分开计数。

返回竞争与活性：

- `ex && data_rvalid` 时不 pop、保持状态、继续发翻译请求。稳定的未对齐、DTLB 权限/PMP 异常可以再次出现。
- PTW 单拍错误没有在 load unit 内锁存，可能需要再次翻译，不能承诺在旧返回之后紧接着一拍就完成。
- 正常无异常路径的 grant、DTLB miss、`stall_ni` 检查不变，没有放宽合法 NI load 的提交时机或 store/write-buffer 约束。

结论：当前目标配置下可保留；跨配置 pop/完成门控问题见第 2.1 节。

### 3.3 Hunk 2：扩大异常结果输出的状态集合

位置：`load_unit.sv:467`，对应 deps 的异常输出判断 `load_unit.sv:449`。

新增行为：从只支持 `WAIT_TRANSLATION`，扩展为 `WAIT_PAGE_OFFSET`、`WAIT_GNT`、`WAIT_TRANSLATION`，仍要求 `!data_rvalid && ex_i.valid && valid_i` 以及配置门控。

安全性依据：

- cache 返回通过 buffer 中的 trans_id 完成；没有 cache 返回的等待态异常使用当前 `lsu_ctrl_i.trans_id`。两条输出路径互斥，不会在同拍覆盖旧返回。
- 等待态队头由 bypass 保持；pop 更新的是下一拍的队列状态，不组合改变当前队头。因此该路径没有新增 `pop -> 当前队头 -> ex -> pop` 反馈。
- 当前 MMU ACC 所有权切换还受 bypass 空条件约束，不能把一个有效等待队头任意视为随时失效或被换成另一所有者。此契约仍需在新 SoC 中保持。
- FSM 的提前 pop 没有同样的配置门控，导致第 2.1 节的跨配置缺陷。

**两个文本 hunk 必须成对处理：**

- 只保留 Hunk 1，会在新增等待态 pop 异常请求，却没有对应异常结果输出。
- 只保留 Hunk 2，会在原等待态未 pop、持续无 grant 时反复输出同一异常，存在重复完成风险。

结论：Hunk 2 不是可独立合入的输出增强，必须与 Hunk 1 一起保留和验证。

## 4. 未修改但必须共同理解的生命周期

### 4.1 接受、pop、完成不是同一事件

- cache 接受为 `data_req && data_gnt`，驱动 `ldbuf_w`。
- `pop_ld_o` 移除 LSU bypass 队头，可以发生在正常 load 接受时，也可以发生在无 cache 请求的异常完成时。
- `data_rvalid` 同时承担正常返回与 kill 应答，驱动 buffer 回收；它本身不等于架构完成。
- `valid_o` 是 load unit 的结果有效，之后还经过 load 返回流水和 scoreboard；最终架构可见性应在 commit/trap 层确认。

### 4.2 原有正常、异常与重试路径

- `IDLE/SEND_TAG` 仍可先 grant、分配 buffer、pop；下一拍翻译异常通过 `SEND_TAG` 的 kill 和 cache 应答完成。新增提前异常路径没有替换这条路径。
- TLB miss 路径仍是 grant、`ABORT_TRANSACTION`、kill 应答释放 slot、`WAIT_TRANSLATION` 再翻译。kill 应答不得计成额外指令完成。
- NI abort 仍先取消已经接受的 cache 尝试，再按原状态机重试；提前结束异常不等于允许正常 NI load 提前访存。
- 原 `WAIT_TRANSLATION` 遇 `ex && data_rvalid` 会转 `IDLE`，但不 pop，随后重新处理同一队头。它与新增等待态的保持原状态不同，不应仅凭重入状态或重复翻译就认定双完成。
- `SEND_TAG` 中的异常属于前一拍已接受请求，等待态提前异常属于仍在 bypass 的当前队头；探针必须区分这两种身份。

### 4.3 Flush 与 ID 重用

- `flush_i` 仅覆盖 load FSM 的下一状态为 `WAIT_FLUSH`，不保证当拍 pop 或 `valid_o` 为零。
- bypass 的 flush 优先清空队列；load buffer 标记 flushed，后续返回回收资源；`WAIT_FLUSH` 发送 kill/tag。
- `flush` 同拍若有新 buffer 写入，写入对该 slot 的 flushed 位有后续覆盖，必须连同下一拍 kill/返回抑制一起检查，不能只观察 flushed 位。
- 当前一级 load 返回流水可能把当拍结果延迟到 flush 后。`scoreboard.sv:198` 检查 issued，`:254` 的同拍 flush 清除优先。不能把 `flush && valid_o` 单独定义为错误。
- 正确判据是旧 epoch 的结果不被架构提交、也不污染重用 ID。新导出若改变返回流水深度、cache 应答契约或 ID 重用时机，需要重新审核，不能泛化当前判断。

## 5. 一次性实验组织方案（未执行）

目标是一次准备完整判别能力，复用同一批事务 trace 解释不同候选原因，而不是改变 RTL、参数或 timeout 后反复试跑。

1. 使用包含真实 MMU/PTW、WT cache 和 LSU bypass 的统一 directed harness，对 deps 与 FPGA 版本施加相同逻辑事务、内存内容及可控的仲裁/返回延迟。完成延迟允许不同，不要求两版本逐拍锁步。
2. 通过合法的 cache stall、仲裁与内存响应时序制造 backpressure；不要独立强制与 `data_req` 不一致的 grant，再把它误算为真实接受。
3. 用足够小且身份明确的 scalar load/store 序列覆盖下表，并包含 ACC/MMU 所有权交叉和 ID 重用。软件驱动时记录实际 PC/指令；接口级夹具也须赋予唯一事务序号。
4. 当前导出配置为主实验。MMU=0/NI=0、单项 buffer 属于预先列明的可移植性子配置，不能伪装成当前目标行为，也不是为追求通过而临时调参。
5. 事前确定每个用例的合法时序、可达性、内存最大延迟、预期完成/取消数量及窗口。所有用例采用同一套 probe schema；必要的配置子运行属于同一预先审查的 campaign，不声称所有参数组合可在一个实例内运行。
6. 本矩阵是最小判别实验，不替代后续代表性 SoC 正确性、性能及平台回归。任何需运行的工作均应另行安排，本次没有执行授权或执行结果。

### 5.1 用例矩阵

| 编号 | 用例组 | 激励与交叉条件 | 主要判别/验收条件 |
| --- | --- | --- | --- |
| C1 | 地址冲突 | 未对齐、DTLB 权限/PMP、PTW fault；异常拍旧返回有/无；冲突保持后解除 | 区分直接异常完成、异常脉冲消失、解除后重新翻译；队头不得无故消失；不能把早退未发生直接判为丢请求 |
| C2 | 等待 grant | cache 初始化/仲裁阻塞；异常拍 cache 可接受/不可接受；`stall_ni` 两值 | 在有效异常、无旧返回、无 flush 时，当前配置恰好一次 pop 和异常结果；该拍零新 cache 接受 |
| C3 | 返回竞争 | 正常旧返回、flushed 返回、kill 应答分别撞异常 | 正确回收旧 slot；异常不覆盖旧结果，不重复完成；区分结果口仲裁与 buffer 回收 |
| C4 | 原有接受/重试 | 首拍立即 grant；DTLB hit/miss；NI abort；`WAIT_TRANSLATION` fault 与返回碰撞 | tag/kill 和重试生命周期闭合；正常 NI 顺序不变；被取消尝试不算指令完成 |
| C5 | Flush 边界 | 异常前一拍、同拍、后一拍；交叉 grant/返回 | 队列正确清空，已接受尝试得到回收；内部 valid 脉冲允许出现，但不得污染新 epoch 或架构提交 |
| C6 | 连续事务/所有权 | fault 后紧接正常 load/store；ACC 翻译竞争；buffer slot 与 scoreboard ID 重用 | 异常、地址、ID 和 MMU owner 不串线；同一逻辑事务没有第二次完成 |
| C7 | 配置边界 | 当前配置；需要通用化时加入 MMU=0/NI=0 及单项 buffer | 跨配置反例应被检测器捕获，不能判为当前配置失败；单项 fall-through 的组合依赖需单独检查 |

### 5.2 假设、证据与判别矩阵

| 候选问题 | 区分它所需的证据 | 预期观察/反证 | 当前证据等级 |
| --- | --- | --- | --- |
| MMU 请求被异常反向门控而形成组合反馈 | `state_q`、translation req、完整异常、canonical 检查及组合依赖 | 当前 WAIT_GNT 的 translation req 应独立于异常保持 1；不能仅用一条稳定波形证明全设计无组合环，通用签核还需对应静态检查 | 当前修改未见该反馈；未运行工具级组合环检查 |
| 撤销未 grant 请求造成丢请求 | `data_req && data_gnt`、WT 接受状态、buffer 写入、队头身份 | 无接受即无 cache 返回义务；已接受尝试必须完成或取消回收 | 当前 WT 握手支持安全撤销；未测 |
| MMU=0/NI=0 的 pop 无完成 | 配置、C0/C1 队头、异常、pop、结果 valid、cache 接受计数 | C1 pop=1、valid=0、无接受，之后队头消失；应报告丢完成 | 静态可构造；当前配置不触发；未仿真 |
| WAIT_PAGE_OFFSET 丢失异常早退机会 | 异常来源、translation req、旧 rvalid、page match、队头保持 | 相撞后异常消失、无 pop、仍等待冲突；冲突解除后的重试区分延迟与永久无完成 | 脉冲丢失可静态推出；系统活性后果待测 |
| 正常返回与提前异常造成双完成 | 指令唯一身份、cache 尝试身份、pop、结果、kill 和 rid | 旧返回完成旧事务；提前异常仅完成当前队头；不能按同一数字 ID 或两次 rvalid 直接判错 | 当前未见确定反例；待测 |
| PTW 单拍错误被旧返回抢占 | PTW 错误状态、请求持续、DTLB 更新、队头身份和最终异常 | 可重走翻译，但最终不得丢完成或把异常转给后继；不承诺下一拍完成 | 无异常锁存，可能重走；待测 |
| Flush 后旧结果污染新 ID | epoch、分配序号、返回流水、scoreboard issued/valid、commit/trap | 原事务取消；迟到内部结果不能标记新事务完成或提交 | 当前路径有过滤；ID 重用交叉待测 |
| 异常属于错误的 MMU owner/队头 | scalar/ACC 请求、owner、寄存 VA、异常内容、当前队头和 PC | 请求到异常归属一致；不得借用前一条 SEND_TAG 请求或 ACC 的结果完成当前队头 | 静态所有权约束已检查；集成交叉待测 |

### 5.3 完整探针矩阵

所有层级应关联到同一事务身份，而不是独立打印局部计数。具体实例前缀在未来 harness 中一次确认，不应通过缺失一组信号就重跑一次的方式补齐。

| 层级 | 必备信号/字段 | 用途与精确语义 |
| --- | --- | --- |
| 指令身份与输入 | PC、指令、分配序号、flush epoch、trans_id；issue valid/ack 或实际接受事件；`lsu_valid_i`、`lsu_ready_o` | 建立唯一逻辑事务身份；只在对应接口契约的实际接受事件上分配新事务，不把 valid 电平当成握手 |
| LSU bypass | 队头完整 `lsu_ctrl`、`status_cnt_q/n`、读写指针、队列 valid、`pop_ld`、`pop_st`、flush | 证明队头稳定、pop 次数和 flush 优先级；`ready_o` 来自队列空状态，不等于 cache grant |
| Load FSM | `state_q/d`、`valid_i`、`translation_req_o`、`pop_ld_o`、`flush_i`、buffer full 与接受条件 | 区分开始请求、等待、提前异常、已接受请求的 tag 周期和重试 |
| 翻译与所有权 | scalar/ACC 请求与响应、`mmu_state_q/d`、VA/PA、DTLB hit/PPN；MMU `lsu_req_q`、寄存 VA、misaligned 异常；完整 exception 字段；translation valid | 证明异常所属请求/owner；translation valid 是翻译结果事件，不是 cache 接受或架构提交 |
| 权限与 PTW | 翻译使能、privilege、SATP/PMP 相关状态、canonical 检查、DTLB/shared-TLB 更新；PTW 状态、active、walking owner、错误/访问错误、更新 VA | 区分稳定可再生异常与单拍 PTW 错误，排除错误权限环境和错误 owner |
| Store/NI 依赖 | page offset/match、store 队列有效项与地址、store-buffer empty、commit trans_id、`stall_ni`、`dcache_wbuffer_not_ni_i` | 分辨地址冲突、提交排序、非幂等写依赖；不能把 `not_ni` 信号无条件等同于所有写缓冲全空 |
| Cache 请求/返回 | data req/gnt/id、address index/tag、size/BE、tag_valid、kill_req、rvalid/rid/data；WT 状态、stall、cache enable/初始化相关控制、miss 请求/应答/返回 | `req && gnt` 计 cache 尝试接受；rvalid 可能是 kill 应答，需要结合状态和身份解释 |
| Load buffer | valid/flushed 的 q/d、读写使能、读写索引、slot 内 trans_id、last ID | slot 分配/回收与重用；occupancy 用 `$countones(ldbuf_valid_q)`；不要用变量名推断未参与控制的 `ldbuf_empty` 语义 |
| 外部访存 | AXI AR valid/ready/ID/address、R valid/ready/ID/response；必要的 store 通路握手 | 验证异常 load 未产生不应发生的实际访问，区分 LSU 接受、cache 尝试和总线事务 |
| 结果与提交 | 返回流水前后 valid/ID/result/exception、scoreboard issued/完成位、commit/trap 及对应 PC/epoch | 分开统计内部结果、被过滤旧结果和架构完成；检查 flush 后 ID 重用污染 |

### 5.4 采样、窗口与计数判据

- 在时钟上升沿前的稳定采样点判定该拍握手和异常仲裁；NBA 后记录状态及计数更新。不得把组合传播中间态当成独立事务。
- 每个目标事件保留前 16、后 256 拍的有界 FSDB 窗口，覆盖接受、等待、结果或取消、排空及 ID 重用。诊断夹具的内存/仲裁最大延迟须事先保证可落入窗口；此窗口不是生产 SoC 的普遍完成时限。
- 触发事件按用例预设，包括目标 fault 的发起、等待态异常/旧返回碰撞、flush 碰撞和后续 ID 重用。若不能覆盖完整生命周期，应在启动前调整方案，而不是事后盲目扩大 timeout。
- 逻辑事务使用“flush epoch + 分配序号”作主键，trans_id 只作关联字段；cache 尝试另用“slot + 分配代数”记录，重试不能算新指令。
- 未取消的逻辑事务最终只能有一次有效完成；取消事务不得架构提交。每个 cache 接受必须有正常返回或取消回收，不得释放不存在的尝试。
- 在当前配置、有效等待态异常、无旧返回且无 flush 时，提前 pop 应与同一队头的异常结果同时发生，且无新 cache 接受。
- `flush && valid_o`、重复 translation req、kill 应答 rvalid 均不是独立失败条件；必须关联生命周期和下游可见性。
- 对 C7 的已知跨配置反例，实验目标是检测器能准确报告丢完成，不是把该变体标为通过。当前目标的通过/失败须独立统计。
- 超界或身份不闭合即保留为失败/未解释结果，先用已捕获 trace 排除替代解释；不得通过临时更改 RTL、参数或超时掩盖。

## 6. 新完整 SoC 导出交接要求

1. 不直接用 deps 的 `load_unit.sv` 覆盖已有 FPGA 文件。保留两个 hunk 的来源、配置条件和待测状态，不拆开合入。
2. 新导出须核实实际编译源、MMU/NI 参数、cache 类型、load buffer 项数、返回流水深度、ACC/MMU 所有权和 flush/ID 回收契约。它们改变时，本报告的静态安全性判断不自动继承。
3. 保留已有适配仅表示避免未经审核的覆盖，不表示当前适配已完成实验验证，更不表示整个导出 SoC 已签核。
4. 当前目标先执行事先审查的判别矩阵，再安排必要的代表性回归。通用化时单独处理 MMU=0/NI=0 的静态丢完成反例；不能将当前配置不触发作为通用正确性的证明。
5. 后续任何 RTL 变更须以静态分析和测量证据一致为前提。本次归档不包含 RTL 修改、EDA 运行或板卡访问。

最终状态：**报告已归档；静态审核结论如上；当前目标实验未执行；新完整 SoC 未因保留此导出适配而获得签核。**
