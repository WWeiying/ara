"""Use the immutable bounded supervisor with only its owned output root changed."""
from pathlib import Path
import sys
sys.dont_write_bytecode=True
H=Path(__file__).resolve().parent
source=H.parent/'software01/execute_software.py'
# The predecessor supervisor uses __file__ only to select this independent root.
exec(compile(source.read_text(),str(source),'exec'),{'__file__':str(H/'execute_software.py'),'__name__':'__main__'})
