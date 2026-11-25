# Resident 板上配对验收

目的：先确认 Resident 在 Linux 中真正完成计算，并且完整 GGML Attention 调用有收益；不加载整模型，不重新综合，不修改 RTL。

## 测什么

| 项目 | 配置 |
|---|---|
| 数据 | 已捕获的真实 Qwen3 Decode Q/K/V/mask，原始有效 KV 为 137 |
| 形状 | D=128，两个 query head、一个 KV head，F16 KV |
| 有效 KV | 65、128、137；前两个为同一捕获数据的前缀回放，不是独立模型捕获 |
| 对照 | 同一 ELF：当前原生 AKV 自动选择 vs Linux Resident |
| 入口 | 当前 llama.cpp 的 `ggml_riscv_akv_flash_attn` |
| 执行 | 每个点 native/resident/resident/native；每进程首调用单列，后三次计入暖态统计 |
| 正确性 | 独立 SoftFloat/算术参考的 256 个 FP32 输出逐位一致、fflags 一致、保护区及输入不变 |
| 路径 | Resident 每调用须成功完成一个 Linux execute；回退原生 AKV 不算 Resident 通过 |

计时包含后端准入、分配、打包、open/ioctl/close、驱动拷贝与保护、计算及结果复制，不含模型加载、GGML 图调度、参考检查和打印。它是算子级完整调用，不是整模型加速比。首调用及进程间漂移同时保留，不能只挑最快一次。

这里的对照不是普通 RVV，而是已经优化的原生 AKV；测的是 Resident 的增量收益。固定源码来自 Git 提交归档，不带入工作区未交付汇编。基准不修改运行时；链接 wrapper 只计数实际 execute 和成功返回，不模拟设备。

## 构建

在宿主机、项目根目录执行，输出必须是新目录：

```sh
python3 verification/performance/resident_deployment/board_pair/build.py \
  --output /home/wangwy/openproject/ara_dsa_signoff_integration/verification/out/resident_board_pair_20261112_02
```

成功后 `board/` 是独立交付目录，另提供 `resident-board-pair.tar.gz`。数据及期望值内嵌静态 ELF；冻结源码、原始输入、构建日志和 source-pins 留在宿主机父目录。`BUILT_NOT_BOARD_TESTED` 只表示构建完成。最初 `_01` 的链接库路径错误已记录；使用成功构建的 `_02`，不要混用。

## 板卡前提

必须先由 FPGA 会话确认：新位流实际含 Resident QK/PV，Linux 和模块匹配，驱动保护/正常内存/缓存一致性契约成立，并已完成模块基础验收。只有一份源码同步记录不够。不能为了通过测试虚报内存条件，不能并发运行其它自定义加速器程序。

驱动的非抢占 F/V 独占、单 hart 和中断保护要求见 `software/llama/platform/linux/README.md`。脚本不自动烧写、不加载模块、不修改 Linux。`--probe` 仅检查设备及 ABI；不证明实际计算正确。Resident 启动后异常应按驱动 fail-stop 处理，不能超时后直接复用未排空上下文。

已有 Linux 6.19.6 候选模块在验证输出根目录的 `resident_deployment_module_20261112_03/module/ara_resident.ko`，SHA256 为 `8c276508542875b0d7b107947399a3eae4386f73659fbc71366aaa946aa444b4`。它不能直接加载到不同版本或配置的板上内核。若需要重建，使用 `software/llama/platform/linux/sdk/README.md` 中的 `Kbuild_norelax` 方法，保留真实计算对象，不能用 stub 替换。FPGA 会话应记录匹配后的内核、模块和位流身份。

将整个 `board/` 传到板卡，确认 ELF 有执行权限。记录实际位流和已加载模块的身份后运行：

```sh
export RESIDENT_PLATFORM_ACCEPTED=yes
export RESIDENT_BOARD_ID='VCU118; bitstream=<actual SHA256>; 50MHz; 4lane; VLEN1024'
export RESIDENT_MODULE_SHA256='<SHA256 of the module actually loaded>'
sh run_board.sh /tmp/resident_pair_01
```

脚本先核对交付文件 SHA256，再探测设备；任一失败立即停止。它不设置强行杀死计算的看门狗。若失去进展，保留串口/内核日志，交由板卡会话按驱动恢复流程处理。返回宿主机后：

```sh
python3 analyze.py /path/to/returned/resident_pair_01 --bundle /path/to/original/board
```

全部功能/路径检查通过后，汇总给出三组实测延迟、加速比和原始样本。收益应大于运行漂移且多次方向一致；如果拷贝/系统调用开销抵消硬件收益，也应原样报告，不把已有 VCS 算术路径收益代替 Linux 实测收益。仅这三点通过不代表所有模型和长上下文均已验收。
