import os
import sys
from pathlib import Path

# Launch the TrustLordge app from dependency-exit-capsule
entry = Path(__file__).parent / "dependency-exit-capsule" / "app.py"
with open(entry, "r", encoding="utf-8") as f:
    code = f.read()

# Execute in current global context
exec(compile(code, str(entry), 'exec'), globals())
