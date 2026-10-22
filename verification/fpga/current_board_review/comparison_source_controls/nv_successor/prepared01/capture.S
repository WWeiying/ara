.text
.global capture_vectors
capture_vectors:
    vse16.v v8,(a0)
    vse16.v v16,(a1)
    vsm.v v0,(a2)
    ret
