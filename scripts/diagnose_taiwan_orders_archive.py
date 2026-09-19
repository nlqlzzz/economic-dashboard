from __future__ import annotations

import json
from pathlib import Path
import sys


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from data_loader import diagnose_taiwan_semiconductor_orders_archive


def main() -> int:
    try:
        frame = diagnose_taiwan_semiconductor_orders_archive()
    except Exception as error:
        print(
            json.dumps(
                {
                    "status": "environment_blocked",
                    "error_type": type(error).__name__,
                    "detail": str(error),
                },
                ensure_ascii=False,
            )
        )
        return 1

    if frame.empty or frame.attrs.get("failed_months"):
        print(
            json.dumps(
                {
                    "status": "incomplete",
                    "loaded_rows": len(frame),
                    "failed_months": frame.attrs.get("failed_months", []),
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 1

    fields = [
        "reference_period",
        "release_date",
        "series_id",
        "value",
        "yoy",
        "source_url",
        "data_vintage",
        "yoy_is_derived",
    ]
    payload = {
        "status": "ok",
        "rows": json.loads(frame[fields].to_json(orient="records", date_format="iso")),
        "attachment_sha256": frame.attrs.get("attachment_hashes", {}),
        "coverage": {
            "expected_months": frame.attrs.get("expected_months"),
            "discovered_months": frame.attrs.get("discovered_months"),
            "missing_discovery_months": frame.attrs.get("missing_discovery_months", []),
        },
        "failed_months": frame.attrs.get("failed_months", []),
        "minimum_request_interval_seconds": frame.attrs.get(
            "minimum_request_interval_seconds"
        ),
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
