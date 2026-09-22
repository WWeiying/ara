# Linux 系统级验证入口

Linux 验证和 bare-metal RVV 差分是两条独立签核线。`check_boot.py` 不会把
“有 OpenSBI 输出”误判为完整 Linux 通过，它要求固定的启动 marker，并记录
kernel、DTB、initramfs 等输入的 SHA-256。

## QEMU/FPGA 日志签核

准备完整 console log 和 payload 后运行：

```bash
python3 verification/linux/check_boot.py \
  --log run/console.log \
  --artifact kernel=linux/Image \
  --artifact dtb=linux/ara_vcu118.dtb \
  --artifact initramfs=linux/initramfs.cpio \
  --output run/linux_boot_check.json
```

默认 marker 要求：

1. OpenSBI banner；
2. Linux kernel banner；
3. `Ara DSA VCU118 Linux init reached`；
4. `Linux console, DDR and RVV handoff are alive`。

通过启动 marker 后，还要执行独立的用户态 smoke：

- 普通 RVV arithmetic/load-store；
- QBS/AKV enabled contract；
- QBS/AKV disabled fallback；
- page fault、非法指令、线程/进程切换后的 vector CSR；
- 长时间循环和文件/内存压力。

`build_linux_bringup.sh` 负责生成 VCU118 的 OpenSBI、DTB、Linux Image 和
BusyBox initramfs。它是 payload 构建步骤，不是 Linux 验证结果；只有
`linux_boot_check.json` 和用户态 smoke 都 PASS，Linux 层才可以签核。
