# 给FPGA会话：仅测试低开销时钟，不重跑模型

原四次模型结果已收到并复核。现在先不要重跑模型或修改位流。
Decode计时扰动3.82%尚未通过2%门槛；下一步先用一个独立小程序判断是否可用
用户态`rdtime`降低计时开销。可读与否均是有用结果，不要求人为打开权限。

主机ELF：

```text
/home/wangwy/openproject/ara_dsa_signoff_integration/verification/out/stage1_clock_preflight_20261109_01/clock-preflight
```

SHA256：`cac1003f8c03d4bf9f9be1f9fd163b3e963ede9dcdce6661de303ebbb10c4cb2`。
同目录`result.json`和`elf-identity.txt`记录源文件哈希和静态RV64GC目标身份。
源码在`verification/performance/next_mechanism/stage1/clock_preflight.c`。

板卡空闲后，复制到新的诊断目录，核对哈希，再执行一次：

```sh
sha256sum ./clock-preflight
./clock-preflight > clock-preflight.jsonl 2> clock-preflight.stderr
echo $? > clock-preflight.exit_code
od -An -tx1 /proc/device-tree/cpus/timebase-frequency > timebase.hex
```

最后一个设备树文件若不存在，保留报错并回传，不创建或修改它。
如实际挂载在`/sys/firmware/devicetree/base/cpus/timebase-frequency`，可读取该路径，
并记录实际路径。`timebase-frequency`为设备树大端整数，不是处理器主频。

程序不加载模型、不调用QBS/AKV、不读MMIO、不更改sysctl/perf权限、不挂载文件
系统、不重启。rdtime在子进程中执行；若被禁止，子进程失败不会终止shell或
其他进程，父进程会报告信号和非零退出码。程序仅对自身关闭core dump。

请回传完整stdout/stderr、退出码、设备树timebase值及实际板卡时钟。不需要
上传模型或生成新VCS数据。通常为秒级诊断；若异常持续运行，先保留状态并报告，
不要等数小时。不要改变内核权限使其强行通过。

成功输出`RDTIME_READABLE_NOT_YET_CALIBRATED`只表示可读和样本递增；主线程还要
核对三段ticks/ns比例、设备树频率和读取开销。它不是硬件cycle PMU，也不代表
新探针或阶段1已经验收。若不可读，则改用减少ROI内记录/计时次数的后继探针。
