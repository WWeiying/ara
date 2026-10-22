# Masked Full17920 Reference: Actual PASS, Not DUT

唯一finite参考和唯一闭合audit均完成，无retry/重编/大raw重读或VCS。

- Spike actual wait0/7.435798840s，限120s；audit actual wait0/231.658382736s，限600s，均无timeout。数值退出先独立落盘，后做结果检查。
- 固定rs4000000;quit/raw768MiB/FW3M。实际firmware到HTIF为2780558，完整17920 calls/286720bits/35840guards/17920flags及vstarts通过。
- 原masked185静态helper对应326144动态helper+capacity3；734720fresh stores/143360 inputLD/17920 outputLWU/8960 mode-record LD均由完整实际raw核验。10752原始FMV.D.X payload（每seed336）保留，不做boxing修复。
- 完整raw2785000行、244036745B，EOF后4437行均为pure park；同一semantic pass计算SHA `e44d70f414592a5be3f303319b2212befed00b0125f68ebabd44b7f8332e0060`，stat前后相同，全部封存输入pins一致。
- 来源为原masked父`rvv_fp_compare_unboxed_e16_mf4` ELF82d90319.../原C03cc5031...，不是已接受unmasked父。新Spike ELF `09c4eaf6033b25922a57e1c7223616e6a849d30b6393a67fd64d91da097a7634`；新mode-sensitive模型正确保留all-off sticky-only、inactive oldbits和原tail允许集。

权威一次执行收据：`run01/COMPLETE.json` SHA `db289ce138bb0e12c0be6bc499fc2099a94ce9a0ab0ffc87d06cebc1a315a867`。
实际raw检查结果：`run01/audit01/result.json` SHA `102f54a83573c2043ef6ad20cec4aa628de179ca6b5c91d3db79453600f58c37`。
退出收据：`run01/spike.wait.json` SHA `f07e9fca229911a94d854f87f31086ade61e7ec4616814808836bbba9b21135d`；`run01/audit.wait.json` SHA `c27faf6c6941418b178479df473b5c539c3a3a26832dcf4cfed655d9b97ba498`。

Hilbert入口review SHA `f7754d412dc1f83be9f318aaaf514011238cdeae63cfb5a0bab119dad995a1b5`，ENTRY SHA `d4171d33604d9a17c452b42d1322cb392ed55924c6ebb98ab667bf120bafd0e9`。独立终态只读取小收据/结果及继承raw hash，不重复扫描。此处是完整source参考接受证据，不是实际Ara backend owner/CVX/uop测量、M9 DUT通过或原Linux失败闭环；无VCS授权。
