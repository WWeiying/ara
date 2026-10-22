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
li t3, 7
csrw vstart, a6
csrr t4, vxrm
csrr t5, vxsat
andi t2, a7, 3
csrw vxrm, t2
srli t2, a7, 2
csrw vxsat, t2
vsmul.vv v24, v8, v16, v0.t
csrr a0, vstart
csrr t1, vxsat
slli t1, t1, 32
or a0, a0, t1
csrw vxrm, t4
csrw vxsat, t5
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
li t3, 7
csrw vstart, a6
csrr t4, vxrm
csrr t5, vxsat
andi t2, a7, 3
csrw vxrm, t2
srli t2, a7, 2
csrw vxsat, t2
vsadd.vv v24, v8, v16, v0.t
csrr a0, vstart
csrr t1, vxsat
slli t1, t1, 32
or a0, a0, t1
csrw vxrm, t4
csrw vxsat, t5
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
li t3, 7
csrw vstart, a6
csrr t4, vxrm
csrr t5, vxsat
andi t2, a7, 3
csrw vxrm, t2
srli t2, a7, 2
csrw vxsat, t2
vsaddu.vv v24, v8, v16, v0.t
csrr a0, vstart
csrr t1, vxsat
slli t1, t1, 32
or a0, a0, t1
csrw vxrm, t4
csrw vxsat, t5
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
li t3, 7
csrw vstart, a6
csrr t4, vxrm
csrr t5, vxsat
andi t2, a7, 3
csrw vxrm, t2
srli t2, a7, 2
csrw vxsat, t2
vssub.vv v24, v8, v16, v0.t
csrr a0, vstart
csrr t1, vxsat
slli t1, t1, 32
or a0, a0, t1
csrw vxrm, t4
csrw vxsat, t5
vsetvli t0, a4, e8, m4, tu, mu
vse8.v v24, (a2)
ret
