# Source-Only Symbolic Counts

No numerical a/b values or expected outputs were generated. A short arithmetic
enumeration of source loop bounds produced the counts below; this is not a Host
oracle/fixture execution, compile, Spike run or reference acceptance.

For every original seed/op/VL/mode/start/control tuple, form
`A={i:0<=i<512, start<=i<VL, selected(mode,i)}`. Output byte i+1 may differ
from sentinel only for i in A. Both guards remain0x5b in the expected result.
Mode2 selects73 indices2,9,...,506, not74.

For each64-byte block position k=0..8, intersect A with byte range
`[64*k,min(64*(k+1),514))` through the mapping i->i+1.
An empty intersection has a known sentinel block, with distinct full/tail
padding. A nonempty symbolic block key is:

`(seed, op, effective_rounding, block_position, ordered_active_indices)`

effective_rounding is control&3 for vsmul/op0 and0 for op1/2/3. This follows
the actual extra_value() FRACTIONAL_SUITE mappings0/4/3/6: only op0 calls
rounded(); initial sticky state never changes the arithmetic output value.
Saturation expectations therefore remain separately indexed per original call.
Equal symbolic keys necessarily give equal expected bytes because a/b are fixed
within each seed and no intervening helper writes source arrays. Different keys
may also give equal bytes, but no such numerical coincidence is assumed here.

| Symbolic count | Value |
| --- | ---: |
| Original call visits |10752|
| Distinct symbolic row keys, including all-sentinel row |442|
| Distinct symbolic block keys, including padded sentinel variants |716|
| Calls with nonempty A |2976|
| Calls with empty A |7776|
| Sum of active element visits |303744|
| Total block visits |96768|
| Full sentinel block visits |75936|
| Tail sentinel block visits |10176|
| Nonempty full block visits |10080|
| Nonempty tail block visits |576|
| Non-sentinel expected word loads |10080*8+576=81216|
| Adjacent equal symbolic block visits within a call |65472|

The last row is an observation, not an additional cache assumption in the chosen
proposal. Only proven sentinel handling is needed for the reported cost subtotal.
The upper ROM bound is `716*64 + 442*9*2 + 10752*2 + 10752 = 86036` bytes.
The descriptor and saturation representations may be changed later only with
explicit full-source equality proof and actual code/cost accounting.

Useful implementation-independent arithmetic checks:

-3*4*7*4 mask epochs=336; per mode84 epochs.
- Original selected writes=84*(512+256+73)=70644.
- Inputs per8 indices:16 initial random writes +2+2+2+1 overrides=23;
  3*64*23=4416 ordered SB.
- Four starts include duplicates; never set-deduplicate calls. For each seed/op,
  28 VL/mode groups*4 starts*8 controls=896 calls, and3*4*896=10752.
- All data comparisons remain65 loads/call even for a known sentinel row.
  Dictionary deduplication concerns immutable expected data only.
