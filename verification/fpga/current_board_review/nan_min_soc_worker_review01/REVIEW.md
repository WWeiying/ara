# MIN Worker 与条件终审入口

结论：**NO BLOCKER**，封存 MIN worker/plan、条件终审 audit/observer及后交接的 event-only waiter 在本任务范围可接受。只读代码/元数据/pins；没有打开任何 reference raw 或 DUT CSV，没有测试/仿真/build/worker 执行或 sealed 输入修改。不是两项 DUT 终态验收，也不替 Main 提供新的运行或审计授权。

## 精确绑定

| 证据 | SHA256 |
| --- | --- |
| `nan_min_soc_vcs_m6_plan01/prepared01/plan.json` | `d695a5bdcbc72c1d411859fb4dc800899a71848adbd6fd7bf86927c77c875c5f` |
| Worker READY | `7d3df769aaaff253c50a5e83ad64cc151293a3afee7f9c0e876d4c66ad0e77b0` |
| Worker `replay.py` | `44539d4add863ab707e769d57440156adde8d196a27b20a00e60ba2e62384546` |
| Worker `checker.py` | `e4d0e91e819124c0336e9bf3964eee5f8940f62434f962d913513ab36d2c1835` |
| Actual `parent_review.json` | `2ad535ba669ae50f8bfc3ad39bb3615faa604512fabcd52fbc1643d5ddaea992` |
| `nan_min_soc_terminal_audit01/READY.json` | `6d3852c74105e0b9c133ad391157d7bbe90783bcb775d7de212f49a868dfb0e6` |
| Auditor `audit.py` | `2ff23478e0d0d96594d43c3ffb48e06b4bc6d77c2f77d33b3fa5c17b699fd908` |
| Auditor `observer.py` | `65b69df727cf3bae3198a2b9ac35a9575295fc12dd375e80c40e12758172b949` |

Worker plan766 pins：762非 raw 文件前后散列一致，4 reference raw 仅 stat 和已产摘要链。READY metadata pins、dryrun command pins、source READY/独立 ENTRY/实际 parent、M6 image/snapshot/config/compiled manifest 均绑定。Auditor6封存 pins 全部匹配。未复核 live process；既有 launch.json 记录直接 owner MainPID1745502、同名 cgroup、RuntimeMax2h、KillMode control-group/Restart no；这只是保存的启动证据，不是当前状态或 outer exit0。

M6 image SHA `a681e2744dc51a9ebfbef39d6da68707e29041e7fe4ad79ed392c62466167da0`，snapshot `3cba2d3a6a10c76cb4a2ee0098e3a3755e76b5903920b8b09b0fdadd2999f438`，config `6aaa87d2cdbabde8aee6baebad81dc7109d08361f788e799a44420f7cd037785`。不新建 identity/build。

## Worker 与完整原 Oracle

精确运行成员为 `nan_min_call1292` / `nan_min_call1232`，源 label 单独为 `rvv_fp_redspecial_e32_m1`。原 tuple `[1,3,3,0,1,0]` / `[1,3,1,0,1,0]`、bank1 fixture646/616、SEW32/m1/CAP32/VL3；target `14881c57`、op1，不是 MAX。实际 source review/ENTRY/READY schema 和142来源 pins 均验证，不以假 attestation 替代。复用源审查，不再次解析 gold raw。

checker 从实际 SoC ELF 构造 specs 并对 plan 完整比较，禁止 op0/op2 全内部范围，要求原21条连续退休和 capacity3/vlenb128。mask0x24仅元素2 active，mask0全 off；bitwise MIN oracle固定为已审 hash `f2a94cb15dc82716bf654436d109a4c3140f4269244b7f596ccb6f8d295bb407`。全144 ordered LBU检查4字节结果、124字节 tail、前后8字节 guards；保留完整 setup、256 input/512 seed/215040 mask初始化、6720 fixture fields，fixture bank/address/order/value都核对。

真实 CSV 没有 Spike 的 CSR write-delta 字段：worker核原指令序列、保存/请求/恢复的真实 GPR值与 source operands、flags/vstart readback0，不能伪称直接 CSR delta或额外 post-restore readback。参考中的严谨 delta 链已被 source READY/ENTRY绑定；不是将缺失 DUT字段默认0。初始化 GPR仅x0已知，未知状态不默认清零。完整 scalar oracle证明架构输出，不冒充直接 v24 payload/wave观测。

strict允许 exact六事件 `retire/cvx_req/cvx_resp/arch_start/uop_alloc/uop_done`，而非只放行旧三类。frozen generic同时严格核 retirement/order、CVX pending/response、arch order/encoding、uop VID ownership/completion/最终 empty queues及 vector-request序列；只允许其原 side-effect-free CSR-read transport replay，不允许数据/内存请求重放。六事件 whitelist不是协议验收的替代。

两个 private CWD 的 immutable monitor路由在 worker线程前安装；actual command/console/runtimeid/5400s必须精确。monitor返回的原 numeric tuple **先 durable 保存**到 `child_outcome.unvalidated.json`，然后才做 command provenance和任何 generic-parent后验；故 rc17/timeout或 generic后验异常不能丢失真实 outcome。已有 Host13/0/0报告和测试代码覆盖真实 frozen-parent early-postcheck rc0/17、timeout -9、两路隔离、错误CWD/预算、late signal/pin drift；未重跑。

first-cause和abort为sticky：非零/timeout/failure_seen即停，generic或strict异常停，late abort拒PASS，最终publish也检查pending signals。COMPLETE/PASS2、两项actual int0/无原因/预算、summary一致、最后磁盘 plan与全pins/image/parent复核后才发布成功；无自动retry。case5400s/jobs2、service7200s/directMainPID、reserved0；cap24/memory32GiB fail-closed。资源读取只忽略退出race，权限等其余OSError不吞掉。

## 条件终审：读 CSV 前的 Gate

审计必须另有 Main `AUTHORIZE_NAN_MIN2_TERMINAL_AUDIT_ONCE`，绑定实际 auditor READY、plan、两成员、complete SHA、actual parent path/SHA。run及child重复 gate，**在任何 CSV open之前**要求 whole2 `PASS_TWO_NAN_MIN_SOURCE_SINGLES_M6_NOT_PARENT`、aborted=false、pins_unchanged=true、retries0、runner COMPLETE/PASS2/summary精确、无任何 first_cause；每项 monitor的actual int0/timeout=false/failure_seen=false以及private command/provenance必须一致。只看到 firmware marker、classification PASS或 missing PID/GC均不够。

child再次核 compiled SoC specs、原raw logs/完整 marker否决、source/image/input/command/evidence pins。对每份已闭合 CSV，`HashLines`只打开一次，遍历同时算全SHA；Observer核exact schema和六事件协议、完整原输出/fixture/init/CSR operands，原 strict消费者收到未修改row。before/after row digest、原始 inode/size/mtime/ctime/EOF与terminal raw SHA一致；独立 strict/generic结构须与worker strict_original/trace_summary完整相同。不是只读 gate PASS。

原 scalar数据与 independent MIN oracle共同检查；Observer保留 unknown GPR、op1/fixture646/616、144B与guard要求。assert-based Observer只在 `sys.flags.optimize==0` 的child运行，否则先拒绝。已有 focused Host覆盖numeric MIN/负零、unknown GPR、guard、原 CSR replay与非CSR重复拒绝；仅审代码与报告，没有重跑。

单计算child限1200s，actual Popen.wait numeric结果在新acceptance前fsync保存；非零/timeout保存STOPPED、禁止再次run。child结果和最终TERMINAL分开，TERMINAL绑定actual exit/result/authorization/plan hashes。Main仍需等真实whole2终态后授权；本审查没有执行审计，也没有whole2/outer service终态事实。

## 事件 Waiter 补充入口

Zeno 在本次结论封存前交接 `nan_min_soc_terminal_waiter01/READY.json`，SHA `f9b95e7ca53c8500353693b94b9ef0c7dd62ed52f55a9fe1248ac72c58985d5e`；waiter.py SHA `6ab72e5bef5d88bb4df65ac79ca57f771774ed03a836d645038bedd45dff8d69`。14非 raw pins均复核一致，绑定实际 launch SHA `4199a32c18f7fd94e72dd8d8d9e07236f48263460c116a1517eb6be46ed0bf08`、同一 plan/parent/auditor。只读审其已有真实短标量 pidfd/4个身份与cgroup负例代码和PASS记录，未运行。

它固定PID1745502、start ticks281255053、boot ID，并核实际 argv（替换原ready中parent placeholders）、精确原cgroup和launch身份；pidfd_open后再次查同一lifetime，身份不符/attach race失败即STOPPED，不误接受复用PID。单次阻塞 poll7200s，无周期仿真轮询；退出后原cgroup须移除或全部membership为空，残留/不可读拒绝。只调用已审 auditor.terminal_gate（纯终态JSON/命令元数据），绑定实际complete SHA后产给Main的metadata-ready记录，**从不调用 audit.run/child、不读CSV、不自动批准**。PIDFD事件不提供numeric worker exit，代码明确worker exit unavailable/service_exit_inferred=false。若来不及attach也只STOPPED，不自动fallback或重试。

独立waiter unit `ara-nan-min-two-source-terminal-event01.service`、RuntimeMax7500s、KillMode control-group/Restart no，仅约束observer；不扩大原DUT7200s服务预算、不杀原worker，也不占simv slot。此审查未attach、未确认waiter服务真实运行；附件启动由Main/Zeno协调，实际audit仍待whole2PASS后另授权。

## Scope 与尚未覆盖

仅接受上述封存 worker/plan、条件auditor及绑定的event-only waiter代码入口；不关闭 prior-helper history、完整Linux/parent、原MIN module84或full MIN覆盖。source/reference输入接受不等于DUT接受；service exit明确不由GC推断。

只读 pin/schema命令 actual exit0：chunk `ff20fb`；final worker/auditor pin复核 actual exit0：chunk `8e8707`；waiter pin/schema复核 actual exit0：chunk `a2195c`。无 raw/CSV、producer导入/执行、Live查询。
