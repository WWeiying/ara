# CVA6 四项上游修复与模块验收

## 结论与冻结范围

本轮仅修改 `hardware/deps/cva6/core/` 下的 `load_unit.sv`、
`csr_regfile.sv`、`cva6_mmu/cva6_mmu.sv`、`cva6_mmu/cva6_ptw.sv`。
未改依赖登记、patch bundle、其他 RTL 或已有 sealed 验证程序，未提交。
原文件已在 `verification/out/upstream_20261009-original-01/` 独立冻结。
逐文件与该快照比较，仅有下面四项修复；原有 dirty 修复全部保留。

宿主机 VCS 完成八次实际模块编译/仿真。每对原版/修复版只有被测 DUT
文件不同，其余输入逐文件 SHA 相同。修复版合计 **440 场景、5880 项检查 PASS**。
原版合计 156 个失败场景，其全部错误都符合预先推导的旧行为，没有把任意
FAIL 当成原缺陷复现。独立 Python checker 的 8 项单元测试通过。

最终离线验收及冻结清单：
`verification/out/upstream_20261009-closure01/audit.json`。
该清单核对了原/新 DUT、冻结输入、实际测试矩阵、镜像、日志、观测数据，
并重新运行同一个功能 oracle 和严格原版失败特征检查。

| 模块 | 场景数 | 检查数 | 原版失败场景/检查 | 修复版 |
|---|---:|---:|---:|---|
| load_unit | 32 | 384 | 16 / 32 | 全部 PASS |
| csr_regfile | 24 | 312 | 8 / 14 | 全部 PASS |
| cva6_mmu | 192 | 2880 | 48 / 144 | 全部 PASS |
| cva6_ptw | 192 | 2304 | 84 / 504 | 全部 PASS |

八次编译各约 24.5–26.3 秒，每次仿真进程约 10.7 秒（包含工具启动开销）。
没有长仿真、超时重试或 RTL 试错迭代。

## 1. load flush 与分配优先级

上游依据：[b30e7dba3e85b887da5a01aab34c2438653efa83](https://github.com/openhwfoundation/cva6/commit/b30e7dba3e85b887da5a01aab34c2438653efa83)。

原逻辑先执行 flush 的全槽取消赋值，再执行新槽分配。两者同周期发生时，
后者清除新槽的 flushed 位。因此旧请求延迟返回时，`valid_o` 可能错误有效。
修复将 flush 放在分配之后，使 flush 具有最高优先级，位置为
`load_unit.sv:166`，不增加状态或流水周期。

实际 load_unit 测试覆盖 IDLE/WAIT_GNT 分配、flush 有/无、3/4/9/17 周期
延迟、transaction ID 0/3，共 32 场景。每场景检查取消位、返回有效性、ID、
数据、异常、回收，然后在旧事务排空后复用同一个 architectural ID 并检查
新返回。原版恰有 16 次取消位错误及 16 次错误有效返回；修复后全部通过。

范围限制：缓存响应由 fixture 从合法模块接口注入；这证明 load_unit 对
取消事务延迟响应的抑制，不代表已在真实 WT cache 中复现该响应序列。
ID 复用检查发生在旧事务排空之后；未宣称已覆盖 scoreboard 的并发 ID 复用。

## 2. 非 RVH 配置下 xRET 清除 MPRV

上游依据：[d2fdf99a3837e12d615dc32f5e3aea03ee62e4ca](https://github.com/openhwfoundation/cva6/commit/d2fdf99a3837e12d615dc32f5e3aea03ee62e4ca)。

原 MPRV 清除语句错误位于 `CVA6Cfg.RVH` 分支内；RVH=0 时不执行。
修复只将 MRET 返回非 M 模式、SRET 的清除语句移出 RVH 条件，位置为
`csr_regfile.sv:2364/2387`。没有吸收相邻虚拟化行为或修改已有 CLIC、SD、
SSTATUS、STVEC 修复。

通过实际 CSR 端口写入状态，再执行 MRET/SRET，没有 force CSR 寄存器。
覆盖 MRET 到 M/S/U、SRET 到 S/U、MPRV=0/1、PIE=0/1，以及先进入 S 模式
再执行 SRET 的邻接场景。检查特权模式、MPRV、有效访存权限、EPC、IE/PIE、
MPP/SPP、FS/VS/SD。原版 8 次 MPRV 错误，其中 6 次同时影响有效访存权限；
修复版 24 场景全部通过。MRET 返回 M 时保持 MPRV 的规则也通过。

## 3. canonical 异常与寄存响应的归属一致

上游依据：[47b72e3193708e870d9e3f333de6e39b95b6e9bc](https://github.com/openhwfoundation/cva6/commit/47b72e3193708e870d9e3f333de6e39b95b6e9bc)。

原条件使用当前 `lsu_req_i/lsu_vaddr_i`，但异常接收者、访存类型、tval 和
TLB 结果属于 `*_q`。相邻 A/B 请求可能导致 A 的异常由 B 地址决定。
修复仅将 canonical 检查的请求及地址改为 `*_q`，位置为
`cva6_mmu.sv:524`。

**early PPN 仍使用当前 lookup 页大小和当前地址**，`cva6_mmu.sv:565`
开始的既有修复未改。不得把提前送给 load_unit 的 PPN 改成旧请求的 PPN。

fixture 实例化实际 MMU、TLB、PTW，仅在 DTLB refill 接口注入合法映射，
不 force hit、PPN、PA 或异常。矩阵为 A/B 请求有效位、各自 canonical
合法性、A 为 load/store（B 取相反类型）、正/负地址、4 KiB/2 MiB/1 GiB。
逐项检查 A/B 的 valid、PA、exception、cause、tval，以及当前 B early PPN
和末尾空闲周期。异常必须属于对应请求：load=13，store=15，tval 为该请求 VA。

原版恰在 48 场景中各错 exception/cause/tval，一共 144 项；early PPN、
PA、B 的寄存响应均未错误。修复版 192 场景、2880 检查全部通过。

范围限制：本矩阵保持翻译模式与权限稳定，misaligned 输入为零。
既有 early PPN 的 `!misaligned_ex_q.valid` 混合阶段门控，以及 RVH G-stage
替换语义，不属于本轮修复或通用正确性结论。未宣称 NI 请求/重试或整机签核。

## 4. 非叶 PTE 的 A/D/U 检查

上游依据：[f7c04c3721693b1c9045ae8a8da0ed6ac1f68cf8](https://github.com/openhwfoundation/cva6/commit/f7c04c3721693b1c9045ae8a8da0ed6ac1f68cf8)。

已重新查看整个提交，它只修改一个文件中的两行逻辑：将非叶 A/D/U 拒绝
去掉 RVH 限定，保持 `ptw_stage_d` 的赋值仍受 RVH 保护。没有额外修复被
隐含带入。当前落点为 `cva6_ptw.sv:546`。

fixture 驱动实际 PTW 请求入口，并按其真实 dcache request 进行 PTE 返回，
不 force 内部状态或异常输出。84 个非叶非法场景覆盖两级指针、A/D/U 所有
7 种非零组合、fetch/load/store、两种返回延迟。108 个邻接场景覆盖三种
合法叶页大小、叶 A=0/D=0、非法 W=1 R=0、V=0、PPN 对齐。
D=0 的 fetch/load 仍允许通过，store 必须拒绝；4 KiB 的奇数 PPN 正常。

独立 oracle 检查页表访问次数与地址、唯一 refill/异常、refill 的 PPN/VA/
ASID/页大小、取指分类、排空回到 idle。原版 84 场景继续访问下一级并产生
错误 refill，504 项错误；修复版全部 192 场景通过。

## 可复现命令

从本 worktree 根目录运行，输出目录必须是新的目录：

```sh
python3 -B -m unittest discover -s verification/cva6 -p upstream_20261009_test.py -v
python3 -B verification/cva6/upstream_20261009_run.py \
  --suite mmu --variant candidate \
  --output verification/out/upstream_20261009-mmu-candidate02
```

`--suite` 支持 `load/csr/mmu/ptw`，`--variant` 支持 `baseline/candidate`。
baseline 使用本轮修改前的精确冻结文件，而非干净 Git HEAD；其中保留了以前
已经修复的功能。每次都独立归档 RTL、fixture、实际接口类型、case、命令、
镜像与日志。checker 拒绝 X/Z、漏字段、重复字段、异常终止、缺少正常结束。

无需重新仿真的最终验收命令：

```sh
python3 -B verification/cva6/upstream_20261009_close.py \
  --output verification/out/upstream_20261009-closure02
```

## 交付界限

- 结论限定当前 RV64/Sv39、RVH=0、PMP=0 的实际模块测试，不外推 Sv32/RVH。
- 修改前后的每对编译输入只有被测 RTL 文件不同；没有在原文件上来回切换。
- load/CSR 最早记录生成后，对 baseline 严格 gate 做了加强；最终 closure
  已对所有八次原始观测重新审计，不修改旧目录或重新仿真。
- 未测整机性能、真实缓存取消流程、Linux 启动、代码覆盖率、综合或 PPA。
  本轮没有改变流水级，但不将模块 PASS 等同于整机性能无退化。
- parent 后续登记依赖与统一构建当前整机镜像。本轮没有更新 registry/bundle。
