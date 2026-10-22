# FP64 非正规输入前导位扫描

## 针对的缺口

gap88 的所有新增点均位于向量 lane 的 C910 divsqrt 模块：
行162、条件23、分支167，没有把标量自检分支算成向量提升。
但 gap88 主要改变结果指数，不充分改变输入规格化时的首个有效位。
源码 `ct_vfdsu_ff1.v:37` 的 casez 需要覆盖不同输入前导零长度。

## 激励及预期值

`vgap89_div64_leading.c` 以 FP64 非正规数 `1ULL << bit` 扫描
bit=0..51。每个值连续重复四次，使四个 lane 都收到该前导位。
e64/m2、VL32，每阶段七批；最后一批用 bit51 补满，不引入未知尾部。

四阶段分别计算正、负的非正规数除以1，以及正、负的最小正规数
除以该非正规数。前者应原样返回；后者应精确返回带符号的
`2^(52-bit)`。所有结果均精确，fflags 应为零，vstart 应为零。
预期值由整数位模式构造，不使用浮点除法。

共28次向量除法、896个元素检查和56个 CSR 检查，即952项。
Spike 全部通过，错误签名及 trap 为零。
旧镜像 VCS 已成功结束，CPU 时间109.610秒，168次请求/响应配对，
异常、协议错误及 outstanding 为零。`admit_fp64_scan.py gap89`
已核对84条向量提交、21504字节与Spike精确一致，无未知字节跳过、
非位精确结果、未完成、未退休或异常请求；标量提交至tohost一致且
trap为零。952项DUT自检及签名掩码检查通过。

独立准入目录：`verification/out/gap89-offline-admitted-696-20261006-01/`。
同设计历史集合达到696项。相对695新增行713、条件18、分支713、
FSM0。此为实际原始覆盖位增量，696项正式百分比尚未导出。

## 证据

- 源码：`apps/riscv-tests/isa/rv64uv/vgap89_div64_leading.c`。
- 预检：`verification/out/gap89-div64-leading-preflight-20261006-01/`。
- VCS：`verification/out/gap89-div64-leading-old-image-20261006-01/`。
- 运行器：`run_gap89_simulation.py`，固定输入和镜像哈希，时限600秒。
- ELF SHA256：`97c6f2683433350e0ffdb9bfebe373d7c70de50b72c8f84a4a39e6a9a1f7931e`。

本测试不改变 RTL，不豁免可达前导零路径，也不接纳失败 VDB。
