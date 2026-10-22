# Operand requester诊断代码覆盖范围审核

## 为什么单独审核

690项PASS的原始bitmap显示`operand_requester`有较多未命中位置。
这里不能直接认定执行路径覆盖很差：同一个模块中还编译了较大的
`FOR_VERIFY`调试打印和本地探针状态。产品功能覆盖和诊断工具自身
覆盖应分开，不通过开启大量打印来虚增处理器功能覆盖。

## 已完成绑定和盘点

源码`hardware/src/lane/operand_requester.sv`与旧镜像build pin一致：
`327291850e6d77797ab9e67c8d24dd7e8bca9019139d85518b0075fd80f5bca2`。
初步审核范围为620至886行和1098至1140行，包含本地debug状态、
周期计数及`$display`。没有扩展到相邻请求、hazard或VRF仲裁区域。

`inventory_operand_debug.py`依据旧compiled Design及line/branch shape
定位4个lane的精确坐标。行块的表头和每条statement均须位于上述
范围内；branch的各条件定位也须在范围内。跨功能区域的混合块保留。
输出为`verification/out/operand-debug-inventory-690-20261006-01.json`。

| 原始位置类型 | 诊断区域位置数 | 690项中未命中 |
| --- | ---: | ---: |
| line | 3076 | 2152 |
| branch | 1832 | 1424 |
| condition | 3656 | 3648 |

这些是逐实例原始位置计数，不是官方DVE分母或覆盖率提升估计。
六项单元测试验证区域内接受、功能语句/表头混合拒绝，以及branch
混合定位拒绝。当前全部标记`REVIEW_REQUIRED_NOT_WAIVED`。

条件点的独立补充工具为`inventory_operand_debug_conditions.py`，输出
`verification/out/operand-debug-condition-inventory-690-20261006-01.json`。
它重新核对condition shape哈希和实例owner，只接收精确单行定位，
未知或多行定位保留。条件点仍需原生表达式/向量身份核验，不能从
XML编号直接生成DVE排除项。

## 源码非干扰审阅

已逐项阅读上述两个区域。其写状态只有下面5个本地观察变量；所有
引用仍在观察区域中，没有用于计算执行ready、grant、hazard或VRF
写入数据。其余操作均读取功能信号并调用`$display`。

| 观察状态 | 用途 | 执行控制反馈 |
| --- | --- | --- |
| debug_maskb_target_q | 选择MaskB诊断打印区间 | 无 |
| debug_group_hazard_q | 选择分组hazard诊断打印区间 | 无 |
| debug_vfmvfs416_q | 选择标量移动诊断打印区间 | 无 |
| debug_vzext_reshuffle_q | 选择整数扩展重排诊断打印区间 | 无 |
| debug_mfpu_cycle_q | 限制MFPU日志输出频率 | 无 |

`debug_addr_opreq_cycle_q`在这些区域中只被读取以限制打印频率，其
区域外声明/更新不在本次候选中。上述区域没有`assert`、`$fatal`、
`$finish`、请求状态更新或产品输出驱动。此源码审阅支持将其作为
验证instrumentation另行统计，但不是对功能路径的豁免证明，也不
代替独立复核及原生DVE捕获；目前仍没有应用排除项。

## 应用前还要做什么

- 独立确认这些本地debug状态只用于观察/打印，不反馈到执行控制。
- 确认范围内没有需验收的断言、protocol checker或错误终止逻辑。
- 精确绑定原生DVE点和checksum，避免排除整个operand_requester实例。
- 捕获、清除、重载及保留邻点检查；原VDB和assertion运行不变。
- 新统计同时保留raw和排除诊断代码后的结果，明确排除的是验证
  instrumentation，不把它写成硬件不可达或已经测试通过的执行路径。

本轮不修改RTL，也尚未生成或应用这组DVE exclusion。

## 独立复核结果

独立源码审阅产物为
`verification/out/operand-debug-noninterference-review-690-20261006-01.json`，
SHA256为`dba1bc6fc1372f7005e264e7b9b528b7abd7ccc32484abbe7a4e94b570066158`。
审阅逐一核对5个观察状态的写入和所有消费者，结论是无产品执行控制
反馈。4908个line/branch位置的清单中没有空statement/expression列表、
外来文件定位或越出范围的正值branch clause端点。

条件清单另由`test_operand_debug_condition_evidence.py`只读复核：
四项测试全部通过，核对所有输入哈希、四个lane中的坐标唯一性、区域
边界、逐位置checksum及690项原始bitmap中的hit位与计数。
这些检查不产生排除文件，也不证明XML编号等于原生DVE编号。

后续先进行line/branch的精确原生绑定与捕获；condition保持待核验。
即使原生捕获通过，也需完成全集合应用及官方统计后才能报告覆盖率
变化。调试代码可以被实际请求及plusarg触发，因此本项属于非功能
诊断代码的统计范围划分，不能解释为结构不可达豁免。

## Branch 原生验收结果

`operand-debug-branch-native1832-20261006-02` 已完成真实 DVE 原生
导出/重载：1832 个精确 branch 记录一致，五阶段逐叶审计保护1176个
其他分支，initial/reset/final exclusion 文件均为空。
父工作线程独立运行 v5 的 verify 命令及七项解析测试通过。
其中功能默认分支仍受保护；line 和 condition 不因此获得排除资格。

前次全量失败不是 RTL bug：VCS 在 generate 范围的原生 annotation
加入 `requester_index` 标记，旧解析器误拒。修正仅允许与封存编译
`generate_info` 逐项精确一致的前缀，不接受任意 annotation。
原失败目录 `operand-debug-branch-native1832-20261006-01` 保留。

本结果仅完成原生记录资格，不等于已在最新历史集合应用；
`application_approval=false`、`official_denominator_verified=false`。
后续必须核对最新同设计集合及保护点，再应用并取得正式统计。

## 701项完整集合的实际分类结果

完整集合已完成原生应用、逐点保护审计和恢复。父线程通过独立
`verify_operand_debug_1832_product701.py qualify`复核，产物为
`verification/out/operand-debug-1832-product701-parent-qualified-20261006-01/qualification.json`，
SHA256为`25968f6335a1d62b3b6fdbeb69db0b0ae2258a8c7ebcf8c278caf9c4d8ead3f2`。
九项工具测试还验证了缺产品行、名字/层级/指标变化、额外顶层和
错误源码绑定均会被拒绝。

| i_system指标 | 原始701项 | 排除非功能调试branch后 |
| --- | ---: | ---: |
| Line | 82.24% | 82.24% |
| Condition | 81.73% | 81.73% |
| Branch | 81.92% | 83.05% |
| FSM | 60.46% | 60.46% |
| Toggle | 63.08% | 63.08% |

这1.13个百分点来自统计范围划分，不是新增激励命中。1832个目标
中408个已命中、1424个未命中；不将它们称为全部不可达。1176个
邻近功能branch保留，五阶段审计完整，最终排除清单为空，原始VDB
没有修改。原生排除文件可复用，但这里没有混入其他豁免策略。

原运行验收返回FAILED，是因报告缺少一个产品树外的厂商UVM录波
顶层。独立复核核验其精确source、checksum及无子实例，然后要求
全部2988个产品行与无豁免报告逐项一致；不忽略任意其他差异。
原失败状态仍保留。这份分类结果不是当前RTL signoff，也没有给
line、condition或功能默认分支扩展排除资格。
