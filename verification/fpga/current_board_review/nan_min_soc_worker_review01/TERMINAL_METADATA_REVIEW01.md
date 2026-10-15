# MIN 两项终态元数据复核

结论：**ACCEPTED，两项原来源 MIN single 的既有独立计算验收链成立，无阻断。** 本次仅终态元数据审查，复用已审封存的唯一计算审计；没有再次读取、散列或解析 raw CSV/reference/log，没有执行 Host/参考/DUT/build。原入口 REVIEW.md/decision.json及所有producer输入保持不变。

## 实际终态与退出

- `nan_min_soc_terminal_audit01/run01/TERMINAL.json`：`ACCEPTED_TWO_MIN_SOURCE_SINGLES_NOT_PARENT`，SHA `e3185919566a52d1e5dfd27539ea43e6edabbfeee3bbd3bdc2e30f3de7d1a286`。
- `result.json` SHA `14705b5190ba343823b37c5c7652759b76679ea93ccd59316eacc0175c58a284`，与TERMINAL绑定一致。
- 实际计算child PID1779586、**int returncode0**、365.891142588s、timed_out=false；低层receipt validated=false不是失败标签。receipt SHA `e6c6431f9c58ec91f6c7610d68a861d1b04ae86ee92794b36215a96d1d6960f0`。已审driver在最终接受前保存actual Popen.wait，不能拿已有result文件代替真实退出。
- ATTEMPT_STARTED记录唯一 `audit.py child` 命令、1200s cap、retries0；实际authorization SHA `f4b9a69c0de2a817baecd8b4034afe52a907ea00c0a8f5b297cfa613e752e148`，绑定封存auditor READY `6d3852c74105e0b9c133ad391157d7bbe90783bcb775d7de212f49a868dfb0e6`、原plan及actual parent。
- 原worker complete SHA `c11e7965f77693e5215541410989a7972e9a60acf06bccc258b85d6dc039a7e6`，`PASS_TWO_NAN_MIN_SOURCE_SINGLES_M6_NOT_PARENT`；aborted=false、pins_unchanged=true、retries0；run.json为COMPLETE/PASS2，成员、summary、jobs2/5400s及原命令与plan一致。

| 单项 | Actual DUT monitor rc / seconds | 原 fixture | 结果 / flags / vstart | Last cycle |
| --- | --- | --- | --- | --- |
| nan_min_call1292 | int0 / 3081.964453610 | bank1 row646 | 0x7fc00000 / 0 / 0 | 2563155 |
| nan_min_call1232 | int0 / 2923.244138951 | bank1 row616 | 0x7fc12345 / 0 / 0 | 2563291 |

两项 monitor timed_out=false、failure_seen=false，未后验receipt独立于runner分类；runner_result为PASS，complete/summary的numeric0一致。无root/case first_cause。private CWD/ELF/command/provenance与各自runtimeid和M6simv匹配；没有用source label替代runtimeid，也没有由GC、missing PID或默认ExecMainStatus推断outer service exit0。此处接受的是DUT case及计算审计退出链，outer service numeric exit未建立。

## 生成摘要对照计划 Gate

本次读取已产result和worker存档JSON，不再解析CSV。两项generated对象与worker strict_original.json完整结构相同，generic加status=VALID后与trace_summary.json相同。

- target均为原op1 `14881c57`、PC `0x80000758`，一次target、无unused helper退休。原calls1292/1232、tuple `[1,3,3,0,1,0]` / `[1,3,1,0,1,0]`、SEW32/m1/CAP32/VL3、mask0x24/0与既有source ENTRY相符。
- 两项independent output ledger各144个严格顺序地址/字节，与原oracle逐项比较：前8guard、4字节canonical/payload结果、124字节tail、后8guard全部完整。独立MIN bitwise oracle的结果与fixture/strict结果一致；非用MAX的相同NaN输出猜测操作。
- strict和independent helper各21条：PC、encoding、rd/value/cycle、连续retirement order匹配原SoC routine。原capacity3、outside-helper CSR7、vlenb/capacity及完整args/setup由已审计算审计核查；生成记录相符。
- 实际saved frm/fflags为0，readback vstart/fflags为0；独立ledger完整保留4次request/restore操作数：a6/a7/t4/t5各0，CSR2/1、exact PC/order一致。没有额外post-restore CSR readback或直接vector-port/wave证明的声称；unknown GPR不默认0。
- 每项初始化计数input256、seed512、mask215040byte、output144byte，fixture field reads6720、selected bank1地址/值相符。完整循环setup保留，但不是执行/验收3360个helper或前序helper history。
- 每项1,852,052总rows、1,851,995retire；15对CVX req/resp、15个arch_start、6对uop_alloc/done。六事件计数之和等于总rows；CVX exception/replay和arch replay均0。已审Observer要求最终pending CVX/uop为空、ownership/order/sequence一致、exact schema、consumer收到未改变row，生成summary与worker逐结构一致。

这两份记录各声明且由已审driver执行**一次**闭合CSV遍历；同时求全文件SHA和协议/strict，结果raw SHA与complete evidence/pin表一致。本次只stat核inode/size/mtime/ctime仍与计算审计身份一致，未重新计算raw散列。记录字节数为212,190,781 /212,190,788；不是新raw验收或第二次fullparse。

## Pins 与证据范围

802项pins_pre/pins_post JSON完全相同，文件SHA均 `1f507a6e67562c5152d7618f0534d93bf7fa12a1f61c4178eb4a3a6982bae743`。原plan766项及全部terminal evidence都包含在802项中。786项非raw内容重新散列通过；16个CSV/reference/compile/console/parser/VCS日志内容未打开，只核stat/已产摘要链。未声称本次重新散列全部802项。

原plan SHA `d695a5bdcbc72c1d411859fb4dc800899a71848adbd6fd7bf86927c77c875c5f`、actual parent SHA `2ad535ba669ae50f8bfc3ad39bb3615faa604512fabcd52fbc1643d5ddaea992`、source READY/独立ENTRY、actual M6 image/config、原/私有两ELF、封存worker/auditor/oracle pins均在链内且非raw复核一致。旧MAX STOPPED/封存输入不变，不把旧错误改成PASS。

只读metadata/source-identity验证命令actual exit0，chunk `ed2e2d`，2.622316263s；未导入或执行任何producer/checker，也未查询service或live process。这是本次元数据复核退出，不是新的计算审计/DUT退出。

## 最终 Scope

Main可以记录：**M6上两项原来源MIN source-single的完整架构oracle及既有独立计算审计通过**。仅call1292 active quiet-NaN与call1232 all-off payload点；不是完整Linux/parent、前序调用、所有MIN/NV/sNaN模式，也不是原MIN module84的SoC替代或全局performance结论。保留原scope；不再需要重复raw parse、测试或DUT dispatch。
