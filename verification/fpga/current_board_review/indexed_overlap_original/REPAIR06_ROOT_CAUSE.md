# RVV-01 Indexed Overlap：混合源布局的去重错误

## 已测量的反例

故障基线为冻结 candidate05。输入为 reference03 的完整原来源程序
`d32m2_i64_fault_ov1/soc.elf`，SHA256：
`5a73bf57dc9d9cef6136ec8daa53e409c77abd5e0e47645d403392df5310347f`。
50轮、32个元素、原41条helper指令及oracle没有缩减。
fixture保留Sv39页故障与同PC重试，但不等同于原Linux缺页时间线。

第17次目标尝试仍从vstart=15开始，随后故障位置为16，不能把两者混淆。
索引按e64解释，目的按e32写入，vs2=vd=v4。活动索引跨v4/v5，
其物理EEW记录分别是32/64。请求却只携带一个old_eew_vs2=32，
而且没有使用源快照。

| 波形时刻/ns | 实测值 |
| ---: | --- |
| 367660.5 | AddrGen请求vstart15，index EEW64，old EEW32，base=0x40000000 |
| 367663.5 | 四路SlideAddrGenA输入均valid，依次为0x17000、0x4000、0x11000、0x1e000；snapshot replay均关闭 |
| 367664.5 | 地址0x4000a000，对应正确的索引15 |
| 367678.5 | idx_final_vaddr_q及mmu_vaddr_o均为错误地址0x0000400040017000 |
| CSV cycle367806 | 异常处理器实际读到同一个错误mtval |

用32位布局解码这些64位源字会将相邻索引拼成
`(index17 << 32) | index16`。与实测错误地址精确一致，不是期望值、
串口打印或异常传输的问题。现有波形没有AddrGen内部FIFO消费节点，
因此不声称已测到最早出错的内部组合节点。

原始证据及独立核查：
[failure_analysis01/WAVE_ADDENDUM.md](failure_analysis01/WAVE_ADDENDUM.md)、
[terminal_review02/WAVE_BOUNDARY.md](terminal_review02/WAVE_BOUNDARY.md)。

## 静态因果链

1. `active_group_has_mixed_eew`对e64活动区间[15,32)选中v4及v5。
   两个已写入源寄存器的EEW不同，要求vs2转换成统一的索引布局。
2. `indexed_load_groups_overlap`为真。为保护索引，转换安排先禁止vd
   转换；此时`indexed_load_index_overlap`为假，因为源尚需转换。
3. 原通用去重表达式看到`vs2 == vd`就把vs2转换也取消了。该分支没有
   区分索引EEW64与目的SEW32，最终既未转换，也未触发快照。
4. 直接请求使用v4的old EEW32。跨入v5后，单一EEW无法描述其64位
   物理布局，产生上述精确错误地址。

其中第2、3步是对确定的RTL表达式的推导，不冒充已直接采集的内部
组合信号。M6探针会补充混合检测、去重后的转换请求与真实操作数消费。

## 最小修复与不变量

在vs2转换去重的保留条件中增加`indexed_load_groups_overlap`。
不修改EEW常量、不重新装载索引、不增加独立存储，也不改变架构vstart。
修复使已有机制按原顺序工作：

```text
混合索引布局 → 活动源寄存器归一化 → 等待实际完成
            → 保存索引源 → 转换目的布局 → 重放原索引
            → 原indexed load及原异常/重启流程
```

- 非indexed load、无源目的重叠的请求，该新增条件为假，保持原去重逻辑。
- 同EEW/同布局的重叠源没有额外源转换请求，不凭空增加转换。
- 快照已有效时，已有重放分支禁止对已保存源再转换；不引入反复转换。
- 活动区间之外的源布局不要求全组转换。已完成前缀可被目的覆盖；重启
  只消费当前vstart之后的原索引，目的prestart仍按现有机制保护。
- VL=0或vstart>=VL依旧在维护之前执行空操作处理。

新增OR仅对已有维护控制起作用。错误路径增加必需的布局维护周期，
不能称为零性能代价；正常路径是否保持周期要由相同ELF对照证明。

## 验收计划

M5输入、失败日志、波形、worker和镜像全部保留。M6独立冻结及构建。
先用同一完整fault ov1 ELF验收50轮/1600次fault、修复和MRET、全部
32元素与guards及CSR；通过后运行原resident ov1和fault ov0两个控制。
失败立即停后续任务，不重试、不放宽oracle。随后运行已核验的48项
代表性回归并比较16项正常控制的完整提交CSV。原Linux故障调度和其它
历史长序列仍单独列为未关闭范围。

当前状态：修复已写入，尚无M6 DUT PASS。
