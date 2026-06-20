from __future__ import annotations

from dataclasses import dataclass

FISHING_ROD_ITEM_ID = "fishing_rod"
FISH_ITEM_ID = "fish"
GOLD_ITEM_ID = "gold"
LUMBER_AXE_ITEM_ID = "lumber_axe"
LOG_ITEM_ID = "log"
PICKAXE_ITEM_ID = "pickaxe"
STONE_ITEM_ID = "stone"


class InventoryError(ValueError):
    """
    Сообщает о доменной ошибке операции с инвентарем.
    """


class InventoryLimitError(InventoryError):
    """
    Сообщает, что операция превысила лимит стака предмета.
    """


@dataclass(frozen=True, slots=True)
class ItemDefinition:
    """
    Описывает неизменяемые свойства типа предмета.
    """

    item_id: str
    display_name: str
    stack_limit: int = 1


@dataclass(frozen=True, slots=True)
class ItemStack:
    """
    Хранит один стак предметов в инвентаре персонажа.
    """

    item_id: str
    display_name: str
    quantity: int


ITEM_DEFINITIONS: dict[str, ItemDefinition] = {
    FISHING_ROD_ITEM_ID: ItemDefinition(
        item_id=FISHING_ROD_ITEM_ID,
        display_name="Удочка",
        stack_limit=1,
    ),
    FISH_ITEM_ID: ItemDefinition(
        item_id=FISH_ITEM_ID,
        display_name="Рыба",
        stack_limit=999,
    ),
    GOLD_ITEM_ID: ItemDefinition(
        item_id=GOLD_ITEM_ID,
        display_name="Gold",
        stack_limit=999,
    ),
    LUMBER_AXE_ITEM_ID: ItemDefinition(
        item_id=LUMBER_AXE_ITEM_ID,
        display_name="Топор для рубки",
        stack_limit=1,
    ),
    LOG_ITEM_ID: ItemDefinition(
        item_id=LOG_ITEM_ID,
        display_name="Бревно",
        stack_limit=999,
    ),
    PICKAXE_ITEM_ID: ItemDefinition(
        item_id=PICKAXE_ITEM_ID,
        display_name="Кирка",
        stack_limit=1,
    ),
    STONE_ITEM_ID: ItemDefinition(
        item_id=STONE_ITEM_ID,
        display_name="Камень",
        stack_limit=999,
    ),
}


def item_definition_for(item_id: str) -> ItemDefinition:
    """
    Возвращает описание предмета по id или создает fallback-описание.
    """
    return ITEM_DEFINITIONS.get(
        item_id,
        ItemDefinition(item_id=item_id, display_name=item_id, stack_limit=999),
    )


def item_stack_for(item_id: str, quantity: int) -> ItemStack:
    """
    Создает стак предметов с display name из локального каталога предметов.
    """
    definition = item_definition_for(item_id)
    return ItemStack(
        item_id=definition.item_id,
        display_name=definition.display_name,
        quantity=quantity,
    )
