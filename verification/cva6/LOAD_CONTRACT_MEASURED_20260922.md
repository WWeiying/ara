# Load 等待态与返回竞争实测

## 结论

候选包内真实 `lsu_bypass + load_unit + wt_dcache_ctrl` 的15组局部定向测试已通过。
22条逻辑请求中，9条正常返回、9条异常返回、4条取消；15次cache尝试全部回收，
没有在本组条件下观察到丢请求、双完成或取消后错误结果。**本轮未修改硬件RTL。**

这不是完整CPU/Linux/FPGA通过：翻译结果和cache存储侧是受控边界模型，没有
实例化真实MMU/PTW、scoreboard、load返回流水、ACC翻译竞争或DDR接口。
MMU=0/NI=0的跨配置问题也不包含在本轮通过范围。

| 项目 | 实测 |
|---|---:|
| 场景 | 15组 |
| 逻辑请求 | 22 |
| 正常/异常/取消 | 9 / 9 / 4 |
| cache尝试接受/返回 | 15 / 15 |
| miss边界请求/返回 | 4 / 4 |
| 仿真有效周期 | 112 |
| SV检查 | 464，零失败 |
| 独立Python原始trace重放 | PASS |
| 检查器/runner host测试 | 41通过 |
| 连同既有CVA6 contract及候选准备工具的host回归 | 78通过 |
| 最终VCS编译墙钟 | 24.624秒 |
| 最终VCS运行墙钟 | 10.691秒，包含启动开销 |

## 为什么运行了两轮

首次运行 `verification/out/load-contract-vcs-20260922` 保留 **FAIL**，不修改旧结论。
它记录完全部112周期后仅有一个SV判据失败：测试台错误要求NI请求必须持续停留
在 `WAIT_WB_EMPTY`。原始代码的default分支实际允许回到IDLE重试。

定位使用首轮已有trace，不改RTL、不调参数、不增加超时：

| 周期 | 实际行为 | 含义 |
|---|---|---|
| 65 | NI条件不满足；cache grant，pop=0；转ABORT_NI | cache尝试被接受，但逻辑队头未释放 |
| 66 | kill=1、rvalid=1、valid=0；转WAIT_WB_EMPTY | 回收cache尝试，不产生指令完成 |
| 67 | write-buffer仍阻塞；转IDLE；pop=0、valid=0、队头保留 | 回到IDLE不等于越序执行 |
| 68 | store/write-buffer条件解除；重新接受、pop=1 | 正常顺序门控通过 |
| 70 / 73 | miss接受 / 正常返回 | 正确地址，只完成一次 |

改进后的判据直接检查“NI约束不满足且无异常时不得pop”，并检查队头身份和
最终完成次数，而不是依赖一个中间状态名称。额外增加了host负例，证明提前pop
仍会被拒绝。第二次运行只确认修改后的检查器闭环，不是第二版硬件试错。

最终结果位于 `verification/out/load-contract-vcs-20260922-02/summary.json`。
两轮原始 `load_trace.jsonl` **逐字节相同**，SHA-256均为：

```text
00e9ae2e495aa0aec5c3eb36f2df5bd3a55cb00ecd3ec04920828b0489066f8b
```

## 关键周期证据

### 1. WAIT_GNT：旧返回优先，新异常没有丢失

- C30：请求8进入WAIT_GNT，旧请求7仍在途。
- C31：fault=1，同时旧cache返回。结果归属7且不是异常；请求8不pop。
- C32：旧返回已结束，可再生异常仍有效。请求8只pop/异常完成一次，零cache接受。

这组捕获证实了结果口优先级与队头保留行为。异常可再生来自本测试的翻译边界
模型，不能外推为真实MMU所有PTW错误必定下一拍重现。

### 2. WAIT_PAGE_OFFSET：脉冲消失造成延期，不等于丢队头

- C39：请求10因地址冲突进入WAIT_PAGE_OFFSET，发出一次翻译请求。
- C40：它的异常撞上请求9的旧返回；9先完成，10保留。
- C41-C42：translation_req=0、fault=0，10仍在队头，没有pop或伪完成。
- C43：冲突解除；C44重新翻译；C45异常再次出现，10正确完成。

这实际确认了先前静态分析的“早退机会可能丢失”边界，不证明永久冲突情况下的
无条件活性，也不能仅凭本组通过就删除后续MMU/store依赖的系统级检查。

### 3. Flush与新grant同拍

- C93：请求18在flush同拍被cache接受，分配slot，但逻辑请求归入取消epoch。
- C94：WAIT_FLUSH产生kill，cache给回收应答；load result valid=0，slot清空。
- 后续无额外结果。其他场景还测试了取消旧miss、清除等待队头后复用ID。

结果层仍只是load unit边界；真正一级返回流水、scoreboard issued位及commit/trap
过滤需要完整核心的证据，不能用测试台自己的取消账本代替。

## 可重放材料

准备与探针说明见 [LOAD_CONTRACT_PLAN.md](LOAD_CONTRACT_PLAN.md)。最终输出保存：

- `manifest.json`：选定封装、配置覆盖、源文件与host程序hash。
- `inputs/`：实际编译的RTL、原定义提取的类型、测试台、检查器和执行工具。
- `build/`：命令、编译日志、simv和共享库。
- `run/`：命令、console、config、完整pre/post周期trace。
- `summary.json`：SV/独立重放判定、覆盖事件、输入前后指纹和产物hash。

| 输入/产物 | SHA-256 |
|---|---|
| load_unit.sv | `042db6cbcfdba16f6810a49de010eeb52105829e444a348df5fc7ec89f3ac7dd` |
| lsu_bypass.sv | `c8b0eebd8c800c6fa2307c35541792a9860dc596a8119ad5b5054a2d43dde008` |
| wt_dcache_ctrl.sv | `d2a8a3207ce394d9e703a8dea514759d14ce9995091c0e88c8dbf3b291861e51` |
| 最终simv | `d6a7d2ddbe339580288cfee0f0e67b9c3898ea53bf2a93453b5e0206cda211e9` |
| 最终manifest | `95d67e777ece6a35273258706ccc21c1e622987f5a0480b8597509511a10bb26` |

不能只取一个PASS字符串，或用相同文件名的新RTL覆盖冻结输入。正常退出和
完整trace都通过检查后，才接受本局部结果。

## 下一步

停止扩充与本根因无关的局部试跑，转向真实SoC组合：候选 `cheshire_soc`、
真实MMU/中断与稀疏外部存储的VCS环境。具体可复用top、源列表、boot机制、
Linux地址及缺失模型已记录到 [SOC_SIMULATION.md](../fpga/SOC_SIMULATION.md)。
整机运行、板卡Linux、上下文隔离和原生llama.cpp仍未完成，不能据此签核。
