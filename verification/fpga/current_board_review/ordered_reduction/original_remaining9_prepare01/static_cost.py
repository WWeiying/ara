"""Pre-reference compiled finite-path admission; not a measured run."""
from common import *
from check_reference import specification


def analyze(dest):
    s=specification(dest);c=s['config'];sy=s['symbols'];ins=s['instructions']
    main=[r for r in ins if sy[c['identity']+'_main']<=r[0]<sy['capacity']]
    # Match the compiled 64-byte mask body and its single mode-dependent skip.
    start,=[i for i,r in enumerate(main) if r[2].split('#')[0].strip()=='li\ta4,36']
    mask=main[start:start+8]
    require([r[2].split()[0] for r in mask]==['li','beq','ld','lbu','add','sb','addi','bne'], 'mask CFG shape')
    require(mask[-1][2].split(',')[-1].split()[0]==format(mask[0][0],'x'), 'mask backedge')
    require(any(r[2].split('#')[0].strip()=='li\ta3,64' for r in main[start-5:start]), 'mask64 bound')
    copies=[i for i,r in enumerate(main) if '<memcpy>' in r[2]]
    require(len(copies)==1, 'input scenarios have no memcpy calls in this ELF')
    i=copies[0]
    require(main[i-4][2].strip()=='li\ta2,32', 'seed32-byte memcpy')
    seed=main[i-4:i+8]
    require(len(seed)==12 and seed[-1][2].split()[0]=='bne', 'seed12 callsite body')
    memcpy=[r for r in ins if sy['memcpy']<=r[0]<sy['replay_text']]
    require([r[2].split()[0] for r in memcpy]==['li','bne','ret','add','lbu','add','addi','sb','j'], 'memcpy7n+3')
    # 872 per capacity unit deliberately includes the unused worst-case 24B
    # copies for scenarios4/5 as well as a 64-instruction simple-scenario path.
    terms={'mask_body_exact':1612800,'fixture_selectors_outer_controls':336000,
           'seed_body_allowance':122880,'input_initialization_allowance':872*c['cap'],
           'startup_bss':8000,'selected_helper_output_oracle':6000,
           'formatting_return':10000,'other_setup_slack':20000}
    upper=sum(terms.values())
    require(upper<3000000,'static budget insufficient: no reference')
    return {'status':'STATIC_ADMITTED_NOT_REFERENCE_PASS','shape':c['shape'],
        'terms':terms,'upper_instructions':upper,'remaining_to_3M':3000000-upper,
        'input_reason':'8*cap elements, two complex paths <=244 each (includes hypothetical memcpy24), six simple <=64; actual compiled input has zero calls',
        'seed_exact':512*(7*32+3+12),'mask_instructions':mask,'seed_instructions':seed,
        'memcpy_instructions':memcpy,'helper21_bytes_match':True,'full_source_unchanged':True,
        'elf_sha256':sha(dest/'spike/program.elf'),'disassembly_sha256':sha(dest/'spike/program.dis'),
        'sourceproof_sha256':sha(dest/'sourceproof.json'),
        'raw_wall_are_independent_hard_limits':True,'limits':LIMITS}


if __name__=='__main__':
    rows=[]
    for shape in SHAPES:
        dest=HERE/shape;row=analyze(dest);save(dest/'static_cost.json',row);rows.append(row)
        print(shape,row['upper_instructions'],flush=True)
    save(HERE/'static_admission.json',{'status':'STATIC_ADMITTED_ALL9_NOT_REFERENCE_PASS','cases':rows})
