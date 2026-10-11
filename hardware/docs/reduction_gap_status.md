# 规约优化缺口与当前验收范围

工作分支为 `reduction-optimization`，4 Lane、VLEN=1024。已提交的验收基点为 `ec64f1e5`，该版本独立完成106程序回归。本轮精确外部seed和接收解耦的模块、定向整机、消融及110程序完整组合回归均已结束并通过；新组合独立运行，不与旧106程序记录累加。原始阶段记录保存在 `reduction_completion_engine.md` 与 `reduction_gap_progress.json`。

## 原始六项机制及边界

| 优化问题 | 当前实现 | 证据及边界 |
|---|---|---|
| 全Mask源仍做无效收尾 | 收齐活动信息后跳过MERGE/FOLD，继续等待正确seed | 独立开关、模块与106程序验收；VL=0独立处理 |
| 普通运算结果尚未排空时规约不能重启 | VMFPU分开执行与提交所有权，允许适用后继局部规约启动 | 混合回归与重启事件观察；真实输入依赖及队列背压保留 |
| FP64反馈和空Lane停顿 | 相邻活动Lane反馈，选择下一个活动Lane并跨空Lane反馈 | 两侧各5000例模块、各10程序及101/106阶段回归；保留活动Lane加法顺序 |
| 精确收尾长期占用SLDU控制和队列 | 完成结果保持槽、透明出口、Word独立额度和四项SLDU描述符 | 分别保留消融；未新增第二个精确合并器或通信网络 |
| Late Seed类型和生产者范围有限 | 整数/逻辑/极值、适用Word浮点、跨VFU普通生产者、VLE/VSLIDEDOWN首字版本捕获 | 已提交版本的106程序通过；本轮另扩展精确FP16/FP32，110程序组合待结束 |
| VL/SEW/Mask及类型切换限制 | 独立上下文元数据与异构流，精确豁免符合条件的seed组范围差异 | 切换矩阵和实际重叠事件；其余RAW/WAR/WAW及Mask所有权检查保留 |

严格有序浮点求和仍保持原顺序。资源占用、真实相关和端口冲突导致的等待仍须保留；支持异构交错不意味着任意两条指令可以同时执行。规约局部结果移交或Lane出口释放也不等于架构完成，指令ID及目的寄存器所有权保留到最终写回。

## 已提交阶段的可归因收益

各行来自不同阶段的同ELF消融，不能相加或当作对官方Ara的统一加速比。全部数值是软件测量窗口的仿真周期；未进行综合、面积、Fmax和功耗测量，也不推导实际执行时间。

| 阶段 | 代表性窗口 | 周期变化 |
|---|---|---|
| 稀疏FP64 | VL2；VL4、mask=0b1010 | 450→434；482→450 |
| seed组范围豁免 | LMUL4整数OR→浮点max | 869→501 |
| Word外部seed | LMUL4、VL64 Load→规约；Slide→规约 | 1540→932；1476→853 |

上述候选由 `hardware/config/reduction_completion_4lane.mk` 复现，106程序清单为 `hardware/config/reduction_completion_regression.json`。完整原始记录在 `hardware/build/rce/gap_external_seed_full_soc_v1`；预期程序集合、冻结ELF、模拟器哈希、退出状态和日志分类均已核验。八个修改的功能SV文件与该冻结构建匹配，身份信息保存在 `reduction_gap_evidence.json`。

## 新增精确外部seed协议

`reduction_rce_exact_external_seed` 在派发器中允许符合条件的外部生产者向精确消费者提供late seed。Lane 0从实际VRF接收事件捕获基址首字，携带生产者ID、寄存器版本、数据和有效字节。SLDU复用精确结果缓存，并为每个消费者描述符保存seed快照；第一次匹配后不再用新缓存内容覆盖它。消费者接收和生产者缓存替换同周期时，先匹配旧缓存，再匹配本周期更新值，保护已排队消费者所需的旧版本。

资格限于非Mask、非重启、非Fault-only-first且nf=0的VLE，以及非Mask、非重启VSLIDEDOWN。基址寄存器、版本和有效字节覆盖必须匹配；寄存器组内部seed、真实源RAW和目的WAW不能随seed一起放宽。其它生产者形态走正常依赖。对VLE，dispatcher先将请求位宽规范化为指令EEW，所以生产者位宽检查使用实际存储元素位宽。宽化规约的请求位宽已规范化为结果位宽，不能拿源SEW代替seed位宽。

FP16/FP32精确路径使用原始浮点位模式，由Central Finalizer插入一次seed并产生结果及异常标志。Word路径的外部捕获不会自动覆盖精确路径；这里通过单独的快照协议接入。每个SLDU描述符增加valid、32位seed和3位原始结果位宽，共36位；四描述符144位，加八条缓存的4位有效字节共32位，合计176位新增声明状态。此统计不包含组合匹配逻辑，也不代表综合面积。

模块快照测试v3使用真实SLDU队列，让队首Slide暂停传输并填满四项描述符，100轮、2000项检查全部通过；覆盖缓存替换与消费者接收同周期、双端口发布、ID复用、不同消费者版本共存，以及寄存器、版本、字节覆盖拒绝和队列满背压。它验证快照协议，不替代整机算术及退休验证。新增FP16/FP32、LMUL、别名、Masked回退应用和3/5交替seed应用也分别在开关两侧通过。

两侧各11程序的整机对照已结束，程序集合、相同ELF、438个相同冻结输入及DPI已核验，唯一宏差异为 `ARA_RED_RCE_EXACT_EXTERNAL_SEED`。代表性FP32、LMUL1周期如下；两侧接收解耦均开启。

| VL | Load→精确规约：关闭→开启 | Slide→精确规约：关闭→开启 |
|---|---|---|
| 1 | 463→401 | 397→323 |
| 4 | 436→372 | 360→299 |
| 16 | 470→390 | 388→309 |
| 32 | 500→420 | 422→373 |

只读观察器记录实际 `exact_sum_in_valid && exact_sum_in_ready`，按发射指令ID归属，不用普通FPU握手冒充精确输入。两个观察器程序通过且软件窗口与无观察器版相同。Load的62条可明确归属指令全部在seed实际写回前1～2周期接受输入；Slide的62条中61条提前，另1条在seed写回后才启动。每程序另有2条额外reshuffle依赖情况单独排除，逐条证据在 `gap_exact_seed_receive_inputs_v1/overlap_verified.json`。这些收益来自seed依赖后移，没有将Ara既有跨VFU并行能力算作新增机制。

## 接收解耦的独立实验结论

`reduction_rce_exact_seed_receive` 允许包头和分段在late seed未就绪时接收并合并。第一次正确seed锁存一次；分段结束而seed仍缺失时进入 `EXACT_SEED_WAIT`。该状态报告Lane数据已消费，但保留SLDU描述符直到seed锁存，再发出 `exact_local_complete`，避免推进issue指针后改变seed查询对象。它没有在seed等待期间启动下一帧的完整能力。

开关两侧分别完成三种模式、每种1200对帧：包内seed、延迟seed、绑定后撤掉ready并改变总线。覆盖格式/舍入模式切换及旧结果背压。延迟模式开启侧19202次Lane数据拍在seed到达前接收，关闭侧为0；整机接收解耦阶段12程序通过。模块仿真时间包含测试台等待，不能作为应用加速证据。

独立五程序消融已通过；Load四窗口、Slide四窗口和相关链819周期窗口均相同。另外两个功能应用没有测量窗口，不能宣称其周期相同。上述明确归属指令在中央包头到达时seed均已就绪，当前九个测量窗口没有证明接收解耦的额外收益，因此常规Make默认仍关闭此实验开关。接收解耦四态仍使用2位状态编码，其组合控制代价未综合测量。

## 当前110程序组合与复现

当前组合回归目录为 `hardware/build/rce/gap_exact_external_seed_full_soc_v1`，运行器已正常退出，110项全部通过，预期集合、冻结ELF、模拟器及日志分类已核验。110程序清单另存为 `hardware/config/reduction_completion_exact_regression.json`，内容与冻结运行清单相同，含原106项和四个新增应用。完整测试配置为 `hardware/config/reduction_completion_exact_4lane.mk`，为复现本次组合同时开启两个新开关；它与常规Make默认配置有区别。新组合验收独立保存，先前106程序通过仍只对应提交 `ec64f1e5`。

先按仓库工具链说明构建这些应用，再构建完整测试配置：

```bash
make -C hardware -f config/reduction_completion_exact_4lane.mk -f Makefile compile
```

以下命令适用于已经构建好的模拟器；输出目录应另选以保留旧证据。

```bash
python3 hardware/scripts/run_reduction_audit.py \
  --sim /absolute/path/to/candidate/simv \
  --out hardware/build/rce/reproduction_exact_full \
  --jobs 8 --timeout 2400 --sim-arg +RCE_STALL_PROFILE \
  --apps-file hardware/config/reduction_completion_exact_regression.json
```

本轮实际执行使用冻结VCS构建，文件清单和依赖哈希在各阶段source manifest中。标准Make配置的宏展开已核对：与冻结构建的规约宏一致，仅多显式结果深度2，与包默认值相同；不能将这项展开检查描述为另一轮已经完成的标准Make编译。运行器冻结ELF并检查成功、失败、断言和退出状态；读取结果通过 `summarize_reduction_stalls.py` 的 `read_suite` 重新验证模拟器、ELF及日志分类。`reduction_gap_evidence.json` 保存逐项哈希和测量窗口摘要，原始日志另存于构建目录。

## 保留限制和未采用实验

中央结果背压时尚未启动通用后台计算；八程序观察仅有1个后继源与seed都齐备的可利用周期，尚不支持增加通用检查点的收益论证。Word与SLDU同周期退休原型使测量窗口344→351周期，已撤出推荐RTL并保留复现补丁。同VFU普通算术Late Seed实验使1386→1482周期，默认关闭；支持这些生产者的架构路径继续存在，通过常规依赖执行。最后到seed的FP64直接反馈也保留单独默认关闭开关，不能把全部机制开启视作最优配置。

既有vstart异常语义、VNCLIPU和独立复现的vslideup反例按用户要求暂不处理。本轮自身机制暴露的错误仍须定位并保留回归。现有证据不覆盖任意Lane数量、内存延迟和所有指令混合，也不是完整RVV形式化证明。综合、面积、Fmax和功耗不在本次范围内。

完整组合验收时438个冻结输入和九个当前功能覆盖文件均匹配。验收后仅修正SLDU缓存说明注释，以反映外部写入和消费者快照；把该明确记录的新注释替换回旧注释可逐字节还原受测文件，没有功能RTL变化。受测源码和注释差异均纳入证据摘要。
