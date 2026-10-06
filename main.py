import sys

import config

# Every state pet/behavior/state_machine.py can put the pet in; each needs
# its own sprite subfolder. Checked individually (not just "is SPRITES_DIR
# non-empty") so that adding a new state later — like "sleep"/"dragged"
# were added after "idle"/"walk_*"/"sit"/"react" already existed on disk —
# doesn't silently leave it with no sprite to draw (state_machine still
# switches to it, paintEvent just draws nothing: the pet "disappears").
_REQUIRED_SPRITE_STATES = ["idle", "walk_left", "walk_right", "sit", "react", "sleep", "dragged"]


# Records which generator produced the sprites on disk, so switching source
# (3D renders <-> 2D sprite sheet <-> procedural placeholders) regenerates
# them even when every state folder already exists.
_SPRITE_SOURCE_MARKER = ".source"


def _sprite_source() -> str:
    """Marker string for the sprite source to use: config.SPRITE_SOURCE, or
    in "auto" the best one available (3D renders > 2D sheet > placeholders).
    Size and layout version are part of it: frames are produced at
    DISPLAY_SIZE, so changing either must regenerate them."""
    from pet.assets import load_cat3d, slice_sheet

    wanted = config.SPRITE_SOURCE
    if wanted in ("auto", "3d") and load_cat3d.available():
        return f"3d:{config.DISPLAY_SIZE}:v{load_cat3d.LAYOUT_VERSION}"
    if wanted in ("auto", "3d", "sheet") and slice_sheet.SHEET_PATH.exists():
        return f"sheet:{config.DISPLAY_SIZE}:v{slice_sheet.LAYOUT_VERSION}"
    return "placeholders"


def ensure_sprites():
    source = _sprite_source()
    marker = config.SPRITES_DIR / _SPRITE_SOURCE_MARKER
    missing = [
        state for state in _REQUIRED_SPRITE_STATES
        if not (config.SPRITES_DIR / state).exists() or not any((config.SPRITES_DIR / state).glob("*.png"))
    ]
    current = marker.read_text(encoding="utf-8").strip() if marker.exists() else None
    if not missing and current == source:
        return
    if source.startswith("3d"):
        from pet.assets import load_cat3d
        load_cat3d.generate_all(config.SPRITES_DIR)
    elif source.startswith("sheet"):
        from pet.assets import slice_sheet
        slice_sheet.generate_all(config.SPRITES_DIR)
    else:
        from pet.assets.generate_placeholders import generate_all
        generate_all(config.SPRITES_DIR)
    marker.write_text(source, encoding="utf-8")


def run_app():
    from PySide6.QtWidgets import QApplication

    from pet.overlay.pet_window import PetWindow

    ensure_sprites()
    app = QApplication(sys.argv)
    window = PetWindow()
    window.show()
    window.activateWindow()
    window.setFocus()
    sys.exit(app.exec())


def main():
    # Installer hook: setup.iss runs the frozen exe with these flags right
    # after copying files, so the multi-hundred-MB model downloads happen
    # during setup (with visible console output) instead of silently on
    # first launch. Reuses the exact same frozen Python/torch/etc as the
    # real app instead of needing a second interpreter inside the
    # installer — see installer/download_models.py and installer/setup.iss.
    if "--download-models" in sys.argv:
        from installer.download_models import main as download_models_main

        lang_arg = [a for a in sys.argv if a.startswith("--lang=")]
        lang = lang_arg[0].split("=", 1)[1] if lang_arg else config.DEFAULT_LANGUAGE
        download_models_main(lang)
        return

    if "--check-ollama" in sys.argv:
        import shutil

        sys.exit(0 if shutil.which("ollama") else 1)

    run_app()


if __name__ == "__main__":
    main()
