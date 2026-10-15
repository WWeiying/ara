.text
.global wholemove_layout_run
wholemove_layout_run:
    csrwi vstart,0
    vl2re8.v v24,(a1)
    vl2re8.v v16,(a2)
    addi t2,a0,128
    bnez a3,1f
    # Reverse EEW: both source registers were loaded at e64, current SEW is8.
    vsetvli t0,zero,e64,m1,tu,mu
    vle64.v v8,(a0)
    vle64.v v9,(t2)
    vsetivli t0,7,e8,m1,tu,mu
    j 2f
1:  # Mixed metadata: v8 loaded at e8, v9 at e64, current SEW is16.
    vsetvli t0,zero,e8,m1,tu,mu
    vle8.v v8,(a0)
    vsetvli t0,zero,e64,m1,tu,mu
    vle64.v v9,(t2)
    vsetivli t0,7,e16,m2,tu,mu
2:  csrw vstart,a4
    vmv2r.v v24,v8
    # Adjacent dependent read, with no CSR drain or vset between the two.
    vmv2r.v v16,v24
    csrr a0,vstart
    csrwi vstart,0
    vs2r.v v24,(a1)
    vs2r.v v16,(a2)
    fence
    csrr zero,vl
    ret
