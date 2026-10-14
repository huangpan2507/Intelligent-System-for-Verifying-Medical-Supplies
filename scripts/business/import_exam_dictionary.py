"""Import table 2 from the supplied PDF's pdftotext -layout export; retain source defects."""

import argparse
import hashlib
import json
import re
from collections import defaultdict
from pathlib import Path

TABLE_FIRST_PDF_PAGE, TABLE_LAST_PDF_PAGE = 4, 16


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("text", type=Path)
    parser.add_argument("pdf", type=Path)
    args = parser.parse_args()
    entries = defaultdict(list)
    for page_number, page in enumerate(args.text.read_text().split("\f"), 1):
        if not TABLE_FIRST_PDF_PAGE <= page_number <= TABLE_LAST_PDF_PAGE:
            continue
        for line in page.splitlines():
            match = re.match(r"^\s*(B[A-Z0-9]+)\s+(.+?)\s*$", line)
            if match:
                entries[match[1]].append({"name": match[2], "pdf_page": page_number, "printed_page": page_number - 2})
    records = []
    for code, citations in entries.items():
        status = "resolved"
        if not re.fullmatch(r"B[0-9A-HJ-NP-Z]{8}", code):
            status = "invalid_source_code"
        elif len({c["name"] for c in citations}) != 1:
            status = "ambiguous_source_code"
        records.append({"code": code, "status": status, "citations": citations})
    result = {
        "id": "wst364.8-2023-cv04.30.002",
        "version": "WS/T 364.8-2023; CV04.30.002",
        "source": "https://www.nhc.gov.cn/wjw/s9497/202311/fedbd15e15514084b419e08a3e989dcd.shtml",
        "source_sha256": hashlib.sha256(args.pdf.read_bytes()).hexdigest(),
        "records": records,
    }
    folder = Path(__file__).resolve().parents[2] / "src/backend/base/langflow/business/code_dictionaries"
    folder.mkdir(exist_ok=True)
    (folder / (result["id"] + ".json")).write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")


if __name__ == "__main__":
    main()
