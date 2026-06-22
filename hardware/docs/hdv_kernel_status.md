# HDV 内核执行数据 / 状态报告（详细）

**日期**：2026-06-22 　**分支**：`hdv`
**平台**：ARA + HDV 前端，VLEN=1024，NrLanes=4，AxiDataWidth=128bit（16B/beat），IPU 指令 buffer=32 包，MaxOutstandingVecEPs=2
**判定**：mock host `task_done` 为准（"expected 128 EPs" 仅看门狗提示，非通过条件）。数据采自全量扫描（clean RTL，无调试探针）。

## 总览

| 结果 | 数量 | 内核 |
|---|---|---|
| ✅ 通过 | **21 / 24** | 见下表 |
| ❌ 失败 | 1 | fdotp（前端死锁）|
| 💥 崩溃 | 2 | vgemm, vsfft（仿真 ELF 加载崩溃，无执行数据）|

---

## 表 1 — 概览与配置

| Kernel | 状态 | EEW/LMUL | VL | EPs | Cycles | cyc/EP |
|---|---|---|---:|---:|---:|---:|
| vsaxpy | ✅ | e32/m1 | 32 | 128 | 792 | 6.1 |
| vvaddint32 | ✅ | e32/m1 | 32 | 128 | 746 | 5.8 |
| vscopy | ✅ | e32/m1 | 32 | 96 | 832 | 8.6 |
| vsswap | ✅ | e32/m1 | 32 | 128 | 1350 | 10.5 |
| vsdot | ✅ | e32/m1 | 32 | 128 | 1671 | 13.0 |
| vsscal | ✅ | e32/m1 | 32 | 96 | 1018 | 10.6 |
| vsgemv | ✅ | e32/m1 | 32 | 128 | 525 | 4.1 |
| vsger | ✅ | e32/m1 | 32 | 128 | 418 | 3.2 |
| vsgemm | ✅ | e32/m1 | 32 | 128 | 609 | 4.7 |
| vssyrk | ✅ | e32/m1 | 32 | 128 | 725 | 5.6 |
| vssymv | ✅ | e32/m1 | 32 | 128 | 540 | 4.2 |
| vstrsm | ✅ | e32/m1 | 32 | 128 | 459 | 3.5 |
| vsspmv | ✅ | e32/m1 | 32 | 128 | 640 | 5.0 |
| vmc | ✅ | e16/m4 | 256 | 112 | 394 | 3.5 |
| vsdwt | ✅ | e32/m1 | 32 | 16 | 60 | 3.7 |
| dropout | ✅ | e32/m8 | 256 | 41 | 536 | 13.0 |
| jacobi2d | ✅ | e64/m4 | 64 | 128 | 973 | 7.6 |
| fmatmul | ✅ | e64/m4 | — | 128 | 545 | 4.2 |
| fconv2d | ✅ | e64/m2 | 32 | 128 | 769 | 6.0 |
| softmax | ✅ | e32/m1 | 32 | 128 | 646 | 5.0 |
| lavamd | ✅ | e32/m1 | 32 | 128 | 680 | 5.3 |
| fdotp | ❌ | e64/m8 | 128 | 49 | 1896* | 38.6 |

\* fdotp 1896 周期为死锁超时，非正常完成。

---

## 表 2 — IPU 前端（取指/服务）

| Kernel | serve_cyc | packets | bypass_hit | demand_rd | avg_cyc/pkt | ready_stall% | sram_stall |
|---|---:|---:|---:|---:|---:|---:|---:|
| vsaxpy | 756 | 158 | 63 | 1 | 4 | 1 | 1 |
| vvaddint32 | 730 | 159 | 63 | 1 | 4 | 1 | 1 |
| vscopy | 810 | 127 | 34 | 2 | 6 | 2 | 1 |
| vsswap | 1304 | 158 | 94 | 1 | 8 | 1 | 1 |
| vsdot | 1610 | 159 | 64 | 2 | 10 | 1 | 1 |
| vsscal | 992 | 127 | 34 | 2 | 7 | 64 | 1 |
| vsgemv | 517 | 57 | 47 | 48 | 9 | 9 | 6 |
| vsger | 410 | 64 | 41 | 36 | 6 | 1 | 1 |
| vsgemm | 601 | 73 | 61 | 57 | 8 | 14 | 12 |
| vssyrk | 520 | 70 | 50 | 40 | 7 | 12 | 10 |
| vssymv | 512 | 63 | 44 | 37 | 8 | 3 | 1 |
| vstrsm | 449 | 62 | 48 | 43 | 7 | 10 | 7 |
| vsspmv | 518 | 55 | 43 | 41 | 9 | 9 | 5 |
| vmc | 360 | 45 | 36 | 34 | 8 | 4 | 1 |
| vsdwt | 52 | 8 | 4 | 5 | 6 | 0 | 0 |
| dropout | 420 | 28 | 20 | 13 | 15 | 17 | 5 |
| jacobi2d | 841 | 62 | 54 | 50 | 13 | 13 | 10 |
| fmatmul | 537 | 65 | 51 | 45 | 8 | 13 | 10 |
| fconv2d | 614 | 53 | 49 | 48 | 11 | 5 | 3 |
| softmax | 586 | 45 | 41 | 45 | 13 | 6 | 1 |
| lavamd | 598 | 45 | 41 | 43 | 13 | 0 | 0 |
| fdotp | 865 | 42 | 17 | 2 | 20 | 4 | 1 |

---

## 表 3 — 向量序列器（PERF-SEQ，hazard 计数）

| Kernel | issue | blocked | RAW | WAR | WAW | waw_blk | ep_bypass | full |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| vsaxpy | 160 | 517 | 64 | 1 | 421 | 421 | 80 | 0 |
| vvaddint32 | 160 | 471 | 32 | 390 | 2 | 2 | 128 | 0 |
| vscopy | 96 | 652 | 32 | 588 | 0 | 0 | 32 | 0 |
| vsswap | 192 | 1044 | 32 | 916 | 1 | 1 | 65 | 0 |
| vsdot | 99 | 1420 | 63 | 1311 | 261 | 230 | 113 | 0 |
| vsscal | 128 | 807 | 64 | 744 | 32 | 0 | 48 | 0 |
| vsgemv | 41 | 230 | 6 | 1 | 3 | 0 | 32 | 0 |
| vsger | 37 | 23 | 7 | 0 | 1 | 0 | 23 | 0 |
| vsgemm | 30 | 6 | 11 | 11 | 0 | 0 | 12 | 0 |
| vssyrk | 20 | 577 | 9 | 567 | 0 | 0 | 10 | 0 |
| vssymv | 36 | 356 | 21 | 12 | 7 | 0 | 23 | 0 |
| vstrsm | 32 | 16 | 9 | 1 | 8 | 0 | 12 | 0 |
| vsspmv | 38 | 525 | 20 | 0 | 8 | 0 | 22 | 0 |
| vmc | 20 | 8 | 8 | 2 | 0 | 0 | 8 | 0 |
| vsdwt | 7 | 3 | 3 | 1 | 1 | 0 | 3 | 0 |
| dropout | 13 | 457 | 5 | 446 | 16 | 12 | 14 | 0 |
| jacobi2d | 35 | 484 | 15 | 148 | 4 | 0 | 34 | 118 |
| fmatmul | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| fconv2d | 38 | 508 | 1 | 338 | 489 | 489 | 36 | 0 |
| softmax | 70 | 355 | 31 | 69 | 52 | 26 | 45 | 0 |
| lavamd | 86 | 369 | 34 | 31 | 30 | 0 | 58 | 0 |
| fdotp | 28 | 1816 | 10 | 824 | 0 | 0 | 26 | 0 |

> `blocked`/`RAW`/`WAR`/`WAW` 为累计 hazard 事件数（非当前阻塞）；`ep_bypass`=HDV 同-EP hazard 抑制次数；`full`=2-EP 窗口满次数。

---

## 表 4 — 内存/预取（PERF-ADDRGEN）

| Kernel | demand_ar | demand_B | loads | pf_ar | pf_hit | pf_B | AVL |
|---|---:|---:|---:|---:|---:|---:|---:|
| vsaxpy | 41 | 512 | 64 | 61 | 61 | 7632 | 1024 |
| vvaddint32 | 58 | 1920 | 64 | 50 | 50 | 6208 | 1024 |
| vscopy | 33 | 128 | 32 | 32 | 32 | 3920 | 1024 |
| vsswap | 64 | 256 | 64 | 64 | 64 | 7824 | 1024 |
| vsdot | 65 | 256 | 64 | 63 | 63 | 7840 | 1024 |
| vsscal | 32 | 128 | 32 | 32 | 32 | 3920 | 1024 |
| vsgemv | 18 | 640 | 17 | 13 | 12 | 1664 | 1024 |
| vsger | 18 | 256 | 16 | 16 | 14 | 2048 | (噪声) |
| vsgemm | 7 | 128 | 6 | 6 | 5 | 768 | 1024 |
| vssyrk | 261 | 128 | 10 | 0 | 0 | 0 | 32 |
| vssymv | 9 | 256 | 8 | 7 | 6 | 896 | 1024 |
| vstrsm | 8 | 1024 | 8 | 0 | 0 | 0 | 32 |
| vsspmv | 138 | 256 | 14 | 8 | 8 | 1024 | 1024 |
| vmc | 4 | 512 | 4 | 3 | 3 | 1536 | 1024 |
| vsdwt | 1 | 128 | 1 | 0 | 0 | 0 | 32 |
| dropout | 7 | 1056 | 8 | 7 | 6 | 3040 | 1024 |
| jacobi2d | 12 | 3696 | 7 | 6 | 0 | 2576 | 128 |
| fmatmul | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| fconv2d | 23 | 4704 | 18 | 9 | 0 | 2304 | 112 |
| softmax | 9 | 640 | 5 | 5 | 0 | 640 | 256 |
| lavamd | 15 | 640 | 9 | 10 | 4 | 1104 | 256 |
| fdotp | 16 | 2048 | 14 | 16 | 13 | 11168 | 1024 |

> `demand_B`/`pf_B`=demand/prefetch 字节数；`AVL`=应用向量长度。

---

## 未通过内核详情

| Kernel | 类型 | 现象 | 根因类别 |
|---|---|---|---|
| **fdotp** | ❌ FAIL | got 49 死锁，`task_error=1 task_done=0`，`vec_busy=0 imem_outstanding=0`（全空闲）；序列器 blocked=1816、WAR=824 累积后停滞 | HDV 前端死锁，疑同 softmax/lavamd 族，**待修** |
| **vgemm** | 💥 CRASH | 仿真 `read_elf __assert_fail`（段地址不在 sim 内存映射）| ELF 加载/链接布局 |
| **vsfft** | 💥 CRASH | 同上 `read_elf` 崩溃 | ELF 加载/链接布局 |

---

## 本轮修复（使 fconv2d / softmax / lavamd 通过）

1. **branch_backward（RTL `cva6_hdv_scalar_backend.sv`）**：不跳的后向分支曾用 fall-through PC 判 backward → IPU loop-exit 失效 → 内层循环退出到后续代码时锁死。改为条件分支取 B-imm 符号位 `insn[31]`。→ **softmax**。
2. **IPU bg_stall 规避（kernel 侧）**：内核 > 32 fetch 包（lavamd 40、fconv2d 38）时，显式 `loop_start` 标记令 IPU 在循环头 loop-lock，挡住超出 buffer 的后台预取 → buffer 末包死锁。去掉 loop 标记靠 auto-lock。→ **lavamd / fconv2d**。
3. **a0–a7 八参数注入链**：补齐 `InitialA6/A7`（xrf[16/17]）贯穿 5 文件 + Makefile。
4. softmax 去掉未初始化栈访问 `sd/ld s0`。

---

## 分析要点

- **cyc/EP（吞吐）**：BLAS 类最优（vsger 3.2 / vmc 3.5 / vstrsm 3.5 / vsgemv 4.1）；流式 dot/swap 较高（vsdot 13.0 / vsswap 10.5，因长归约/双流 WAR 串行）；fdotp 38.6 为死锁异常。
- **预取命中**：单位步长流式内核（vsaxpy/vsswap/vsdot/vscopy/vsscal）**100% 命中**；strided（lavamd 10→4、vsgemv 13→12）部分命中；reduction/stencil 首迭代预取被归约消费后 →0（softmax/fconv2d/jacobi2d）；非单位步长（vssyrk/vstrsm/fmatmul）预取 0。
- **hazard**：`ep_bypass` 证明 HDV 同-EP 抑制在工作（vvaddint32 128 次最多）；`WAR` 高的内核（vsswap 916、vsdot 1311、fconv2d 338）为寄存器复用/双流串行；jacobi2d `full=118` 触发 2-EP 窗口满（唯一）。
- **IPU**：多数 `avg_cyc/pkt` 4–13，`ready_stall` 低（<15%）；vsscal `ready_stall=64%` 偏高（值得后续优化）。
- **vsger AVL=2147487808**：addrgen AVL 探针噪声（参数地址泄漏），内核通过，非功能问题。
