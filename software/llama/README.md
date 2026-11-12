# llama.cpp 的默认优化配置

本配置面向明确支持QBS/AKV的Ara目标，不用于任意RVV处理器。
普通llama.cpp构建不变；选择 `cmake/ara-optimized.cmake` 后，应用不再需要逐个
设置性能开关。格式、维度、布局和设备检查仍由原后端执行。

## 默认策略

| 项目 | Ara配置中的默认行为 |
|---|---|
| QBS投影 | 开启；保留格式、形状、布局及设备检查 |
| 激活上下文及跨算子复用 | 开启；保留原身份和生命周期检查 |
| M4准备、packed布局、parallel sums、prepared cache | 开启；K1536/K2048/K4096适用缓存图另选retained-maxima producer，其他形状保持原实现 |
| 原生AKV | 开启，自动选择原有内核；不支持时走普通GGML |
| 量化Attention、Grouped Prefill、Register-PV | 默认请求开启，但仍需原有准入和独立的普通内存确认 |
| Portable Decode | AUTO仅为原路径不支持的特征或大query分组选用；普通plain路径不强制切换，显式0优先 |
| QK PANEL4 | SDK native-auto对F16、D128、6行query、KV长度至少128且能力匹配时选择；显式0优先 |
| 新Resident Decode | 仅在编译了可信provider的版本中自动请求；默认筛选D128、每KV两行query、128至256个有效token |
| 其他Resident形状、特征或平台条件不满足 | 保留原生AKV或普通实现，不强制进入Resident |
| 直接M8准备及乘法协作 | 受限自动候选；要求真实协作能力、Q4_K/K2048及合适形状，现有M4缓存或context复用优先 |
| 仿真执行、普通内存授权、详细诊断 | 不默认开启或声明 |
| worker数量 | API与common应用的未指定线程数默认为1；显式参数仍有效 |

Resident筛选范围是根据现有收益和验证范围制定的保守软件策略，不是硬件最大能力，
也不承诺范围内每个形状都有固定加速比。没有provider源码时，Resident编译选项
仍默认OFF，避免一个空provider使原来可用的AKV整体回退。提供者必须自行满足
其初始化和授权契约；不能把阶段5的固定QEMU测试provider直接当成板卡授权。

`GGML_RISCV_AKV_QUANT_KV_NORMAL_MEMORY` 不由此配置自动置1。只有运行环境确认
内存条件后才可显式设置，不能为了让计数变高而跳过检查。

## 构建完整程序

下面使用当前扩展已审核的冻结源码和SDK，包含PANEL4及协作能力查询，
不包含当前未提交的AKV汇编：

```sh
export ARA_SDK_ROOT=/home/wangwy/openproject/ara_dsa_signoff_integration/verification/out/optimization_extension_unified_build_20261111_02/inputs/sdk
LLAMA_SOURCE=/home/wangwy/openproject/ara_dsa_signoff_integration/verification/out/optimization_extension_unified_build_20261111_02/inputs/llama
cmake -S "$LLAMA_SOURCE" -B /path/to/FRESH_BUILD \
  -C "$LLAMA_SOURCE/cmake/ara-optimized.cmake" \
  -DCMAKE_TOOLCHAIN_FILE=/home/wangwy/llama/platforms/cva6-qemu/toolchain-rvv.cmake
cmake --build /path/to/FRESH_BUILD \
  --target llama-simple llama-completion llama-bench --parallel 8
```

这些是完整llama.cpp程序，而不是独立算子测试。构建使用固定GNU工具链，
采用 `-fno-fast-math -ffp-contract=off` 保持已验证的数值约束。
不重用带有旧cache值的构建目录，以免旧OFF选项遮蔽新配置。

若已具备对应硬件与可信部署provider，可额外传入：

```sh
-DGGML_RISCV_AKV_PROVIDER_SOURCE=/path/to/reviewed_provider.c
```

这会使新的构建默认包含Resident支持，运行时仍须通过完整provider准入。
显式设置 `-DGGML_RISCV_AKV_RESIDENT=OFF` 可以阻止其编译。

## 运行与关闭

部署到匹配目标后，默认运行即可，不必再设置QBS/M4/AKV性能环境变量：

```sh
/path/to/FRESH_BUILD/bin/llama-simple -m model.gguf -n 32 'Hello'
```

显式关闭单项仍优先于默认值：

```sh
GGML_RISCV_AKV_RESIDENT=0 /path/to/program ...
GGML_RISCV_QBS=0 GGML_RISCV_AKV=0 /path/to/program ...
```

`GGML_RISCV_ACCEL_AUTO=0` 关闭隐式选项，不覆盖用户已经显式设置的其他开关。
进程稳定缓存的准备策略需要在程序启动前设置；运行中改变环境变量不作为受支持用法。
`llama-bench`具有自己的线程参数，测量当前单worker机制时仍应显式传入 `-t 1`。

## 实现和验证入口

- `accel-options.h` 为默认策略源；llama中的同名头文件必须保持字节一致。
- `test_accel_options.cpp` 检查显式覆盖、默认范围及不授权平台/内存的边界，
  并确认未知诊断开关不会增加master环境变量查询。
- `run_auto_model_v2.py` 与 `auto_model_init.c` 使用实际构建的完整 `llama-simple`，
  在原生QBS/AKV QEMU中比较手动开启与不设置性能开关的两侧运行。
  相同SmolLM2模型、相同文本、每侧两步输出，逐位比较98304个logits，
  并要求QBS原生工作量和AKV执行计数一致。结果以独立输出的result.json为准。
- `provider_link_fixture.c` 仅用于强符号链接检查，始终拒绝平台授权，不是部署provider。
  静态链接通过OBJECT及传递对象依赖引入实际provider，而不是期待链接器从普通
  archive member中抽取一个已经被弱符号满足的实现。该可选构建需要CMake3.21以上。
  应使用生成的完整程序；裸静态库或安装包的第三方链接不在这项检查范围内。

这项新增检查验证默认策略的接入，不替代阶段5五模型验收，也不代表新FPGA性能。
阶段5原标签和原始证据保持不变。本轮llama工作区还包含原有未提交修改，
不能将当前工作区未经区分地称为阶段5标签对应的干净源码。

## 2026-11-10 的既有检查结果

实际完整程序位于：

`/home/wangwy/openproject/ara_dsa_signoff_integration/verification/out/llama_auto_build_20261110_01/bin/`

- `llama-simple`、`llama-completion`、`llama-bench` 均完成RISC-V静态编译和链接。
- AUTO开启、关闭、宏未定义三种策略配置各通过32322项检查。
- `llama_auto_model_20261110_02/result.json` 为
  `FULL_LLAMA_DEFAULTS_MODEL_CHECKED`；相同完整程序手动/默认两侧的98304个logits逐位一致。
- 每侧QBS原生命令17538条、仿真命令0条；AKV实际完成30个Decode算子、90个group，
  两侧工作量相同。短Prefill的30次size fallback保留，不将其算作加速命中。
- 可选provider构建通过，最终ELF的两个provider hook为强符号，QK/PV叶函数存在，
  provider对象直接到达最终链接，没有依赖弱符号已经满足后的archive抽取。
  此fixture拒绝一切授权，未作为部署provider运行模型。
- 原第一次smoke在执行编译器前失败：直接解析Buildroot wrapper的真实路径破坏了
  它依赖的argv[0]别名。V2保留正常gcc调用路径；原失败记录未删除。

源码及程序身份见 `integration_manifest_20261110.json`。当前没有替换板上ELF，
没有改主RTL，也没有将这些工作区修改自动提交或推送到llama仓库。

## 2026-11-11 的补充验收

逐项决定和证据范围见
[`OPTIMIZATION_ENABLEMENT_20261111.md`](../../hardware/docs/OPTIMIZATION_ENABLEMENT_20261111.md)。
上节程序和 `integration_manifest_20261110.json` 是保留的历史交付，不能代表后续源码。

- 默认策略新增M4 preflight请求；普通构建不变，专用配置编译开启。
  16个GNU/Spike启动检查数值、packed bytes、缓存失效、CSR和拒绝条件。
  真实Qwen2.5图中，330次新producer实际进入、498次tag4缓存命中；
  OFF/ON的303872个FP32 logits逐位相同。原日志分帧错误保留为FAIL，
  独立、绑定日志哈希的审计通过；不是改写原结果。
- PANEL4当前RTL的OFF/AUTO对照通过，代表性D128/GQA6/KV128完整SDK调用
  周期减少6.47%。这是该形状的RTL结果，不是全模型或任意上下文的加速比。
- Portable条件默认通过选择、GGML宿主数值、GNU/Spike和真实Refact模型对照。
  原生路径实际完成32个Decode算子、128个group；两侧token一致，Prefill logits逐位一致。
  Decode非逐位相同，KL为0.00553、最大logit绝对差为1.234；
  满足该次预设数值门槛，不等于广泛模型精度验收。
- 全组合硬件通过真实VMFPU和代表性SoC测试。共享FMA存在小幅调用延迟代价，
  可以用 `shared_fma=0` 独立关闭。软件程序的默认请求不会改变已经烧写的位流。

包含最新PANEL4 C文件的SDK需使用审核过的冻结输入：仅在固定SDK上覆盖该C文件，
不能复制当前未提交的AKV汇编。应从新构建的清单确认SDK路径、源码及ELF哈希，
不要用旧CMakeCache或历史ELF冒充最新配置。

新完整程序及冻结SDK见 `integration_manifest_20261111.json`；
程序目录为 `verification/out/enablement_unified_build_20261111_01/build/bin/`
（位于 `ara_dsa_signoff_integration`），不是旧交付的 `bin/`。
这批程序已通过独立构建审计；模型观测程序从相同对象和静态库重链接，
另加标量观测wrapper，独立记录ELF身份，不把两个ELF混称为同一文件。
Refact原worker因错误要求整个 `llama_decode` 保存vcsr而判FAIL；
独立ABI审计检查原始记录、量化源码和反汇编后通过，原日志和FAIL未改写。
SDK局部保存CSR的约定及两侧CSR一致要求未放宽。

## 进一步接入的当前版本

上述`integration_manifest_20261111.json`及其ELF保留为前一轮交付，
不包含新增的协作能力查询和直接M8准备。当前扩展见
[`OPTIMIZATION_EXTENSION_20261111.md`](../../hardware/docs/OPTIMIZATION_EXTENSION_20261111.md)。

- 硬件命名配置为`make -C hardware config-check config=llm`，明确选择既有共享资源。
  普通默认配置不变，软件设置不会改变已经烧写的位流。
- 新SDK从QBINFO index5读取实际协作能力。旧硬件返回0时自动保留M4；
  必须将新SDK头文件与对象一起重新编译，不混用旧静态对象。
- M4的K2048/K4096准备及缓存链实测周期减少约12%；40次独立适配层检查通过。
  K4096使用真实激活字节重排，不代表真实K4096模型算子或模型端到端收益。
- M8直接生成packed布局，不另做整块repack；多worker、特殊输入、已有M4缓存
  或context复用均保留原路径。显式`GGML_RISCV_QBS_WIDE_M=0`关闭新候选，
  显式`=1`仍是旧实验路径，两者不能混称为同一producer。
- `software/llama/platform/`提供默认拒绝的Resident部署适配层。
  当前没有板卡binding；普通构建不链接空provider，保留既有native AKV。

本轮未更新板上ELF或位流，也未运行综合。新程序的构建身份和M8原生配对验收
以扩展文档及新的独立结果为准，不使用前一轮ELF冒充最新软件。

当前完整程序为唯一验证工作区中的
`verification/out/optimization_extension_unified_build_20261111_02/build/bin/`。
新交付索引为`integration_extension_manifest_20261111.json`；三份静态ELF均通过
独立构建审计，尚未使用这三份新ELF完成模型级或板卡验收。
M8原生配对也已通过，完整调用ABBA均值周期减少2.05%，各取最短值减少0.65%；
后者更保守。仅据此保留已有限定的one-shot候选，不称为整模型提速。
