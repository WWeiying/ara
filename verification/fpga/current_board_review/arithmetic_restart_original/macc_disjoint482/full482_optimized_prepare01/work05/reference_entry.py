#!/usr/bin/env python3
"""Execute exactly one reference on the accepted unchanged work05 software."""
import sys
from pathlib import Path

sys.dont_write_bytecode=True
OUT=Path(__file__).resolve().parent
sys.path.insert(0,str(OUT.parent))
import reference

reference.p.HERE=OUT
syntax=reference.p.read(OUT/'final_syntax.json')
reference.p.require(syntax['status']=='PASS_FINAL_C_ALL_TOKENS_AND_EXACT_NEW_MESSAGE' and
    syntax['actual_execution']['actual_returncode']==0 and
    syntax['source_sha256']==reference.p.sha(OUT/'prepared03/case.c'),'Actual final syntax/source gate')
reference.p.save(OUT/'reference_entry_binding.json',dict(
    entry_path=str(Path(__file__)),entry_sha256=reference.p.sha(Path(__file__)),
    implementation_path=str(OUT.parent/'reference.py'),implementation_sha256=reference.p.sha(OUT.parent/'reference.py'),
    pre_reference_sha256=reference.p.sha(OUT/'PRE_REFERENCE.json'),
    syntax_receipt_sha256=reference.p.sha(OUT/'final_syntax.json'),
    source_model_or_flags_changed=False,reference_invocations_allowed=1,DUT_runs=0))
reference.main()
