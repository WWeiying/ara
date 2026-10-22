# 本批覆盖率收尾与未通过项目

## 统计范围

本批使用2026-09-30封存的VCS镜像，不修改RTL、不重新编译。
通过测试的覆盖率与失败测试分开保存。其它修复镜像的PASS不能合并
到本镜像VDB中。用户要求本批完成后暂停，不继续增加激励或修RTL。

## 本批通过的激励

`vgather_war797`在四轮中执行Gather后紧接indexed load，检查旧源
读取完成之前不能被后续load覆盖。VCS正常退出；独立Spike参考下，
39052条标量指令、存储、24项CSR、源与快照guard和16个向量目标组
比较全部通过。向量比较16384字节，没有未知字节跳过。

相对原797项集合新增118个serialized Toggle位置、24个Condition
位置。LDU完成等待目标新增18个位置，覆盖全部四个队列entry。
这些是数据库覆盖位置数量，不是猜测的物理位/翻转方向数量。

资格证据：
`verification/out/gather-war797-successor-qualified-parent-20261008-01/qualification.json`。

## 冻结旧镜像中明确未通过的激励

| 激励/输出目录 | 观察到的问题 | 定位程度 | 覆盖准入 |
| --- | --- | --- | --- |
| `mask-compare-restart-known-old-image786-agent-20261008-01` | 非零vstart的VMSLTU破坏prestart mask位；首错PC为0x800024f8，期望f3、实得f7 | MaskB将lane级vstart用于EW64旧mask word寻址，返回了错误旧位；有效区比较正确，不能解释为合法tail差异 | 未纳入 |
| `gap71-canonical-qbs-positive779-run-agent-20261008-03` | 首次故障后v8快照检查index60失败，160项检查中1项失败 | 故障custom请求零VRF写回；128字节快照完全符合EW8物理内容按EW32解读。问题集中于目标EEW布局元数据与物理内容不一致，具体更新周期尚未由直接探针证实 | 未纳入 |

以上均以原始console、commit/vector trace及独立取证为依据，不能
用进程退出0认定通过；没有在本批修复，也没有用整模块豁免隐藏。
这张表列出本次收尾核验的明确失败，不宣称是全部历史任务的索引。

## 已有修复、但不能混入本镜像的项目

`vgap35_carry_ta`和`vgap35_slide_bound`在旧镜像分别出现3项、6项
错误：carry/borrow在非零vstart下操作数与MASKU位打包错位；
VSLIDEDOWN写使能没有保护prestart元素。

另一个封存修复镜像已有15项回归PASS，包含459项carry检查、535项
slide检查，以及QBS/AKV和扩展/规约代表点。证据为
`verification/out/gap35-restart-repair-20261005-01/status.json`。
它不能证明当前旧覆盖镜像已修复，亦不能用于混合RTL版本统计。
其中QBS fault测试通过不等于上表后续canonical故障场景已经闭环。

## 非RTL故障的收尾问题

- 原Gather检查器错把生产者要求为SLDU3；实际RTL经MASKU2写回。
  使用独立后继检查器修正，两组严格/负向测试均通过，没有改原轨迹。
- Gather store在没有VRF写回时部分活动上下文字段未记录。
  只对真正的writer强制VL/vstart，store仍保留完整标量/存储检查。
- 原797项ELF去重附件只有796个成员。后继根据封存的第797项VSMUL
  manifest和真实ELF补齐，不删除去重检查、不改历史文件。
- C910部分位DVE接口诊断没有取得合格的bit-detail映射；属于工具
  资格未通过，不是处理器激励失败，不能据此应用部分位豁免。

## 收尾任务

Gather已正式准入，集合为798项PASS。目录为
`verification/out/gather-war-offline-admitted798-v2-parent-20261008-01/`，
`admission-manifest.json` SHA为
`f5efacbc0c28c2766d6899f28b002a308f35bdadf33c7e4934a7d241d6b44da3`。
后继修复了796成员附件的缺项，保留原797项覆盖顺序，新增唯一Gather
ELF/VDB；父端18项准入测试、4项历史清单测试及实际准入均通过。

17个SRT独立算术核心的原生豁免汇总已完成。服务正常退出0、未超时；
父端复核26个输出hash、594个根/17个新增根、797项成员及五阶段
恢复/重载一致性通过。目录为
`verification/out/trusted-srt797-global-parent-20261008-01/`，qualification
SHA为`8333bde0a8c1f5032362882eda934f2d5c670ac34896390678d5d00c8166b776`。

| 797项可信IP整模块口径 | Line | Condition | Branch | FSM | Toggle |
| --- | ---: | ---: | ---: | ---: | ---: |
| 577个根 | 84.62% | 80.46% | 82.45% | 80.74% | 72.81% |
| 594个根 | 84.38% | 80.27% | 81.90% | 80.74% | 72.97% |

该原生报告仍只含797项，不能把其百分比冒充798项的新汇总结果。
原始报告和旧豁免报告均保留。Toggle未达到80%，本目标不是完成，
而是按用户要求在当前批次结束后暂停。不启动下一批激励或修RTL。
