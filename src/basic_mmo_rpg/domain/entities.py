from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from basic_mmo_rpg.domain.geometry import Rect, Vec2


class EntityKind(StrEnum):
    """
    Перечисляет широкие визуально-смысловые категории объектов мира.
    """

    NPC = "npc"
    GATE = "gate"
    CREATURE = "creature"
    OBJECT = "object"
    LOOTABLE = "lootable"


class LootClaimPolicy(StrEnum):
    """
    Перечисляет условия доступности loot-компонента.
    """

    ALWAYS = "always"
    AFTER_DESTROYED = "after_destroyed"
    RUNTIME_ONCE = "runtime_once"


@dataclass(frozen=True, slots=True)
class IdentityComponent:
    """
    Хранит публичную идентичность объекта мира.
    """

    kind: EntityKind
    name: str
    destroyed_name: str | None = None
    visual: str = ""


@dataclass(frozen=True, slots=True)
class BodyComponent:
    """
    Хранит физическое тело объекта мира.
    """

    position: Vec2
    width: int
    height: int
    solid: bool = True
    visible: bool = True


@dataclass(frozen=True, slots=True)
class InteractionComponent:
    """
    Хранит параметры обычного взаимодействия с объектом мира.
    """

    radius: float = 64.0
    dialogue: str = ""


@dataclass(frozen=True, slots=True)
class LootableComponent:
    """
    Хранит server-authoritative правило одноразового loot-а.
    """

    reward_item_id: str
    reward_quantity: int
    success_text: str
    claim_policy: LootClaimPolicy = LootClaimPolicy.ALWAYS


@dataclass(frozen=True, slots=True)
class CombatComponent:
    """
    Хранит runtime-состояние боевой части объекта мира.
    """

    hit_points: int
    max_hit_points: int
    attackable: bool = True
    destroyed: bool = False
    min_damage: int = 0
    max_damage: int = 0
    hit_chance: float = 0.85
    attack_distance: float = 64.0
    swing_cooldown_seconds: float = 1.5


@dataclass(frozen=True, slots=True)
class RespawnComponent:
    """
    Хранит runtime-таймер восстановления разрушенного объекта.
    """

    seconds: float
    remaining: float = 0.0


@dataclass(frozen=True, slots=True)
class GateComponent:
    """
    Хранит runtime-состояние калитки.
    """

    is_open: bool = False


@dataclass(frozen=True, slots=True)
class ShearableComponent:
    """
    Хранит runtime-состояние шерсти creature-сущности.
    """

    has_wool: bool = True


@dataclass(frozen=True, slots=True, init=False)
class WorldEntity:
    """
    Хранит объект мира как набор независимых компонентов.
    """

    entity_id: str
    identity: IdentityComponent
    body: BodyComponent
    interaction: InteractionComponent | None
    lootable: LootableComponent | None
    combat: CombatComponent | None
    respawn: RespawnComponent | None
    gate: GateComponent | None
    shearable: ShearableComponent | None

    def __init__(
        self,
        entity_id: str,
        identity: IdentityComponent | None = None,
        body: BodyComponent | None = None,
        interaction: InteractionComponent | None = None,
        lootable: LootableComponent | None = None,
        combat: CombatComponent | None = None,
        respawn: RespawnComponent | None = None,
        gate: GateComponent | None = None,
        shearable: ShearableComponent | None = None,
        *,
        kind: EntityKind | None = None,
        name: str | None = None,
        position: Vec2 | None = None,
        width: int | None = None,
        height: int | None = None,
        interaction_radius: float = 64.0,
        dialogue: str = "",
        solid: bool = True,
        visible: bool = True,
        is_open: bool | None = None,
        hit_points: int | None = None,
        max_hit_points: int | None = None,
        has_wool: bool | None = None,
    ) -> None:
        """
        Создает объект из компонентов или из старой плоской формы для совместимости.
        """
        if identity is None or body is None:
            if kind is None or name is None or position is None or width is None or height is None:
                msg = "world entity requires components or legacy fields"
                raise ValueError(msg)
            identity = IdentityComponent(kind=kind, name=name)
            body = BodyComponent(
                position=position,
                width=width,
                height=height,
                solid=solid,
                visible=visible,
            )
            interaction = InteractionComponent(
                radius=interaction_radius,
                dialogue=dialogue,
            )
            if is_open is not None:
                gate = GateComponent(is_open=is_open)
            if hit_points is not None or max_hit_points is not None:
                maximum = max_hit_points if max_hit_points is not None else hit_points
                current = hit_points if hit_points is not None else maximum
                if current is None or maximum is None:
                    msg = "combat hit points must be complete"
                    raise ValueError(msg)
                combat = CombatComponent(
                    hit_points=current,
                    max_hit_points=maximum,
                    attackable=False,
                )
            if has_wool is not None:
                shearable = ShearableComponent(has_wool=has_wool)

        object.__setattr__(self, "entity_id", entity_id)
        object.__setattr__(self, "identity", identity)
        object.__setattr__(self, "body", body)
        object.__setattr__(self, "interaction", interaction)
        object.__setattr__(self, "lootable", lootable)
        object.__setattr__(self, "combat", combat)
        object.__setattr__(self, "respawn", respawn)
        object.__setattr__(self, "gate", gate)
        object.__setattr__(self, "shearable", shearable)

    @property
    def kind(self) -> EntityKind:
        """
        Возвращает широкую категорию объекта.
        """
        return self.identity.kind

    @property
    def visual(self) -> str:
        """
        Возвращает визуальный вариант отрисовки объекта.
        """
        return self.identity.visual

    @property
    def base_name(self) -> str:
        """
        Возвращает обычное имя объекта без учета разрушения.
        """
        return self.identity.name

    @property
    def name(self) -> str:
        """
        Возвращает актуальное публичное имя объекта.
        """
        if self.is_destroyed and self.identity.destroyed_name is not None:
            return self.identity.destroyed_name
        return self.identity.name

    @property
    def position(self) -> Vec2:
        """
        Возвращает мировую позицию тела объекта.
        """
        return self.body.position

    @property
    def width(self) -> int:
        """
        Возвращает ширину тела объекта.
        """
        return self.body.width

    @property
    def height(self) -> int:
        """
        Возвращает высоту тела объекта.
        """
        return self.body.height

    @property
    def solid(self) -> bool:
        """
        Возвращает, блокирует ли объект движение.
        """
        return self.body.solid

    @property
    def visible(self) -> bool:
        """
        Возвращает, нужно ли показывать объект клиентам как видимый объект мира.
        """
        return self.body.visible

    @property
    def interaction_radius(self) -> float:
        """
        Возвращает радиус обычного взаимодействия.
        """
        if self.interaction is None:
            return 0.0
        return self.interaction.radius

    @property
    def dialogue(self) -> str:
        """
        Возвращает реплику обычного взаимодействия.
        """
        if self.interaction is None:
            return ""
        return self.interaction.dialogue

    @property
    def is_open(self) -> bool | None:
        """
        Возвращает состояние калитки.
        """
        if self.gate is None:
            return None
        return self.gate.is_open

    @property
    def hit_points(self) -> int | None:
        """
        Возвращает текущие HP объекта.
        """
        if self.combat is None:
            return None
        return self.combat.hit_points

    @property
    def max_hit_points(self) -> int | None:
        """
        Возвращает максимальные HP объекта.
        """
        if self.combat is None:
            return None
        return self.combat.max_hit_points

    @property
    def has_wool(self) -> bool | None:
        """
        Возвращает состояние шерсти creature-сущности.
        """
        if self.shearable is None:
            return None
        return self.shearable.has_wool

    @property
    def is_destroyed(self) -> bool:
        """
        Возвращает, разрушен ли объект.
        """
        return self.combat is not None and self.combat.destroyed

    @property
    def is_attackable(self) -> bool:
        """
        Возвращает, можно ли выбрать объект целью атаки.
        """
        if self.combat is None:
            return False
        return self.combat.attackable and not self.combat.destroyed and self.combat.hit_points > 0

    @property
    def rect(self) -> Rect:
        """
        Возвращает прямоугольник объекта в мировых координатах.
        """
        return Rect(self.position.x, self.position.y, self.width, self.height)

    @property
    def center(self) -> Vec2:
        """
        Возвращает центр объекта в мировых координатах.
        """
        return self.rect.center
