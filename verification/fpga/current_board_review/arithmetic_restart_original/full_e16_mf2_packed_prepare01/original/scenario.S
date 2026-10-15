.text
.global capacity
capacity:
li t0, -1
vsetvli a0, t0, e16, mf2, tu, mu
ret
.global op_0
op_0:
vsetvli t0, a4, e16, mf2, tu, mu
vle16.v v8, (a0)
vle16.v v16, (a1)
vle16.v v24, (a2)
vlm.v v0, (a5)
vsetvli t0, a3, e16, mf2, tu, mu
li t3, 7
csrw vstart, a6
vadd.vv v24, v8, v16, v0.t
csrr a0, vstart
vsetvli t0, a4, e16, mf2, tu, mu
vse16.v v24, (a2)
ret
.global op_1
op_1:
vsetvli t0, a4, e16, mf2, tu, mu
vle16.v v8, (a0)
vle16.v v16, (a1)
vle16.v v24, (a2)
vlm.v v0, (a5)
vsetvli t0, a3, e16, mf2, tu, mu
li t3, 7
csrw vstart, a6
vsub.vv v24, v8, v16, v0.t
csrr a0, vstart
vsetvli t0, a4, e16, mf2, tu, mu
vse16.v v24, (a2)
ret
.global op_2
op_2:
vsetvli t0, a4, e16, mf2, tu, mu
vle16.v v8, (a0)
vle16.v v16, (a1)
vle16.v v24, (a2)
vlm.v v0, (a5)
vsetvli t0, a3, e16, mf2, tu, mu
li t3, 7
csrw vstart, a6
vand.vv v24, v8, v16, v0.t
csrr a0, vstart
vsetvli t0, a4, e16, mf2, tu, mu
vse16.v v24, (a2)
ret
.global op_3
op_3:
vsetvli t0, a4, e16, mf2, tu, mu
vle16.v v8, (a0)
vle16.v v16, (a1)
vle16.v v24, (a2)
vlm.v v0, (a5)
vsetvli t0, a3, e16, mf2, tu, mu
li t3, 7
csrw vstart, a6
vor.vv v24, v8, v16, v0.t
csrr a0, vstart
vsetvli t0, a4, e16, mf2, tu, mu
vse16.v v24, (a2)
ret
.global op_4
op_4:
vsetvli t0, a4, e16, mf2, tu, mu
vle16.v v8, (a0)
vle16.v v16, (a1)
vle16.v v24, (a2)
vlm.v v0, (a5)
vsetvli t0, a3, e16, mf2, tu, mu
li t3, 7
csrw vstart, a6
vxor.vv v24, v8, v16, v0.t
csrr a0, vstart
vsetvli t0, a4, e16, mf2, tu, mu
vse16.v v24, (a2)
ret
.global op_5
op_5:
vsetvli t0, a4, e16, mf2, tu, mu
vle16.v v8, (a0)
vle16.v v16, (a1)
vle16.v v24, (a2)
vlm.v v0, (a5)
vsetvli t0, a3, e16, mf2, tu, mu
li t3, 7
csrw vstart, a6
vsll.vv v24, v8, v16, v0.t
csrr a0, vstart
vsetvli t0, a4, e16, mf2, tu, mu
vse16.v v24, (a2)
ret
.global op_6
op_6:
vsetvli t0, a4, e16, mf2, tu, mu
vle16.v v8, (a0)
vle16.v v16, (a1)
vle16.v v24, (a2)
vlm.v v0, (a5)
vsetvli t0, a3, e16, mf2, tu, mu
li t3, 7
csrw vstart, a6
vsrl.vv v24, v8, v16, v0.t
csrr a0, vstart
vsetvli t0, a4, e16, mf2, tu, mu
vse16.v v24, (a2)
ret
.global op_7
op_7:
vsetvli t0, a4, e16, mf2, tu, mu
vle16.v v8, (a0)
vle16.v v16, (a1)
vle16.v v24, (a2)
vlm.v v0, (a5)
vsetvli t0, a3, e16, mf2, tu, mu
li t3, 7
csrw vstart, a6
vsra.vv v24, v8, v16, v0.t
csrr a0, vstart
vsetvli t0, a4, e16, mf2, tu, mu
vse16.v v24, (a2)
ret
.global op_8
op_8:
vsetvli t0, a4, e16, mf2, tu, mu
vle16.v v8, (a0)
vle16.v v16, (a1)
vle16.v v24, (a2)
vlm.v v0, (a5)
vsetvli t0, a3, e16, mf2, tu, mu
li t3, 7
csrw vstart, a6
vminu.vv v24, v8, v16, v0.t
csrr a0, vstart
vsetvli t0, a4, e16, mf2, tu, mu
vse16.v v24, (a2)
ret
.global op_9
op_9:
vsetvli t0, a4, e16, mf2, tu, mu
vle16.v v8, (a0)
vle16.v v16, (a1)
vle16.v v24, (a2)
vlm.v v0, (a5)
vsetvli t0, a3, e16, mf2, tu, mu
li t3, 7
csrw vstart, a6
vmaxu.vv v24, v8, v16, v0.t
csrr a0, vstart
vsetvli t0, a4, e16, mf2, tu, mu
vse16.v v24, (a2)
ret
.global op_10
op_10:
vsetvli t0, a4, e16, mf2, tu, mu
vle16.v v8, (a0)
vle16.v v16, (a1)
vle16.v v24, (a2)
vlm.v v0, (a5)
vsetvli t0, a3, e16, mf2, tu, mu
li t3, 7
csrw vstart, a6
vmin.vv v24, v8, v16, v0.t
csrr a0, vstart
vsetvli t0, a4, e16, mf2, tu, mu
vse16.v v24, (a2)
ret
.global op_11
op_11:
vsetvli t0, a4, e16, mf2, tu, mu
vle16.v v8, (a0)
vle16.v v16, (a1)
vle16.v v24, (a2)
vlm.v v0, (a5)
vsetvli t0, a3, e16, mf2, tu, mu
li t3, 7
csrw vstart, a6
vmax.vv v24, v8, v16, v0.t
csrr a0, vstart
vsetvli t0, a4, e16, mf2, tu, mu
vse16.v v24, (a2)
ret
.global op_12
op_12:
vsetvli t0, a4, e16, mf2, tu, mu
vle16.v v8, (a0)
vle16.v v16, (a1)
vle16.v v24, (a2)
vlm.v v0, (a5)
vsetvli t0, a3, e16, mf2, tu, mu
li t3, 7
csrw vstart, a6
vmul.vv v24, v8, v16, v0.t
csrr a0, vstart
vsetvli t0, a4, e16, mf2, tu, mu
vse16.v v24, (a2)
ret
.global op_13
op_13:
vsetvli t0, a4, e16, mf2, tu, mu
vle16.v v8, (a0)
vle16.v v16, (a1)
vle16.v v24, (a2)
vlm.v v0, (a5)
vsetvli t0, a3, e16, mf2, tu, mu
li t3, 7
csrw vstart, a6
vdivu.vv v24, v8, v16, v0.t
csrr a0, vstart
vsetvli t0, a4, e16, mf2, tu, mu
vse16.v v24, (a2)
ret
.global op_14
op_14:
vsetvli t0, a4, e16, mf2, tu, mu
vle16.v v8, (a0)
vle16.v v16, (a1)
vle16.v v24, (a2)
vlm.v v0, (a5)
vsetvli t0, a3, e16, mf2, tu, mu
li t3, 7
csrw vstart, a6
vremu.vv v24, v8, v16, v0.t
csrr a0, vstart
vsetvli t0, a4, e16, mf2, tu, mu
vse16.v v24, (a2)
ret
.global op_15
op_15:
vsetvli t0, a4, e16, mf2, tu, mu
vle16.v v8, (a0)
vle16.v v16, (a1)
vle16.v v24, (a2)
vlm.v v0, (a5)
vsetvli t0, a3, e16, mf2, tu, mu
li t3, 7
csrw vstart, a6
vdiv.vv v24, v8, v16, v0.t
csrr a0, vstart
vsetvli t0, a4, e16, mf2, tu, mu
vse16.v v24, (a2)
ret
.global op_16
op_16:
vsetvli t0, a4, e16, mf2, tu, mu
vle16.v v8, (a0)
vle16.v v16, (a1)
vle16.v v24, (a2)
vlm.v v0, (a5)
vsetvli t0, a3, e16, mf2, tu, mu
li t3, 7
csrw vstart, a6
vrem.vv v24, v8, v16, v0.t
csrr a0, vstart
vsetvli t0, a4, e16, mf2, tu, mu
vse16.v v24, (a2)
ret
.global op_17
op_17:
vsetvli t0, a4, e16, mf2, tu, mu
vle16.v v8, (a0)
vle16.v v16, (a1)
vle16.v v24, (a2)
vlm.v v0, (a5)
vsetvli t0, a3, e16, mf2, tu, mu
li t3, 7
csrw vstart, a6
vadd.vx v24, v8, t3, v0.t
csrr a0, vstart
vsetvli t0, a4, e16, mf2, tu, mu
vse16.v v24, (a2)
ret
.global op_18
op_18:
vsetvli t0, a4, e16, mf2, tu, mu
vle16.v v8, (a0)
vle16.v v16, (a1)
vle16.v v24, (a2)
vlm.v v0, (a5)
vsetvli t0, a3, e16, mf2, tu, mu
li t3, 7
csrw vstart, a6
vadd.vi v24, v8, 3, v0.t
csrr a0, vstart
vsetvli t0, a4, e16, mf2, tu, mu
vse16.v v24, (a2)
ret
.global op_19
op_19:
vsetvli t0, a4, e16, mf2, tu, mu
vle16.v v8, (a0)
vle16.v v16, (a1)
vle16.v v24, (a2)
vlm.v v0, (a5)
vsetvli t0, a3, e16, mf2, tu, mu
li t3, 7
csrw vstart, a6
vslideup.vi v24, v8, 2, v0.t
csrr a0, vstart
vsetvli t0, a4, e16, mf2, tu, mu
vse16.v v24, (a2)
ret
.global op_20
op_20:
vsetvli t0, a4, e16, mf2, tu, mu
vle16.v v8, (a0)
vle16.v v16, (a1)
vle16.v v24, (a2)
vlm.v v0, (a5)
vsetvli t0, a3, e16, mf2, tu, mu
li t3, 7
csrw vstart, a6
vslidedown.vi v24, v8, 2, v0.t
csrr a0, vstart
vsetvli t0, a4, e16, mf2, tu, mu
vse16.v v24, (a2)
ret
.global op_21
op_21:
vsetvli t0, a4, e16, mf2, tu, mu
vle16.v v8, (a0)
vle16.v v16, (a1)
vle16.v v24, (a2)
vlm.v v0, (a5)
vsetvli t0, a3, e16, mf2, tu, mu
li t3, 7
csrw vstart, a6
vrgather.vv v24, v8, v16, v0.t
csrr a0, vstart
vsetvli t0, a4, e16, mf2, tu, mu
vse16.v v24, (a2)
ret
.global op_22
op_22:
vsetvli t0, a4, e16, mf2, tu, mu
vle16.v v8, (a0)
vle16.v v16, (a1)
vle16.v v24, (a2)
vlm.v v0, (a5)
vsetvli t0, a3, e16, mf2, tu, mu
li t3, 7
csrw vstart, a6
vredsum.vs v24, v8, v16, v0.t
csrr a0, vstart
vsetvli t0, a4, e16, mf2, tu, mu
vse16.v v24, (a2)
ret
.global op_23
op_23:
vsetvli t0, a4, e16, mf2, tu, mu
vle16.v v8, (a0)
vle16.v v16, (a1)
vle16.v v24, (a2)
vlm.v v0, (a5)
vsetvli t0, a3, e16, mf2, tu, mu
li t3, 7
csrw vstart, a6
vcompress.vm v24, v8, v0
csrr a0, vstart
vsetvli t0, a4, e16, mf2, tu, mu
vse16.v v24, (a2)
ret
.global op_24
op_24:
vsetvli t0, a4, e16, mf2, tu, mu
vle16.v v8, (a0)
vle16.v v16, (a1)
vle16.v v24, (a2)
vlm.v v0, (a5)
vsetvli t0, a3, e16, mf2, tu, mu
li t3, 7
csrw vstart, a6
vle16.v v24, (a0), v0.t
csrr a0, vstart
vsetvli t0, a4, e16, mf2, tu, mu
vse16.v v24, (a2)
ret
