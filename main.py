import sys

from PySide6.QtWidgets import QApplication

import config


def ensure_sprites():
    if not config.SPRITES_DIR.exists() or not any(config.SPRITES_DIR.iterdir()):
        from pet.assets.generate_placeholders import generate_all
        generate_all(config.SPRITES_DIR)


def main():
    ensure_sprites()

    from pet.overlay.pet_window import PetWindow

    app = QApplication(sys.argv)
    window = PetWindow()
    window.show()
    window.activateWindow()
    window.setFocus()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
