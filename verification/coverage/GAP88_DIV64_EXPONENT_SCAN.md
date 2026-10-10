# FP64 非正规结果指数扫描

## 从覆盖缺口到激励

693 项旧镜像的源码绑定分支清单显示，C910 除法器
`ct_vfdsu_round.v:414` 和 `ct_vfdsu_srt.v:423` 的非正规结果指数
case 仍有大量未命中位置。此处的位数跨实例聚合，不等于独立功能数。
仅覆盖一个最小非正规数，不能代表逐级移位和舍入路径已覆盖。

`vgap88_div64_exp.c` 计算正负最小正规 FP64 数除以 `2^shift`，
shift 从 0 到 63，分别使用五种 frm。每批 32 元素、e64/m2，
共 20 次向量除法，640 个元素结果和 40 个 fflags/vstart 检查。

shift<=52 时，结果位模式为 `1ULL << (52-shift)`，是精确结果。
shift=53 是最小非正规数的一半：RNE 取偶数零、RMM 远离零；
shift>53 时，RNE/RMM 均取零，只有按符号方向的定向舍入取最小
非正规数。所有 shift>52 的非精确微小结果要求 UF|NX，其他结果
不要求 underflow。正负结果均保留符号，包括负零。

该预期值由整数位模式构造，不调用被测除法或复制 RTL 舍入逻辑。
Spike 已完成 680 项自检，错误签名和 trap 为零。
旧镜像 VCS 已成功结束，CPU 时间 68.230 秒，120 次请求和响应配对，
协议错误、异常及 outstanding 均为零。680 项 DUT 自检通过。
`admit_gap88_offline.py` 核对 60 条向量提交、15360 字节与 Spike
完全一致，没有未知字节跳过、非位精确结果、未完成或未退休请求；
标量提交至 tohost 一致且 trap 为零。已检查完整输入哈希及签名。

## 实际覆盖增量

独立准入目录：`verification/out/gap88-offline-admitted-695-20261006-01/`。
相对 694 项同设计集合新增行 162、条件 23、分支 167、FSM 0。
历史集合达到 695 项。该增量来自实际 VCS bitmap，不由指令数推算；
已按 raw-bitmap-delta 的实际实例逐项汇总，全部增量均属于向量 lane
的 C910 divsqrt 路径，不含标量自检覆盖增量；其中包含 srt、round、
pack 等多个子模块，不能归给单一子模块。
695 项正式 DVE 报告已独立启动，百分比尚待导出并核验。

## 证据与限制

预检目录：`verification/out/gap88-div64-exp-preflight-20261006-01/`。
VCS目录：`verification/out/gap88-div64-exp-old-image-20261006-01/`。
运行器：`run_gap88_simulation.py`，固定镜像、源码、ELF 和 Spike 轨迹。
ELF SHA256：`6fc7824106b068ca11d2858df588a9c878f75681ebfd9af478138c96205b855d`。

本测试不宣称命中所有指数分支或控制状态。未修改 RTL，历史失败
仍保留且不计入本集合；后续发生 RTL 故障则记录，暂不修改 RTL。
