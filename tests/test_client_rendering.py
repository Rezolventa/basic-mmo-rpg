from __future__ import annotations

from pathlib import Path

import pytest

from basic_mmo_rpg.storage.map_loader import load_tile_map


def test_renderer_loads_tile_sprites_independent_of_cwd(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """
    Проверяет, что клиентский renderer ищет PNG-спрайты от корня проекта, а не от cwd.
    """
    monkeypatch.setenv("SDL_VIDEODRIVER", "dummy")

    import pygame

    from basic_mmo_rpg.client.rendering import Renderer

    tile_map = load_tile_map(Path("assets/maps/starter_map.json"))
    pygame.init()
    try:
        pygame.display.set_mode((1, 1))
        monkeypatch.chdir(tmp_path)

        renderer = Renderer(tile_map)

        assert len(renderer.tile_sprites["T"]) == 8
        assert len(renderer.tile_sprites["R"]) == 3
        assert len(renderer.tile_sprites["C"]) == 1
    finally:
        pygame.quit()
