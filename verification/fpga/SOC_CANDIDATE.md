# 完整 SoC 隔离候选与下一道验证门禁

## 当前状态

2026-09-22 已生成完整、无软链接的 FPGA 工程候选：

`verification/out/fpga-soc-candidate-20260922-04/package/`

状态为 **PREPARED_NOT_BUILT**。这是包含 RTL、板级脚本、约束和 Linux 启动材料的
独立副本，不是已经通过整机仿真、Vivado、Linux 或板卡验证的版本。没有覆盖
`hardware/fpga/ara_dsa_vcu118`、共享依赖、原 `ara_dsa` 或任何已有 bitstream。

## 这次交接具体带入什么

| 部分 | 处理 | 依据与限制 |
|---|---|---|
| Ara dispatcher | 带入完整XLEN的VILL/保留位检查、非法配置恢复 | 源码与已通过的定向回归对应；已有layout/control/VL cast不再重复变换 |
| CVA6请求与CSR | acc_dispatcher、issue_read_operands、csr_regfile、两个package共5份文件 | 同步fence pending、stall保留、SSTATUS的VS读写修复 |
| CVA6 decoder | 带入ECALL、breakpoint、实际选中interrupt的tval修复 | 与448项异常测试的冻结源码/批准补丁一致，不扩大到其它配置 |
| PLIC | 更换为58槽/2 context/标准映射及IE0、completion修复；3份RTL字节变化 | 5份生成RTL全部与7组VCS测试冻结输入匹配；gateway/target无需变化 |
| AXI/reg桥 | 更换2份RTL | 与PLIC集成、MMIO五组回归同时使用的源码完全一致 |
| 旧PULP除法补丁 | 5份文件恢复到已固定的干净preimage | 不继续封装已实测错误的隔离补丁；当前标量/向量仍选THMULTI，不能称PULP已签核 |
| FPGA特有适配 | 保留其余RTL；尤其完整保留load_unit成对的等待态异常修改 | 已匹配范围不重复改写，未验证部分仍须独立验收 |
| Linux | ndev57模板、匹配DTB、内嵌相同DTB的OpenSBI和已检查initramfs | kernel Image字节不变；更新四文件checksum，不保留旧DTB校验表 |

总计19份RTL被列入替换核查，17份实际变化。每一份实际变更都记录原/新hash和来源；
包内其它RTL若意外变化，准备步骤直接失败。目录中的旧文档验收记录仅是历史信息，
当前状态以新 `CANDIDATE_STATUS.md` 与 manifest 为准。

## 如何生成和复核

在验证worktree根目录执行，输出目录必须不存在：

```sh
make -C verification fpga-soc-candidate \
  SOC_CANDIDATE_OUT=/absolute/path/to/verification/out/fpga-soc-new
```

`prepare_soc_candidate.py` 是本轮固定输入组合的交接工具，不是忽略版本变化的
通用覆盖脚本。它要求本地已有对应的生成物及验证证据；在其它机器上须先重建
相同准备/验证步骤或带齐归档，不能用空文件或伪造PASS绕过证据检查。

它依次核查：

1. 原导出manifest和checksum固定指纹，以及完整封装RTL的校验和。
2. CVA6/FPnew批准补丁的精确状态、submodule，以及需保留文件的固定指纹。
3. PLIC/MMIO冻结源、镜像和日志hash，重新离线解析原始周期记录，不重跑仿真。
4. 候选RTL与对应实测输入一致，PLIC为58槽/2 context，MMIO两轮使用同一修复桥。
5. Linux四文件hash、模板来源、OpenSBI内嵌DTB逐字节一致。
6. dispatcher适配链在当前已吸收适配的源码上原样返回；未知输入仍被拒绝。
7. 普通文件复制，无软链接/硬链接共享；更新嵌套Linux和全包checksum。
8. 原输入前后不变，全部RTL差异恰好等于声明清单。

源树指纹在验证之前固定，复制时不得重新接受一个已变化的基线；证据、分析器、
补丁和归档材料均绑定到核查时的指纹，并在结束时再次检查。仅复制原封装已校验的
文件和明确列出的Linux支持文件。本次另有251份未被原封装校验的历史报告、
应用生成物等未纳入候选，原文件仍保留，没有删除或冒充新RTL的运行结果。

归档保留原manifest/checksum、批准依赖及外设补丁、逐文件变更表、subsystem
summary/source表与Linux bundle manifest。目录如下：

```text
fpga-soc-candidate-20260922-04/
  manifest.json                         # 本次准备结果，不是整机PASS
  package/
    CANDIDATE_STATUS.md
    manifest.json
    SHA256SUMS
    rtl/
    scripts/ constraints/ board_files/
    linux/artifacts/
    provenance/verification_handoff/
```

`checked-inputs.json` 记录本次核查的证据指纹。完整原始trace和仿真镜像仍在
对应验证输出目录，包内summary中的路径也指向那些归档；这份候选包本身并非
已经包含所有原始证据的独立重放包，跨机器交接需一并保留相应证据目录。

本轮host检查59项通过，涉及隔离复制/漂移/路径门禁、适配器精确白名单和既有
source checker。未知dispatcher修改以及部分VILL修改仍拒绝。旧导出包级测试有
历史VMFPU快照不一致，不为让它变绿而更新原导出；详见适配器测试与候选状态。
具体为 `test_export.MainlineSyncTests.test_exported_ara_matches_reviewed_mainline_with_fpga_patches`：
其固定 `db90e341` 快照与已有封装VMFPU不同，该失败在本轮适配器修改前已存在。
不能将上述59项局部通过表述为整个旧export测试集通过。

## 来源缺口与行为缺口分开处理

此前226项`missing_source`现已在明确的pinned本机checkout中全部定位。
221项直接等于导出，5项经现有适配纯函数精确复现；所有实际源文件均等于固定
提交的Git blob。见 [来源核查](reports/FPGA_SOURCE_ORIGINS_20260922.md)。

这说明源码来源可追溯，不说明所有适配功能正确，也没有把原source checker的
`accepted=false`改成PASS。验证worktree默认映射处仍缺这226项；后续应建立显式、
固定提交的本地来源映射。Cheshire的本地Bender覆盖和14个失效的本机origin也
不能当作跨机器可复现的依赖配置。

## 下一道门禁：load等待态异常

后续局部实测已完成：真实bypass/load/WT控制器的15组场景、22条逻辑请求通过，
并已确认异常脉冲与旧返回竞争会造成延期但本组条件下不丢队头。见
[实测记录](../cva6/LOAD_CONTRACT_MEASURED_20260922.md)。其中翻译与cache存储侧
是边界模型，不是实际MMU/PTW、返回流水和scoreboard的组合验证；下面的系统级
门禁仍保留，完整候选状态不因此升为SoC或Linux通过。

独立审核发现：FPGA导出的load_unit与当前deps存在成对修改，不能整文件覆盖。
在当前有MMU的目标配置下，尚未找到确定的新组合环、丢请求或双完成反例，但
异常与旧load返回同拍的行为仍缺定向实测。因此这份适配原样保留，且标为待验证。

另有一个**静态可构造、当前目标不触发**的跨配置问题：当MMU和非幂等区域支持
均关闭时，等待态可能pop异常请求而没有输出完成。不能据此声称当前板卡必然失败，
也不能把这份修改无条件推广为通用CVA6修复。

完整分析与一次性判别矩阵见
[LOAD_UNIT_HANDOFF_20260922.md](reports/LOAD_UNIT_HANDOFF_20260922.md)。实验应覆盖：

- 地址冲突和等待grant期间的未对齐、权限、PTW fault。
- 异常与正常旧返回、flushed返回、kill应答碰撞，区分架构完成和cache尝试回收。
- flush边界、异常后正常请求、队列/ID重用及ACC翻译竞争。
- 同时抓取队头身份、MMU/PTW状态、cache请求/返回、load buffer和scoreboard/trap。

先用同一份捕获判断究竟是异常丢失、仅延期、重试还是双完成，再决定是否改RTL。
修复和回归后才推进完整SoC外部中断、Linux用户态RVV、板卡长时回归以及
QBS/AKV原生模型执行。custom隐藏上下文的进程隔离仍是独立门禁，不由普通RVV
寄存器保存恢复或QEMU单进程成功替代。
