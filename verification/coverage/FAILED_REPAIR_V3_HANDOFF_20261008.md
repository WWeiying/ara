# 原6项与17项邻接验收：v3 准备交接

## 状态

仅准备后继 runner 和离线单测，不启动 EDA、构建、仿真、服务或全量回归。
不修改 v2 runner、Avicenna 的 checker、其他封存 helper、原始 FAIL 或 RTL。

- 新 runner：`run_failed_repair_20261008_v3.py`。
- 离线单测：`test_failed_repair_20261008_v3.py`。
- 默认调用只打印 `PREPARED_ONLY` 及原6项/17项清单；后续真正执行必须显式加 `--execute`。
- 原6项与17项顺序和两阶段门禁复用冻结 v2；仍为最多5个 worker，发现失败后停止补发，已在跑的独立点完成留证，全部通过后暂停等人工下一步。

### 最新执行决策：build03 不复用 build02

父端确认新的 `vmset` 同源初始X根因，Avicenna准备 `masku` 修复；后续使用 **build03新镜像，全6项+17项重新执行**。启动时省略 `--previous-output`、`--wait-previous-unit`，不复用build02的任何PASS。本文下方保留复用功能的严格契约，但它不是当前build03的执行策略。

新镜像路径的调用链明确为：v3 `main()` 在进程内临时将冻结调度器的 `audit` 绑定为v3 `audit`，后者对 `qbs_canonical` 直接调用已pin的 `audit_qbs_canonical_repair_v2.audit(directory, output=新目录)`。只有QBS/FOF之外的case才委托旧通用audit。退出或异常都会恢复旧globals；没有改写任何v2文件。离线单测覆盖这个调用分派，并把“旧checker收到QBS调用”作为硬失败。

FOF接口补充：`vgap112_sv39_fof`也单独分派至Ampere的 `audit_fof_repair_v2.audit(directory)`，不会进入旧FOF blanket-known checker。执行入口先调用 `fof_checker()` 导入v2及其依赖，再交给调度器生成source pins。范围仍为原6+17，不增加新验收点。

**FOF v2已由Ampere冻结，父端确认亲跑15项PASS。** 已核对并填入 `FOF_CHECKER_SHA=3b7e93f1722d81eeea4989aa2dbdf1f6eb498b486db1ecff5c108da4837e95c0`；对应单测文件hash为 `6483b34c9f7f7babc8287fe62bd0ac7f79ba38bbb6d2f49646a837e21cf38826`。不再等待接口确认，不创建v4。v3完成最小集成后冻结，交父端启动build03新镜像的原6+17验收，不复用build02。

本次只跑6项接口离线单测，全部PASS（0.084秒）：FOF v2实际分派、非PASS拒绝、未确认hash阻止启动、预导入先于调度、globals异常恢复，以及QBS v2分派保护。没有重做全套re-audit，没有启动EDA。

## Avicenna checker 接口

用户已转交 Avicenna 的 v2 PASS 及24项单测闭环：

```text
verification/coverage/audit_qbs_canonical_repair_v2.py
SHA256 3f4a87537a63e443f7415396ee5fe43620f138785fcf4bc153480ec0925955f8

verification/out/qbs-canonical-repair-v2-audit-20261008-02/receipt.json
SHA256 ded9b3364cc35b6dcf98cced5a68c7bbbf235dbb2f0babb49b9e55ced0cfa55c
```

适配实际已有 API，不要求修改 checker：

- 新仿真完成后：`audit(directory, output=独立新目录)`，返回严格证据或抛异常。该 API 可能运行 VPD 转换器，只在后续人工授权的执行路径调用。
- 同 build 历史日志离线复验：先绑定上面的 PASS receipt、input/output pins，再调用 `native_architecture(commit, vector, info, blob, output)` 和 `cycle_wave(已合格VCD, last_cycle, console)`。不再启动转换器，也不启动仿真。
- 离线复验仍运行软件 fixture、数值/UART、恢复指令、owner/完整读回和 read-engine 波形检查。结果须与合格 receipt 的 stdout/perf/architecture/cycles 完整一致；只将内存 tuple 规范化成 JSON array 比较，不删除字段或放宽数值。
- 波形判据保持门控时钟语义：295个活动边沿不等于147935个主时钟周期。由 reset 到 simulator finish 的绝对时间戳、核心周期下界及末态排空检查完整性。
- 不再要求错误的 tohost 地址或 `arch_start.pc`；沿用 v2 的 native MMIO `_eoc`、精确退休 PC 和请求 owner 绑定。
- 保留 `per_beat_protocol_certified=False` 与 `independent_full_scalar_ISA_replay=False`，不把现有检查范围升级成没有证据的证明。

## 复用边界

只允许从 `failed-repair-acceptance-20261008-03` 复用，并要求原 campaign 已终止、所属服务已由冻结 v2 的等待机制确认停止。

1. 一般情况只接纳原 `audit.json` 为 PASS 的已完成点，并重新执行其独立 checker。
2. 唯一 FAIL 例外为该目录的 `qbs_canonical`，原因必须精确等于 `ValueError: Exact terminal tohost store`，且原 audit SHA 必须为 `6b953c059f5d8f2387fd1192fb3c7ae6694066861d2c2caded28749e4effc1f5`。
3. 这个例外还必须通过上述已闭环 QBS v2 的严格离线重验；新的目录记录 PASS、原 status=FAIL、纠正原因为 checker，不改原 audit。
4. 其他 FAIL、TIMEOUT、已启动但不完整、campaign仍运行、缺少正常finish、协议错误，全部拒绝复用，也不自动重试。
5. 只有从未启动且状态为 QUEUED、目录为空或仅有预置 ELF/Spike 的点，才交给原 runner 后续启动。
6. FOF若需要新build，旧build的PASS也不能用来替代新build验收。`build-image.json`（包括共享库）和 `build-source-pins.json` 任一路径/hash不一致即拒绝；同image但当前源码已改也拒绝。新build须不带 `--previous-output`，重新执行相同23项范围。

复用时同时核对：build完成状态、全量镜像/源码pins、冻结runner来源、原ELF与本地/参考ELF、Spike参考（若有）、started与command的精确命令和工作目录、1800秒预算、两份日志的唯一SUCCESS/正常finish/一致结束时间、trace不超出结束时间、UVM/AXI汇总及contract。

终止协议不是统一强求UVM report：MMIO用例要求完整UVM收尾及AXI汇总；`+COMMIT_TOHOST`用例则要求`ara_commit_monitor.sv`的精确finish来源、两份日志一致的独立ARA_CONTRACT终态（请求响应配对、无错误/在途/悬挂），再由该用例原严格checker验证实际终止store及架构结果。后者本来就先于UVM report阶段退出，结果明确记录这点，不宣称补出了缺失的UVM阶段或逐beat证明。不是看到UVM失败就自动降级，而是根据冻结的case/ELF启动协议事先选定检查路径。

acceptance03中的一部分PASS实际来自acceptance02。v3追溯其 `reused_completed_same_image`、原始evidence pins、acceptance02源码/image pins及冻结v1控制流，不能把03的symlink当成03重新仿真。

## 进程退出码的证据限制

旧runner没有单独写 `process-exit.json`，不能事后伪造一个。冻结v1/v2都先 `proc.wait()`、拒绝非零退出、检查pins，然后才调用audit；因此原PASS或这一个精确checker FAIL可以由控制流推导仿真返回0。v3还要求完整正常finish及严格数据复验。

结果明确写 `simulator_process_exit_verified=False` 和 `process_exit_basis`，表示没有独立退出码文件。不得把该推导表述为已有独立OS退出码证据。一般FAIL不能借此获准，尤其不能根据SUCCESS文字掩盖后续崩溃。

## 原证据保护

v3只向新的结果目录复制原始日志/轨迹/小型VPD；不链接会被checker写入的旧comparison/audit JSON，不复制或合并旧VDB。
旧文件pins在重验前后复核。原FAIL保留，新结果单独记录纠正来源及原audit hash。

## 离线单测命令（不是启动验收）

```bash
cd /home/wangwy/openproject/ara_dsa_signoff_integration
env PYTHONDONTWRITEBYTECODE=1 \
  PYTHONPATH=verification:verification/coverage:verification/tools/plic-venv/lib/python3.9/site-packages:verification/tools/soc-venv/lib/python3.9/site-packages \
  python3 -m unittest verification.coverage.test_failed_repair_20261008_v3 -v
```

测试中禁止 `subprocess.run/Popen`；真实QBS receipt测试只读现有轨迹/VCD，在临时目录写独立重验输出。负向项覆盖：其他FAIL/超时/不完整、伪造原因、非白名单audit、checker拒绝、build/source/image/ELF/命令漂移、finish缺失、时间不一致、协议失败、历史输入被改、acceptance02继承证据漂移等。

接入FOF v2之前的离线核验结果：**35项全部PASS，7.511秒**。包含真实QBS v2 receipt重放、两类实际终止日志检查、新镜像QBS分派不调用旧checker、临时globals在正常/异常退出后恢复。没有执行 `--execute` 的真实调度器，也没有启动任何EDA工具。

后续执行仍沿用v2的 `--image-directory`、新 `--output`、`--wait-build-unit`（若需要）、`--previous-output` 与对应 `--wait-previous-unit`。v3只额外要求 `--execute`。本交接没有运行这些命令。
