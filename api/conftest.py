import sys
from pathlib import Path

# we need to make sure "main" can be imported when pytest runs from repo root
sys.path.insert(0, str(Path(__file__).parent))
