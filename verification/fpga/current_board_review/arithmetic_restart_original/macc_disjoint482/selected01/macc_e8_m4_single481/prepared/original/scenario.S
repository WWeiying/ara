.text
.global capacity
capacity:
li t0, -1
vsetvli a0, t0, e8, m4, tu, mu
ret
.global op_0
op_0:
vsetvli t0, a4, e8, m4, tu, mu
vle8.v v8, (a0)
vle8.v v16, (a1)
vle8.v v24, (a2)
vlm.v v0, (a5)
vsetvli t0, a3, e8, m4, tu, mu
lb t3, 0(a1)
csrw vstart, a6
vmacc.vv v24, v8, v16, v0.t
csrr a0, vstart
vsetvli t0, a4, e8, m4, tu, mu
vse8.v v24, (a2)
ret
.global op_1
op_1:
vsetvli t0, a4, e8, m4, tu, mu
vle8.v v8, (a0)
vle8.v v16, (a1)
vle8.v v24, (a2)
vlm.v v0, (a5)
vsetvli t0, a3, e8, m4, tu, mu
lb t3, 0(a1)
csrw vstart, a6
vnmsac.vv v24, v8, v16, v0.t
csrr a0, vstart
vsetvli t0, a4, e8, m4, tu, mu
vse8.v v24, (a2)
ret
.global op_2
op_2:
vsetvli t0, a4, e8, m4, tu, mu
vle8.v v8, (a0)
vle8.v v16, (a1)
vle8.v v24, (a2)
vlm.v v0, (a5)
vsetvli t0, a3, e8, m4, tu, mu
lb t3, 0(a1)
csrw vstart, a6
vmadd.vv v24, v8, v16, v0.t
csrr a0, vstart
vsetvli t0, a4, e8, m4, tu, mu
vse8.v v24, (a2)
ret
.global op_3
op_3:
vsetvli t0, a4, e8, m4, tu, mu
vle8.v v8, (a0)
vle8.v v16, (a1)
vle8.v v24, (a2)
vlm.v v0, (a5)
vsetvli t0, a3, e8, m4, tu, mu
lb t3, 0(a1)
csrw vstart, a6
vnmsub.vv v24, v8, v16, v0.t
csrr a0, vstart
vsetvli t0, a4, e8, m4, tu, mu
vse8.v v24, (a2)
ret
.global op_4
op_4:
vsetvli t0, a4, e8, m4, tu, mu
vle8.v v8, (a0)
vle8.v v16, (a1)
vle8.v v24, (a2)
vlm.v v0, (a5)
vsetvli t0, a3, e8, m4, tu, mu
lb t3, 0(a1)
csrw vstart, a6
vmacc.vx v24, t3, v8, v0.t
csrr a0, vstart
vsetvli t0, a4, e8, m4, tu, mu
vse8.v v24, (a2)
ret
.global op_5
op_5:
vsetvli t0, a4, e8, m4, tu, mu
vle8.v v8, (a0)
vle8.v v16, (a1)
vle8.v v24, (a2)
vlm.v v0, (a5)
vsetvli t0, a3, e8, m4, tu, mu
lb t3, 0(a1)
csrw vstart, a6
vnmsac.vx v24, t3, v8, v0.t
csrr a0, vstart
vsetvli t0, a4, e8, m4, tu, mu
vse8.v v24, (a2)
ret
.global op_6
op_6:
vsetvli t0, a4, e8, m4, tu, mu
vle8.v v8, (a0)
vle8.v v16, (a1)
vle8.v v24, (a2)
vlm.v v0, (a5)
vsetvli t0, a3, e8, m4, tu, mu
lb t3, 0(a1)
csrw vstart, a6
vmadd.vx v24, t3, v8, v0.t
csrr a0, vstart
vsetvli t0, a4, e8, m4, tu, mu
vse8.v v24, (a2)
ret
.global op_7
op_7:
vsetvli t0, a4, e8, m4, tu, mu
vle8.v v8, (a0)
vle8.v v16, (a1)
vle8.v v24, (a2)
vlm.v v0, (a5)
vsetvli t0, a3, e8, m4, tu, mu
lb t3, 0(a1)
csrw vstart, a6
vnmsub.vx v24, t3, v8, v0.t
csrr a0, vstart
vsetvli t0, a4, e8, m4, tu, mu
vse8.v v24, (a2)
ret
