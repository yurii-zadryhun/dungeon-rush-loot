from __future__ import annotations

from dataclasses import asdict, dataclass

from .domain import Action


@dataclass(frozen=True)
class RelativeRect:
    left: float
    top: float
    right: float
    bottom: float

    def pixels(self, size: tuple[int, int]) -> tuple[int, int, int, int]:
        width, height = size
        return (
            int(width * self.left),
            int(height * self.top),
            int(width * self.right),
            int(height * self.bottom),
        )

    def to_dict(self) -> dict[str, float]:
        return asdict(self)


@dataclass(frozen=True)
class LootUiProfile:
    crop: RelativeRect
    targets: dict[Action, RelativeRect]

    def target(self, action: Action) -> RelativeRect:
        try:
            return self.targets[action]
        except KeyError as exc:
            raise ValueError(f"No touch target for {action.value}") from exc


LOOT_UI = LootUiProfile(
    crop=RelativeRect(0.125, 0.40, 0.875, 0.82),
    targets={
        Action.SELL: RelativeRect(0.20, 0.842, 0.44, 0.888),
        Action.EQUIP: RelativeRect(0.56, 0.842, 0.80, 0.888),
        Action.CONFIRM_SELL: RelativeRect(0.20, 0.725, 0.44, 0.765),
    },
)


# Static profile for the current-equipment screenshots supplied for the Android
# importer (709x1536 layout). It clips tightly to the foreground item modal and
# excludes the aggregate build stats visible underneath it. Later this can be
# replaced by popup detection without changing import/parsing logic.
EQUIPMENT_IMPORT_CROP = RelativeRect(0.075, 0.425, 0.925, 0.705)
