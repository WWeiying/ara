# Preparation Attempt 01

Stopped before any Spike execution or DUT launch. All three host prefixes and
five negative oracle controls plus the allowed-tail control passed. All three
selected original parent ELF rebuilds were byte-identical to archived ELFs.

The preprocessor-equality assertion was too strong: the later oracle contains
`if(0 && op>=4)bi=14` when UNBOXED_COMPARISONS=0, which preprocessing retains.
The successor checks optimized, stripped original parent ELF bytes instead.
This is a preparation assertion failure, not an architectural mismatch. Inputs,
oracle, and assembly were not changed to address it. Retain this directory.
