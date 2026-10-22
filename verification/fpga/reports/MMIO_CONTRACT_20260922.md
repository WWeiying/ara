# AXI64 / reg32 桥：读范围与错误归属回归

## 结论

2026-09-22，使用同一冻结 testbench，原桥和隔离修复桥各运行一次有界 VCS
实验。原桥五组均失败，修复桥五组均通过。测试直接验证实际桥接 RTL，不包含
CPU、PLIC 或完整 SoC；它补充而不替代 [PLIC 集成复验](PLIC_CONTRACT_20260922.md)。

两次实验仅有 `axi_to_detailed_mem.sv`、`axi_to_reg_v2.sv` 两份 RTL 不同，
TB、独立寄存器模型、host 检查器及其余编译输入的 SHA-256 相同。修复位于
`verification/fpga/patches/mmio-read-range.patch`，尚未覆盖正式 FPGA 导出。

| 项目 | 原桥负例 | 隔离修复桥 |
|---|---:|---:|
| 检查组 | 0/5 PASS | 5/5 PASS |
| 接受的 AR / 返回的 R beat | 65 / 74 | 65 / 74 |
| AW / W / B | 6 / 6 / 6 | 6 / 6 / 6 |
| 实际外设寄存器访问 | 154 | 91 |
| 失败检查 | 381 | 0 |
| 检查调用数 | 8419 | 8116 |
| 上升沿前采样周期 | 1091 | 937 |
| 编译 / 运行墙钟秒数 | 25.88 / 10.69 | 26.08 / 10.74 |

381 是失败检查次数，不是381个独立bug；同一次错误访问可以造成掩码、读副作用、
返回值及最终状态的多项失败。检查数随握手/等待周期而变化，不能当作独立测试数量。
少了63次无关寄存器访问，也不能据此宣称整机或模型提速。

## 仿真前固定的判别方案

| 候选问题 | 判别信号与检查 | 反例或排除条件 |
|---|---|---|
| 窄读访问非目标 bank | 从已接受 AR 的地址/size 独立枚举有效字节；对照每次外部 reg 握手及 read-effect 计数 | 不能仅检查 AXI 返回的有效字节正确 |
| 掩码错误使用当前 AR 或 W | 交错地址/size/ID、W先于AW、AW先于W；同时记录 selected meta、meta buffer、bank FIFO、request cut 和外部访问 | 后续总线输入改变时，旧事务的范围和属性仍必须不变 |
| 错误响应被吞掉或错归邻居 | 目标与相邻寄存器分别注入 error，跟踪 buffered meta、response bank mask、bank error 和 RRESP | 目标错误必须 SLVERR；仅被抑制邻居错误时必须 OKAY |
| 抑制 bank 后 response join 卡住 | 记录两个 bank 的 request/response valid-ready、局部零掩码回复、pending 数及 RLAST | 每个接受请求仍完整结束，不能用吞响应避免副作用 |
| 破坏原写路径或背压协议 | 部分写、零strobe写、写后读回、B/R及reg反压、AW/W独立时序 | ID/RLAST一致，held response稳定，写字节和次数正确 |

测试中的 oracle 只从 AXI 握手生成期望，不从 DUT metadata 或掩码反推期望。
寄存器模型含独立存储和读取副作用：成功读取后，下次返回值随读取计数变化。
TB 按读/写与 bank 分别核对顺序，以允许合法仲裁交错；host 还从原始周期日志
独立重算请求范围、响应序列和实际寄存器访问集合。集合检查不替代 TB 的顺序检查。

探针按上升沿前 `#1step` 采样，最多4096周期，记录90个字段。完整路径为
AXI接受、selected metadata、metadata buffer、memory request、两个bank、request
cut、有效/抑制请求、外部reg、bank response以及AXI响应；包含reset和测试组。
请求用单调序号与beat序号关联，不把可复用AXI ID当作唯一事务标识。
可恢复语义错误累计，独立组间排空并复位；协议、未知控制值、超时立即失败。

## 实际覆盖

当前桥配置为 AXI数据64/address48/ID4/user2、reg32、`CutMemReqs=1`、
`CutMemRsps=0`、`BufDepth=1`、`OutFifoDepth=1`。ID宽度是TB配置，不代表全SoC。

| 检查组 | 具体激励 | 原桥 | 修复桥 |
|---|---|---|---|
| size_lanes | 全部8个字节偏移 x 4个size，包含未对齐首beat | FAIL | PASS |
| queued_reads | 8个连续、不同地址/size/ID的读；前一个R反压时提出后一个AR | FAIL | PASS |
| mixed_channels | W提前18周期、AW提前10周期，读写交错，0x81部分写和零strobe写，写后读回 | FAIL | PASS |
| incr_bursts | 4个INCR burst，包含offset3/size2的首beat和后续对齐beat | FAIL | PASS |
| error_mapping | 不同64-bit word内的高低bank、无效邻居、所选错误寄存器、越界和写错误 | FAIL | PASS |

共18个未对齐AR请求、4个burst。修复桥实测159个R反压周期、16个B反压周期、
60个reg等待周期、99个“AR等待且前一个R受阻”周期，以及3次W等待期间的AR接受。
这些只是各自非零活动证据，不是可相加的stall分解；也不代表同时接受了两个AR，
因为本配置的请求缓冲深度为1。

## 修复范围

读范围按当前beat的地址与size计算；未对齐首beat的终点是自然对齐边界，
不是简单的 `address + 2^size`。例如offset3/size2只覆盖byte3，offset4/size3
覆盖byte4..7。掩码随已有strb通路穿过bank FIFO和request cut，不增流水级。
零掩码bank在桥内部完成，仍向上游join贡献响应，但不会触及外设。

响应掩码从该返回事务的 `meta_buf` 重建。原表达式中的
`meta_buf.addr % DataWidth/8` 按运算顺序为 `(addr % DataWidth)/8`，
并非 `addr % (DataWidth/8)`；地址加法/移位表达式还不能正确表达未对齐首beat。
隔离修复统一使用精确有效字节范围，避免所选bank错误被漏报或无关bank被计入。

`EnableReadByteMask` 默认关闭，只由寄存器桥开启。其它默认 memory 实例的路径
保持不变，不能将本报告当作其错误归属已经修复或已验证的证据。被实际访问的
32-bit寄存器是否支持逐字节读副作用，仍取决于外设本身。

## 独立复核的周期链

两轮同一请求 `AR seq53 / R beat62 / ID2 / addr=0x04000004 / size2`，
错误寄存器位于高bank。周期均为上升沿前采样：

| 事件 | 原桥 | 修复桥 |
|---|---|---|
| AR及memory请求接受 | 932，mem_strb=00 | 789，mem_strb=f0 |
| 目标寄存器接受并报错 | 933，regerr=1 | 792，regerr=1 |
| 非目标低bank | 934额外读取0x04000000 | 790在桥内完成，不访问reg |
| response bank选择 | 01，错误选择低bank | 10，选择高bank |
| R响应 | 935握手，错误返回OKAY | 793起保持SLVERR，801握手 |

另一个地址偏移反例为beat67的 `0x04000038`：原桥975接受、977目标报错、
983仍返回OKAY；修复桥828接受、829报错、830正确返回SLVERR。
这两条链将返回错误与对应metadata、bank错误、最终响应关联，排除了仅靠最终
数据值推断根因的问题。原桥六个RRESP不符的beat为62/63/65/67/70/73；修复桥为零。

独立复核还确认：原桥148次reg读、修复桥85次reg读，差值为63；两路均有6次reg写，
各次写和B响应相同。修复桥74个beat的掩码、ID/RLAST、有效返回字节及访问bank集合
全部吻合，五个AXI通道在等待期间未见payload变化。W等待反例中，旧桥637周期
读取0x04000094时误带WSTRB=0f；修复桥536周期同场景的读范围为正确的f0。
独立审查只复用已捕获日志，没有追加仿真。

## 复现与归档

从验证 worktree 根目录运行，输出目录必须不存在：

```sh
make -C verification mmio-contract \
  MMIO_DIR=/absolute/path/to/hardware/fpga/ara_dsa_vcu118/rtl \
  MMIO_RUN_OUT=/absolute/path/to/verification/out/mmio-baseline-new

make -C verification mmio-contract \
  MMIO_DIR=/absolute/path/to/verification/out/mmio-fixed-candidate-20260922-03/rtl \
  MMIO_RUN_OUT=/absolute/path/to/verification/out/mmio-fixed-new
```

第一条是负例，预期返回FAIL，不能包装成DUT通过。实际归档：

- 原桥：`verification/out/mmio-contract-baseline-vcs-20260922/`。
- 修复桥：`verification/out/mmio-contract-fixed-vcs-20260922/`。
- 各目录保存 `sources.json`、`inputs/`、`probe_plan.json`、编译/运行命令、
  `run/console.log`、`run/mmio_signals.log`、`summary.json`；运行前后无输入漂移。
- 修复镜像SHA-256：`424856e0f720369c66279550df5e5f6d537d9a6d82d27e34e2d6d7a88d1c498b`。
- 修复周期日志SHA-256：`a981623f85525560d03887b2b77330e2b33c4220dbe6efbe8324a34808359ea3`。
- 原桥周期日志SHA-256：`f9c49fe4323ba1dddc6eb3dc05afa1b2b239559228e6b7f6057245cb59be308c`。
- 本轮相关 generator/checker/runner/plan host 单测153项PASS，不替代RTL功能测试。

原桥VCS进程在末尾 `$fatal` 后仍返回0，底层命令状态因此是PASS；上层runner
根据语义失败、原始周期证据和日志完整性判为FAIL。签核必须使用最终summary，
不能只取进程退出码或底层命令状态。

## 未覆盖范围与主线衔接

尚未验证其它cut组合、AXI位宽/深度配置、原子操作、FIXED/WRAP及多beat写burst；
未验证CPU、跨互连顺序、完整外设清单、DDR、Linux或板卡。下一阶段应把已验证
PLIC/MMIO与当前CVA6/dispatcher修复纳入新的完整SoC交接快照，保留原FPGA适配，
再运行系统中断及Linux路径，不能直接使用旧bitstream宣称修复已经上板。
