"""Write Wave G local integration demo JSON + MOCK receipts.

EXTERNAL_API_KEY_REQUIRED=NO. Fixture actor only. No C retune.
Does not contact live Gitea or CT102.
"""

from __future__ import annotations

import sys
from pathlib import Path

ACP_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ACP_ROOT / "src"))
sys.path.insert(0, str(ACP_ROOT / "tests"))

from test_transaction_integration_demos import main  # noqa: E402

if __name__ == "__main__":
    main()
