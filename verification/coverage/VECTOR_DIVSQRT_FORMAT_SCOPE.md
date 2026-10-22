# 向量除法器的格式可达性候选

## 已核对的源码事实

当前工作区以下六份源码均与旧镜像 build-source-pins 一致：VMFPU、
ara_pkg、fpnew_top、opgroup_block、opgroup_multifmt_slice 和
fpnew_divsqrt_th_64_multi。封存编译命令使用 default、四lane、VLEN1024。

VMFPU中 `fp_dst_fmt` 的全部赋值分别为 FP64、FP8、FP16、FP16、
FP32、FP64，没有 FP16ALT。目的格式沿 fpnew 的端口传至 divsqrt
包装器；包装器的格式寄存器只复制输入，reset格式值0为FP32，
不会自行生成FP16ALT。包装器仍包含 `FP16ALT -> divsqrt_fmt=0001`
的case臂，属于应进一步审查的向量集成路径候选。

`test_vector_divsqrt_format_scope.py` 四项只读检查通过：源码hash、
全部目的格式赋值、传递端口、包装器格式流水及封存编译命令。
这不是RTL形式证明，也不是DVE原生排除资格。

## 不允许推大的结论

- 当前候选只针对向量lane的包装器，不包括CVA6标量FPU。
- 未以“没被软件用到”为理由排除普通FP16/32/64功能。
- 尚未将case原生vector编号绑定到FP16ALT具体臂；XML编号不是语义。
- 尚未核对所有内部格式信号的状态传播，因此不排除整个BF16子块。
- 不自动豁免default或复位路径；合法异常拒绝也需要独立测试。
- 单独调用包装器、其他配置或强制注入format不在本论证范围。

后续需独立检查格式传递链、原生case映射及精确邻点保护，方能形成
可应用的排除项。当前未生成exclusion、未修改RTL、未改变总覆盖率。
