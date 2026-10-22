# 当前 RTL 全回归

## 范围

本轮重新运行历史已登记的 798 项主回归激励，不继承旧镜像的 PASS 或 VDB。
前 600 项保留原 ELF、检查器和逐项运行限制：201 项随机/严格重放、346 项
定向测试、52 项 UVM 测试和 1 项 AXPY 性能检查。随后运行 198 项扩展激励。
主队列最多 8 路并行，不自动修 RTL、不自动重试；功能失败继续，基础设施错误
停止派发。不能可靠重新核对的扩展项应明确标为检查未闭环，不能算作 PASS。

另外独立重跑 WT cache invalidation / AXI R 冲突测试：30 项修复后场景，
以及 5 项原版对照（1 项正常控制、4 项预期失败）。对照不计入修复后 PASS 数。
因此主回归和新增定向测试合计 828 个修复后测试场景，不包含主机脚本单元测试。
模块测试与 SoC 测试分别报告，不把模块测试 VDB 合并到 SoC 数据库。

本轮不运行完整 Linux 启动或先前预算暂停的超长 FPGA 原始软件；这些不属于
上述 798 项历史集合，不能据本轮结果宣称系统级 signoff 或原始板测问题全部关闭。

## 当前环境

- 工作树：`/home/wangwy/openproject/ara_dsa_signoff_integration`
- 编译：`verification/out/full-regression-build-20261015-01/`
- 回归：`verification/out/full-regression-20261015-01/`
- 宿主机 VCS；覆盖率使用 VCS/DVE，不使用 Verilator、URG。
- 本轮包含 WT adapter RREADY 外部 invalidation 修复；不包含 FPGA AXI ID remap 优化。

## 查看进度

在验证工作树根目录执行：

```bash
jq . verification/out/full-regression-20261015-01/progress.json

jq '{status,phase,total,completed,passed,counts,reason}' \
  verification/out/full-regression-20261015-01/full-regression-core-20261015-01/checkpoint.json

systemctl --user status \
  ara-full-recollection-full-regression-core-20261015-01.service --no-pager

tail -n 20 verification/out/full-regression-build-20261015-01/compile.log
```

`checkpoint.json` 在输入冻结完成后生成；文件尚不存在不代表仿真失败。
`progress.json` 是父级阶段记录；逐项完成数量以 core checkpoint 和 extension
进度文件为准。DVE 导出成功前，不报告本轮覆盖率百分比。

## 检查依据

core 使用既有定向自检/trace audit、Spike 标量及向量严格比较、UVM 协议检查和
独立 audit，不将旧 PASS 直接当成新结果。历史 wall-clock 预算只在精确匹配
ELF 的既有审查规则内复用，不修改程序或 RTL watchdog。覆盖率仅收集实际通过
检查的当前镜像 VDB；旧 exclusions 不匹配新设计时不能强行套用。
