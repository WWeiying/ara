# LZC 补齐节点可达性审核

## 目的和适用范围

将真正的参数不可达点与尚未命中的可达点分开。早期步骤只做结构证明
和诊断；后续已生成原生DVE exclusion并在689项历史PASS集合中核验。
以下过程记录按各阶段证据范围理解，不将早期预检等同于最终验收。

## 最新完成状态

`verification/out/lzc-historical-689-20261006-01/status.json`记录
`RAW_WAIVED_COMPLETE_HISTORICAL_ONLY`，服务正常退出。实际完成：

- 精确180个条件向量排除记录，覆盖120个原生条件表达式组。
- 检查180个邻近保留向量未被排除；没有排除整个实例。
- 初始和最终排除清单为空，raw与reset报告完全相同。
- 原始VDB不变，不重跑仿真，不改变RTL；仅用于历史PASS覆盖集合。

尚有限制：142个保留inventory坐标没有全部逐项原生查询；证明只
适用于二态正常工作，不证明四态初始化。层级百分比刷新及官方分母
变化仍待核查：顶层raw/waived条件为80.60%/80.67%，`i_system`
两份报告均为81.40%。不能据此直接宣称该层级豁免提升多少。

下一组1144个参数关闭operand queue分支候选尚未应用。对689项bitmap
初检发现仅72个点的父scope有匹配metric checksum，其余1072个点的
父scope checksum为null，需从编译shape重新绑定实际metric所在层级。
null不是匹配证据，也不能把该父scope的零位当作不可达证明。

后续只读核查从design ownership追溯实际`operand_queue`定义，发现
这些父scope的branch定义仍属于`srcdef=-18`；genblk子scope是独立
LZC定义，不应将operand branch直接搬到子scope。已报告对689份
原始branch数据重新OR与缓存一致、1144候选均未命中；该核查仍需
封存独立可复验清单。完整原生格式资格目前仅有18点pilot，其余
1126点仍需捕获、精确绑定及回读，尚不具备整体豁免应用证据。

## 689项集合的保留缺口复查

独立重新运行`lzc_padding_candidates.py`，使用封存编译design/condition
shape及最新689项原始bitmap，输出
`verification/out/lzc-retained-689-20261006-01.json`。仍为180个结构
不可达候选和142个保留坐标；保留点中19个已命中、123个未命中。
未命中点包含120个不属于本次internal-OR证明范围的点，以及以下
3个已证明可达的OR组合。它们必须保留，不能因未命中而豁免。

| Lane | 队列 | FP16分量 | raw_index | 树节点(level,index) | 左右OR组合 |
| --- | --- | ---: | ---: | --- | --- |
| 2 | MFPU C | 0 | 8 | (1,0) | 01 |
| 3 | MFPU C | 1 | 8 | (1,0) | 01 |
| 3 | MFPU C | 1 | 28 | (2,1) | 10 |

两种树节点组合的结构见证均为`in_tmp=0x10`。由于实例MODE=1，
WIDTH=10，反转后的真实FP16尾数是`0x20`。gap80全lane模式仅测试
尾数0、1、2、3、最高两位及全一，没有测试该中间单比特。
这给出可证伪的激励假设，而不是已命中结论：先核对请求到MFPU C
的路由及物理分量，再独立Spike自检和旧镜像定向运行，最后比较同一
scope/metric checksum/raw_index是否由0变1。不得按输入模式推算增量。

gap83已实测补齐上述3个OR缺口。对690项bitmap重新绑定编译shape，
输出`verification/out/lzc-retained-690-20261006-01.json`，保留坐标
22个已命中、120个未命中。剩余120个全为第95行左子树selector，
optype16/23各60，truth table为01，缺少的是vector1。逐generate
坐标核对WIDTH10/23结构证明，120个节点的左子树均没有真实输入，
对应sel_nodes恒零，因此selector为1在二态正常工作下不可达。

进一步拆分后不能直接将120个点视作同一种原生豁免：optype16的
60点是精确的布尔比较，已完成结构候选与编译shape绑定；optype23的
60点记录整个ternary表达式，必须先证明DVE的vector1表示选择条件
为真，而非输出数据位为1。工具`lzc_selector_candidates.py`把后者
标为`HOLD_TERNARY_NATIVE_SEMANTICS`，不自动批准；八项测试通过，
包括可达左子树保留、源/表达式/真值表错绑拒绝。实际输出
`verification/out/lzc-selector-candidates-690-20261006-01.json`。
既有native tree显示selector与ternary的ID并非直接对应XML顺序，
因此不得用XML condregid直接生成原生排除项。

这是一组新的结构候选，不是已应用豁免：仍须独立重建selector表达式
身份、核实DVE各selector/ternary原生ID和向量顺序、捕获回读并检查
保留邻点；不能复用第93行OR的原生condition ID或原180点排除清单。

审核对象是 common_cells 的 `lzc.sv`，源文件 SHA256 为
`f31989be4369ea7c4809c0c3d61df28581e9ac7666005fde6e476a975d1acd07`。
工具遇到其他源文件版本会拒绝执行。

## 结构证明

LZC 将 WIDTH 个真实输入放入向上取整的二叉树。叶节点超出 WIDTH 的
部分恒为零。内部节点的 `sel_nodes` 等于其子树真实输入的 OR。
MODE 只改变真实输入的排列，不改变存在多少真实位。

以内部节点 `(level, index)` 表示 generate 坐标；下面的二位组合依次
是左、右子树的 OR，不是未经核实的 DVE condition vector 编号。

| WIDTH | 内部节点 | 不可能的左右组合 |
| --- | --- | --- |
| 10 | (1, 1)、(2, 2) | 01、11 |
| 10 | (2, 3) | 01、10、11 |
| 23 | (1, 1) | 01、11 |
| 23 | (2, 3)、(3, 6)、(3, 7) | 01、10、11 |

其他内部节点的左右子树均有真实位，因此 00、01、10、11 都能构造出来。
工具为每个可达组合给出 `in_tmp` 位模式见证；不能仅凭某组测试未命中
就将这些节点豁免。整个证明采用二态输入，不证明初始化期间的 X/Z 行为。

## 校验与剩余工作

```bash
python3 -B -m unittest discover -s verification/coverage \
  -p test_lzc_padding_proof.py -v
python3 -B verification/coverage/lzc_padding_proof.py \
  --source hardware/deps/common_cells/src/lzc.sv --width 10 --width 23
```

五项单元测试通过：独立按 RTL heap 子节点关系重建位范围和完整坐标、
WIDTH10 全部 1024 个输入、WIDTH23 可达见证、二次幂宽度无 padding、
非法宽度拒绝。已运行源文件哈希绑定的证明命令。
证明仅覆盖 `g_not_last_level` 的内部 OR 和左子树选择条件，不包含最后
一级的 `g_reduce/g_base/g_out_of_range` 叶节点赋值或 index 数据结果。

应用豁免前仍必须完成：映射原生 DVE 条件表的表达式和向量顺序，绑定
精确 instance/metric checksum/leaf identity，核对旧镜像参数及源清单，
独立审核并执行原生 exclusion roundtrip 和保留邻点检查。
历史剩余 305 个 LZC 条件缺口不能直接全部排除。

## 与 685 项覆盖坐标的诊断绑定

`lzc_padding_candidates.py` 将已有 source inventory 的 MFPU LZC 条件点
与 gap79 bitmap 对齐。仅接收匹配源哈希、WIDTH checksum、generate 坐标、
第 93 行内部 OR 表达式、optype=13 以及三行二列 `000110` 条件表的点。
遇到 checksum、row/vector 或覆盖命中与证明矛盾时拒绝；不认识的条件保留。

本次实测得到 **180 个结构不可达候选、142 个保留坐标**。这里遍历的是
历史 inventory 中的目标坐标，部分保留坐标已被新增测试命中，因此这些
计数不能替代最新剩余缺口数量，也不能换算成覆盖率提升。
结果在 `gap79-old-image-20261006-01/lzc-padding-candidates.json`，绑定
inventory、bitmap、源文件哈希；没有生成 native exclusion 文件。
配套六项负例/保留逻辑测试通过，连同结构测试共 11 项通过。

独立审核随后发现工具未主动重建 `raw_index` 的完整 native 身份；实际
清单没有错绑，但修改坐标的负例会逃过检查。已从编译后的 design/cond
shape 重建每个 scope 的点，逐项比较 native_id、file_id、表达式、属性、
spec、truth table、row 等全部字段，增加身份及坐标错绑拒绝测试。
共 13 项测试通过；对 685 项的 shape-bound 复算仍为 180/142，结果另存
`lzc-padding-candidates-shape-bound.json`，未覆盖原诊断结果。
142 个保留坐标中 17 个已命中、125 个尚未命中。

180 个点仍须独立审核原生 DVE 的输入列顺序、具体 leaf identity 和二态
适用范围。只有完成精确捕获、roundtrip 和保留点检查后，才允许应用。

## 原生条件树导出

使用已计入 685 项集合的 `vgap79_add16`，对 lane0 MFPU A 的第一个
FP16 LZC scope 做一次只读 DVE 导出。原生条件树得到 36 行，输出在
`verification/out/lzc-native-discovery-20261006-01/native-condition-tree.csv`。
没有选择排除项或保存 exclusion，不修改原始 VDB。

启动脚本误查 stdout，记录为 FAILED；实际 DVE GUI 日志包含
`LZC_READ_ONLY_DISCOVERY_DONE 36` 和 `DVE_COVERAGE_EXPORT_DONE`。
独立后处理 `verify_lzc_discovery.py` 已校验全部输入哈希、CSV 表头/行数/
路径唯一性、一个 selected test 和 GUI 完成标记，生成
`discovery-verification.json`。保留原失败状态，不重复运行 DVE。

这只证明条件表达式树成功导出；表达式树不是 truth-table vector 的
逐行资格证明，不能用 36 行推算 180 点已获豁免资格。

进一步的只读 vector 控件导出另存 `lzc-native-vectors-20261006-*`。
第一次因 DVE 内嵌 Tcl 不支持 `lassign` 而终止，尚未读取任何向量行；
将其改为兼容的 `lindex` 后启动独立 02 会话。两次均不排除覆盖点，
成功与否以 GUI 完成标记和后续逐行核验为准，不由进程退出码单独决定。

02 会话在条件选择阶段终止，DVE 对 Condition 的 selected 返回格式与
此前 Branch 的 flat 格式不同。依据它自动保存的 `session.tcl`，改为
`-first` 后取第一项再 unselect，03 会话继续只读导出。所有中断均保留
原日志，不生成 exclusion，不计入正式覆盖报告。

另一个重要限制：原生表达式树的部分 selector/ternary ID 与 XML
`condregid` 并非按表达式一一对应；第 93 行内部 OR 已核对一致。
不能据此推广到其他条件，后续必须按完整表达式和 truth-row 绑定。

## 单向量原生捕获的验收结果

`verification/out/lzc-native-singleton-20261006-03/` 已完成一次精确原生
捕获及保存、清除、重载、再次保存、最终清除。使用的是已验收的
`vgap79_add16` 子集，仅验证 exclusion 文件格式和行为，不是总集合报告。

实际排除对象为 lane0 MFPU A 的 FP16 LZC，内部 OR 节点
`(level=1, index=1)` 的 `01` 向量。其右子树恒零，因此该组合不可达。
原生向量 ID 为 **2**，不能将 XML row 或 raw_index 当作原生向量 ID。

后处理已确认以下证据：

- `first.el` 与 `second.el` 解析后完全相同，恰好一个条件向量记录。
- 与最新 687 项的 native-bound 候选逐项匹配 instance、module/metric
  checksum、condition ID、表达式、点 checksum、width、bit 和向量。
- 三份 empty exclusion 文件均为空；全部七个输入文件哈希保持不变。
- GUI 日志按顺序显示 before/reset/final 的 target=0、selected/reloaded
  的 target=1；邻近可达 retained 向量始终为 0，即未被排除。

最新完整候选另存于
`gap80-old-image-20261006-01/lzc-padding-candidates-native-bound.json`，
仍为 180 个结构不可达候选、142 个保留坐标。
本次仅验证一个向量的原生捕获与回读；不能据此认定其余 179 个点已
完成原生验收，更不能认定总覆盖率已应用豁免。完整捕获、独立审核和
687 项集合上的正式汇总仍待完成。

可复验上述单点证据的命令如下；输出文件必须是新路径：

```bash
python3 -B verification/coverage/verify_lzc_singleton_artifacts.py \
  --capture verification/out/lzc-native-singleton-20261006-03 \
  --candidates verification/out/gap80-old-image-20261006-01/lzc-padding-candidates-native-bound.json \
  --output /absolute/new/artifact-verification.json
```

已有证书是该 capture 目录中的 `artifact-verification.json`。对应五项
测试验证真实回读和额外记录、清除残留、GUI 状态缺失、pin 篡改的拒绝行为。

## 全集合准入的源码绑定限制

687 项离线准入实测通过原始 650 项检查，随后在历史 gap65 recovery
receipt 的源码哈希检查处拒绝。三个源码文件的当前工作区内容已变化：
`ara_dispatcher.sv`、`lane/lane_sequencer.sv`、`sldu/sldu.sv`。
这不是新的测试失败，也不能通过修改原 receipt 哈希解决。

已在主工作区找到三份与旧编译 pin 及原 receipt 精确同哈希的源码，
复制到 `verification/out/old-image-source-evidence-20261006-01/`，逐项
记录 `manifest.json`。没有覆盖当前 RTL。该副本仅是历史源码证据；
准入工具仍须审核如何绑定原 pathname 与副本，并核验其他全部证据，
才能继续正式豁免汇总。单凭找回三份源码不能声称全集合准入已通过。

`old_image_source_snapshot.py` 已独立检查这些副本。工具只接受上述三个
源码路径；编译 pin 文件和历史 receipt 本身也绑定固定 SHA256，防止
同时修改副本与 manifest 后伪造匹配。哈希和 JSON 解析使用同一次读取
的字节，并在结束时复验文件身份和目录拓扑。六项测试覆盖真实三文件
匹配、扩大白名单、路径越界、字节变化、符号链接，以及验证过程中
文件被同内容新实体替换时的拒绝行为。

```bash
python3 -B verification/coverage/old_image_source_snapshot.py \
  --snapshot "$PWD/verification/out/old-image-source-evidence-20261006-01"
python3 -B -m unittest discover -s verification/coverage \
  -p test_old_image_source_snapshot.py -v
```

该工具仅输出历史字节绑定，不改变准入检查的读路径，也不使失败的
全集合检查自动通过。接入准入流程前仍须独立审核精确源码映射。

## 全量原生捕获预检

`capture_lzc_batch.py` 对实际 687 项证据运行 `load_evidence` 及最终
重新哈希已通过：180 个目标、262 组 scope/条件表达式、142 个保留坐标、
140 份已绑定文件。加载样本是已验收的 `vgap79_add16`；此步没有启动
DVE，也没有改动覆盖数据库。

原生状态查询还有一个必须排除的歧义：
`gui_exclusion -excluded -selected` 的多选返回值不能未经实测就当作
排除项数量。应逐向量选择并确认身份，再单点查询，累加核验结果；
目标和保留邻点均如此。mock 测试不能自行定义“返回数量”后据此证明
真实 DVE API。完成该修正及原生验收之前，不应用全量 exclusion。

逐向量修正后的 17 项测试通过，包含两个目标中的一个未排除时必须
拒绝的测试。原生格式捕获已独立启动为用户服务
`ara-lzc-native-batch-20261006-01.service`，输出目录为
`verification/out/lzc-native-batch-20261006-01/`。启动检查确认真实 DVE
进程存活，指定旧设计和单项 PASS 样本已加载。完成仍须检查原生
180 记录回读、清除残留及邻点完整审计，不能以启动成功代替验收。

该 01 会话随后结束为 FAILED。GUI 根因是保留坐标中部分 selector
表达式无法按 XML 名称在原生条件列表选中；不是处理器测试失败。
独立核验 `initial-empty.el` 和 `final-empty.el` 均为空，`first.el` 尚未
生成，未保存任何目标排除。原始失败目录和日志保留，不计为成功。

下一次捕获仅对有批准目标的第 93 行 OR 表达式查询全部相邻向量；
其他保留条件不猜测原生名字。142 项完整保留清单仍须静态重新绑定，
并由 first/second 文件严格仅含批准 180 向量、无其他记录来证明没有
误排除。原生邻点审计与完整保留清单的检查范围必须分别报告。

第二次捕获 `lzc-native-batch-20261006-02` 已正常结束。主会话离线
`verify()` 和独立只读审核均确认以下结果：

- first/second 各 180 条，完整解析记录一致，包括实际捕获的 vector ID。
  两份文件字节顺序不同，不能宣称文件 SHA 相同。
- initial/reset/final exclusion 均为空；五轮审计恰好 600 行。
- 36 个 compiled scope 的签名、shape 和结构证明一致；只加载一个
  已验收样本，未混入其他测试或镜像。
- 142 项保留 inventory 由完整离线绑定和 `.el` 无额外记录保护，不是
  逐项 GUI 查询；原生邻点审计包含目标表达式的 180 个可达向量。
- 独立复核 status 中声明的 155 个 pins，全部匹配。

资格范围仅为该旧镜像的原生格式及 roundtrip 捕获。工具封存仍有
缺口：当次记录了 `bin/dve` wrapper，未在运行前封存实际 `dve.exe`。
不得事后补哈希后冒称已经证明当次运行前身份。后续正式应用必须
补齐实际工具链封存；此外，full687 准入仍有 checker 版本冲突。
因此没有应用到正式 687 项汇总，也没有产生 aggregate 批准记录。

后续工具身份准备已新增 `dve_tool_identity.py`。在本机实际运行
`prepare`/`revalidate` 通过，记录 launcher、xvfb-run、getarch_dve 与
`gui/dve/linux64/bin/dve.exe` 四个文件。支持验证观察到的 DVE 子进程
`/proc/PID/exe`，不能把 wrapper PID 当作实际 DVE。十三项测试覆盖正常
封存、字节变化、同内容实体替换、非 ELF、缺失架构脚本、错误 PID、
空/不完整记录、角色/环境篡改、可执行文件重定向、启动参数以及本次
启动的子进程身份。live 正例使用真实非 EDA 子进程验证 `/proc` 机制，
不能据此声称已验证新的 DVE 运行。
它没有接入正式 aggregate runner，不追认此前运行，也不宣称完整
动态库封存。正式使用前还须独立审核及运行前/后调用，不能只导入
辅助模块就声称工具身份闭合。

独立审核发现的两项缺陷已修正：环境构造清除 DVE/VERA 重定向、
QADEBUG 和相关注入变量，并固定 coverage 启动参数；重验要求四个
角色及全部文件完整、路径/环境与 launcher 推导一致。进程检查必须
绑定本次 launch PID 和 starttime，核验祖先链及前后身份，不能选择
另一份既存 DVE。完整 record 仍须由调用方封存 SHA 并必经检查。

```bash
systemctl --user status ara-lzc-native-batch-20261006-01.service --no-pager
```

只读 `bwrap` 私有路径视图已实测可用。把三份精确旧源码仅映射到
该子进程的历史路径后，原始 helpers 无需修改即可读取旧字节；磁盘
当前 RTL 不变。该视图下再次 full687 检查通过原始 650 项阶段，随后
拒绝历史 receipt 中 `verification/ara_verify/spike_trace.py` 的哈希。
这说明还有比较工具版本冲突，不能把它当作第四个 RTL source 顺带
放行。仍需找到精确旧 checker 并评估检查语义，全集合准入尚未通过。

## 当前精确记录复核

父会话重新用`lzc_native_records.parse_records()`解析batch02的
`first.el`与`second.el`，确认180条记录排序后完全一致，三个清空阶段
文件均为空。随后实际执行`bind_records()`，将全部记录与gap80的
`lzc-padding-candidates-native-bound.json`逐项绑定，检查通过。
没有整instance排除或额外向量。此复核不追认旧DVE执行文件的运行前
身份，也不表示已应用到全集合。正式汇总应保留raw报告，并单独生成
使用精确180条记录的waived报告及保留邻点检查证据。

## 689项历史集合的实际应用任务

独立`apply_lzc_historical.py`及Tcl hook已实现并通过10项测试。
实际prepare重核native180记录、结构候选、旧参数源码、保留坐标及
689项唯一成员；manifest SHA为
`bb4bfae5bac62dcb4d08e4407b3c349204a288245ddb1a3a5bc893d7532de6f8`。
服务`ara-lzc-historical-689-20261006-01.service`已启动，父会话确认
PID2346438及本次DVE运行身份记录存在。输出目录为
`verification/out/lzc-historical-689-20261006-01`，日志为`service.log`。

该任务只对旧镜像历史PASS集合生成raw/waived/reset对照。它不依赖
201项当前checker诊断通过，不签发新RTL signoff或旧receipt。
证明域是正常二态运行；所有真实输入位模式均允许，不把仅未命中的
可达向量豁免。初始化四态行为不在结构证明范围内。
正式结果仍须核验精确180原生记录、邻点保留、raw/reset一致和工具
及输入前后身份；启动本身不等于豁免已完成。
