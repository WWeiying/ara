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
| 内存生命周期 | 输入先复制至独立内核RAM；plan、workspace及输出由内核持有；逐页校验物理可达范围，排空后才释放；不把用户指针直接交给硬件 |
| 真实计算能力发现 | AKVINFO index4的版本化编码由实际QK/PV实现支持条件生成，SDK严格解码；旧设备返回0，不启用Resident |

原有用户态provider继续保留，但这条路径不靠它声称`whole_process_ram`或独占所有权。
`GET_INFO`只声明驱动接口和边界，不是硬件能力授权；实际计算前仍查询真实AKVINFO。

## 执行区间与异常

`ara_resident_broker.c`在开始计算前完成分配和`copy_from_user`，然后依次：

1. 持有CPU hotplug读锁，要求只有一个在线CPU且当前硬件hart与部署配置一致。
2. 获得mutex、禁止抢占，调用Linux的`kernel_fpu_begin`和`kernel_vector_begin`。
3. 在IRQ仍开启时完成两个begin，再关闭本地IRQ，建立内核计算所需的RNE、VCSR和VSTART。
4. 执行真正的SDK计算；成功后读向量CSR等待Ara idle，再用`fence`排空写事务。
5. 恢复IRQ、退出vector/FPU区间、恢复抢占并释放锁。只有成功才复制结果。

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
| `ara_resident_uapi.h` | 固定宽度的GET_INFO/EXECUTE接口，无裸内核地址 |
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
