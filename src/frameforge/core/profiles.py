from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class TuningProfile:
    name: str
    config_name: str
    section: str
    setting: str
    values: tuple[int, ...]
    default_value: int
    description: str


TUNING_PROFILES = (
    TuningProfile(
        name="Дальность прорисовки травы",
        config_name="SkyrimPrefs.ini",
        section="Grass",
        setting="fGrassStartFadeDistance",
        values=(1000, 3000, 5000, 7000),
        default_value=3000,
        description=(
            "Меньшее значение уменьшает расстояние, на котором видна трава; pop-in станет заметнее. "
            "Выбери 1000, 3000, 5000 или 7000. Прирост FPS зависит от сцены и компьютера."
        ),
    ),
    TuningProfile(
        name="Плотность / отключение травы",
        config_name="Skyrim.ini",
        section="Grass",
        setting="iMinGrassSize",
        values=(40, 60, 80, 0),
        default_value=40,
        description=(
            "Большее значение уменьшает плотность травы; 40, 60 и 80 дают постепенно более редкий покров. "
            "Значение 0 отключает траву полностью и заметно меняет внешний вид. Отрицательные значения не предлагаются."
        ),
    ),
)

PROFILES_BY_CONFIG = {profile.config_name.casefold(): profile for profile in TUNING_PROFILES}
