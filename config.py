# DLX AI configuration
# Keep prototype parameters here so the main program logic stays simple.

PROGRAM_NAME = "DLX A"
PROGRAM_VERSION = "0.1.0"
PROGRAM_DESCRIPTION = "Local AI prototype for Raspberry Pi"
AI_TITLE = "Dedicated Local AI"

# Local LLM
MODEL_NAME = "phi3.5:latest"
OLLAMA_API_BASE = "http://127.0.0.1:11434/api"
CONVERSATION_HISTORY = True
REQUEST_TIMEOUT_SECONDS = 10
GENERATION_SHUTDOWN_TIMEOUT = 1.0

# Hardware monitoring / SSH control interface
# The current prototype samples and refreshes control data every 15 seconds.
HARDWARE_SAMPLE_INTERVAL = 15.0
STATUS_FILE = "/tmp/dlx_ai_status.json"
CONTROL_REFRESH_INTERVAL = 15.0
STATUS_STALE_AFTER_SECONDS = 45

# GUI
FULLSCREEN = True
WINDOW_WIDTH = 480
WINDOW_HEIGHT = 320
WINDOW_BACKGROUND = "black"
TEXT_BACKGROUND = "black"
TEXT_FOREGROUND = "white"
INPUT_BACKGROUND = "black"
INPUT_FOREGROUND = "white"
CHAT_FONT_FAMILY = "DejaVu Sans"
CHAT_FONT_SIZE = 16
DISPLAY_MARGIN = 8
GUI_STREAM_POLL_MS = 40
SCROLL_LINES_PER_KEYPRESS = 2

# Conversation format
USER_PREFIX = "ME: "
MODEL_PREFIX = "AI: "
BLANK_LINES_AFTER_MODEL = 2

# Technician-only exit shortcut.
# This is kept here so it can be changed without editing application logic.
TECHNICIAN_EXIT_SHORTCUT = "<Control-Alt-KeyPress-q>"

# Linux hardware paths
TEMPERATURE_PATH = "/sys/class/thermal/thermal_zone0/temp"
