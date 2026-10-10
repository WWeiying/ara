# FP16 非正规结果指数与舍入扫描

FP16结果打包有独立格式条件。此前FP32/64覆盖不能代替该路径。
本测试对正负最小正规FP16数除以`2^shift`，扫描shift0至15，
每个指数连续重复四次进入四lane，覆盖全部五种合法frm。
最大除数为32768，仍为有限FP16数，不使用溢出为Inf的除数。

- shift<=10：精确结果尾数为`1<<(10-shift)`，保持符号。
- shift=11：半个最小非正规数；RNE取偶数零，RMM取远离零结果。
- 更小结果：正数仅RUP、负数仅RDN得到最小非正规数。
- shift>10：要求UF|NX；其余精确结果不置fflags。
- 每条操作后要求vstart为零。

VL64、e16/m1；10次vfdiv，640个结果检查和20个CSR检查。
独立预期由整数位模式构造，Spike已完成660项自检且失败签名、
trap为零。旧镜像VCS已完成严格验收，30条向量指令、3840字节
严格匹配，无未知字节跳过、非位精确指令或未完成请求，软件自检
及contract通过。历史集合达到701项PASS，相对700新增line30、
condition162、branch138、FSM0。

- 源码：`apps/riscv-tests/isa/rv64uv/vgap94_div16_exp_lanes.c`。
- 预检：`verification/out/gap94-div16-exp-lanes-preflight-20261006-01/`。
- 仿真：`verification/out/gap94-div16-exp-lanes-old-image-20261006-01/`。
- ELF SHA256：`3809de513568a4258b6f4deb28ca27cf5862c2361bca29ee53f10304ab2ca836`。
- 准入：`verification/out/gap94-offline-admitted-701-20261006-01/`。

输入、源码及镜像哈希固定。需要严格标量/向量差分、contract和
自检全部通过方可准入；失败VDB不合并。未修改RTL或放宽检查。
