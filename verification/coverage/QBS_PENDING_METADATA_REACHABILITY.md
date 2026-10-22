# QBS pending metadata路径可达性审查

## 范围与证据

依据690项历史PASS bitmap，对bank1 payload buffer的364个未命中
branch位置重新定位：285行为140个，378行为80个，403行为144个。
378/403是weight/activation side metadata的条件写入，不能把全部364个
点都归类为不可达。

`qbs_payload_buffer.sv`当前源码与封存编译pin一致：
`664916dbe39405b316c1bff5e750d33b3fecffdfaf5a3c6385287d362ca0056e`。
上述位置由封存Design的模块定义、branch checksum `3808980594`
和原始bitmap定位，不使用当前RTL重编译结果。

## 待独立复核的不变量

payload buffer中，side字节由`location.plane == 2`识别。有效且mask
开启的side字节在`weight_consumed_o`/`activation_consumed_o`中无条件
被消费，不参与SRAM word仲裁。adapter计算
`remaining = mask & ~consumed`，保存pending时用remaining替换strb。
因此新接收beat中的side字节不会留到pending beat；重复保存pending
时同样不会增加已消费的字节。reset清空pending valid，clear关闭其有效性。

若上述adapter映射在封存配置下成立，则slot0中的有效side hit为零。
side写入逻辑的`enable = use_newer || (valid0 && older_hit)`退化为
`enable == use_newer`。在enable为真的写入周期，选择older分支没有
正常集成路径的见证。单独payload buffer模块接受任意外部输入时，
该分支可能可达；本证明只针对当前adapter集成，不能跨配置推广。

## 不能立即豁免的原因

- 尚需绑定adapter源码pin、两个bank实例参数及mask/location传播路径。
- XML中的branch vector `id=1`不是布尔值；例子的原生向量为`0101`，
  必须核对其究竟代表哪条条件路径，不能直接把编号1当作older分支。
- 285行payload write分支不属于上述side不变量，继续保留。
- 不排除整个buffer、side写入块或断言，真实newer路径仍需覆盖。
- 应独立验证reset、clear、保存新beat和重试旧beat的所有转移，然后
  精确native绑定、roundtrip及邻点保护后才允许应用。

本审查未修改RTL、未生成exclusion、未运行新仿真，属于待资格核验
的结构候选，不是正式覆盖率提升或已批准豁免。

## 已执行的源码绑定和转移检查

`test_qbs_pending_metadata_invariant.py`四项测试通过。测试首先要求
payload buffer、adapter和compute engine三份源码哈希与旧build pins
一致，再检查side消费、remaining mask、pending strb保存，以及pending
target有效位和注册location的对应关系。

布尔枚举检查有效side位必被消费；64种reset/clear/old-valid/new-beat/
side-mask/payload-remaining组合均保持pending中无有效side位的不变量。
另行检查：若不具备该集成不变量，独立payload模块仍可选择older，
因此不能把豁免推广至任意客户端。

这只是源码绑定的局部代数/转移检查，不是RTL形式证明，也不是一次
处理器仿真。尚需独立审阅整个映射与参数契约及原生branch路径语义；
四项测试通过不等于准许生成DVE exclusion。

## 两个bank的精确清单

`inventory_qbs_pending_metadata.py`已读取两个bank的封存Design及branch
shape，重新核对三份源码pin、metric checksum和完整enable/use_newer
表达式结构。输出为
`verification/out/qbs-pending-metadata-inventory-690-20261006-01.json`。

每个bank的metadata写入路径共672个原始branch位置，其中448个已
命中、224个未命中；两个bank合计448个未命中候选。已命中路径全部
明确标记保留，未命中路径标记`HOLD_NATIVE_PATH_SEMANTICS_REQUIRED`。
只有原生路径语义与上述older-only不变量一致的点才能进入资格审查；
这里没有用XML编号替代原生语义，也没有应用豁免或推算百分比。

## VCS路径编码实测

独立小型`qbs_side_path_calibration.sv`保留同样的嵌套enable/ternary
结构。三次实际VCS运行分别执行disable、older及newer，全部自检通过。
每次dut的3位branch bitmap只命中一个位置，与compiled shape重新
关联后得到：`1000=disabled`、`0101=older_selected`、
`0011=newer_selected`。结果位分别是未写、0x11和0x22。

`check_qbs_side_calibration.py`已核对三次成功日志、shape checksum、
唯一hit及原生branch_vector，证据在
`verification/out/qbs-side-path-semantics-20261006-01.json`。
此校准确认未命中的0101确为older路径，并与adapter不变量一致；
但没有生成DVE exclusion，没有完成处理器448项的native roundtrip，
不能据此宣称豁免已应用。校准VDB不加入处理器PASS集合。

## 最新692集合的复核

`test_qbs_pending_metadata_evidence.py`五项只读检查全部通过：清单及
校准证据的全部输入哈希不变，最新集合精确692个唯一测试，同一
metric checksum下448个older路径仍全部未命中，896个disable/newer
邻点全部保留且仍命中，坐标无重复。新增除法和平方根没有提供违反
该不变量的见证，但“不命中”本身不作为不可达证明。

下一步仍须独立审阅adapter集成不变量及精确DVE native路径绑定。
不直接把清单中的XML id转成排除项，不自动排除896个已命中邻点。

## 独立审阅补充（2026-10-06）

独立逐写入审查认可下述限定不变量：对weight/activation每个pending
字节b，`pending_valid && pending_target[b].valid && pending.strb[b] &&
pending_location[b].plane == 2`恒假。不是所有pending location均非plane2；
消费后的side location/target可以仍留在寄存器中，但其strb已关闭。

四份源码字节均独立SHA256对照
`verification/out/repaired-aligned-build-20260930-01/build-source-pins.json`一致：

| Source | SHA256 |
| --- | --- |
| hardware/include/qbs_pkg.sv | f64946527f9f88608a1ab6fdfb19f9854f932ca0a84fa27f4a1aa55cece5234d |
| hardware/src/vlsu/qbs/qbs_block_adapter.sv | 6038223062242987b6b6064ae85aa875199c5065429202843ac66c99f6336372 |
| hardware/src/vlsu/qbs/qbs_payload_buffer.sv | 664916dbe39405b316c1bff5e750d33b3fecffdfaf5a3c6385287d362ca0056e |
| hardware/src/vlsu/qbs/qbs_compute_engine.sv | a37865b05e1e48e19cfd0a1d75a657e9fc55cdc3adbdd389e17dbd90ddd42ad2 |

源码闭环：compute 324/366行实例参数base=0/4、NativeView=0、
UniqueInputBytes=1；adapter 179行强制PredecodedWriteLocations和
StreamWriteData，payload 76-83行直接采用注册location。adapter
237-254行同步保存ingress beat/target/location，256-282行保持字节
索引映射且pending mask包含strb门控。payload 305-308行令有效side
字节无条件consumed；adapter 160-161行remaining清除该字节。
adapter 285-315行覆盖pending全部写入：reset/clear关闭有效性，
新beat保存remaining并同拍保存对应target/location，旧beat重试仅缩减
strb，不新增有效side。新beat优先于旧beat的同时活动情况同样保持
不变量；无活动时状态保持。ingress reset/clear计数归零使未初始化
storage不可见，首次有效队列项已同步写入三个字段。已保存location
不随profile变化重新解码，因此该论证不依赖假定profile恒定或把
运行断言当作前提。payload 374-378/400-403行因此enable等于use_newer，
enable内选择older的路径不可达。

独立从封存branch shape重新生成完整1344坐标，与690清单逐对象一致，
再对692 bitmap复核：378行每种1000/0101/0011向量160点，403行每种
288点；448个0101全部未命中，896个1000/0011全部命中。检查了同一
generate前缀的enable/use_newer表达式、parent_bit=0/1及条件/ternary
结构（第二表达式type=0、totalbranches=-2），不是用XML编号推语义。
校准三条实际路径提供1000=disable、0101=older、0011=newer证据。
现有9项测试通过，但64组合测试是简化代数模型，不是RTL形式证明。

结论仅针对reset后的正常双态集成运行，不包括X/强制注入状态或
任意payload客户端；不推广配置、不排除285行功能写入或断言。
可进入精确native资格捕获，尚不能批准448项统计应用：仍需处理器
两bank实际DVE叶绑定、export/reset/import/export/finalreset及邻点
保护审计。校准VDB不计入历史PASS集合；本补充不构成新RTL signoff。

## 完整原生资格核验结果

`qbs-pending-native448-20261006-02`已完成真实DVE的
export/reset/import/export/finalreset，服务退出码0。父线程再次运行
`capture_qbs_pending_metadata_v2.py verify`，得到
`QBS_FULL_EXACT_ROUNDTRIP_NOT_APPLICATION_APPROVAL`。

- 精确448个branch目标记录全部匹配，3790个保护点保持不变。
- 全部4238个原生branch向量经过逐点状态审计。
- 初始、reset及final exclusion均为空，原始VDB没有改变。
- 两次导出以解析后的精确原生记录比较，不以文件字节相同代替。
- config SHA256为
  `33ef2f845e91ee8fdac3de5d659fcb3cedd744d22750852c93549113d2903106`。

这只完成原生格式资格，不自动批准应用到聚合报告。正式应用前
仍需绑定最新PASS集合、确认这些目标仍为未命中，并核验实际加载
测试、保护点、原始/豁免/恢复报告及统计分母。当前未宣称豁免收益，
也没有批准condition或其他QBS路径的排除。
