"""Small immutable first-failure receipt shared by this preparation only."""
import traceback
def context(error,stage,current=None,case=None):
    return dict(case=case,checker_stage=stage,error_type=type(error).__name__,message=str(error),
                current=current,traceback=traceback.format_exc(limit=6))
