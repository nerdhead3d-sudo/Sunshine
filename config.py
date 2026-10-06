import os
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent

# When running from source (dev/CI), all writable data lives under
# BASE_DIR like before. When running from a PyInstaller-frozen install
# (sys.frozen, see the installer build), BASE_DIR is typically inside
# Program Files, which isn't writable without admin rights — sprites,
# downloaded models, the conversation DB, and learned faces instead go to
# %LOCALAPPDATA%\Sunshine, so the app works from a standard non-admin
# install and survives an upgrade/reinstall (those files aren't touched by
# the installer at all).
if getattr(sys, "frozen", False):
    _WRITABLE_ROOT = Path(os.environ.get("LOCALAPPDATA", BASE_DIR)) / "Sunshine"
else:
    _WRITABLE_ROOT = BASE_DIR / "pet"  # dev/CI: unchanged paths, same as before this existed

ASSETS_DIR = BASE_DIR / "pet" / "assets"
SPRITES_DIR = _WRITABLE_ROOT / "assets" / "sprites" if getattr(sys, "frozen", False) else ASSETS_DIR / "sprites"
DATA_DIR = _WRITABLE_ROOT / "data"
# Synthesized at first run by pet/assets/generate_sounds.py, like the sprites.
SOUNDS_DIR = _WRITABLE_ROOT / "assets" / "sounds" if getattr(sys, "frozen", False) else ASSETS_DIR / "sounds"

OLLAMA_HOST = "http://127.0.0.1:11434"
# llama3.2:latest (3B), not the 1B variant: misurato direttamente su questa
# macchina (GTX 970) — il modello 1B è velocissimo ma incoerente/divaga
# (es. inventa di aver visto cose mai viste); il 3B, una volta caricato in
# GPU, risponde in circa lo stesso tempo "a caldo" (~1-2s per una risposta
# breve) con risposte molto più sensate — paghi solo un caricamento a
# freddo più lungo la primissima volta dopo l'avvio di Ollama.
OLLAMA_MODEL = "llama3.2:latest"
# Lower than Ollama's own default (0.8): a small model left at default
# temperature drifts off-topic more (confirmed in practice — see CLAUDE.md
# on the "fazzoletto"/hallucinated-vision incidents). Still has some
# variety, just noticeably more grounded in what was actually said.
OLLAMA_TEMPERATURE = 0.4

# Mood classifier: a small neural network trained from scratch by us (see
# pet/mood/train.py and pet/mood/datasets/<lang>.py) on hand-written
# datasets, not a pretrained model. One model per language. Updates each
# identity's "mood" score.
MOOD_MODEL_DIR = BASE_DIR / "pet" / "mood" / "model"
MOOD_EMA_ALPHA = 0.3  # how much each new reading shifts the running mood average
MOOD_HAPPY_REACT_THRESHOLD = 0.4  # running mood score above which the pet plays a happy reaction

# Languages: Italian is the default and has by far the richest mood
# dataset; the others are smaller starting points (see pet/mood/datasets/).
SUPPORTED_LANGUAGES = ["it", "en", "fr", "es", "de", "pt"]
DEFAULT_LANGUAGE = "it"

# Chat brain: Ollama (config.OLLAMA_*) by default — on a machine with a
# GPU (this one has a GTX 970) it answers in ~1s once the model is loaded,
# vs. several seconds on the CPU-only gpt4all path below, and the replies
# come out noticeably more coherent at the same model size (measured: same
# llama3.2:1b weights, just GPU vs. CPU-quantized inference). Set to True
# to use the fully offline gpt4all/llama.cpp path instead (no Ollama
# server dependency, but slower and less coherent on this hardware) — also
# selectable per-user at runtime from the tray "Impostazioni..." dialog
# regardless of this default, see pet/settings_store.py.
USE_LOCAL_LLM = False
LOCAL_LLM_REPO_ID = "bartowski/Llama-3.2-1B-Instruct-GGUF"
LOCAL_LLM_FILENAME = "Llama-3.2-1B-Instruct-Q4_K_M.gguf"  # ~770MB, runs fine on 8GB RAM, CPU-only
LOCAL_MODEL_DIR = _WRITABLE_ROOT / "local_models"
LOCAL_LLM_CONTEXT = 2048
LOCAL_LLM_MAX_TOKENS = 100  # keeps spoken replies short instead of rambling
LOCAL_LLM_MAX_TURNS_PER_SESSION = 20  # recycle the chat session after this many turns, so the
                                       # finite context window (LOCAL_LLM_CONTEXT) never overflows

PET_NAME = "Sunshine"

# Wake word (Lumo-style): when enabled, the always-listening mic ignores
# any utterance that doesn't contain this word, and strips it from the
# rest before treating it as a command/chat message. Off by default —
# it's a bigger UX change (you have to address the pet by name every
# time) than something to silently switch on.
WAKE_WORD_ENABLED = False
WAKE_WORD = PET_NAME

# Voice: TTS via edge-tts (online neural voices) first; if that fails
# (typically no internet) falls back to Piper, an offline neural voice
# (good quality, ~60MB model downloaded from Hugging Face once); if even
# that fails, falls back further to robotic offline pyttsx3/SAPI5. STT via
# faster-whisper, fully offline (model downloaded from Hugging Face once),
# auto-detecting the spoken language unless fixed (see SUPPORTED_LANGUAGES
# and VoiceChatController's language-switch voice commands).
TTS_RATE = "+25%"   # edge-tts speaking-rate offset; "+0%" for the normal speed
PIPER_VOICE_REPO = "rhasspy/piper-voices"
PIPER_MODEL_DIR = LOCAL_MODEL_DIR / "piper"
STT_SAMPLE_RATE = 16000
STT_WHISPER_MODEL = "small"  # tiny/base/small/medium: bigger = more accurate but slower/heavier
STT_WHISPER_MODEL_DIR = LOCAL_MODEL_DIR / "whisper"
# Whisper's own confidence that a recorded clip contains no real speech.
# The energy-based VAD below only filters out *quiet* sound, so it still
# hands Whisper short bursts of background noise that are loud enough to
# trigger it (a chair creak, a cough, a door) but aren't speech — Whisper
# doesn't say "I don't know" in that case, it hallucinates a short, often
# wrong-language phrase (confirmed in practice: real noise transcribed as
# "あ、すみません。" and "You"). Segments with no_speech_prob above this are
# discarded as silence instead of being passed on to the chat/intents.
STT_NO_SPEECH_PROB_THRESHOLD = 0.6

LANGUAGE_NAMES = {
    "it": "italiano", "en": "inglese", "fr": "francese",
    "es": "spagnolo", "de": "tedesco", "pt": "portoghese",
}

# edge-tts voice id per language (online, best quality).
TTS_VOICES = {
    "it": "it-IT-IsabellaNeural",
    "en": "en-US-AriaNeural",
    "fr": "fr-FR-DeniseNeural",
    "es": "es-ES-ElviraNeural",
    "de": "de-DE-KatjaNeural",
    "pt": "pt-BR-FranciscaNeural",
}

# Piper voice basename per language (offline fallback, see rhasspy/piper-voices).
PIPER_VOICE_BASENAMES = {
    "it": "it/it_IT/paola/medium/it_IT-paola-medium",
    "en": "en/en_US/lessac/medium/en_US-lessac-medium",
    "fr": "fr/fr_FR/siwis/medium/fr_FR-siwis-medium",
    "es": "es/es_ES/davefx/medium/es_ES-davefx-medium",
    "de": "de/de_DE/thorsten/medium/de_DE-thorsten-medium",
    "pt": "pt/pt_BR/faber/medium/pt_BR-faber-medium",
}

# Substring matched against offline SAPI5 voice ids (pyttsx3), last-resort
# fallback; only "it-it" is confirmed installed on this machine, others
# will just fall through to whatever default voice Windows has installed.
TTS_FALLBACK_VOICE_HINTS = {
    "it": "it-it", "en": "en-us", "fr": "fr-fr",
    "es": "es-es", "de": "de-de", "pt": "pt-br",
}

# Continuous listening (energy-based voice activity detection): how loud a
# block must be relative to the calibrated noise floor to count as speech,
# and how long to wait in silence before considering an utterance finished.
VAD_CALIBRATION_SECONDS = 1.0
VAD_THRESHOLD_MULTIPLIER = 3.0
VAD_MIN_THRESHOLD = 80.0
VAD_SILENCE_SECONDS = 0.8
VAD_MIN_SPEECH_SECONDS = 0.4
VAD_START_CONFIRM_SECONDS = 0.2  # level must stay above threshold this long before it counts as real speech
MIC_RETRY_SECONDS = 5.0  # how often to retry opening the mic if it's unavailable/disconnected

# Where the pet's sprites come from (main.ensure_sprites):
#   "3d"     pre-rendered frames of the rigged 3D cat (pet/assets/cat3d/,
#            made offline with Blender, see tools/cat3d/)
#   "sheet"  the 2D AI-generated sprite sheet (pet/assets/sheets/black_cat.png)
#   "placeholders"  procedural pixel-art (no artwork needed)
#   "auto"   the first of these that is available
SPRITE_SOURCE = "auto"

# Sprites are generated at SPRITE_SIZE and scaled up for display.
SPRITE_SIZE = 64
DISPLAY_SCALE = 5  # 320px; sprite-sheet frames are sliced straight at this size (slice_sheet)
DISPLAY_SIZE = SPRITE_SIZE * DISPLAY_SCALE

FRAME_INTERVAL_MS = 220   # default animation frame rate (idle, sit, sleep, ...)
MOVE_INTERVAL_MS = 60     # movement/state-machine tick rate
WALK_SPEED = 4            # pixels per movement tick
RUN_SPEED = 10            # pixels per movement tick while running

# Per-state animation speed, overriding FRAME_INTERVAL_MS: the sprite-sheet
# walk/run cycles have 8-10 frames and look like slow motion at 220ms.
# Walk/run are tuned for the 3D frames (16-frame walk, 12-frame run) so a
# full stride roughly matches WALK_SPEED/RUN_SPEED and the paws don't slide.
STATE_FRAME_INTERVAL_MS = {
    "walk_left": 70, "walk_right": 70,
    "run_left": 60, "run_right": 60,
    "jump": 80, "fall": 90, "land": 55, "play": 80, "react": 80,
    "idle": 140, "sit": 260, "sleep": 320, "dragged": 120,
    "turn_front": 65, "turn_back": 65, "front": 140,
}
# Animations played once and then held on their last frame (instead of
# looping) until the state ends.
ONE_SHOT_STATES = {"jump", "land", "play", "turn_front", "turn_back"}

# Visible height of the cat inside its DISPLAY_SIZE x DISPLAY_SIZE window:
# the sheet frames leave the top ~40% transparent (tallest pose ~195/320).
# Used as the headroom a window needs above it to count as a platform —
# requiring the whole DISPLAY_SIZE rejected almost every window on a
# 1080p monitor once the sprite grew to 320px.
PET_VISIBLE_HEIGHT = int(DISPLAY_SIZE * 0.62)
GROUND_MARGIN = 0         # pixels above the taskbar/work-area edge (0 = paws right on the taskbar)

# Sit/sleep: while idle, the pet sometimes sits down instead of walking off
# again; while sitting, it can drift into a longer sleep before waking back
# to idle. Durations are in movement ticks (MOVE_INTERVAL_MS each).
SIT_CHANCE = 0.3                    # probability idle -> sit instead of walk
SLEEP_CHANCE = 0.25                 # probability sit -> sleep instead of idle
SIT_DURATION_TICKS = (60, 150)      # ~3.6-9s
SLEEP_DURATION_TICKS = (150, 300)   # ~9-18s
# Idle can also turn into a run (instead of a walk) or a short playful
# pounce (the sheet's ATTACK row, "play" state).
RUN_CHANCE = 0.25                   # probability a walk is a run instead
PLAY_CHANCE = 0.1                   # probability idle -> play
PLAY_TICKS = 14                     # ~0.85s: one pass of the pounce animation
# Facing the viewer (3D renders: turn_front / front / turn_back): on its
# own, and for as long as Sunshine is talking. Chance/duration tuned by
# simulating the state machine so that, over time, the pet faces right,
# left and the viewer about a third each (user request).
FRONT_CHANCE = 0.35                 # probability idle -> turn to face the viewer
FRONT_DURATION_TICKS = (100, 220)   # ~6-13s facing the viewer when it's spontaneous
FRONT_LINGER_TICKS = 25             # ~1.5s still facing the viewer after Sunshine stops talking
TURN_TICKS = 8                      # ~0.5s: one pass of the turn animation

# Drag: holding the pet with the mouse and moving it past this many pixels
# (in either axis) turns a click into a drag instead of toggling mute.
DRAG_MOVE_THRESHOLD_PX = 6

# Petting ("carezza", Lumo-style): small back-and-forth wiggling while held
# down, without ever crossing DRAG_MOVE_THRESHOLD_PX net displacement, is
# treated as a stroke rather than a drag attempt or a click. Measured as
# cumulative path length traveled (sum of all incremental mouse deltas)
# since mouse-down.
PET_STROKE_MIN_PATH_PX = 60
PET_STROKE_MOOD_VALENCE = 0.5  # positive mood nudge applied once per stroke gesture

# Drop: when released mid-air, the pet falls (fall animation) instead of
# teleporting, then plays the landing animation on touchdown.
FALL_ACCEL = 1.5          # pixels/tick^2 of downward acceleration while falling
FALL_MAX_SPEED = 14       # terminal velocity, pixels per movement tick
LAND_TICKS = 9            # ~0.55s landing animation on touchdown
FALL_MEOW_MIN_PX = 200    # dropped from at least this high: long "miaaaooo" while falling

SOUND_EFFECTS_VOLUME = 0.5  # 0..1, pet sound effects (meow, purr, thud...)

ACTION_BUBBLE_DURATION_MS = 4000  # how long a narrated-action bubble stays visible

# Index into QGuiApplication.screens() used as the pet's home screen.
# Falls back to screen 0 if this index doesn't exist (single-monitor setups).
SECONDARY_SCREEN_INDEX = 1

# Window climbing: the pet periodically hops onto the top edge of a visible
# application window (like a classic desktop mascot) and walks along it for
# a while before coming back down to the ground.
WINDOW_SCAN_INTERVAL_MS = 3000   # how often to re-scan visible windows
CLIMB_CHECK_INTERVAL_MS = 8000   # how often to consider climbing, while grounded
CLIMB_CHANCE = 0.4               # probability of climbing at each check
CLIMB_DURATION_MS = 15000        # how long to stay on a window before descending
JUMP_TICKS = 12                  # ~0.7s: duration of the jump arc onto a window
JUMP_ARC_PX = 90                 # roughly how far the arc rises above the higher end
MIN_PLATFORM_WIDTH = DISPLAY_SIZE * 1.2
PLATFORM_CHECK_INTERVAL_MS = 250 # while on a window: how often to check it's still there
PLATFORM_TOLERANCE_PX = 3        # window top may differ this much from the pet's feet

# Recognition (Fase 4): webcam-based identification of people (deep-
# learning face embeddings, see face_embeddings.py) and cats (Haar
# cascades + LBPH — InsightFace's detector/aligner only handles human
# face geometry, cats stay on the classical approach). No manual
# enrollment needed: unknown faces/cat-faces are learned automatically
# (see AUTO_LEARN_*) once seen consistently.
WEBCAM_INDEX = 0
RECOGNITION_INTERVAL_MS = 400
CAT_FEATURE_SIMILARITY_THRESHOLD = 0.55  # HOG descriptor cosine similarity above which two cat crops count as the same cat
RECOGNITION_CONSECUTIVE_FRAMES = 6       # frames needed in a row before confirming (~2.4s)
RECOGNITION_DIR = BASE_DIR / "pet" / "recognition"
RECOGNITION_SAMPLES_DIR = (_WRITABLE_ROOT / "recognition" / "samples") if getattr(sys, "frozen", False) else RECOGNITION_DIR / "samples"
RECOGNITION_MODELS_DIR = (_WRITABLE_ROOT / "recognition" / "models") if getattr(sys, "frozen", False) else RECOGNITION_DIR / "models"

# Face embedding model for people (InsightFace, ONNX Runtime, CPU). "_sc"
# is the small/compact variant (~15MB) chosen for compatibility with
# modest hardware over the larger, slightly more accurate "_l" variant.
FACE_EMBEDDING_MODEL = "buffalo_sc"
FACE_EMBEDDING_MODEL_DIR = (_WRITABLE_ROOT / "recognition" / "face_models") if getattr(sys, "frozen", False) else RECOGNITION_DIR / "face_models"
FACE_EMBEDDING_DET_SIZE = (320, 320)
FACE_EMBEDDING_SIMILARITY_THRESHOLD = 0.40  # cosine similarity above which two faces count as the same person

AUTO_LEARN_ENABLED = True
AUTO_LEARN_SAMPLE_COUNT = 40       # consecutive unknown-face frames before auto-training (~16s)
AUTO_LEARN_MAX_FRAME_DIFF = 40.0   # cats: mean abs pixel diff vs. last buffered crop. People: cosine
                                    # similarity vs. last buffered embedding, see AUTO_LEARN_MIN_FACE_SIMILARITY.
                                    # Above/below this, treat it as a different face and restart the
                                    # buffer (avoids merging two different individuals who alternate
                                    # in front of the webcam)
AUTO_LEARN_MIN_FACE_SIMILARITY = 0.35  # people: cosine similarity below this resets the learning buffer

# Liveness ("anti-foto", Lumo-style): a real face held in front of the
# webcam always has tiny natural jitter (breathing, hand tremor, micro
# head movements); a printed photo or phone screen held up to impersonate
# someone tends to stay unnaturally still. Heuristic only — not real
# biometric liveness detection (no depth/IR sensor here) — just refuses to
# *confirm* a known identity (blocking the allow_open_apps privilege) if
# the face's position was frozen for the whole confirmation window;
# doesn't affect plain conversation, which has no such privilege anyway.
LIVENESS_ENABLED = True
LIVENESS_MIN_POSITION_STDDEV_PX = 0.8

# Appearance-change detection: heuristic pixel-diff comparison between the
# current face crop and the first sample ever saved for that identity (no
# real semantic understanding of "haircut" vs "beard" — just "something
# changed a lot in this region of the face"). Expect false positives from
# lighting/angle changes; thresholds are deliberately conservative.
APPEARANCE_HAIR_FRACTION = 0.25    # top fraction of the 200x200 face crop = hair/forehead region
APPEARANCE_BEARD_FRACTION = 0.30   # bottom fraction = chin/beard region
APPEARANCE_DIFF_THRESHOLD = 45.0   # mean abs pixel diff above which a region counts as "changed"

# Installer-time choices (monitor, spoken language), written once by
# installer/setup.iss as plain JSON and applied here as overrides on top
# of the defaults above — absent entirely for dev/source runs and for
# anyone who installs without going through the installer, in which case
# these two lines are a no-op and the hardcoded defaults above stand.
def _apply_install_settings():
    import json

    install_settings_path = _WRITABLE_ROOT / "data" / "install_settings.json"
    if not install_settings_path.exists():
        return
    try:
        data = json.loads(install_settings_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return

    global SECONDARY_SCREEN_INDEX, DEFAULT_LANGUAGE
    if "secondary_screen_index" in data:
        SECONDARY_SCREEN_INDEX = int(data["secondary_screen_index"])
    if data.get("language") in SUPPORTED_LANGUAGES:
        DEFAULT_LANGUAGE = data["language"]


_apply_install_settings()
