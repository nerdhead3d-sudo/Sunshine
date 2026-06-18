from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
ASSETS_DIR = BASE_DIR / "pet" / "assets"
SPRITES_DIR = ASSETS_DIR / "sprites"
DATA_DIR = BASE_DIR / "pet" / "data"

OLLAMA_HOST = "http://127.0.0.1:11434"
OLLAMA_MODEL = "llama3.2:1b"

# Mood classifier: a small neural network trained from scratch by us (see
# pet/mood/train.py and pet/mood/dataset.py) on a hand-written Italian
# dataset, not a pretrained model. Updates each identity's "mood" score.
MOOD_MODEL_DIR = BASE_DIR / "pet" / "mood" / "model"
MOOD_EMA_ALPHA = 0.3  # how much each new reading shifts the running mood average
MOOD_HAPPY_REACT_THRESHOLD = 0.4  # running mood score above which the pet plays a happy reaction

# Chat brain: fully offline local model (gpt4all, no server/compiler/CUDA
# needed) by default, instead of depending on a running Ollama instance.
# Set to False to use OllamaClient (config.OLLAMA_*) instead.
USE_LOCAL_LLM = True
LOCAL_LLM_REPO_ID = "bartowski/Llama-3.2-1B-Instruct-GGUF"
LOCAL_LLM_FILENAME = "Llama-3.2-1B-Instruct-Q4_K_M.gguf"  # ~770MB, runs fine on 8GB RAM, CPU-only
LOCAL_MODEL_DIR = BASE_DIR / "pet" / "local_models"
LOCAL_LLM_CONTEXT = 2048
LOCAL_LLM_MAX_TOKENS = 100  # keeps spoken replies short instead of rambling
LOCAL_LLM_MAX_TURNS_PER_SESSION = 20  # recycle the chat session after this many turns, so the
                                       # finite context window (LOCAL_LLM_CONTEXT) never overflows

PET_NAME = "Sunshine"

# Voice: TTS via edge-tts (online neural voices) first; if that fails
# (typically no internet) falls back to Piper, an offline neural voice
# (good quality, ~60MB model downloaded from Hugging Face once); if even
# that fails, falls back further to robotic offline pyttsx3/SAPI5. STT via
# faster-whisper, fully offline (model downloaded from Hugging Face once).
TTS_VOICE = "it-IT-IsabellaNeural"
TTS_RATE = "+25%"   # edge-tts speaking-rate offset; "+0%" for the normal speed
PIPER_VOICE_REPO = "rhasspy/piper-voices"
PIPER_VOICE_BASENAME = "it/it_IT/paola/medium/it_IT-paola-medium"
PIPER_MODEL_DIR = BASE_DIR / "pet" / "local_models" / "piper"
TTS_FALLBACK_VOICE_HINT = "it-it"  # substring matched against offline SAPI5 voice ids (pyttsx3)
STT_SAMPLE_RATE = 16000
STT_LANGUAGE_CODE = "it"  # ISO 639-1, used by faster-whisper
STT_WHISPER_MODEL = "small"  # tiny/base/small/medium: bigger = more accurate but slower/heavier
STT_WHISPER_MODEL_DIR = BASE_DIR / "pet" / "local_models" / "whisper"

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

# Sprites are generated at SPRITE_SIZE and scaled up for display.
SPRITE_SIZE = 64
DISPLAY_SCALE = 3
DISPLAY_SIZE = SPRITE_SIZE * DISPLAY_SCALE

FRAME_INTERVAL_MS = 220   # animation frame rate
MOVE_INTERVAL_MS = 60     # movement/state-machine tick rate
WALK_SPEED = 3            # pixels per movement tick
GROUND_MARGIN = 12        # pixels above the taskbar/work-area edge

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
MIN_PLATFORM_WIDTH = DISPLAY_SIZE * 1.2

# Recognition (Fase 4): webcam-based identification of people and cats via
# Haar cascades + LBPH. No manual enrollment needed: unknown faces/cat-faces
# are learned automatically (see AUTO_LEARN_*) once seen consistently.
WEBCAM_INDEX = 0
RECOGNITION_INTERVAL_MS = 400
RECOGNITION_CONFIDENCE_THRESHOLD = 65.0  # LBPH distance: lower = more confident (stricter)
RECOGNITION_CONSECUTIVE_FRAMES = 6       # frames needed in a row before confirming (~2.4s)
RECOGNITION_DIR = BASE_DIR / "pet" / "recognition"
RECOGNITION_SAMPLES_DIR = RECOGNITION_DIR / "samples"
RECOGNITION_MODELS_DIR = RECOGNITION_DIR / "models"

AUTO_LEARN_ENABLED = True
AUTO_LEARN_SAMPLE_COUNT = 40       # consecutive unknown-face frames before auto-training (~16s)
AUTO_LEARN_MAX_FRAME_DIFF = 40.0   # mean abs pixel diff vs. last buffered crop; above this, treat
                                    # it as a different face and restart the buffer (avoids merging
                                    # two different people who alternate in front of the webcam)
