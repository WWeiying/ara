# Resident 调用成本候选：FPGA 测试交接

## 本次改了什么

本次只改软件，不改主 RTL、FPGA RTL、总线或位流。

1. 连续 K/V 不再先复制到用户态打包缓冲区，再复制到内核；直接从原输入复制到内核。
   非连续布局仍按步长打包，mask也取消了多余的用户态复制。
2. 用户态工作区和内核六个对齐缓冲区复用分配容量；输入每次刷新，输出和scratch
   按原要求初始化。不是缓存旧KV，也不跨调用保留硬件任务。
3. Q/K/V的有限F16校验使用整数RVV批量检查，不放宽NaN、Inf、地址或权限约束。
4. 新增可选分段诊断；默认不采样时间。保留每次设备打开、能力发现和安全检查。

例如D128、有效KV=137时，少一次70,144字节的用户态K/V打包。内核仍复制同样的
真实输入。重复形状的内核分配从每次六个降为复用后的零个。这些是减少的工作量，
不是已经测得的加速比。

## 已完成的检查

| 检查 | 结果 |
|---|---|
| 主机与ASan/UBSan | 布局、四种K/V连续/步长组合、刷新输入、重复调用、失败后复用及不发布部分输出通过 |
| 内核准备逻辑 | 6,144种形状、全部65,536种F16数据/mask编码及非法域、别名、能力拒绝通过 |
| Spike RVV校验 | 全部65,536种F16编码、10种长度、150个首/中/尾非法值场景及CSR检查通过 |
| Linux模块构建 | Linux 6.19.6通过，无ALIGN/RELAX加载问题；broker未引入FP/RVV算术 |
| QEMU Linux | 单CPU、双CPU各57项通过；分配复用、错误退出、卸载重载通过。旧QEMU不支持Resident计算，不能据此称数值通过 |
| SoC/VCS真实计算 | 同一个计算对象，真实Qwen3输入，D128/Hq2/KV65；256个FP32输出逐位一致，FFLAGS=3，协议检查通过 |

正向VCS测试实际发出FULL、REFILL、两次QK、两次PV和RELEASE。测试对象SHA与
候选模块中的计算对象一致。身份和证据路径见包内`acceptance.json`。

## 请FPGA会话执行

> 使用当前已验证Resident能力的新位流，不重综合。读取本包`acceptance.json`，
> 将新ELF和新`ara_resident.ko`放到独立目录。保留旧模块、旧ELF和原始结果。
> 确认Linux 6.19.6模块ABI、设备树/固件、单在线hart和RAM契约匹配，停止其他
> Resident用户后正常卸载旧模块，加载新模块`profile=0`，不强制卸载。
> 先跑三个原生AKV/Resident配对点65、128、137；未通过正确性或实际路径检查就停止。
> 不启动整模型，不更换位流，不把仿真时间当性能。

```sh
cd /板上独立目录/board
sha256sum -c SHA256SUMS
uname -r
# 由FPGA会话确认旧模块已安全卸载、设备节点及部署契约正确。
insmod ./ara_resident.ko profile=0
./resident-ggml-pair --probe
export RESIDENT_PLATFORM_ACCEPTED=yes
export RESIDENT_BOARD_ID=实际板卡和位流标识
export RESIDENT_MODULE_SHA256=$(sha256sum ara_resident.ko | cut -d' ' -f1)
sh run_cost_pair.sh /新的结果目录
```

测试仍使用同一ELF、50 MHz、4 Lane、VLEN1024、F16 KV、单worker。
以相同输入、相同检查与旧结果比较，分别给出冷态和暖态数据。首个暖态样本若
仍有明显缓存/缺页影响，要单列，不能直接当稳态结论。

主要结果收齐后，如仍明显偏慢，再正常卸载/重新加载`profile=1`，单独运行：

```sh
RESIDENT_PHASE_STATS=1 ./resident-ggml-pair resident 137 > phases-137.log
```

`PHASE`中列出分配/清零、输入复制、RAM校验、计算调用、输出复制时间以及每次
分配数量和输入字节数。`execute_ns`包括内核状态管理、数值准入及完整Resident
计算，不等于纯RTL时间。诊断增加了计时和ioctl开销，不得混入主要配对均值。

## 验收边界

本候选已通过上述软件、Linux生命周期及RTL计算检查，但**还没有新板测性能**。
只有板测能说明是否已经达到比原生AKV更经济的调用方式。若仍较慢，默认继续
使用原生AKV，不以移除保护检查来换取性能。Resident仍保持可选择开启。
