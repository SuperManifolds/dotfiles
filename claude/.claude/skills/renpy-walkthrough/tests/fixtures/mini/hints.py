SCOPE = ["*"]
LIST_SCREENS = {"picker": {"arg": 0, "text": "text", "unproxy": ["record"]}}
HINTS = {
    "script.rpy:10": ("Trust gates a later scene.", {0: ("good", "Trust +2 · scene later"), 1: ("bad", "Trust -1")}),
    "@m1": (None, {1: ("info", "Needs trust")}),
}
INPUT_HINTS = {}
