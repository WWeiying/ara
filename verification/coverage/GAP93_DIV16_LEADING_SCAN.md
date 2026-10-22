# FP16 非正规尾数前导位扫描

普通FP16除法不同于FP16到FP32扩宽归约。本测试不绕过或修复
已记录的归约故障，而是独立覆盖除法的合法输入规格化路径。

输入是全部10个单比特非正规尾数，每个位置连续重复四次进入
四个lane。依据`ara_pkg.sv`四lane EW16表，元素0/1/2/3的首字节
映射到0/8/16/24。尾部填充重复位置9；VL32、e16/m1。

四个phase分别检查正/负非正规数除以1，以及正/负最小正规数
除以非正规数。前者期望原位模式；后者期望`2^(10-bit)`，即
指数字段`15+10-bit`、尾数零。全部结果精确，要求fflags和vstart
为零。共8次vfdiv、256个结果检查和16个CSR检查。

Spike已经完成272项自检，错误签名和trap为零。旧镜像VCS现已
完成严格验收：标量/向量差分、软件自检和contract全部通过。
24条向量指令、1536字节严格匹配，无未知字节跳过或非位精确
指令。VCS报告CPU时间40.970秒。历史集合达到700项PASS，
相对699项新增line118、condition189、branch152、FSM0。

- 源码：`apps/riscv-tests/isa/rv64uv/vgap93_div16_leading.c`。
- 预检：`verification/out/gap93-div16-leading-preflight-20261006-01/`。
- 仿真：`verification/out/gap93-div16-leading-old-image-20261006-01/`。
- ELF SHA256：`111af3a3f8ea81549fd2420ed4120c160f801b90cc8f377becfc8301305e63a1`。
- 验收：`verification/out/gap93-offline-admitted-700-20261006-01/`。

镜像、源码和输入哈希固定。失败或超时VDB不进入覆盖率，未修改
RTL、未新增FP16功能豁免，不代表当前RTL signoff。
