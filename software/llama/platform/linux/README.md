# Linux Resident Attention 接入

## 为什么使用内核托管调用

Resident利用已装入AKV context的Q/K/V数据，通过共享RVV算术资源执行QK和PV。
普通RVV寄存器的保存恢复不等于AKV私有context的保存恢复。
本实现不让一个未保护的用户态lease跨越多次系统调用，而是把一个完整Decode
group交给驱动：复制输入、获得执行权、FULL、QK、Softmax、PV、REFILL、RELEASE、
等待排空，最后复制输出。需要多个KV tile时，在同一受保护区间内循环。

这是一条新增的可选Linux路径，不替换既有native AKV、量化KV或普通RVV实现。
它解决的是接入正确性，不是已经证明更快的零拷贝优化。复制、分配和系统调用
都可能抵消部分计算收益，因此尚未默认推广。

## 三个缺口如何处理

| 原缺口 | 当前实现 |
|---|---|
| 私有状态跨操作保护 | 一个完整group在内核执行，CPU hotplug读锁、单在线hart校验、全局mutex和禁止抢占共同保护；计算期间关闭本地S-mode IRQ |
| 内存生命周期 | 输入先复制至独立内核RAM；plan、workspace及输出由内核持有；逐页校验物理可达范围，排空后才允许缓冲区复用，设备移除时释放；不把用户指针直接交给硬件 |
| 真实计算能力发现 | AKVINFO index4的版本化编码由实际QK/PV实现支持条件生成，SDK严格解码；旧设备返回0，不启用Resident |

原有用户态provider继续保留，但这条路径不靠它声称`whole_process_ram`或独占所有权。
`GET_INFO`只声明驱动接口和边界，不是硬件能力授权；实际计算前仍查询真实AKVINFO。

## 执行区间与异常

`ara_resident_broker.c`先取得全局mutex，复用或扩展有界缓冲区，完成
`copy_from_user`和RAM检查，然后依次：

1. 持有CPU hotplug读锁，要求只有一个在线CPU且当前硬件hart与部署配置一致。
2. 保持mutex并禁止抢占，调用Linux的`kernel_fpu_begin`和`kernel_vector_begin`。
3. 在IRQ仍开启时完成两个begin，再关闭本地IRQ，建立内核计算所需的RNE、VCSR和VSTART。
4. 执行真正的SDK计算；成功后读向量CSR等待Ara idle，再用`fence`排空写事务。
5. 恢复IRQ、退出vector/FPU区间、恢复抢占并释放hotplug读锁。
   只有成功才复制结果；完成发布或错误收尾后释放mutex。

FP/vector begin/end本身也属于受监控区间。同步内核异常或执行开始后的失败会
进入fail-stop，而不是释放可能仍被硬件使用的RAM，也不会改走RVV重算。
当前不提供故障后的透明恢复；恢复必须确认复位了加速器，不能直接kexec继续。
IRQ-off期间AXI永远不返回的情况，也不能靠普通Linux软件超时解决。

M-mode中断/NMI不受S-mode IRQ屏蔽控制。因此部署必须绑定不干扰该加速器及
FPU/vector状态的固件。本实现拒绝多在线CPU、PREEMPT_RT和preemptive-vector配置；
不是通用多核加速器虚拟化驱动。

## 支持范围

- 一次一个F16 Decode group，1至8个query heads，共用一组K/V。
- D64、D96或D128，1至256个有效KV tokens；超过范围仍走既有路径。
- 有限F16 Q/K/V，mask为有限值或负无穷，至少一个有效元素。
- `0 < scale <= 1`；当前不接入ALiBi、softcap、sinks或量化KV。
- Q/K/V、mask、输出均为明确长度的普通RAM；不接受用户描述符、用户命令列表或内核指针。

这些是首版Linux执行入口的边界，不是Resident RTL的全部能力，也不是模型种类限制。
GGML可以为不同KV heads及分组调用该接口；完整算子的结果全部暂存在私有输出中，
所有group成功后才发布到真实dst。已有任何group执行后，后续失败都是terminal，
不能把“dst尚未发布”当成重新运行整个算子的许可。

## 文件与构建

| 文件 | 作用 |
|---|---|
| `ara_resident_uapi.h` | 固定宽度的GET_INFO/EXECUTE及可选GET_STATS接口，无裸内核地址 |
| `job_layout.h` | ABI、形状、大小、对齐、保留位及地址溢出检查 |
| `ara_resident_broker.c` | 复制、资源管理、CPU/异常保护和结果发布 |
| `sdk/` | 与内核LP64 ABI一致的SDK计算对象及数学实现 |
| `client_v2.c` | 标量系统调用；先检查Linux线程V策略与FD/V/Zfh/Zvfh，再打开设备 |
| `client_rv64.S` | 执行入口的VSTART检查，以及FCSR/VCSR保存和异常标志合并 |

`client.c`是保留的早期检查输入，新的GGML构建使用`client_v2.c`，两者不能同时链接。
client的C接口遵循普通RVV函数调用约定，调用方应以VSTART=0进入；执行汇编入口
另外拒绝非零VSTART。不能把系统调用之前未知的VSTART，宣称为已被之后的prctl检查保留。
独立execute封装成功时合并计算fflags，其余状态按接口约定恢复；不承诺保存全部向量寄存器。

内核模块构建方法见`sdk/README.md`，输出必须独立于开发源码目录。
本轮使用GNU14.3；用户态LP64D静态对象不能混入该内核LP64闭包。
SDK必须从固定归档提取，只覆盖审核过的能力头文件、runtime和原生选择C文件，
不纳入工作区未交付的`akv_v2_attention_rvv.S`。

llama.cpp通过以下显式选项编译新路径：

```sh
-DGGML_RISCV_AKV_LINUX_PORTAL=ON
-DGGML_RISCV_AKV_LINUX_PORTAL_DIR=/absolute/frozen/software/llama/platform/linux
```

运行时`GGML_RISCV_AKV_LINUX_PORTAL=0`仍可关闭。未编译、没有设备、不适用形状或
首次执行前明确拒绝时，保留原实现。不要在未验收设备上先设置假provider。

## 部署约束

驱动仅绑定`pulp,ara-resident-attention-v1`节点，要求实际hart、四lane、VLEN1024、
48位范围内的RAM窗口、已确认的内存一致性及固件保护条件。逐页校验不是只检查
首尾地址。设备树是可信平台描述，不是给任意设备手填几项属性就能获得正确性。

本轮不修改板卡DTS，不加载板卡模块，不更换位流。接入板卡前必须结合具体SoC
确认缓存一致性、物理窗口、S-mode地址翻译及固件条件；不能自动将原来的板卡
配置当成已经满足，也不设置`NORMAL_MEMORY`环境变量绕过准入。

## 验证证据

所有输出位于`ara_dsa_signoff_integration/verification/out/`：

- `resident_deployment_discovery_20261112_020612/`：五个SDK宿主测试、C++、16种VCS配置，1920个SV到真实SDK解码向量。
- `resident_deployment_client_20261112_03/`：6144种布局、非法输入、错误发现、八项OS准入拒绝和无重试检查；另有三个真实RV64/Spike CSR封装用例。
- `resident_deployment_kernel_compute_final_20261112_01/`：真实Kbuild计算对象；6144种准备形状、全部F16/mask编码，以及超过390万个expf输入的逐位和异常标志对照。
- `resident_deployment_module_20261112_03/`：最终Linux 6.19.6模块链接通过；broker无FP/vector算术，计算闭包无未解析libc/libm，不含ALIGN/RELAX重定位。
- `resident_deployment_compute_vcs_20261112_02/`：最终计算对象在真实SoC/VCS上执行真实Qwen3的65-token、双head、D128输入；256个输出逐位和fflags一致。FULL、REFILL、两次QK、两次PV、RELEASE均实际执行，独立协议检查通过。
- `resident_deployment_compute_vcs_sv39_20261112_01/`：相同最终计算对象在S-mode、Sv39及`0xffffffc000000000`高地址别名下再次通过；Q/K/V、mask、scratch、描述符和输出均经高地址访问。256个输出逐位一致，fflags为3；555个MMU请求周期、330对请求/响应，无协议错误、异常或未完成请求。
- `resident_deployment_ggml_20261112_portal05/`：原始GGML适配、ASan/UBSan及四种GNU源码构建配置；`resident_deployment_ggml_20261112_v2_02/`补齐最终client_v2的OS准入及实际native/resident对象构建、标量入口反汇编检查。
- `resident_deployment_linux_smoke_20261112_030729/`：真实QEMU Linux加载最终模块；单CPU和双CPU各42项检查通过，包括ioctl、无效地址、重复调用、客户端CSR及卸载/重载。旧QEMU的INFO4为0，单CPU在真实内核执行区间内安全拒绝，输出不变；双CPU在查询硬件前拒绝。

宿主和Spike检查不冒充Linux执行，Linux模块编译不冒充模块运行，VCS计算对象
验证也不冒充完整Linux内核运行。新接口的复制和系统调用开销尚未测量，不能据此
报告整模型加速。既有QBS/AKV板测版本和原始证据不被这轮结果替换。

### 实际模块加载发现的链接问题

首次真实Linux加载拒绝了部分链接计算对象中的`R_RISCV_ALIGN`。
原因是这些子对象通过自定义规则合并，未自动获得Kbuild的模块`-mno-relax`选项。
修复使用`sdk/Kbuild_norelax`，为全部相关C/ASM对象显式继承模块选项并禁止relax，
不删除重定位来伪装可加载，也不修改内核模块加载器。

当前可加载候选为`resident_deployment_module_20261112_03/module/ara_resident.ko`，
计算对象来自`resident_deployment_kernel_compute_norelax_20261112_01/`。
FP/vector/custom运算指令序列与前版相同，新模块不含ALIGN/RELAX重定位。
新对象另通过`resident_deployment_compute_vcs_20261112_02/`的同输入RTL回归，
256个输出及fflags仍一致。完整模块SHA256为：

`8c276508542875b0d7b107947399a3eae4386f73659fbc71366aaa946aa444b4`

Linux已实际加载并注册该模块。中间测试init曾错误拒绝扩展minor编号，最终
successor改用标准设备号编码，并对5组设备号完成往返与边界检查；原失败记录
保留，不改写为PASS。最终两组Linux各42项检查均通过。

需注意：旧QEMU未声明Resident能力，因此Linux这组结果证明的是实际模块加载、
输入检查、计算前拒绝和执行区间退出，不是Linux中的Resident数值计算。
正向数值计算与高虚拟地址翻译由上述同一计算对象的SoC/VCS测试覆盖；这两类
证据不能合并宣称完整Linux模型已通过。

当前没有遗留的本轮仿真任务。最终源码、计算对象、模块及结果哈希索引见
`software/llama/resident_linux_manifest_20261112.json`。接入板卡和默认开启前，仍需
核对平台契约并测量完整GGML调用成本；本轮未修改板卡环境或原交付版本。

## 调用成本优化候选（2026-11-13）

上述2026-11-12条目描述接入基线及其历史验收，不表示下面的新候选已通过板测。
随后同位流配对板测发现：有效KV为65、128、137时，Resident完整Linux调用
分别约为原生AKV的6.28、7.03、7.05倍耗时。结果逐位正确、Resident实际执行，
但该结果不能用于宣称加速；原始证据位于验证工作树的
`verification/out/resident_board_pair_fpga_20261113_01/`。

当前候选不修改RTL、指令、注意力数学算法或KV容量，只减少调用链的冗余工作：

| 环节 | 当前处理 | 保留的保护 |
|---|---|---|
| GGML K/V准备 | 连续token布局直接作为ioctl输入；非连续布局才打包 | 驱动仍复制到独立内核RAM，不让硬件直接使用用户地址 |
| 用户态分配 | 线程私有工作区复用容量，输出缓存上限64 KiB；更大的合法输出临时分配 | 每次重新转换Q、读取K/V，全部group成功才发布dst |
| 内核分配 | 六个64字节对齐缓冲区在全局锁下复用；形状增长才重新分配 | 输入每次复制；输出和scratch清零；RAM逐页重新检查 |
| 有限数校验 | 用整数RVV批量检查F16指数域 | 不放宽NaN/Inf限制，不引入浮点异常，mask/scale检查仍保留 |
| 成本归因 | 可选GET_STATS及只读`profile`模块参数 | 默认关闭时钟采样；诊断样本不混入主要性能结果 |

这不是把KV永久缓存到硬件，也不是跨调用保留旧输入。原先每次重新打开设备、
检查线程向量策略与ISA、查询驱动能力的步骤仍保留，避免权限或设备状态改变后
误用缓存资格。Resident仍是可选路径，不能因为软件开销减少就默认认为比原生AKV快。

新候选的构建、定向检查、驱动及ELF封存、板测步骤见
[`call_cost/README.md`](../../../../verification/performance/resident_deployment/call_cost/README.md)。
性能主测试使用`profile=0`；另用`profile=1`诊断分配、复制、RAM检查和计算调用。
`execute_ns`包含内核F/V状态管理、数值准入及完整Resident计算，不是纯RTL周期。
后续板测需使用新驱动和新ELF，但不需要为此次软件修改重新生成位流。

## Linux 加速目标与会话复用候选

前述调用成本候选已完成板测：65、128、137个有效KV token的Resident暖态耗时
分别为6.279、7.158、6.925 ms，仍慢于同轮原生AKV的2.218、3.202、2.879 ms。
这是同位流的完整调用结果，不能用设计阶段VCS的1.20842倍收益代替。
板测证据位于验证工作树的
`verification/out/resident_cost_board_fpga_20261113_01/acceptance.json`。

下一步以完整Linux调用快于同轮原生AKV为验收条件，不以“比上一版Resident快”
作为最终目标。设计阶段的17.25%周期减少是参考，不是当前FPGA环境的保证值。

本轮先实现可选择的线程会话复用，设置
`GGML_RISCV_AKV_LINUX_SESSION=1`后，一个worker保留设备FD，不再逐次执行
open、GET_INFO、close。一个group的暖态入口从六次系统调用变为三次：当前
线程策略检查、ISA检查、EXECUTE。系统调用次数减少不等于时间减少一半。
默认不启用这个候选；未设置或设置为0仍使用原来的逐次打开方式。

| 保留内容 | 处理方式 |
|---|---|
| 权限与ISA | 每次重新检查，不缓存线程许可 |
| 硬件所有权 | 仍由每次EXECUTE建立和释放；FD不代表持有硬件context |
| 设备失效 | 驱动逐次检查epoch；执行返回错误后关闭缓存FD，不自动重试 |
| 数值与发布 | Q/K/V重新读取，全部group成功后才发布输出，错误不发布部分结果 |
| 生命周期 | worker退出时关闭FD；卸载模块前退出相关程序，不强制卸载 |

封存候选位于验证工作树的
`verification/out/resident_board_pair_session_20261113_03/`，包含可切换会话模式
的静态ELF和原先已验收的同一模块。111项驱动/计算源码身份一致，未修改RTL、
内核计算对象或数学实现。新增会话测试和原有接口测试在宿主及ASan/UBSan下通过，
真实RV64对象的两条入口保护路径也完成检查；本轮没有重复跑相同计算对象的VCS，
没有连接板卡，尚无新的Linux性能数字。

构建与复测方法见
[`session_cost/README.md`](../../../../verification/performance/resident_deployment/session_cost/README.md)。
原始单入口审计不适用于编译器生成的两条保护路径，已另建双入口审计及反例测试；
早期审计失败记录保留，不改写为通过。

会话复用只减少重复发现成本，不是零拷贝。下面的注册视图候选进一步处理输入
复制和多组head的重复提交；两种候选不能混用模块或验收结果。

## 注册原始KV页与批量提交候选（2026-11-13）

本轮没有修改RTL、FPGA副本或总线，也没有扩大硬件缓存。修改位于本目录的
Linux驱动、客户端和llama.cpp的`linux-resident.inc`，只优化调用与输入管理。

原路径是每次把K/V复制到内核缓冲区，再逐组执行。新路径先注册GGML已有的
KV存储，固定其物理页，建立只读内核映射。后续调用读取同一份数据，而不是
读取另一份缓存副本。用户态在两次调用之间写入的新KV会直接被读取；不需要
另做一次全量同步。Q及mask仍复制到内核私有缓冲区，结果也仍通过安全路径返回。

| 项目 | 新实现与约束 |
|---|---|
| 数据布局 | 保留原始token/head步长；支持head连续或多个head按token交错的布局，不要求先重新打包K/V |
| 地址有效性 | 注册时检查页所在的允许RAM区间，并使用MMU interval notifier；注册与pin过程采用序列检查，任何失效永久撤销该句柄 |
| 数据更新 | 每次读取当前数据，仍做有效元素的有限数检查；不检查其他head或填充间隙中的无关内容 |
| 提交粒度 | 一次ioctl最多提交16组，每组最多8个查询head，共用一次内核F/V状态借用 |
| 中断 | 每个group完成后恢复中断；整批保持不可调度及CPU热插拔保护，不把整批都放进一个禁止中断区间 |
| 发布 | 所有group成功后才复制到用户态私有结果缓冲区；GGML在所有batch成功后才写目的tensor |
| 失败 | 执行前不支持或设备失效可回退；已有group执行后的失败为终止性错误，不重放，不改走原生路径重算 |
| 会话 | 逐线程保留FD和最多32个注册句柄；退出时释放。FD和注册句柄不代表持续占有硬件 |

`copy_to_user`本身不提供原子发布保证：若复制途中缺页失败，私有输出可能只有
前缀被写入。因此不能把驱动描述成对任意用户地址都“全部写入或全部不写入”。
驱动同时拒绝输出或返回描述符与输入范围重叠，GGML通过私有缓冲区保证最终
tensor不暴露部分结果。

### 适用条件

- 显式设置`GGML_RISCV_AKV_LINUX_VIEWS=1`，自动启用线程会话；默认不开启。
- 仍仅支持一个worker、一个online CPU、D=64/96/128、有效KV不超过256。
- K/V地址和步长需满足64字节对齐。GGML的普通CPU存储只保证其自身对齐要求，
  不能假定每个模型的实际KV地址都满足新路径要求；不满足时回退。
- 每个K或V跨度最多1 MiB，最多32个KV head；全局限制为64 MiB的页取整pin计费量，
  不是新增64 MiB缓存，也不等于大页情况下实际保留内存的严格上限。
- 调用期间禁止用户线程、内核、DMA或固件并发改写输入。只读别名和页固定不能
  单独保证源数据不可变。程序还必须管理tensor存储的生命周期。
- 普通私有匿名页、解除映射、权限变化及fork需按生命周期处理；COW导致注册过程
  自身失效时安全拒绝，不能清除失效标志继续使用旧页。

以D128、2个查询head、1个KV head、137 token为例，输入**payload复制量**从
70,930字节变为786字节，仅剩Q和mask。这里不含ioctl元数据；硬件仍要读取K/V，
因此不能把这项减少写成DDR流量减少98.9%或性能提高同样比例。4个KV head可以
从4次执行提交合成1次，但权限检查、数值检查及必要状态保存恢复仍然存在。

### 验证及交接

- 布局/溢出/别名检查在GCC及Clang C/C++、ASan/UBSan下分别通过2,100,202项断言。
- 计算准备包含6,144种原有形状和72种新增步长组合；无关NaN填充、活动数据更新
  和有效区域特殊值拒绝均有检查。
- GGML客户端包含原路径、线程会话、注册视图、批分组、失效、淘汰、失败不重放
  以及不发布部分结果的宿主与sanitizer回归。
- 最新Linux/QEMU在单核及双核各通过552项检查，使用实际页固定和notifier；
  双核安全拒绝执行。QEMU未执行Resident算术，不能据此宣称硬件计算或性能通过。
- 真实计算使用独立的短VCS测试，链接模块中同一个计算对象，检查高地址、4 KiB页、
  打包/交错步长、同一存储更新、输出和fflags，最终状态以该次`result.json`为准。

详细契约、三路径板测脚本及结果汇总器见
[`view_cost/README.md`](../../../../verification/performance/resident_deployment/view_cost/README.md)。
Linux证据：验证工作树下`verification/out/resident_view_linux_v2_agent_20261113_01/`。
板测比较原生AKV、仅会话复用、注册视图三组，分开报告冷态注册和暖态调用，
并额外检查真实数据构造的交错布局及连续更新。未连接板卡、未重新生成位流；
是否恢复或超过设计阶段收益，必须以新的同板完整调用测量为准。
