# FP32 非正规结果指数扫描

FP32 和 FP64 使用不同的非正规结果移位表，不能将 FP64 覆盖结果
当作 FP32 的完成证据。`vgap91_div32_exp_lanes.c` 对正负最小正规
FP32 数除以 `2^shift`，shift=0..31，覆盖五种 frm。
每指数连续重复四次，依据 `ara_pkg.sv` 四lane EW32 shuffle映射，
四个元素分别进入四个lane。

shift<=23 为精确结果，预期绝对位模式 `1u << (23-shift)`；
shift=24 为半ULP，RNE取偶数零、RMM远离零；更小结果只在按符号
方向的定向舍入下变为最小非正规数。shift>23要求UF|NX，精确结果
fflags为零。所有操作后vstart必须为零。

e32/m2、VL64，共20次向量除法，1280个结果检查及40个CSR检查。
Spike已完成1320项自检，错误签名和trap为零。旧镜像VCS已正常
完成，并通过完整标量、向量差分和contract验收。严格比较60条
向量指令、15360字节，无未知字节跳过、非位精确指令或未完成请求。
已纳入698项历史PASS集合，相对697项新增line308、condition99、
branch335、FSM0。原生DVE百分比须另行导出，不能由点数推算。

预检：`verification/out/gap91-div32-exp-lanes-preflight-20261006-01/`。
VCS：`verification/out/gap91-div32-exp-lanes-old-image-20261006-01/`。
ELF SHA256：`a27c532ee3162bade19ee1d25bf92b14fbbe543e3b5ebd041a699d466638433c`。
运行器固定输入及镜像hash，时限600秒；失败VDB不进入PASS-only统计。
未修改RTL，也未将FP16/32/64合法路径豁免。

验收证据：`verification/out/gap91-offline-admitted-698-20261006-01/`。
此结果仅适用于封存旧镜像，不代表当前RTL的全量signoff。
