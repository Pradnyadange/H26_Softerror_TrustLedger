import sys
sys.path.insert(0, "D:/mlh/work/LinkWatch-fix")
from datetime import datetime
from unittest.mock import patch
from linkwatch.report import render_report

RESULTS = [
    {"name": "alpha", "url": "http://a.test", "up": True, "status": 200, "reason": "OK",
     "title": "Alpha", "elapsed_ms": 12, "last_modified": None,
     "checked_at": "2022-03-01T10:00:00+00:00"},
    {"name": "beta", "url": "http://b.test", "up": False, "status": None,
     "reason": "connection error", "title": "", "elapsed_ms": None,
     "last_modified": None, "checked_at": "2022-03-01T10:00:00+00:00"},
]

class FixedDatetime(datetime):
    @classmethod
    def now(cls):
        return cls(2026, 10, 15, 12, 0, 0)

with patch("linkwatch.report.datetime", FixedDatetime):
    out = sys.argv[1]
    render_report(RESULTS, output=out, title="LinkWatch Status")
    print("Rendered to", out)
