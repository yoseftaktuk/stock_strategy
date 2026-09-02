class KillSwitch:
    def __init__(self) -> None:
        self._enabled = False

    def is_enabled(self) -> bool:
        return self._enabled

    def activate(self) -> None:
        self._enabled = True

    def deactivate(self) -> None:
        self._enabled = False
