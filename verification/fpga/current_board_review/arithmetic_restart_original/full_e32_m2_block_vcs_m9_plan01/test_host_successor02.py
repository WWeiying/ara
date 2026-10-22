"""Only hoist immutable snapshot PC lookup; execute every original Host test."""
from pathlib import Path
HERE=Path(__file__).resolve().parent
source=(HERE/'test_host.py').read_text()
old="""                for key,address in (('cache_read',c.lifecycle.CACHE_LOAD_PC),('cache_store',c.lifecycle.CACHE_STORE_PC),
                    ('fp_read',c.lifecycle.FP_LOAD_PC[0]),('mask_read',c.lifecycle.mask_schedule(0)[16][4])):"""
new="""                for key,address in snapshot_sites:"""
start="        for row in observer.rows(HostRows()):"
sites="""        snapshot_sites=(('cache_read',c.lifecycle.CACHE_LOAD_PC),('cache_store',c.lifecycle.CACHE_STORE_PC),
            ('fp_read',c.lifecycle.FP_LOAD_PC[0]),('mask_read',c.lifecycle.mask_schedule(0)[16][4]))
"""
assert source.count(old)==source.count(start)==source.count("c.HERE/'host01.json'")==1
source=source.replace(old,new).replace(start,sites+start).replace("c.HERE/'host01.json'","c.HERE/'host02.json'")
exec(compile(source,str(HERE/'test_host.py'),'exec'),globals())
