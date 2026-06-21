import sys

import config


def ensure_sprites():
    if not config.SPRITES_DIR.exists() or not any(config.SPRITES_DIR.iterdir()):
        from pet.assets.generate_placeholders import generate_all
        generate_all(config.SPRITES_DIR)


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
