# Preparation History

The initial provenance preflight stopped before output-directory creation,
compilation, host execution or Spike. It expected the current
`repro/reduce_fp_moves.py` to have the archived single-generator hash:
`e05a820dd9dd163088038a20fc62bf453f32f91ea798b70adc6a30cda35b76ae`.
The current prefix-capable successor instead hashes to
`2407d5672efb54250eae027ba6ba1fde9193f7760482cff9daf0d31867a6f2d6`.

The three core sources (`fp_move_oracle.c`, `fp_moves.py`, `floating.py`) do
match their original hashes. SELECTION.md's three-source identity statement
does not establish the fourth, later reducer as byte-identical.

The adapter now records both reducer identities and explicitly labels the
current file as an equivalence checker, not the original generator. Archived
generator bytes have not been recovered. This does not replace any archived
scenario C/S/header or ELF: they remain manifest-pinned authoritative inputs.
The current reducer/generator must additionally reproduce every archived C/S
byte for byte before preparation is allowed. No oracle, tuple, membership,
expected result, or RTL was changed to resolve this preflight failure.
