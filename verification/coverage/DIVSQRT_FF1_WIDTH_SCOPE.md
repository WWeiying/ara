# 窄格式除法子单元的前导位覆盖候选

## 为什么不能继续盲目补输入

C910除法器复用52位尾数前导位编码器。FP32/FP16实际尾数分别只有
23/10位，转换时左对齐、低位补零。上层WIDTH32/16包装器并不
允许Double格式进入相应子单元，所以部分52位case臂无法触发。
这不同于“软件没用到”，是封存配置下的位级输入约束。

## 源码链与结构范围

五份源码均与旧镜像build-source-pins一致：divsqrt包装器、
ct_vfdsu_scalar_dp、ct_vfdsu_prepare、ct_vfdsu_ff1及ct_vfdsu_top。
四项只读测试通过，见`test_divsqrt_ff1_width_scope.py`。

1. WIDTH32的格式译码只产生0100/0010/0001，WIDTH16只产生
   0010/0001。格式寄存器reset为0，保存上述值，不产生1000。
2. 包装器将格式四位接到func[16:13]；scalar_dp寄存器按原位复制。
   ex1_double仅reset为0或接func[16]，ex1_single同理接func[15]。
3. prepare的FP32尾数为`{operand[22:0],29'b0}`，FP16为
   `{operand[9:0],42'b0}`，默认BF16形式为`{operand[6:0],45'b0}`。
4. 因此WIDTH32的两个前导位输入低29位恒为零；WIDTH16低42位
   恒为零。合法非零输入的最高有效1不能位于这些固定零位置。
5. FF1的52个非零casez臂和全零臂分割全部双态52位输入；default
   不处理合法双态输入。X/Z或强制内部注入不属于这个结构结论。

zero-input臂仍可达，不能豁免。WIDTH64子单元允许完整FP64尾数，
不得应用上述低位限制。也不排除普通FP16/32/64舍入、异常或结果
打包功能；只有精确绑定到相应WIDTH实例的前导位case臂才是候选。

## 下一步资格条件

目前没有批准或应用排除，没有改变覆盖率分母。需要分别核对
实际生成实例的参数和父子连接、原始点checksum，以及具体case臂
与原生DVE标识的对应关系。原生case编号不能凭XML排列推定。
候选必须在最新PASS集合中仍未命中；已命中点直接否决相应推论。
随后做精确export/reset/import/邻点保护校验，才可提出正式豁免。

这些源码检查不是整个子单元的RTL形式证明，尤其不能推广到
任意第三方调用、其他配置、CVA6标量FPU或全部BF16子块。

## 原生case位映射校准

已用封存哈希一致的`ct_vfdsu_ff1.v`编译独立短testbench，依次
驱动52个单比特位置、全零及仅用于定位default臂的X输入。
后者不是处理器激励，也不是宣称X状态可豁免的功能验证。
工具要求每种输入精确自检成功、与处理器branch checksum/宽度
一致，并且相对全零基线恰好新增一个唯一覆盖位。

最初前台尝试因每次VCS启动/退出开销而中止，完整记录保留在
`verification/out/ff1-case-calibration-20261006-01/`。随后复用同一
已编译模块，在独立`ff1-case-calibration-20261006-02`目录后台
执行；没有重编译处理器或修改RTL。驱动脚本为
`calibrate_ff1_cases.py`，完成后应输出`mapping.json`。

校准现已完整完成，后台服务退出码0，54种输入全部满足精确自检、
checksum一致及唯一新增覆盖位检查。父线程重新核对所有输入和数据
哈希，以及54个位置的完整无重复映射。`mapping.json`的SHA256为
`fd50e6f852836c3147bc3230f0e75599153e8410f148cbb78fd96f8d3d6a1edd`。

实测raw index：default为0，全零为1，单比特bit=n为n+2。这里的
raw index不是DVE原生排除编号。完整映射仍不批准排除；这些独立
VDB全部不进入701项处理器PASS集合，也不会直接修改DVE百分比。

## 父级参数传递的只读核验

`test_ff1_parent_width_scope.py`的六项检查通过。FPnew package、top、
opgroup block、multiformat slice及THMULTI wrapper的源码哈希均与
旧镜像封存清单一致。父级Width及format mask逐级传递；DIVSQRT
使用ACTIVE_FORMATS，而不是CONV或DOTP格式集合；子实例WIDTH由
相应ACTIVE_FORMATS的最大浮点宽度决定。额外检查封存哈希一致的
VMFPU源码，确认FPUFeatures.Width固定64、EnableVectors固定1，
并通过Features参数传入实际i_fpnew_bulk实例。

package按`width / fp_width(fmt) > lane_no`选择格式。若父级Width=64
且FP64/FP32/FP16均启用，四个子位置的最大宽度分别为64/32/16/16。
701项数据库中的32个FF1实例恰好对应四个向量lane、四个FPnew子
位置和两个操作数，没有缺项或重复。这仍是条件性的参数传递证明：
封存testharness未覆盖SoC的FPUSupport参数；SoC默认
FPUSupportHalfSingleDouble，package编码111000使FP64/FP32/FP16启用，
父级逐层传递FPUSupport。检查涉及的各层源码哈希均与封存清单一致。
这没有批准任何原生排除；原生资格和输入配置绑定仍须独立验收。

## 最新集合的精确候选清单

`inventory_ff1_width_candidates.py`联合执行上述六项及尾数补零四项
检查，读取54种实测输入映射，核验校准输入/输出哈希，再绑定701项
位图中的32个FF1实例及其共同checksum、54位宽度。

结果为904个候选位置：WIDTH32的8个操作数实例各29点，WIDTH16
的16个操作数实例各42点。所有904点在最新集合中均未命中；任何
已命中候选都会使工具报错。其余824个位置完整保留，包括WIDTH64
全部位置以及所有实例的全零和default臂，不把X校准当作正常输入。

清单为`verification/out/ff1-width-candidates-701-20261006-01.json`。
其中raw index只是位图诊断坐标，不是DVE原生编号。尚未生成或应用
排除，未改变分母；仍需原生export/reset/import、邻点保护及完整集合
的统计应用核验。904个候选也不能直接解释为百分比提升。

## 原生准备工具与实际编译选项核对

`prepare_ff1_native904.py`的六项工具测试通过。它只准备审阅输入，
没有DVE启动动作；精确验证父级实例的FPUSupport实参为同名参数，
核对compiled source/shape、54种校准映射、904目标及824保护位置。
配置明确保留`launch_allowed=false`，不能据此跳过原生资格过程。

父线程另外解析旧镜像保存的实际VCS命令
`sim/simv.daidir/vcs_rebuild`，确认单条命令、唯一top为ara_tb、唯一
filelist为封存bender_script_default；命令与filelist均没有FPUSupport
覆盖或-pvalue/-gvalue/-parameters选项。命令SHA256为
`1c831c38b0c9d332cdcb73459ee628a715560a8750553a2c0f6dc624cec17b6a`，
filelist SHA256为
`7ce8ae92a31a9448eae96eead471846ae48744980d59e8a85cdf3d33ec126880`。
这比只看make请求更直接，但仍不替代源码defparam/实际展开配置
审计。没有重新编译处理器或变更运行参数。

完整审计现已完成：`audit_ff1_native904_flags.py`严格解析实际VCS
参数和递归filelist，仅接受已审阅的选项、宏和绝对输入路径；核验
458项manifest记录，扫描其中450份RTL/include文件中的defparam、
config覆盖及配置宏重定义。三份当前已变化的源文件使用独立封存
副本，均与编译时和历史验收两份哈希记录一致，没有覆盖当前源码。
厂商隐式UVM库不属于这份处理器源文件扫描，不扩展其审计结论。

产物为`verification/out/ff1-native904-flags-audit-20261006-01/flags-audit.json`，
SHA256为`86b4aa45908db349ba061f192141039eb97e24f3aacb5685b3f178a7d454922d`。
父线程运行五项测试及完整verify，得到`FF1_FLAGS_OFFLINE_REVERIFIED`。
实际参数与源文件覆盖审计已通过；仍未捕获原生904项记录或批准
分母调整，需继续执行精确原生选择、保护审计及最终清空。

## 原生资格核验完成

后续`verification/out/ff1-native904-capture-20261006-02`已正常退出。
父线程使用`capture_ff1_native904_v2.py verify`独立重建核验结果，
得到`FF1_NATIVE904_V2_REVERIFIED`。1728个坐标包含904个目标和
824个保护点；904个记录的导出、清除、回导一致，default和zero
仍保留，最终排除状态为空。原生结果状态为
`FF1_NATIVE904_ROUNDTRIP_VERIFIED_NOT_APPLICATION_APPROVAL`。

配置SHA256为
`43d28c2145a33638d9d6adbc9d22d4f30b90e102b3d6471b1c669b09492aa032`，
结果SHA256为
`15c65c3f1e6a43079ea64dc73fe388004c596a32dadc59d8be33cbe6d911baf7`。
这次捕获使用一个处理器测试验证原生坐标和往返流程，不能替代
完整701项报告。没有接纳独立校准VDB，尚未批准分母调整或报告
完整集合百分比；完整应用仍需核验成员、保护点和恢复结果。
