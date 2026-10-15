Host bridge stopped with actual process exit1 before completing the first CSV:
source_owners.py used the newer fixture's cfg['mask'] key, absent in the original
two-single spec_values schema. Original mask expectation is already defined by
the sealed observer.expected(...); successor uses those exact16 expected bytes.
No DUT or new reference was started. This directory is retained, not accepted.
