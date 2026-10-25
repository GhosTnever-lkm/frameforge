from __future__ import annotations

from pathlib import Path


def csgo_launch_arguments(windowed_overlay: bool) -> list[str]:
    arguments = ["-applaunch", "4465480"]
    if windowed_overlay:
        arguments.extend(("-windowed", "-noborder"))
    return arguments


def build_managed_autoexec(existing: str, enabled: bool) -> str:
    marker_start = "// >>> FrameForge managed CS:GO Legacy menu >>>"
    marker_end = "// <<< FrameForge managed CS:GO Legacy menu <<<"
    lines = [marker_start, "exec frameforge_menu", "ff_menu", "toggleconsole", marker_end] if enabled else []
    block = "\n".join(lines)
    if marker_start in existing and marker_end in existing:
        before, remainder = existing.split(marker_start, 1)
        _, after = remainder.split(marker_end, 1)
        result = before.rstrip()
        if block:
            result += "\n\n" + block
        result += after
        return result.lstrip("\n")
    result = existing.rstrip()
    if block:
        result += ("\n\n" if result else "") + block + "\n"
    return result


def build_csgo_profile_files(
    folder: Path,
    *,
    fps_limit: int,
    dynamic_lights: bool,
    bloom: bool,
    blending: bool,
    red_crosshair: bool,
    startup_menu: bool,
    dark_sky: bool,
    hide_sky: bool,
    existing_autoexec: str = "",
) -> dict[Path, str]:
    """Build FrameForge-owned CS:GO Legacy CFG contents without touching disk."""
    folder = Path(folder)
    fps_cfg = folder / "frameforge_fps.cfg"
    fps_lines = [
        "// FrameForge Counter-Strike: Global Offensive Legacy performance profile",
        f"fps_max {fps_limit}",
        "// Change one setting at a time and compare the same scene with FrameForge benchmark.",
    ]
    if dynamic_lights:
        fps_lines.append("r_dynamic 0")
    if bloom:
        fps_lines.append("mat_disable_bloom 1")
    if blending:
        fps_lines.append("mat_disable_fancy_blending 1")

    files = {fps_cfg: "\n".join(fps_lines) + "\n"}
    has_sky_profile = dark_sky or hide_sky
    help_lines = [
        "echo ================= FRAMEFORGE =================",
        "echo ff_perf - apply FPS profile",
    ]
    if red_crosshair:
        help_lines.append("echo ff_accessibility - red high-contrast crosshair")
    if has_sky_profile:
        help_lines.append("echo ff_night - apply selected local-practice sky profile")
    help_lines.extend((
        "echo ff_skyoff - hide skybox (local practice)",
        "echo ff_skyrestore - restore skybox",
        "echo ================================================",
    ))
    menu_lines = [
        "// FrameForge in-game console menu for CS:GO Legacy",
        f'alias ff_menu "{"; ".join(help_lines)}"',
        'alias ff_perf "exec frameforge_fps"',
    ]
    if red_crosshair:
        menu_lines.append('alias ff_accessibility "exec frameforge_accessibility"')
    if has_sky_profile:
        menu_lines.append('alias ff_night "exec frameforge_practice_sky"')
    menu_lines.extend((
        'alias ff_skyoff "sv_cheats 1; r_drawskybox 0"',
        'alias ff_skyrestore "r_drawskybox 1"',
        "exec frameforge_fps",
        "echo FrameForge console menu ready. Type ff_menu for commands.",
    ))
    files[folder / "frameforge_menu.cfg"] = "\n".join(menu_lines) + "\n"

    if red_crosshair:
        files[folder / "frameforge_accessibility.cfg"] = (
            "// FrameForge high-contrast red crosshair preset for CS:GO Legacy\n"
            "// Highlights the crosshair, not enemy player models.\n"
            "cl_crosshaircolor 5\n"
            "cl_crosshaircolor_r 255\n"
            "cl_crosshaircolor_g 64\n"
            "cl_crosshaircolor_b 64\n"
            "cl_crosshairusealpha 1\n"
            "cl_crosshairalpha 255\n"
        )
    if has_sky_profile:
        sky_lines = [
            "// FrameForge CS:GO Legacy local-practice sky options",
            "// sv_cheats and server-side sky commands require a local/practice server that permits them.",
            "sv_cheats 1",
        ]
        if dark_sky:
            sky_lines.append("sv_skyname sky_csgo_night02")
        if hide_sky:
            sky_lines.append("r_drawskybox 0")
        sky_lines.extend((
            "// Restore skybox with: r_drawskybox 1",
            "// Restore default sky by changing map or restarting the local server.",
        ))
        files[folder / "frameforge_practice_sky.cfg"] = "\n".join(sky_lines) + "\n"

    autoexec = folder / "autoexec.cfg"
    autoexec_text = build_managed_autoexec(existing_autoexec, startup_menu)
    if autoexec_text:
        files[autoexec] = autoexec_text
    return files
