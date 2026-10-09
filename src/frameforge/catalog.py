"""Game support catalog: Skyrim has reversible settings; other games have manual guides."""

GAMES = [
    {
        "name": "The Elder Scrolls V: Skyrim Special Edition",
        "mode": "config",
        "description": "Adjust grass fade distance in SkyrimPrefs.ini or density in Skyrim.ini. The game may regenerate settings; mod-manager profiles can use separate INIs and are not auto-detected.",
        "source": "https://stepmodifications.org/wiki/Guide:SkyrimPrefs_INI/Grass",
        "tweaks": ["Grass fade distance: 1000 / 3000 / 5000 / 7000", "Grass density: 40 / 60 / 80; 0 disables grass", "Changes are previewed and backed up; this does not promise a fixed FPS gain."],
    },
]

GUIDES = {
    "Counter-Strike 2": "Проверь тени, сглаживание и качество эффектов на одной и той же карте. Снижение эффектов может улучшить читаемость сцены, а снижение теней изменит видимость объектов. Меняй параметры только в меню игры.",
    "Dota 2": "Для снижения нагрузки сравни качество теней, эффекты и качество рендеринга во время одной и той же командной схватки. Более низкие эффекты могут упростить визуальную картину; проверь читаемость способностей.",
    "Apex Legends": "Проверь тени, объёмное освещение и качество эффектов в тренировочной зоне. Снижение качества может уменьшить визуальные помехи, но также убрать часть теней и деталей окружения.",
    "PUBG: Battlegrounds": "Проверь качество теней, эффектов, постобработки и растительности на одном маршруте. Дальность обзора может влиять на восприятие объектов, поэтому не снижай её без сравнения игрового процесса.",
    "Fortnite": "Сравни доступные режимы рендеринга и качество теней, эффектов и постобработки в одной локации. Режимы производительности меняют не только нагрузку, но и внешний вид; названия и параметры могут меняться с обновлениями.",
    "VALORANT": "Проверь качество материалов, деталей, теней и эффектов в тире. Начинай с теней и декоративных эффектов; оставь достаточную детализацию, чтобы визуальные сигналы оставались заметными.",
    "Minecraft: Java Edition": "Сравни дальность прорисовки и симуляции, частицы, сглаживание и шейдеры на одном сохранении. Шейдеры и высокая дальность могут сильно менять нагрузку; проверь также выделенную игре память, не завышая её без необходимости.",
    "Cyberpunk 2077": "Сравни трассировку лучей, объёмные эффекты, плотность толпы и качество отражений. Если игра ограничена GPU, проверь апскейлер, поддерживаемый твоей видеокартой; фиксируй разрешение и режим апскейла при сравнении.",
    "Grand Theft Auto V": "Сравни MSAA, траву, тени и расширенные параметры дальности в одной и той же сцене. Расширенные ползунки могут заметно повысить нагрузку; увеличивай их только после измерения.",
    "The Witcher 3": "Проверь трассировку лучей, плотность растительности, качество теней и HairWorks, если параметр доступен. Сравни одну и ту же сохранённую точку и зафиксируй выбранный режим рендеринга.",
    "Rust": "Сравни качество теней, дальность прорисовки, траву и эффекты на одном сервере и маршруте. Изменение дальности может влиять на то, как далеко видны объекты; убедись, что компромисс приемлем.",
    "Warframe": "Проверь объёмные эффекты, отражения, частицы и динамическое освещение во время одинаковой миссии. Снижение эффектов может повысить читаемость в бою, но изменит визуальную насыщенность.",
}

GUIDE_GAMES = list(GUIDES)

# Stable identifiers let a benchmark record which recommendations the user
# manually changed without storing free-form data or touching game files.
GUIDE_CHECKLISTS = {
    "Counter-Strike 2": (
        ("cs2.shadows", "Качество теней"),
        ("cs2.anti_aliasing", "Сглаживание"),
        ("cs2.effects", "Качество эффектов"),
    ),
    "Dota 2": (
        ("dota2.shadows", "Качество теней"),
        ("dota2.effects", "Эффекты"),
        ("dota2.rendering", "Качество рендеринга"),
    ),
    "Apex Legends": (
        ("apex.shadows", "Качество теней"),
        ("apex.volumetric_lighting", "Объёмное освещение"),
        ("apex.effects", "Качество эффектов"),
    ),
    "PUBG: Battlegrounds": (
        ("pubg.shadows", "Качество теней"),
        ("pubg.effects", "Эффекты и постобработка"),
        ("pubg.foliage", "Качество растительности"),
    ),
    "Fortnite": (
        ("fortnite.renderer", "Режим рендеринга"),
        ("fortnite.shadows", "Качество теней"),
        ("fortnite.effects", "Эффекты и постобработка"),
    ),
    "VALORANT": (
        ("valorant.materials", "Качество материалов"),
        ("valorant.shadows", "Качество теней"),
        ("valorant.effects", "Декоративные эффекты"),
    ),
    "Minecraft: Java Edition": (
        ("minecraft.render_distance", "Дальность прорисовки"),
        ("minecraft.simulation_distance", "Дальность симуляции"),
        ("minecraft.shaders_particles", "Шейдеры и частицы"),
    ),
    "Cyberpunk 2077": (
        ("cyberpunk.ray_tracing", "Трассировка лучей"),
        ("cyberpunk.volumetrics", "Объёмные эффекты"),
        ("cyberpunk.crowd_density", "Плотность толпы"),
    ),
    "Grand Theft Auto V": (
        ("gta5.msaa", "MSAA"),
        ("gta5.grass", "Качество травы"),
        ("gta5.extended_distance", "Расширенная дальность"),
    ),
    "The Witcher 3": (
        ("witcher3.ray_tracing", "Трассировка лучей"),
        ("witcher3.foliage", "Плотность растительности"),
        ("witcher3.hairworks", "HairWorks, если доступен"),
    ),
    "Rust": (
        ("rust.shadows", "Качество теней"),
        ("rust.view_distance", "Дальность прорисовки"),
        ("rust.grass_effects", "Трава и эффекты"),
    ),
    "Warframe": (
        ("warframe.volumetrics", "Объёмные эффекты"),
        ("warframe.reflections", "Отражения"),
        ("warframe.particles_lighting", "Частицы и динамическое освещение"),
    ),
}
GUIDE_CHECKLIST_LABELS = {
    item_id: label
    for checklist in GUIDE_CHECKLISTS.values()
    for item_id, label in checklist
}

GUIDE = (
    "Выбери игру, чтобы увидеть отдельный чек-лист. FrameForge не меняет файлы этих игр.\n\n"
    "Меню и названия параметров могут меняться с обновлениями. Сравнивай одну и ту же сцену, меняй по одному параметру и возвращай настройку, если качество изображения или читаемость ухудшились."
)
