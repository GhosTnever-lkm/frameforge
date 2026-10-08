from pathlib import Path

from .safety import CONFIG_NAMES, SafetyError, validate_config_path


def find_skyrim_config(selected_folder: Path, config_name: str = "SkyrimPrefs.ini") -> Path:
    """Resolve a user-selected Skyrim Special Edition user-settings folder."""
    folder = Path(selected_folder).expanduser()
    if folder.name.casefold() != "skyrim special edition":
        raise SafetyError("Choose the Skyrim Special Edition folder under Documents\\My Games.")
    if config_name.casefold() not in CONFIG_NAMES:
        raise SafetyError("This Skyrim INI file is not supported.")
    return validate_config_path(folder / config_name)
