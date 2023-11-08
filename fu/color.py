_FMT = '\033[{}m'
RESET = _FMT.format(0)
BOLD = _FMT.format(1)
FAINT = _FMT.format(2)

_COLOR = _FMT.format("38;2;{};{};{}")

_WHITE = _COLOR.format(0xf8, 0xf8, 0xf2)
_PURPLE = _COLOR.format(0xAE, 0x81, 0xFF)
_GREY = _COLOR.format(0x88, 0x84, 0x6F)
_YELLOW = _COLOR.format(0xE6, 0xDB, 0x74)
_GREEN = _COLOR.format(0xA6, 0xE2, 0x2E)
_MAGENTA = _COLOR.format(0xF9, 0x26, 0x72)
_CYAN = _COLOR.format(0x66, 0xD9, 0xEF)
_ORANGE = _COLOR.format(0xFD, 0x97, 0x1F)

WORD = _WHITE
NUM = _PURPLE
COMMENT = _GREY
STRING = _YELLOW
CONSTANT = _PURPLE
FUNC_NAME = _GREEN
KEYWORD = _MAGENTA
TEMPLATE = _CYAN
PARAM = _ORANGE
TYPE = _GREEN
