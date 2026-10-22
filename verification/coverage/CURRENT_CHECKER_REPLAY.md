# 旧镜像日志的当前比较器重验

## 原因与范围

旧镜像、原 VDB、原测试结果和历史 receipt 均保留。历史 receipt 中
`spike_trace.py` 的固定 SHA 与当前工具不同，不能修改历史 pin，也不能
把当前工具冒充旧工具。当前工作从现存日志产生新独立验收证据，不
重新运行处理器，不修改 RTL，不修复本轮记录的 RTL bug。

这是一项新的准入工作，不能以原 PASS 标志代替重新检查。没有完整
重验之前，不宣称 full687 准入通过，也不使用它授权 aggregate 豁免。

## 日志形式盘点

对 `gap80-old-image-20261006-01/combined-inputs.txt` 的687个测试VDB，
按VDB父目录的实际文件盘点得到：

| 形式 | 项数 | 下一步检查 |
| --- | ---: | --- |
| 随机测试完整逐指令日志 | 201 | 当前标量/向量比较器、退出条件、检查点、存储签名及原 contract |
| 扩展测试完整逐指令日志 | 33 | Spike签名、逐指令比较、编译及请求参数、原 contract |
| 需要 producer 专用检查 | 453 | 查原生产计划与验收方法，不统一套逐指令比较 |

这只是日志布局分类，不是新的 PASS 判定。第三类不能被解释为缺失
全部日志，例如定向测试的VDB在`work/`，标量trace和gold结果在其父目录。
不同类别的ISA功能、系统功能及接口协议应使用各自独立检查方法。

## 已完成的代表性重放

旧随机样本 `seed1417` 的当前比较器重放结果如下：

| 观察项 | 实测 |
| --- | ---: |
| 标量比较状态 | TERMINAL_MATCH |
| 已匹配指令 | 2720 |
| 向量比较状态 | PASS |
| 已比较向量请求 | 236 |
| 已比较字节 | 11925 |
| 按架构未知状态跳过的字节 | 14179 |
| 非bit-exact指令 | 0 |

路径为`repaired-aligned-600-20260930-01/results/c0000-seed1417-60ee5eb40a30/tests/seed1417/`。
退出PC和tohost来自原RTL命令，比较调用遵循当前`random_rvv.py`。
这里只完成了代表性比较路径验证，不是新的全项准入或测试覆盖增量。

## 正式重验要求

- 为每项绑定旧镜像身份、输入ELF、Spike执行证据、RTL执行证据、日志、
  VDB与测试名称。复制镜像必须按文件哈希证明相同，不能只比路径名。
- 当前比较器和依赖源码另行封存。运行前后重新核验文件身份和哈希，
  不篡改历史源码pin或旧比较结果。
- 从ELF和生产命令核对entry、退出PC、tohost、VLEN/lane配置及store
  trace布局。不根据保存的PASS结果调整参数使其通过。
- 不能将向量`PASS`独自作为验收；原标量检查点、memory检查、退出签名、
  软件自检及硬件contract必须保持。
- ISA允许的tail/mask agnostic及其传播应沿用有依据的未知状态规则。
  不把合法未知字节说成全部已比对，也不能无依据跳过确定的活动结果。
- PREFIX、部分比较、工具异常或超时不视为PASS；RTL首错单独记录，不
  在本阶段修复。有效的新PASS才能进入新的覆盖率输入清单。
- 多路重放只读取已有日志，不启动VCS；新sidecar与原结果分开保存。
  重放日志并不新增覆盖位，只解决后续采用和豁免的验收依据。

201项离线诊断已结束：199项通过、2项工具拒绝，原因均为
`Missing ISA tail/mask/vl/vstart policy`。拒绝对应`cases/067.json`
及`cases/122.json`，不是case名称中的数字索引。两项正在核对是否为
只需验证内部VRF保持写回、却错误要求架构写入policy的检查器问题；
尚不能据此认定RTL故障或将两项记作当前检查器PASS。
历史覆盖结果不因本次工具拒绝被覆盖，也不据诊断批准新RTL signoff。

随后两项均已完成独立sidecar闭环：
`verification/out/random-policy-two-offline-20261006-02/`记录两项
`PASS_DIAGNOSTIC_ONLY`。二者都是`vfmv.f.s`向标量f0写回，原检查器
对内部VRF保持写回错误要求架构向量写入policy。新检查严格比较每条
活动的128字节均为已知值且等于先前架构状态；没有跳过这些写回。
真正架构向量目的写回仍要求完整policy。七项测试通过，包含改值、
未知值、缺少先前状态及架构写回缺policy的拒绝测试，源pin已复验。
原201结果保留199 PASS/2拒绝，新证据补齐两项诊断，不新增测试VDB
或覆盖位，不把历史集合宣称为当前RTL的全量signoff。

## 工具验收进展

随机重验工具的10项单元测试通过，但父会话首次执行实际`prepare`
命令时，在历史清单哈希索引处遇到`KeyError: all-passed-outcomes.json`。
这属于工具绑定错误，不是处理器失败；尚未生成新准入证据，不能依据
单测通过启动正式批次或宣称201项重验完成。开发中的修正必须保留
历史清单的哈希核验，不能通过删除校验来使准备阶段通过。

上述清单绑定已修正。父会话实际完成一次`prepare`及`check`：
`current-random-replay-parent-20261006-01/diagnostic.json`记录1项
`PASS_DIAGNOSTIC_ONLY`、0项失败，未启动仿真，未批准整体687项准入。
样本`seed1417`除逐指令比较外，验证了4096字节最终寄存器签名的
读回地址序列以及原运行约束。它没有逐指令memory checkpoint。

201项ELF布局预检中，198项可解析，3项因重复的局部`$d`映射符号
被解析器拒绝。已检查`seed1409-replacement`的符号表：同名项
为`STB_LOCAL/STT_NOTYPE`，分别标记不同section的数据范围，属于
合法映射符号，不是业务地址歧义。修正应仅处理合法mapping symbol，
仍严格核验tohost、退出地址和签名相关业务符号。
这201项的已解析ELF没有checkpoint符号；不能把最终寄存器签名
重验描述为逐条存储后签名验证。未观测的功能仍属于覆盖边界。

后续mapping-symbol修正后，201项ELF均解析成功，相关18项单元测试
通过。只读审查未发现阻断本次离线诊断的问题，但上述证据边界保持。
正式后台任务为`ara-current-random-replay-201-20261006-01.service`，
已通过实际PID和CPU活动确认运行。准备阶段先封存输入，重验阶段
使用最多8个worker；不运行VCS，原始VDB和历史结果不变。

```bash
systemctl --user status ara-current-random-replay-201-20261006-01.service --no-pager
tail -n 20 verification/out/current-random-replay-201-20261006-01.driver.log
```

输出目录为`verification/out/current-random-replay-201-20261006-01/`。
完成后查看`diagnostic.json`和`cases/`，服务成功退出也不能代替核查
逐项结果。此批即使全部通过，也仅重验201项随机日志，不增加覆盖位，
不代替其他486项各自的验收契约。

## 扩展日志重验结果

`current-extension-replay-32-20261006-01/diagnostic.json`已生成：
32项诊断重验通过，0项失败。其中14项完成源码绑定重放；扩展集合
仍有19项未完成完整准入闭环，不能把32项诊断通过等同于全项正式准入。
本次只读取历史日志，不新增覆盖位，也不覆盖原始结果。

`vgap76_red32`单独保留，未重放、未重新准入。历史结果包含14项
非bit-exact比较和112个未知状态跳过字节。小整数求和的数值级证明
不能替代实际写回、符号零及异常标志的独立核验。该项不应被描述为
本批新增的严格PASS，也不应仅凭这些诊断数字判定新的RTL故障。

DVE执行文件身份工具额外清除了`REPORT_FLAG`、`NOGUI_FLAG`、
`REPORT_USE_THIS_EXE`和`UCLI_USE_THIS_EXE`，并将继承的`PATH`固定为
`/usr/bin:/bin`，保留许可证环境设置。其13项测试通过；这仅证明
启动约束的测试结果，不代表已完成新的DVE运行或应用了豁免。

## 201项逐项诊断进展

父会话读取全部201份`cases/*.json`：199项为
`PASS_DIAGNOSTIC_ONLY`，2项为`FAILED_DIAGNOSTIC_ONLY`。
最终输入哈希复核和总报告尚在运行，不能用逐项文件数量冒称任务结束。
两项拒绝分别为seed820和seed1115，理由均为
`Missing ISA tail/mask/vl/vstart policy`，尚不是RTL数值首错证明。

seed820已定位至arch_seq96、PC`0x800006ee`、指令`0x42e01057`。
Spike记录标量`f0`返回以及e32/mf2/VL13/vstart0，不含架构向量寄存器
写回。RTL活动包含16条内部写回。现有`unknown_audit()`先无条件要求
policy字段，再区分架构写回与原值保持写回，可能错误地要求原值保持
路径具备不需要的tail/mask字段。必须继续验证该路径的每个确定字节
等于前态，不允许跳过内部写回或放宽有效数据比较。
运行中的封存checker不修改；后续修正应另存严格验收结果并保留拒绝记录。
