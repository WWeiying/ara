# 既有优化的进一步接入

## 本轮范围

在 `OPTIMIZATION_ENABLEMENT_20261111.md` 的已测配置上，补命名构建入口、
常见 K 的准备复用、协作 M8 自动选择和 Resident 平台接入。
不扩展 SRAM、不改总线、不综合、不替换板卡位流，不覆盖既有结果。
实际源码在 `ara_dsa` 和 llama.cpp 的 `qbs-activation-context` 工作区，
验证输出只写 `ara_dsa_signoff_integration/verification/out/`。

## 构建与能力查询

新增 `config/llm.mk`，明确选择四 lane、VLEN1024 和已测的 `candidate_all`。
普通 `config=default` 仍保持旧默认；命令行显式关闭单项的行为保留。

```sh
make -C hardware config-check config=llm
```

后续 VCS/DC 目标可使用同一 `config=llm`，并指定独立构建输出路径，
不要复用正在运行的旧构建目录。本轮没有运行 DC。

QBINFO 新增 index5 bit0，表示实际启用的 Q4_K 协作乘法能力。
它来自顶层 `QbsLaneMulSupported`：必须同时满足使能、QBS、四 lane、VLEN1024
和乘法延迟支持条件，再传到 dispatcher。
这不是新计算指令，不改变描述符、布局、舍入或运算流水。
旧 index0/1 的值不变，未知 index 返回0的行为保留；旧硬件对 index5 返回0。
软件参考设备不自行声明协作能力。

ABI 常量由 `config/qbs_abi.json` 和 `scripts/gen_qbs_abi.py` 同步生成。
SDK 在设备查询时读取一次新能力，检查几何、Q4_K 和 M8 布局；
没有该位的新程序保留 M4，旧 SDK 的编译路径也不凭环境变量授权。
新增能力字段要求 SDK 与应用使用相同头文件重新编译，不混用旧静态对象。

本轮构建配置4项检查、生成器一致性检查，以及SDK原有测试均通过。
新增能力宿主测试覆盖32种组合；包级双配置覆盖64个VLEN、两种使能，
逐一比较255个旧查询项。`optimization_extension_capability_20261111_05/result.json`
及独立 `terminal-audit.json` 均为PASS：旧/新镜像的index5及SDK解码分别为0/1，
其余255项逐位相同，旧设备选择仍为0；两次实际CVXIF均310次请求/310次响应，
异常、未完成项和协议错误均为0。
QBINFO不分配后端VID，因此该项采用已有CVXIF-only UVM测试类，不添加伪后端流量，
不改RTL或屏蔽检查；外部仍独立检查程序成功、数值、全部请求/响应及UVM错误。
原通用dut类错误要求本程序必须有VID的失败保留，不改写旧报告。

## 准备复用与 M8 的选择原则

扩展前先比较同一实际 producer 和 value_cache 的 cold+两次命中链路：
K2048使用真实Qwen3激活的前四行；K4096将同一8x2048激活字节重排为4x4096，
明确属于准备链实验，不冒充真实K4096模型算子或模型端到端性能。
检查完整payload、guard、输入身份、异常标志和缓存计数；只有RTL实测正收益的
K才进入默认选择。Spike用于功能，不把它的cycle计数当作硬件性能。

当前已将retained-maxima producer的缓存图准入扩为K1536、K2048、K4096，
仍要求单worker、实际缓存lookup策略、M4准备/packed/parallel sums开启。
不能仅靠K匹配强制进入该路径；关闭任何相应开关仍使用既有实现。

| K | 既有准备及缓存链平均周期 | 新producer平均周期 | 周期减少 |
|---|---:|---:|---:|
| 2048 | 83,123 | 73,146 | 12.00% |
| 4096 | 164,392.5 | 144,680 | 11.99% |

每个形状采用ABBA顺序，单次包含一次cold准备及两次缓存命中。
证据为 `optimization_extension_preflight_framing_audit_20261111_01/result.json`。
原worker因为UART字段间的CSR探针日志插入而判FAIL；独立审计只重组已识别的
8条记录、24个片段，随后重用原严格数值检查，并对未改的完整原日志运行协议检查。
原FAIL和原始日志保留，未重跑仿真，未将原worker重新标为PASS。
请求/响应100,664对且全部排空；数值、CSR、输入、payload和guard均通过。
表中数据是准备及缓存调用链的周期，不是整模型加速。

实际GGML适配层的40次独立GNU/Spike启动检查亦已通过，见
`optimization_extension_preflight_adapter_20261111_01/result.json`。
检查包含自动选择、各项关闭、header未启用、CSR、VSTART、迟到的特殊输入、
分配失败、缓存失效与仅lookup不fill等条件，不通过放宽数值容差取得PASS。

M8使用与已接受M4相同的极值tie规则、量化舍入及block sums，直接产生M8布局。
不采用旧rowwise量化再整体repack的路径，也不在写入部分输出后切换producer。
默认候选限已测Q4_K/K2048、整8行和合适输出宽度，并要求新协作能力。
现有M4缓存或跨算子context已能复用时优先保留它们，避免为减少硬件执行周期而
增加重复量化。多worker、特殊数值或不适用形状保留既有M4路径。
显式旧WIDE_M实验入口与新的受限自动路径分别记录，不混称为同一种数值producer。

`optimization_extension_m8_target_20261111_09/result.json` 已通过38次GNU/Spike
定向启动，以及真实prepared-cache和repack trait检查。
覆盖迟到的非法数值、非RNE、VSTART、大小溢出、输入输出别名、显式关闭和不适用K；
真实repack检查one-shot选择M8、QKV复用选择M4、双worker分块及context复用。
双worker检查使用单核协作barrier，不代表多核并发压力测试。
这些短检查不提供硬件性能数据；原生SDK的M4/M8配对另行记录。
最终K门禁组合另通过 `optimization_extension_m8_joint_20261111_02/result.json`：
实际依赖包含新K门禁及SDK producer，K2048的tag4冷准备和暖命中有效，
实际trait的M8/M4/context布局及guard检查通过。

原生M4/M8配对已通过 `optimization_extension_m8_native_20261111_01/result.json`。
同一ELF使用真实Qwen3数据、M8/K2048/N32、ABBA四次调用，共八条原生命令，
检查74,752字节payload和1,024个FP32输出，以及sticky fflags、guard和借用归还计数。
独立协议核对44,865对CVXIF、33,114对后端请求/响应，AXI读写分别6,450对和12,412对；
异常、未完成项及错误均为0。未改变容差，没有用仿真执行替代原生计算。

| 完整调用周期 | M4 | M8 | 周期减少 |
|---|---:|---:|---:|
| ABBA均值 | 146,836 | 143,821 | 2.05% |
| 各自最短值 | 144,631 | 143,691 | 0.65% |

计时包含准备、能力查询、规划、SDK原生执行和最终fence，排除打印及结果核对。
首个M4存在冷启动开销，不能只凭均值扩大收益判断；两次M8均快于最快M4。
以最短调用比较，M8执行段省4,352周期，但准备段多3,450周期，最终净省940周期。
因此这是小幅正收益，保留受限自动选择，不宣称翻倍，也不取代可复用M4或推广
到未验证的格式/K范围。该one-shot算子结果不是完整模型收益。

## Resident 的真实部署边界

新增 `software/llama/platform/` 为可配置、默认拒绝的平台provider适配层。
它绑定实际镜像、OS、内存生命周期和独占执行保证，不把环境变量、单worker、
进程锁或 `mlock` 当作私有硬件状态保护的替代。
匹配平台可通过已有CMake的provider-source入口接入；无真实binding时继续不编译
Resident，而不是链接空provider导致原本可用的native路径退化为普通实现。

`extension_resident_deployment_20261111_02/result.json` 为
`RESIDENT_DEPLOYMENT_HOST_GNU_CHECKED`：GNU、UBSan和生成bundle分别通过918项，
GNU对象另有标量检查。正例binding是测试替身，不是板卡授权。
原01记录保留；02订正了非必要的“release不得调用内核”文档限制，
允许经过验证、能保持CSR/私有上下文/lease的内核入口，两个GNU对象字节不变。
当前板卡尚缺经核验的Resident私有状态保护与内存/独占租约实现，因此本轮不能
据此宣布Linux/VCU118上的Resident默认已开启。详见该目录的 `DEPLOYMENT.md`。

observe/acquire/release可以使用经证明保全完整CSR、私有上下文及lease的内核入口，
不要求一定避开系统调用；但普通Linux系统调用和标量handler自身并不构成该证明。
不能在尚未确认用户CSR访问安全时，先读CSR再用读到的值证明安全。
最终合同及对象身份检查见 `extension_resident_deployment_20261111_03/result.json`。
03只订正文档和注释，预处理代码及两个GNU对象与02相同；未重新宣称执行918项，
也未将测试替身的正例授权写成真实Linux支持。

## 验收状态

构建配置、能力查询、M4准备及适配器、M8最终组合短门禁、Resident部署合同均已完成
上述限定范围的检查，原生M8配对功能与周期结果亦已完成。
最终源码、SDK覆盖、完整程序哈希与证据索引见
`software/llama/integration_extension_manifest_20261111.json`。

新完整程序位于唯一验证工作区的：

`verification/out/optimization_extension_unified_build_20261111_02/build/bin/`

GNU14.3静态构建的`llama-simple`、`llama-completion`、`llama-bench`均通过独立审计。
审核实际编译依赖中的新能力查询、M4/M8头文件和原生AKV对象；使用固定SDK归档及
四个明确的C/头文件覆盖，八份汇编与归档一致，未纳入本地未交付AKV汇编。
SDK、应用和静态库在同一轮重编译，没有混用旧capability结构对象。

验收记录为该目录的`delivery-successor.json`和`audit2-build-audit.json`。
原配置尝试和原审计的文件名冲突失败均保留；独立successor使用新报告文件名审计
已生成的程序，不改写原FAIL，也没有为了审计再次编译目标。
这证明构建和链接身份，不表示这三个新ELF已跑过完整模型或在板卡上验收。
后续重新构建使用 `verification/performance/optimization_extension/unified_build_v3.py`。
该successor将独立审计清单置于不同文件名，静态自检已复现旧冲突并确认新输出
和消费路径分离；未因此再启动编译或仿真，本轮已封存输入和报告未改。

| 程序 | SHA256前16位 |
|---|---|
| llama-simple | `b2c78376d44d05f9` |
| llama-completion | `84b8dd3be5269ac1` |
| llama-bench | `da3e20f7cd0871ff` |

## 开关与回退

| 项目 | 选择方式 | 未使用时的原因或回退 |
|---|---|---|
| 共享整数乘法器、共享FMA | 硬件使用`config=llm`，单项显式0仍优先 | 普通`config=default`不改；已烧写位流不会因软件配置改变 |
| QBS、AKV、激活context、M4准备及缓存 | 软件使用`cmake/ara-optimized.cmake` | 保留各项能力、形状、类型、生命周期检查和显式关闭 |
| M4 retained-maxima | 自动请求；仅已测K及实际缓存lookup | 不适用时使用既有producer，不强制缓存无复用的输入 |
| 新直接M8准备 | 自动请求；还需QBINFO协作位及受限形状 | 旧硬件查询为0，保留M4；有M4缓存或context复用时也保留M4 |
| Resident | 仅可信平台binding满足合同后可用 | 当前没有板卡binding，不编译provider，不损害既有native AKV |
| Quant KV、Grouped Prefill、Register-PV | 已有条件默认请求 | F16 KV不会命中量化KV路径，普通内存资格仍须独立确认 |
| QBACC、refill overlap、旧Grouped-PV | 不推广默认开启 | 前两者已有完整调用退化证据；旧Grouped-PV与Register-PV冲突 |

M8可通过进程启动前设置`GGML_RISCV_QBS_WIDE_M=0`关闭自动候选。
显式`=1`保留旧实验的rowwise再repack路径，不等同于本轮直接M8 producer。
`GGML_RISCV_ACCEL_AUTO=0`只关闭隐式默认，不覆盖用户另外显式设置的开关。
本轮未替换板上ELF或位流，不能将源码默认请求描述为板卡已经启用全部机制。
