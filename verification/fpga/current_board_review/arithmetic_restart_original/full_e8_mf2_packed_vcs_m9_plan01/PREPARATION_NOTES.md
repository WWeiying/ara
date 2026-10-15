# Static Specification Selection

Initial read-only `python3 -B -c ... specification()` exited1 (chunk9ff6f0):
`uart_store,=... ValueError: too many values to unpack`.
No Host or DUT had started. Actual replay_write has two SB instructions:
normal UART `80001104:00f70023` (basea4/sourcea5) and syscall-error diagnostic
`80001126:00e68023` (basea3/sourcea4). The new specification now selects and
asserts the actual normal site. No ELF/compiler/runtime/checker predecessor
was changed. Error output remains subject to the original console/exit veto.
