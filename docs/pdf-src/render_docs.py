r"""Render the three customer/operator PDFs at the repo root from their HTML sources.

    backend\.venv\Scripts\python.exe docs\pdf-src\render_docs.py

WeasyPrint needs the GTK3 runtime staged at deploy\_thirdparty\gtk3 (see
docs/DEPLOYMENT.md, third-party binaries). The PDFs are gitignored (/*.pdf);
these HTML files are the source of truth.
"""
import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
os.add_dll_directory(str(ROOT / "deploy" / "_thirdparty" / "gtk3" / "bin"))
from weasyprint import HTML  # noqa: E402

JOBS = [
    ("pricing_sheet.html", "Campus_Pricing.pdf"),
    ("user_guide.html", "Campus_Overview_and_User_Guide.pdf"),
    ("technical_guide.html", "Campus_Technical_and_Troubleshooting_Guide.pdf"),
]

only = set(sys.argv[1:])
for src, dst in JOBS:
    if only and src not in only and dst not in only:
        continue
    out = ROOT / dst
    HTML(str(HERE / src)).write_pdf(str(out))
    print(f"wrote {out}  ({out.stat().st_size:,} bytes)")
