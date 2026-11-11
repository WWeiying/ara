# 阶段5交付：GGML接入、模型回归与固定版本

状态：阶段5有限验收合同完成。五组模型回归、源码恢复和统一输入身份检查通过。
交付标签：`stage5-ggml-resident-20261110`，以该标签的Git对象固定源码组合。
工作目录为 `/home/wangwy/openproject/ara_dsa`，分支为 `ara_dsa`。

## 1. 本阶段交付什么

本阶段将已有的驻留Attention执行方式接入真正的llama.cpp/GGML计算图，
建立原生QEMU指令模型，完成指令、SDK和模型三个层次的检查，并固定可复现的
源码、编译输入、模型和结果身份。没有新增主RTL、扩大SRAM或修改总线，
也没有进行综合、PPA或新位流验收。

新GGML路径仍为显式选择的实验能力，不默认开启。已有QBS投影、普通RVV、
原生AKV、量化KV与不支持场景的fallback保持各自的准入条件。

交付的源码组合是固定版本加已登记的overlay，而不是当前两个脏工作区的混合副本：

| 部分 | 固定身份与用途 |
|---|---|
| RTL/SDK机制基线 | `c49289ff8f433b8780954e207d6b0149f7bc2c32`，阶段4交付 |
| 实际归档SDK | `f50092f2d22238c6be4b6c159a1ad71a4ea68678`；构建配方检查与上述SDK范围的一致性 |
| llama.cpp基础 | `da56aa750559c180d631b466de983ff2bb5d54d9` |
| GGML源码变换 | `stage5/runtime/overlays/prepare.py`，包含经过适配并核对哈希的auto-pair改动和Resident接入 |
| QEMU | QEMU10.2.0基础加 `stage5/delivery/qemu_bundle/`，实际执行镜像为BUILD07 |
| 模型平台提供者 | `stage5/models/final/provider.c`，仅用于冻结测试部署，不是板卡授权 |

本文中的 `stage5/` 均指
`verification/performance/next_mechanism/stage5/`。
`stage5/delivery/manifest.json` 汇总每组模型的原始结果、独立审计、ELF、命令、
模型文件、磁盘、输入清单和SHA256；原始日志及大文件仍保存在清单所列外部目录。

## 2. 接入和安全边界

调用链为：

```text
llama_decode
  -> GGML计算图 / FLASH_ATTN_EXT
  -> RISC-V AKV选择器及平台准入
  -> 原生AKV或Resident SDK
  -> 原生自定义指令
  -> QEMU指令模型；RTL执行证据继承阶段3/4
```

- CMake的 `GGML_RISCV_AKV_RESIDENT` 默认OFF。
- 编译开启后，运行时的同名环境变量为1也只是请求，不构成硬件或内存授权。
- 无可信平台提供者时，在INFO及自定义指令之前拒绝新路径，并保留普通GGML实现。
- 新Resident路由限单worker、单query Decode、F32 Q和F16 K/V，支持D64/96/128；
  同时检查形状、布局、RNE、VLEN、别名、完整访存范围和独占上下文。
- 一次调用在开始计算前固定整次路由，不把已执行部分转到另一条路径重新计算。
  计算开始后的SDK错误为终止性错误；非零VSTART也不伪装成普通fallback。
- Prefill、量化KV和带额外特征的旧路径保留独立授权。不能把量化缓存解释成F16，
  也不能把多个Prefill query行当成Decode的多个head。
- 生产能力查询index4仍为0。测试提供者只对所固定的QEMU/Linux、进程和映射作出
  授权，不能据此声明FPGA普通内存条件或生产部署已经通过。

平台提供者在setup阶段检查真实OS和线程条件，在每次acquire时核查访存范围及映射。
普通私有RAM仍允许合法读写；新增的共享映射放行仅限精确模型路径的 `r--s` 映射，
不能因此授权可写span。其他共享、未知文件或设备映射仍拒绝。
所有权覆盖整次调用，包括内部工作区、Q转换和最后的RELEASE。

## 3. 指令及SDK验证

四组门禁在同一BUILD07上完成：原生AKV定向测试、原QBS测试、阶段4完整调用性能
测试ELF和阶段4功能测试ELF。后两者在QEMU中用于核对功能和状态，不用于测量周期。

| 检查 | 实际完成内容 |
|---|---|
| AKV定向 | 100个使能场景；生命周期、合法性、访存故障、异常值、标志和禁用对照；ROM负例 |
| QBS继承 | 原生QBS指令、合法与非法控制、异常原因和tval，与已有模型契约一致 |
| 完整调用性能ELF | 原封不动的阶段4 ELF，4次调用、1024个结果值及FCSR核对 |
| 完整调用功能ELF | 原封不动的阶段4 ELF，18次调用、2816个结果值及非RNE/CSR检查 |

总门禁结果为
`stage5_qemu_four_gates_20261110_03/result.json`，SHA256：
`d1fe3d705d1caa1923536eff66a6e4fa51030d180e2db01c1724ccc1a4f211d0`。
四组结果均指向同一QEMU二进制SHA256：
`1f4619e1573ed6626b259912d6780ac9d40e8cca8ed38ec32694a0b1d399388a`。

模型使用的完整库构建包含222个翻译单元、776项编译依赖和四个静态库。
编译、汇编与链接使用固定GNU工具链；不使用ZCC。工具、头文件、链接库、
实际编译命令和依赖身份保留在库构建记录中。

## 4. 五组真实模型回归

每组使用同一ELF、模型和输入token，分两个子进程执行Resident请求OFF/ON。
每侧执行一次Prefill和两次单token Decode，输入采用固定真实文本的token前缀，
并在guest内重新核对分词器和前缀身份。两次Decode为相同输入的teacher-forced
对照，不是自由生成长文本。实际上下文容量均为256，不能据此宣称长上下文覆盖。

这里的OFF只是关闭Resident请求，不是关闭所有硬件加速。Smol和Qwen3的Decode
对照仍使用原生AKV，量化KV两侧均使用既有量化Attention。原有AKV/QBS运行开关
和独立provider准入条件仍需满足，不能只设置Resident环境变量。

| 模型与权重 | K/V缓存 | D | Q/KV heads | 上下文长度 | 比较logits数 | 结果与实际路径 |
|---|---|---:|---:|---|---:|---|
| SmolLM2-135M Q4_K_M | F16/F16 | 64 | 9/3 | 63,64,65 | 147456 | 通过；Decode执行Resident，短Prefill保持普通路径 |
| Qwen3-1.7B Q4_K_M | F16/F16 | 128 | 16/8 | 136,137,138 | 455808 | 通过；Decode执行Resident，Prefill保留既有AKV |
| Qwen2.5-1.5B Q4_0 | Q4_0/Q8_0 | 128 | 12/2 | 40,41,42 | 455808 | 通过；原量化Attention路径，无Resident |
| 同一Qwen2.5模型 | Q8_0/Q8_0 | 128 | 12/2 | 40,41,42 | 455808 | 通过；独立检查Q8缓存布局，无Resident |
| Gemma3-1B Q4_K_M | F16/F16 | 256 | 4/1 | 4,5,6 | 786432 | 通过；D256拒绝Resident，原fallback正确 |
| 合计 | | | | | 2301312 | 完整logits、greedy token和CSR对照一致 |

这里比较的是每次API调用的完整词表logits，不是少量抽样元素。检查同时覆盖实际
路由、每层完成次数、QK/PV/context事件和原生QBS入口；不能以软件开关为1代替
执行了快路径的证据。D256和量化KV组也没有被计作Resident正例。

Qwen3开启侧的两次Decode合计56次Resident调用、448个group，实际产生1344条
QK和1344条PV事件。Smol开启侧合计60次调用、180个group，QK/PV各540条。
这些数值是功能与路由证据，不是模型加速比或指令退休率。

Smol原worker因短Prefill期望不正确而FAIL，保留原报告，并通过单独的源码约束
审计验收。Qwen2.5中K为Q4_0、V为Q8_0的那一组，原worker把投影命令汇总误当作
所有QBS调用而FAIL，单独审计核对额外量化Attention命令后通过；Q8_0/Q8_0组
直接使用修正后的检查器验收。原FAIL未改写成PASS。

量化KV每侧为486132条投影命令，加5600条直接Attention命令，严格等于491732个
原生入口。5600来自28层乘184条Prefill命令，再加两次28层乘8条Decode命令；
检查器从冻结SDK的分块调度推导计数，同时核对每层状态和布局，不接受任意额外调用。
QEMU的入口日志在执行之前产生，因此明确取消的TB记录被单独核对并剔除，不声称
这些入口数就是指令退休数。

## 5. 性能结论和默认策略

阶段5模型运行证明集成后的功能、路由和状态一致性，不提供RTL或板上模型速度。
先前阶段3的完整Attention prototype调用为34695对28711周期，即1.20842倍；
它已经包含准备、softmax、归一化和最终排空，但不包含完整模型计算图的开销。

阶段4的M4准备复用在完整投影调用上仅为1.020137倍；带额外特征的Resident入口
在其代表点为1.040052倍，部分小形状更慢。因此不将它们默认推广，也不把这些
局部结果相加或连乘为模型加速比。当前交付保留显式选择与可靠fallback。

## 6. 复现和版本使用

从仓库根目录设置：

```sh
S=verification/performance/next_mechanism/stage5
OUT=/home/wangwy/openproject/ara_dsa_signoff_integration/verification/out
```

恢复GGML源码到新的构建输入目录，不覆盖当前llama工作区：

```sh
python3.11 -B "$S/runtime/overlays/prepare.py" \
  --output "$OUT/stage5_ggml_overlay_delivery_FRESH"
```

SDK从固定Git对象提取；目标目录应预先创建并保持空目录：

```sh
git archive f50092f2d22238c6be4b6c159a1ad71a4ea68678 \
  software/akv software/qbs | tar -x -C "$FRESH_SDK_DIRECTORY"
```

QEMU的独立源码恢复只需原始压缩包、已提交增量包和恢复器，不依赖历史OUT目录：

```sh
PRIMARY=/home/wangwy/openproject/ara_dsa/verification/qbs/qemu/build/qemu-10.2.0.tar.xz
python3.11 -B "$S/delivery/qemu_source_v2.py" reconstruct \
  --archive "$PRIMARY" --bundle "$S/delivery/qemu_bundle" \
  --destination "$FRESH_QEMU_DESTINATION"
```

原始压缩包SHA256为
`9e30ad1b8b9f7b4463001582d1ab297f39cfccea5d08540c0ca6d6672785883a`。
实际完整恢复目录为 `stage5_source_reconstruct_20261110_02`：84955个条目、
78571个文件、6312个目录和72个软链接，内容与权限身份全部匹配，清单SHA256为
`164d0a470c70b2d524956608c7aeb0533ab503b797f749978931838647c1bc56`。
初版解包失败来自两个软链接目标末尾的 `/` 被安全过滤器规范化；V2在完成原安全
检查后保留已认证的原始目标写法，没有放宽最终清单检查，也没有修改源码增量包。
原失败目录和日志仍保留。17项恢复器测试与实际整棵源码恢复均通过，未重新编译。

模型准备使用 `models/final/run.py prepare`；显式传入库prepare/build路径、
库结果SHA、当前源身份及已验收的S3结果。低开销前端由 `models/launch_assets.py`
生成。F16模型使用该launcher，量化KV模型通过 `models/quant_launch.py` 加装严格
量化命令检查器。每次复现必须使用新输出目录，不能在原结果目录重跑或复用旧日志。

例如，在保留本机已验收的外部依赖时，准备一个新的Qwen3对照：

```sh
python3.11 -B "$S/models/final/run.py" prepare \
  --output "$OUT/stage5_models_execution_final_qwen3_FRESH" \
  --case qwen3_f16 \
  --library-prepare "$OUT/stage5_libraries_prepare_20261110_02" \
  --library-build "$OUT/stage5_libraries_build_20261110_01" \
  --library-sha256 f47864d88068b2aec18b7f63c9578d2bfeabd9e59f3fde5c5b0b386ece3b21fd \
  --source-sha256 ba99c06541ecc7e60022bf6531000b7583c935a3ce3a51cf52471d1ea5f288b1 \
  --s3-reader "$PWD/$S/qemu/execution/run_v4.py" \
  --s3-reader-sha256 d416c71665df4fb9995d97563493c2cfc17cd02546bf679d3a5e8cbc9a594d55 \
  --s3-result "$OUT/stage5_qemu_four_gates_20261110_03" \
  --s3-sha256 d1fe3d705d1caa1923536eff66a6e4fa51030d180e2db01c1724ccc1a4f211d0
```

此命令仅准备新输入；还需生成新的quiet launch assets，审核其SHA和prepare/pins
后，通过 `launch_assets.py service-command` 生成直接systemd启动命令。
原始运行的完整命令和资源设置保留在各组 `attempt.json`、`qemu-command.json`、
`launch-assets-binding.json` 及服务记录中。量化组还必须传入清单固定的
quant-launch/checker SHA，不可改用原投影计数检查器。

完整编译仍需清单中的GNU工具链、系统库、Linux镜像、模型和冻结输入。
QEMU源码包不是自包含的Linux/模型/工具链发行版；现有库和模型配方也仍依赖已登记的
外部输入。不能直接删除 `verification/out` 的封存材料后只靠一个脚本重现所有历史结果。

本轮保持单vCPU、guest内存4GiB、宿主进程上限8GiB。低开销模型运行将三个纯诊断
开关置0，但保留QBS汇总、AKV事件与完整logits；guest期限10000秒，直接拥有进程的
systemd服务期限12600秒。首次预测超时而主动停止的冗长诊断运行不计入通过数。

## 7. 最终验收边界

五组模型结果、源身份和整棵QEMU源码恢复已闭合；统一清单的引用哈希、同一镜像/
库/provider契约、阶段4至本阶段的RTL/SDK零改动及发布标签一并核对。
不将本轮结果扩展为任意模型、任意上下文、多worker、FPGA或物理实现的验收。
