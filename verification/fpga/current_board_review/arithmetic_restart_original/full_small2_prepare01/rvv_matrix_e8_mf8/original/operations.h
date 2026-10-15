extern unsigned long op_0(const word *, const word *, word *, unsigned long, unsigned long, const uint8_t *, unsigned long);
extern unsigned long op_1(const word *, const word *, word *, unsigned long, unsigned long, const uint8_t *, unsigned long);
extern unsigned long op_2(const word *, const word *, word *, unsigned long, unsigned long, const uint8_t *, unsigned long);
extern unsigned long op_3(const word *, const word *, word *, unsigned long, unsigned long, const uint8_t *, unsigned long);
extern unsigned long op_4(const word *, const word *, word *, unsigned long, unsigned long, const uint8_t *, unsigned long);
extern unsigned long op_5(const word *, const word *, word *, unsigned long, unsigned long, const uint8_t *, unsigned long);
extern unsigned long op_6(const word *, const word *, word *, unsigned long, unsigned long, const uint8_t *, unsigned long);
extern unsigned long op_7(const word *, const word *, word *, unsigned long, unsigned long, const uint8_t *, unsigned long);
extern unsigned long op_8(const word *, const word *, word *, unsigned long, unsigned long, const uint8_t *, unsigned long);
extern unsigned long op_9(const word *, const word *, word *, unsigned long, unsigned long, const uint8_t *, unsigned long);
extern unsigned long op_10(const word *, const word *, word *, unsigned long, unsigned long, const uint8_t *, unsigned long);
extern unsigned long op_11(const word *, const word *, word *, unsigned long, unsigned long, const uint8_t *, unsigned long);
extern unsigned long op_12(const word *, const word *, word *, unsigned long, unsigned long, const uint8_t *, unsigned long);
extern unsigned long op_13(const word *, const word *, word *, unsigned long, unsigned long, const uint8_t *, unsigned long);
extern unsigned long op_14(const word *, const word *, word *, unsigned long, unsigned long, const uint8_t *, unsigned long);
extern unsigned long op_15(const word *, const word *, word *, unsigned long, unsigned long, const uint8_t *, unsigned long);
extern unsigned long op_16(const word *, const word *, word *, unsigned long, unsigned long, const uint8_t *, unsigned long);
extern unsigned long op_17(const word *, const word *, word *, unsigned long, unsigned long, const uint8_t *, unsigned long);
extern unsigned long op_18(const word *, const word *, word *, unsigned long, unsigned long, const uint8_t *, unsigned long);
extern unsigned long op_19(const word *, const word *, word *, unsigned long, unsigned long, const uint8_t *, unsigned long);
extern unsigned long op_20(const word *, const word *, word *, unsigned long, unsigned long, const uint8_t *, unsigned long);
extern unsigned long op_21(const word *, const word *, word *, unsigned long, unsigned long, const uint8_t *, unsigned long);
extern unsigned long op_22(const word *, const word *, word *, unsigned long, unsigned long, const uint8_t *, unsigned long);
extern unsigned long op_23(const word *, const word *, word *, unsigned long, unsigned long, const uint8_t *, unsigned long);
extern unsigned long op_24(const word *, const word *, word *, unsigned long, unsigned long, const uint8_t *, unsigned long);
#define OPERATION_COUNT 25
#define OPERATION_FUNCTIONS op_0, op_1, op_2, op_3, op_4, op_5, op_6, op_7, op_8, op_9, op_10, op_11, op_12, op_13, op_14, op_15, op_16, op_17, op_18, op_19, op_20, op_21, op_22, op_23, op_24
#define OPERATION_NAMES "vadd.vv", "vsub.vv", "vand.vv", "vor.vv", "vxor.vv", "vsll.vv", "vsrl.vv", "vsra.vv", "vminu.vv", "vmaxu.vv", "vmin.vv", "vmax.vv", "vmul.vv", "vdivu.vv", "vremu.vv", "vdiv.vv", "vrem.vv", "vadd.vx", "vadd.vi", "vslideup.vi", "vslidedown.vi", "vrgather.vv", "vredsum.vs", "vcompress.vm", "load"
#define OPERATION_KINDS 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1, 1, 1, 2, 3, 0
