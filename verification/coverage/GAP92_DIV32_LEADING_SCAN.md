# FP32 非正规尾数前导位扫描

## 缺口与假设

FP32和FP64除法具有不同的规格化和打包路径。FP64前导位扫描的
覆盖收益不能作为FP32完成的证据。本测试针对FP32尾数的23个
合法单比特位置，检查精确的非正规数输入及输出，不改变RTL。

## 激励与独立预期

四个phase分别为正/负非正规数除以1，以及正/负最小正规数除以
非正规数。位位置0至22，每个位置连续重复四次，依据四lane的
EW32 shuffle映射进入全部lane。最后一批的填充元素重复位置22。

- 非正规数除以1：期望保留符号和原始单比特尾数。
- 最小正规数除以`2^(bit-149)`：结果为`2^(23-bit)`；期望指数
  字段为`127+23-bit`，小数部分为零。
- 全部运算精确，要求fflags为零，执行后vstart为零。
- e32/m2、VL64，共8次vfdiv、512个结果检查、16个CSR检查。

预期以整数位模式构造，没有使用浮点计算作为软件oracle。
Spike已完成528项自检，失败签名和trap为零；VCS已完成并通过严格
标量/向量差分、自检及contract验收。比较24条向量指令、6144字节，
无未知字节跳过、非位精确指令或未完成请求。集合已达到699项PASS，
相对698项新增line352、condition37、branch352、FSM0。
VCS报告CPU时间67.010秒，此时间不是DVE导出耗时。

## 可复现证据

- 源码：`apps/riscv-tests/isa/rv64uv/vgap92_div32_leading.c`。
- 预检：`verification/out/gap92-div32-leading-preflight-20261006-01/`。
- 仿真：`verification/out/gap92-div32-leading-old-image-20261006-01/`。
- ELF SHA256：`bf0185fcbe0d192f868e521e82c31c1f462cdf58fa444a16bd797c00ed482ade`。
- 独立runner固定旧镜像、输入及源码哈希，超时600秒。
- 准入证据：`verification/out/gap92-offline-admitted-699-20261006-01/`。

失败或超时VDB不纳入覆盖率。运行使用旧镜像，不代表当前RTL
signoff；未将合法FP32路径豁免，也未修改已封存的验收脚本。
