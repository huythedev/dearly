"""Create a local virtual environment without requiring shell activation."""
import os
import subprocess
import sys
from pathlib import Path

if sys.version_info < (3,11):
    raise SystemExit('Install Python 3.11 or newer first.')
root=Path(__file__).resolve().parent
subprocess.run([sys.executable,'-m','venv',str(root/'.venv')],check=True)
python=root/'.venv'/('Scripts/python.exe' if os.name=='nt' else 'bin/python')
subprocess.run([str(python),'-m','pip','install','-r',str(root/'requirements.txt')],check=True)
print('\nReady. From the backend directory run:')
print(f'"{python}" run.py serve --host 0.0.0.0 --port 8000')
