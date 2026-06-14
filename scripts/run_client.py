from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"

if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))


def run() -> None:
    """
    Запускает клиентское приложение из вспомогательного скрипта.
    """
    from basic_mmo_rpg.client.app import main

    main()


if __name__ == "__main__":
    run()
