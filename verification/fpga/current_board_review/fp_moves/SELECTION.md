# RVV-10 原始数值失败选例

## 选例时状态与边界

本节保留授权实测前的静态结论；后续candidate02实测与周期证据见
[README](README.md)，不要将下述“尚未实测”理解为最新状态。

本次仅静态核查与归档身份复核，没有构建、运行参考模型/RTL或修改RTL。
结论：优先选择原始 `e16/m1/op6 vfmv.s.f` 单例，而非再造一个slide VL2测试。
当前candidate02仍有标量插入与普通prestart屏蔽冲突的静态路径；尚未形成
当前镜像的实测反例，不能据此修改RTL，也不能把38项算术PASS扩大至此来源。

下文 `C` 为 `/home/wangwy/fpga_runs/ara_hw_campaign_20261007_01`。
原始输入保持原路径，不复制覆盖或重生成。

## 49条记录的身份

`C/all_failure_scope_audit02/audit.json` 中RVV-10/failed共49条，其中47条
为按操作划分的失败程序；另两条为包含多个操作的原父程序/详细版：

| 原父程序 | 原ELF SHA256 |
| --- | --- |
| rvv_fp_move_restart_e16_mf4 | `4ddd1326a597f72617e11c7b562a15825da524f6331e8bf323ea7b8f6b5e42e7` |
| rvv_fp_move_restart_detail_e16_mf4 | `1b2fb83597613dfff353a59ea1b4eb9edc3a78b98e1f6729905691446c1b5cc0` |

这不是49个独立bug，也不包含另列的57个stall。47条的逐项名称、原ELF
哈希和原始失败行在 `C/rvv_small_fp_moves01/manifest.json`；原序列前缀与
单例的数据症状对应在 `C/rvv_move_symptoms02/symptoms.json`，47条均confirmed。
后者只证明旧板测症状一致，不证明内部根因。两条父记录不能额外计为新元组。

所有47条首错元组共有：`seed=0 scalar=0 invalid_box=0 VL=2 mask=0
sticky=0 vstart=1 actual_flags=0 errors=1`。mask=0是模式编号，实际为
全一mask，不是all-off；op4/5/6不使用谓词。区别如下：

| op | 原操作 | 形状 | 条数 | 旧板测首错元素0：期望 -> 实际 |
| --- | --- | --- | ---: | --- |
| 2 | vfslide1up.vf v24,v8,ft0,v0.t | e16/mf4 | 1 | 0x7bff -> 0 |
| 3 | vfslide1down.vf v24,v8,ft0,v0.t | e16/mf4 | 1 | 0x7bff -> 0x8000 |
| 4 | vfslide1up.vf v24,v8,ft0 | 下述15形状 | 15 | 最大有限数 -> +0 |
| 5 | vfslide1down.vf v24,v8,ft0 | 下述15形状 | 15 | 最大有限数 -> -0 |
| 6 | vfmv.s.f v24,ft0 | 下述15形状 | 15 | +0 -> 最大有限数 |

15形状为e16/{mf4,mf2,m1,m2,m4,m8}、e32/{mf2,m1,m2,m4,m8}、
e64/{m1,m2,m4,m8}。最大有限数分别为0x7bff、0x7f7fffff、
0x7fefffffffffffff；-0分别为0x8000、0x80000000、0x8000000000000000。
全部首错returned_vstart=0，scalar_result仍为0x123456789abcdef0，
两侧guard均0x5b。op0/1/7不属于这47个数值失败分区，不能凭族名归入它们。

## 选定源程序与完整Oracle

选择 `rvv_small_fp_move_restart_e16_m1_ops6`，保留归档的一次实际失败调用。
其原全分区为 `rvv_fp_move_restart_e16_m1_ops6`，manifest配置数21504；
单例删除此前循环，不能称为已执行原全分区。归档前缀版本保留原循环顺序，
且已与单例匹配旧板测首错。当前验收若只跑单例，范围仍只能写单例。

| 输入 | C下相对路径 | SHA256 |
| --- | --- | --- |
| 原全分区ELF | rvv_fp_move_partitions02/op6/overlay/opt/ara-tests/rvv_fp_move_restart_e16_m1_ops6 | `71fb6c794309206f76240f97a5eac9da1b93e774fbf635e4e0be384df4778797` |
| 归档单例ELF | rvv_small_fp_moves01/binaries/rvv_small_fp_move_restart_e16_m1_ops6 | `588d0ea3caafdcba7f5db6e03454c5a54ddfa3a44791adc22d8172c74857f0d6` |
| 归档前缀ELF | rvv_prefix_fp_moves01/binaries/rvv_prefix_fp_move_restart_e16_m1_ops6 | `f940b9c48dbdaf778e6be0ab51a522272870ef7079917be1a106f554400a07ab` |

单例目录为 `C/rvv_small_fp_moves01/rvv_small_fp_move_restart_e16_m1_ops6/`：

- scenario.c：`f3b7fc0920da06deb80d87069158d93649a1f7ae2cd1677af6d897df3fcd9ea4`
- scenario.S：`d557d054fac3b9f1869d0a00c19087e00f49a65f5420eea800a3771fcd70724d`
- inputs.h：`785f21c3b77039c9116ba701b1ce56fc5c2ba17970564d91ce54d662f930b001`
- operations.h：`bf90c6c91023c00c2071c23b51bca3145cdf495f0b68df8b122cea3de3d53a09`
- scenario.dis：`c8c40136eef94c8759530603a1f7d9af4f64bbdce48c9fa3d724743876f5d219`

归档单例op6入口PC=0x106c0；目标PC=0x106f0，编码42005c57；随后
0x106f4读vstart，0x106f8读fflags，0x1070a完整vse16读回。PC只属于此
Linux ELF，未来裸机适配必须重新记录映射，不能沿用地址冒充同一ELF。

完整setup：capacity()设e16/m1/tu/mu取得cap；a[i]=inputs[i%16]，
旧目标output[i+1]=inputs[(3*i+11)%16]，两侧guard=0x5b；mask128字节全ff。
ft0由fld读入boxed +0，即0xffffffffffff0000。op6先用cap完整加载v8、
v24和v0，再设VL2、fflags0、vstart1，执行目标，立即采样vstart/fflags，
恢复原fflags，再用cap存回v24。保留这些加载和vtype次序，不直接预置VRF；
这也是保留实际stored-EEW状态的方法，不另造混合EEW情形。

oracle只把元素0改为0，元素1及所有tail保持旧目标；另外完整检查
returned_vstart=0、fflags=0、未用的scalar_result哨兵和两侧guard。
VLEN1024时cap=64，VLEN512时cap=32。期望最终标记：
`RVV_FP_MOVE_PASS sew=16 cases=1 errors=0`。旧板测元素0仍0x7bff。
当前源 `fp_move_oracle.c` 明确使用 `op==6 && start<vl && i==0`；
绝不能为适配而改成普通 `i>=start` oracle。

## 当前RTL静态判别

所查dispatcher、lane_sequencer、VALU、simd_alu、SLDU与candidate02冻结
文件逐项SHA一致，因此以下不是只对尚未构建工作区的推测。

1. `hardware/src/ara_dispatcher.sv:1204` 默认继承CSR vstart；3888的
   VFMVSF把内部vl缩为非零时1，但没有把内部vstart归零。4070处的
   NaN-box检查对本例有效boxed +0不改变数据。5962的空操作判断仍比较
   架构CSR的1<2，不会吞掉本例；requires_zero_vstart也不含VFMVSF。
2. `hardware/src/ara_sequencer.sv:292` 将其路由到VALU，不经过VMFPU/SLDU。
   `lane/lane_sequencer.sv:430` 内部VL1在四lane下只给lane0一个元素，
   448处将全局vstart1转换为lane0本地vstart1；其他lane为VL0快完成。
3. `lane/simd_alu.sv:571` 对VFMVSF直通opa；VALU的scalar复制得到0。
   `lane/valu.sv:943` 的BE同时要求 `be(1,EW16)` 与
   `active_from_vstart(first_element=0,vstart=1,EW16)`，二者相交为0。
   issue计数从VL1初始化，故预计会完成一个BE0结果而未写元素0。
   这是可证伪的静态预测，不是本轮实测。
4. 相比之下，op2..5走SLDU；`sldu/sldu.sv:715` 已统一屏蔽prestart
   输出字节，803处仅vstart=0才插入slide1up标量，lane侧源流另有起点修复。
   因此旧slide前缀错误已有相关修复，仍需原来源验收，不能推导所有47项PASS。

所查文件SHA（相对hardware/src）：

- ara_dispatcher.sv：`8ea44e035165be966bc80cea3abc31a8af85fde3e46470116854480a92171ab2`
- lane/lane_sequencer.sv：`60137df7264ccd09b2a9a1548d2e522c4785bd43c26a06a27024a0c8eb114da0`
- lane/valu.sv：`f8a8cd12e9d4732eca87e1c9a1aa48b52a8e684f2d7e64d0e8ec1faa9411c778`
- lane/simd_alu.sv：`8d84858bd3dbb3baab5e2b12b8eb0c36cceb407373adee9dc0285ab8dfa962bc`
- sldu/sldu.sv：`1908da4368316c0979e388e934cf04dacf2d266297b36d35b1a803222d2a311e`

## 待授权的最小测量

不启动。后续只替换Linux打印/exit/_start包装，保留scenario.S、inputs.h、
op6调用与全部检查；记录新ELF哈希与目标PC，先参考模型，再复用candidate02
镜像。归档已有的是QEMU VLEN512/1024各47项PASS，不是新Spike或VCS结果。

目标前后限定窗口观察：CSR vl/vstart、frontend指令、backend_req
op/vl/vstart/vd/scalar/valid/ready、lane0的vfu_operation握手、VALU
vinsn_issue_q/issue_cnt_q/result_write.{id,addr,wdata,be}、实际VRF grant/BE、
vinsn_done及最终vse16读回。按目标VID匹配，排除setup加载或内部维护握手。
若目标接受且data=0、BE=0而后读回0x7bff，则支持插入资格被prestart误杀；
若BE正确且VRF已经写0，则转查布局/存回，不可继续沿此假设改RTL。
若没有接受或发生异常，先查dispatcher，不把retire/done等同实际写回。

最小后续控制仅需同源op6的start0、start==VL2和VL0（若获授权），分别
区分正常插入、空操作与尾部保护；保留当前原元组不变，控制不能替代主例。
现有 `apps/riscv-tests/isa/rv64uv/vfmvsf.c` 覆盖正常与VL0，没有非零vstart。
不建议先跑21504配置或全47矩阵；原完整程序的验收仍单列。

## 本次只读核对记录

重算47个原分区ELF、47个归档单例ELF、188个scenario源文件及三份归档
症状报告的SHA，全部匹配各自manifest。生成器/oracle当前源也与原manifest
的三项源SHA一致。两份旧QEMU报告与单例manifest身份一致，各47项exit0。

- 单例manifest SHA：`e517533db5227820bbce08f6230f32b904d1d0a02169178e99d4f98221495d52`
- symptoms.json SHA：`dacc94e171ac5e8baa2fd0c4674e8283ca772fda32d5d7347234dcf55f5c07a9`
- reference_1024.json SHA：`c35c37949ce3eb6103c40327a8b657444d99025677e06cf0d73f6a03403bf0ea`
- reference_512.json SHA：`38f338a10b9db5d82326cb9fb6f3e2bdef1bf335ea23e09d69c0548b7895d964`
