"""Load the frozen experiment modules without changing their recorded sources."""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'experiments'))
