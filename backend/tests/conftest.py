from pathlib import Path
import sys

# Permit both `pytest` from the repository root and `python -m pytest` in backend.
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
