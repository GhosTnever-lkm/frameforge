from pathlib import Path

from .safety import CONFIG_NAME, SafetyError, validate_config_path


def find_skyrim_config(selected_folder: Path) -> Path:
    """Resolve a user-selected Skyrim Special Edition user-settings folder."""
    folder = Path(selected_folder).expanduser()
    if folder.name.casefold() != "skyrim special edition":
        raise SafetyError("Choose the Skyrim Special Edition folder under Documents\\My Games.")
    return validate_config_path(folder / CONFIG_NAME)
