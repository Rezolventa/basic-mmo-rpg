from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"

for root in (PROJECT_ROOT, SRC_ROOT):
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))


def run() -> None:
    """
    Запускает изолированный редактор карты из вспомогательного скрипта.
    """
    from tools.map_editor.app import main

    main()


if __name__ == "__main__":
    run()
