"""Exact-anchor partition of the frozen matched caller, not its arithmetic."""
import hashlib

from audit import require

SOURCE_SHA = '9b9e5b83b8ef23f3f894a3dc7bdbd783531293f6bf6553bb160d23081b49bf91'
GROUPS = ((0, 1, 2, 3, 4, 6), (5,))
STAGES = ((0, 1, 3), (2,))
K = (2048, 2048, 2048, 2048, 2048, 6144, 2048)
PROFILE = (1, 2, 1, 1, 1, 2, 2)
ORDER = (0, 1, 1, 0)


def contract(group):
    require(type(group) is int and group in (0, 1), 'Explicit partition 0 or 1 required')
    parts = GROUPS[group]
    return dict(group=group, parts=list(parts), stages=list(STAGES[group]),
                native_commands=4*len(parts), outputs_checked=256*len(parts),
                q4_calls=sum(PROFILE[p] == 1 for p in parts),
                q6_calls=64*sum(PROFILE[p] == 2 for p in parts),
                pairs_per_backend=sum(64*K[p] for p in parts))


def scope(group):
    c = contract(group)
    return (f'DECODE_PARTITION_SCOPE group={group} m=1 n=64 parts={len(c["parts"])} '
            f'stages={len(c["stages"])} order=ABBA full_k=1 full_n=0 full_ggml=0 completion=csr_and_fence')


def transform(source, group):
    c = contract(group)
    require(hashlib.sha256(source.encode()).hexdigest() == SOURCE_SHA, 'Frozen matched driver SHA differs')
    text = source
    edits = []

    def edit(before, after, count=1):
        nonlocal text
        require(text.count(before) == count, 'Partition anchor count differs: '+before[:70])
        text = text.replace(before, after)
        edits.append(dict(before=before, after=after, occurrences=count))

    anchor = 'static constexpr unsigned Generation[Parts]={1,1,1,2,2,0,3};'
    selected = ','.join('true' if p in c['parts'] else 'false' for p in range(7))
    stages = ','.join('true' if s in c['stages'] else 'false' for s in range(4))
    edit(anchor, anchor+f'\nstatic constexpr bool Selected[Parts]={{{selected}}};'
         +f'\nstatic constexpr bool UsedStage[Stages]={{{stages}}};')
    old_scope = ('MATCHED_DECODE_SCOPE m=1 n=64 parts=7 stages=4 order=ABBA full_k=1 '
                 'full_n=0 full_ggml=0 completion=csr_and_fence')
    edit(old_scope, scope(group).replace('DECODE_PARTITION_', 'MATCHED_DECODE_'))
    anchor = '        const bool native=order[trial];'
    edit(anchor, anchor+f'\n        printf("MATCHED_DECODE_BEGIN group={group} trial=%u backend=%u\\n",trial,unsigned(native));')
    edit('        for (unsigned p=0;p<Parts;++p) {',
         '        for (unsigned p=0;p<Parts;++p) {\n            if (!Selected[p]) continue;', 2)
    edit('        for (unsigned s=0;s<Stages;++s) {',
         '        for (unsigned s=0;s<Stages;++s) {\n            if (!UsedStage[s]) continue;')
    # All excluded storage remains allocated with its original layout. Check
    # it only outside the timed interval, including unused output rows.
    edit('        unsigned errors=completed!=Parts;',
         f'''        unsigned errors=completed!={len(c['parts'])};
        unsigned untouched_errors=0;
        for (unsigned p=0;p<Parts;++p) if (!Selected[p]) {{
            const auto *bytes=reinterpret_cast<const unsigned char *>(output[p]);
            for (size_t i=0;i<sizeof(output[p]);++i) untouched_errors+=bytes[i]!=0xa5;
        }}
        for (unsigned s=0;s<Stages;++s) if (!UsedStage[s])
            for (size_t i=0;i<sizeof(activation[s]);++i) untouched_errors+=activation[s][i]!=0xa5;
        errors+=untouched_errors;''')
    edit('native_commands!=(native?14u:0u)', f'native_commands!=(native?{2*len(c["parts"])}u:0u)')
    edit('rvv_q4_calls!=(native?0u:4u)', f'rvv_q4_calls!=(native?0u:{c["q4_calls"]}u)')
    edit('rvv_q6_calls!=(native?0u:192u)', f'rvv_q6_calls!=(native?0u:{c["q6_calls"]}u)')
    edit('q6_calls=%u outputs=448 errors=%u',
         f'q6_calls=%u outputs={64*len(c["parts"])} untouched_errors=%u errors=%u')
    edit('execution_sum,(unsigned long)region,native_commands,rvv_q4_calls,rvv_q6_calls,errors);',
         'execution_sum,(unsigned long)region,native_commands,rvv_q4_calls,rvv_q6_calls,untouched_errors,errors);')
    edit('MATCHED_DECODE_RESULT trials=4 native_commands=28 outputs_checked=1792 errors=%u',
         f'MATCHED_DECODE_RESULT group={group} trials=4 native_commands={c["native_commands"]} '
         f'outputs_checked={c["outputs_checked"]} errors=%u')
    restored = text
    for e in reversed(edits):
        require(restored.count(e['after']) == e['occurrences'], 'Nonreversible partition edit')
        restored = restored.replace(e['after'], e['before'])
    require(restored == source, 'Partition must restore frozen source byte-for-byte')
    text = text.replace('MATCHED_DECODE_', 'DECODE_PARTITION_')
    return text, dict(source_sha256=SOURCE_SHA, group=c, edits=edits,
                      source_reversibility_checked=True, arithmetic_and_timer_helpers_unchanged=True,
                      generated_sha256=hashlib.sha256(text.encode()).hexdigest())
