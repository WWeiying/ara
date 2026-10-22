# 大偏移 slide 的掩码 RAW 核查

## 已经测量的事实

程序为原始来源移植的 `e8_m8_single`，使用 final03 冻结镜像；不是新构造的
全零源测试。VL=1024、offset=1023、vstart=0、全一掩码，目标元素1023
应为185，实际保持旧值91。`capture01/selected.vcd` 显示：

- 103390.5ns，VLM 对 v0 发出128字节请求，EMUL=1，EEW8，长度正确。
- 103684.5ns，MaskM 请求起点3、长度1、EEW64、hazard=8，读的是最后一个
  聚合掩码字；这也是 offset1023 所需的位置。
- 103689.5ns，四路 MaskM valid 均有效，但全部64位数据为 X。
- 103695.5ns，源最低字节185、移位后最后字节185、最后字节选择
  `out_en_flat=0x80000000` 均正确。
- 最终结果写请求及地址127正确，但四路 BE 都为0，因此保留旧目标。

`decode_requests.py` 检查已经抓取的请求；`decode_capture.py` 检查消费端。
这足以排除本例的源数据、目标位置和 VLM 请求长度错误，但还不能独自
证明 X 的产生原因。

## 可证伪的原因假设

普通 operand requester 的 chaining 使用生产者 vid 的逐拍写回脉冲。
它适用于从同一个字位置顺序推进的生产者/消费者，不证明任意后续字已写回。
这里消费者直接跳到掩码字3，可能被生产者写掩码字0的脉冲提前放行。

第二次同镜像/同 ELF 的 `capture02` 增加真实 requester 的元数据、stall、
读 grant、LDU 最终 VRF 写 grant/address/data/BE，以及实际 bank 请求。
判据是：读取掩码字3发生在生产者写字3之前，同时读请求按首字写回脉冲
被放行。若顺序不是如此，就不能采用这个原因或修改相关性规则。

## 修复边界审查

若上述判据成立，优先在 sequencer 生成依赖时，将 masked VSLIDEUP 跳过
至少一个聚合掩码字的真实 v0 RAW 依赖标为 wait-complete。阈值为
`NrLanes * ELEN` 个掩码位，与数据 SEW 无关；不是按数据字节计算。

不要把 lane 的 `hazard_vm` 简单视作纯 RAW：当前 sequencer 也把旧目标
读者的 WAR 合并到该字段。应在 `write_list[VMASK].valid` 所确定的生产者
位置设置依赖，复用已有 wait-complete 清除/完成协议。不能将所有 slide、
所有源或者所有 WAR 都改为等待退休。

零偏移、聚合字内偏移、未屏蔽操作、无在飞 mask 生产者，以及已有合法
顺序 chaining 应保持原控制条件。该方案不新增数据缓存或流水级，但跨字
依赖本身必须等待有效数据；不能承诺错误路径原先的周期数保持不变。

这个文件记录测量与修复判据，不是修复已通过声明。最终修改与前后对照
必须另附真实源码、构建哈希、完整程序结果及邻近边界测试。

## 第二次测量：原因得到证实

`capture02/status.json` 为 CAPTURED，架构结果仍为 FAIL，原首错完全一致。
`mask_producer_events.json` 记录 lane0 的真实 VRF 端口事件，时间单位 ns：

| 时间 | 事件 | 地址 | 数据/控制 |
| ---: | --- | ---: | --- |
| 103683.5 | LDU 最终写 grant，vid3 | 0 | 全一，BE=ff |
| 103685.5 | LDU 最终写 grant，vid3 | 1 | 全一，BE=ff |
| 103686.5 | MaskM 读 grant | 3 | hazard=08、written=08、wait=00、stall=0 |
| 103687.5 | LDU 最终写 grant，vid3 | 2 | 全一，BE=ff |
| 103689.5 | LDU 最终写 grant，vid3 | 3 | 全一，BE=ff |

读字3比写字3早三个周期。精确地说，本次放行来自字1的写回脉冲，而非
前述假设举例的字0；错误是把较早位置的写回当作任意跳读位置已就绪。
实际载入的数据为全一，地址也正确，不是软件掩码未初始化。
`decode_mask_producer.py` 从已完成的 VCD 得出 `read_before_write=true`。
第一次离线分析未识别 fsdb2vcd 的 grant 数组展开形式，修正解析字段为
`operand_requester_gnt[6]` 后得到上述结果，没有重跑 RTL 或改波形。

候选只在 `ara_sequencer.sv` 的真实 v0 RAW 依赖生成位置，加上 masked
VSLIDEUP 且 `stride >= NrLanes * ELEN` 的 wait-complete 条件。新文件哈希：
`f1d6095e1ade018b9225678a493438da04e7d84f68a956bdf7a116941bfafc5b`。
当前已冻结到 final04，后续要用原始六个源程序和专门 RAW 前后对照验收。
本段不把候选写入视为修复通过。
