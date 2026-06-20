import random
import re

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QGuiApplication, QIcon, QPainter
from PySide6.QtWidgets import QApplication, QMenu, QSystemTrayIcon, QWidget

import config
from pet.behavior.state_machine import PetStateMachine, State
from pet.overlay.action_bubble import ActionBubble
from pet.overlay.sprite_animator import SpriteAnimator
from pet.overlay.voice_chat import VoiceChatController
from pet.overlay.window_tracker import top_edge_platforms
from pet.recognition.recognizer import RecognitionService

_PLACEHOLDER_NAME_RE = re.compile(r"^Persona\d+$")


class PetWindow(QWidget):
    """Frameless, transparent, always-on-top sprite that wanders back and
    forth across the bottom of its home screen. Click to mute/unmute its
    always-listening voice chat.
    """

    def __init__(self):
        super().__init__()
        self.setWindowFlags(
            Qt.FramelessWindowHint
            | Qt.WindowStaysOnTopHint
            | Qt.Tool
        )
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_NoSystemBackground, True)
        self.setFixedSize(config.DISPLAY_SIZE, config.DISPLAY_SIZE)
        self.setFocusPolicy(Qt.StrongFocus)

        self.animator = SpriteAnimator()
        self.state_machine = PetStateMachine()
        self.frame_index = 0
        self.current_pixmap = None
        self._last_state = None
        self._muted = False

        self._screen_rect = self._home_screen_geometry()
        self._x = self._screen_rect.x() + self._screen_rect.width() // 2
        self._ground_y = (
            self._screen_rect.y()
            + self._screen_rect.height()
            - config.DISPLAY_SIZE
            - config.GROUND_MARGIN
        )
        self._y = self._ground_y
        self.move(self._x, self._y)

        self._platforms = []
        self._on_platform = False
        self._platform_bounds = None

        self._dragging = False
        self._drag_started = False
        self._drag_mouse_start = None
        self._drag_window_start = None
        self._falling = False
        self._fall_velocity = 0.0
        self._fall_target_y = 0.0
        self._fall_target_platform = None  # (x0, x1) if falling onto a window, else None

        self._update_pixmap()

        self.anim_timer = QTimer(self)
        self.anim_timer.timeout.connect(self._advance_frame)
        self.anim_timer.start(config.FRAME_INTERVAL_MS)

        self.move_timer = QTimer(self)
        self.move_timer.timeout.connect(self._tick)
        self.move_timer.start(config.MOVE_INTERVAL_MS)

        self.action_bubble = ActionBubble()

        self.voice_chat = VoiceChatController(self)
        self.voice_chat.action_ready.connect(self._on_action_text)
        self.voice_chat.mood_changed.connect(self._on_mood_changed)
        self.voice_chat.start()

        self.recognition = RecognitionService(self)
        self.recognition.identity_recognized.connect(self._on_identity_recognized)
        self.recognition.identity_learned.connect(self._on_identity_learned)
        self.recognition.appearance_changed.connect(self._on_appearance_changed)
        self.recognition.start()

        self.window_scan_timer = QTimer(self)
        self.window_scan_timer.timeout.connect(self._refresh_platforms)
        self.window_scan_timer.start(config.WINDOW_SCAN_INTERVAL_MS)
        self._refresh_platforms()

        self.climb_timer = QTimer(self)
        self.climb_timer.timeout.connect(self._maybe_climb)
        self.climb_timer.start(config.CLIMB_CHECK_INTERVAL_MS)

        self._setup_tray()

    def _setup_tray(self):
        icon_path = config.SPRITES_DIR / "idle" / "idle_0.png"
        icon = QIcon(str(icon_path)) if icon_path.exists() else self.windowIcon()

        menu = QMenu()
        self.mute_action = menu.addAction("Muta microfono")
        self.mute_action.setCheckable(True)
        self.mute_action.toggled.connect(self._set_muted)
        menu.addSeparator()
        menu.addAction("Esci", QApplication.quit)

        self.tray = QSystemTrayIcon(icon, self)
        self.tray.setToolTip(config.PET_NAME)
        self.tray.setContextMenu(menu)
        self.tray.show()

    @staticmethod
    def _home_screen_geometry():
        screens = QGuiApplication.screens()
        index = config.SECONDARY_SCREEN_INDEX if config.SECONDARY_SCREEN_INDEX < len(screens) else 0
        return screens[index].availableGeometry()

    def _advance_frame(self):
        self.frame_index += 1
        self._update_pixmap()
        self.update()

    def _tick(self):
        if self._dragging:
            return

        if self._falling:
            self._fall_velocity = min(self._fall_velocity + config.FALL_ACCEL, config.FALL_MAX_SPEED)
            self._y += self._fall_velocity
            if self._y >= self._fall_target_y:
                self._land(self._fall_target_y, self._fall_target_platform)
            self.move(self._x, self._y)
            return

        if self._on_platform and self._platform_bounds is not None:
            left_bound = self._platform_bounds[0]
            right_bound = max(left_bound, self._platform_bounds[1] - config.DISPLAY_SIZE)
        else:
            left_bound = self._screen_rect.x()
            right_bound = self._screen_rect.x() + self._screen_rect.width() - config.DISPLAY_SIZE

        at_left = self._x <= left_bound
        at_right = self._x >= right_bound

        state = self.state_machine.tick(at_left, at_right)

        if state == State.WALK_LEFT:
            self._x -= config.WALK_SPEED
        elif state == State.WALK_RIGHT:
            self._x += config.WALK_SPEED

        self._x = max(left_bound, min(self._x, right_bound))
        self.move(self._x, self._y)

        if state != self._last_state:
            self._last_state = state
            self.frame_index = 0
            self._update_pixmap()
            self.update()

    def _refresh_platforms(self):
        hwnd = int(self.winId())
        self._platforms = top_edge_platforms(
            self._screen_rect,
            exclude_hwnd=hwnd,
            min_width=config.MIN_PLATFORM_WIDTH,
            pet_height=config.DISPLAY_SIZE,
        )

    def _maybe_climb(self):
        if self._dragging or self._falling or self._on_platform or not self._platforms:
            return
        if random.random() > config.CLIMB_CHANCE:
            return

        x0, x1, top = random.choice(self._platforms)
        target_y = top - config.DISPLAY_SIZE
        if target_y < self._screen_rect.y():
            return  # safety net: never stand above the visible screen area

        self._on_platform = True
        self._platform_bounds = (x0, x1)
        self._x = max(x0, min(self._x, x1 - config.DISPLAY_SIZE))
        self._y = target_y
        self.move(self._x, self._y)
        self.state_machine.trigger_react(15)

        QTimer.singleShot(config.CLIMB_DURATION_MS, self._climb_down)

    def _climb_down(self):
        self._on_platform = False
        self._platform_bounds = None
        self._y = self._ground_y
        self.move(self._x, self._y)
        self.state_machine.trigger_react(15)

    def _compute_landing(self):
        """Where the pet should land if dropped right now: the top edge of
        a window directly below its current x position (if its footprint
        overlaps one enough), otherwise the ground. Returns
        (landing_y, platform_bounds_or_None)."""
        pet_left, pet_right = self._x, self._x + config.DISPLAY_SIZE
        min_overlap = config.DISPLAY_SIZE * 0.5

        best_top = None
        best_bounds = None
        for x0, x1, top in self._platforms:
            if top < self._y or top > self._ground_y:
                continue  # not below the pet's current position, or below the ground
            overlap = min(pet_right, x1) - max(pet_left, x0)
            if overlap < min_overlap:
                continue
            if best_top is None or top < best_top:
                best_top = top
                best_bounds = (x0, x1)

        if best_bounds is not None:
            return best_top - config.DISPLAY_SIZE, best_bounds
        return self._ground_y, None

    def _land(self, landing_y: float, platform_bounds):
        self._y = landing_y
        self._falling = False
        self._on_platform = platform_bounds is not None
        self._platform_bounds = platform_bounds
        self.state_machine.end_drag()
        self.state_machine.trigger_react(config.LAND_REACT_TICKS)
        self._last_state = self.state_machine.state
        self.frame_index = 0
        self._update_pixmap()
        self.update()

    def _update_pixmap(self):
        self.current_pixmap = self.animator.get_frame(self.state_machine.state.value, self.frame_index)

    def paintEvent(self, event):
        painter = QPainter(self)
        if self.current_pixmap:
            painter.drawPixmap(0, 0, self.current_pixmap)
        painter.end()

    def closeEvent(self, event):
        self.voice_chat.stop()
        self.recognition.stop()
        self.recognition.wait(2000)
        super().closeEvent(event)

    def _on_identity_recognized(self, name: str, kind: str):
        self.state_machine.trigger_react()
        if kind != "person":
            return

        if _PLACEHOLDER_NAME_RE.match(name):
            # Learned in a previous session but never got a real name
            # (e.g. the app was closed before it could ask) — ask now.
            self.voice_chat.request_name_for(name, on_named=self._on_person_renamed)
        else:
            self.voice_chat.set_identity(name, seen_via_camera=True)
            self.voice_chat.announce(f"Ciao {name}!")

    def _on_identity_learned(self, name: str, kind: str):
        self.state_machine.trigger_react()
        if kind == "person":
            self.voice_chat.request_name_for(name, on_named=self._on_person_renamed)
        else:
            self.voice_chat.announce(f"Ho imparato a riconoscere questo gatto, lo chiamo {name}.")

    def _on_person_renamed(self, old_name: str, new_name: str):
        self.recognition.rename_identity("person", old_name, new_name)

    def _on_action_text(self, text: str):
        self.action_bubble.show_action(text, self._x, self._y, self._screen_rect)
        self.state_machine.trigger_react(10)

    def _on_mood_changed(self, label: str, value: float):
        if value >= config.MOOD_HAPPY_REACT_THRESHOLD:
            self.state_machine.trigger_react(10)

    def _on_appearance_changed(self, name: str, region: str):
        if region == "capelli":
            text = f"Ti sei tagliato i capelli, {name}?"
        else:
            text = f"Ti sei fatto la barba, {name}?"
        self.voice_chat.announce(text)
        self.state_machine.trigger_react(10)

    def _set_muted(self, muted: bool):
        self._muted = muted
        self.voice_chat.set_paused(muted)
        self.mute_action.setChecked(muted)  # keep tray menu in sync when toggled by clicking the pet
        self.state_machine.trigger_react(10)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.activateWindow()
            self.setFocus()
            self._drag_started = False
            self._drag_mouse_start = event.globalPosition().toPoint()
            self._drag_window_start = (self._x, self._y)

    def mouseMoveEvent(self, event):
        if self._drag_mouse_start is None:
            return

        delta = event.globalPosition().toPoint() - self._drag_mouse_start
        if not self._drag_started:
            if abs(delta.x()) < config.DRAG_MOVE_THRESHOLD_PX and abs(delta.y()) < config.DRAG_MOVE_THRESHOLD_PX:
                return
            self._drag_started = True
            self._dragging = True
            self.state_machine.start_drag()
            self.frame_index = 0
            self._last_state = self.state_machine.state

        self._x = self._drag_window_start[0] + delta.x()
        self._y = self._drag_window_start[1] + delta.y()
        self.move(self._x, self._y)
        self._update_pixmap()
        self.update()

    def mouseReleaseEvent(self, event):
        if event.button() != Qt.LeftButton:
            return

        if self._drag_started:
            self._dragging = False
            left_bound = self._screen_rect.x()
            right_bound = self._screen_rect.x() + self._screen_rect.width() - config.DISPLAY_SIZE
            self._x = max(left_bound, min(self._x, right_bound))

            landing_y, landing_platform = self._compute_landing()
            if self._y >= landing_y:
                self._land(landing_y, landing_platform)
            else:
                self._falling = True
                self._fall_velocity = 0.0
                self._fall_target_y = landing_y
                self._fall_target_platform = landing_platform
            self.move(self._x, self._y)
        else:
            if not self.voice_chat.interrupt():
                self._set_muted(not self._muted)

        self._drag_started = False
        self._drag_mouse_start = None
        self._drag_window_start = None

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Escape:
            QApplication.quit()
        else:
            super().keyPressEvent(event)
