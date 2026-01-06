from PySide6.QtCore import QObject, Signal

from core.state import SystemStatus
from engine.base import EnginePort


class EngineBridge(QObject, EnginePort):
    sig_token = Signal(str)
    sig_trace = Signal(str)
    sig_status = Signal(SystemStatus)
    sig_usage = Signal(int)

    def __init__(self, impl: EnginePort):
        super().__init__()
        self.impl = impl
        self._gen_id = 0
        self._active_gid = 0

        impl.sig_token.connect(
            lambda t: self.sig_token.emit(t)
            if self._active_gid == self._gen_id
            else None
        )
        impl.sig_trace.connect(
            lambda t: self.sig_trace.emit(t)
            if self._active_gid == self._gen_id
            else None
        )
        impl.sig_status.connect(
            lambda s: self.sig_status.emit(s)
            if self._active_gid == self._gen_id
            else None
        )
        impl.sig_usage.connect(
            lambda u: self.sig_usage.emit(u)
            if self._active_gid == self._gen_id
            else None
        )

    def load_model(self) -> None:
        self.impl.load_model()

    def unload_model(self) -> None:
        self.impl.unload_model()

    def generate(self, user_input: str) -> None:
        self._gen_id += 1
        gid = self._gen_id
        self._active_gid = gid
        self.impl.generate(user_input)

    def stop_generation(self) -> None:
        self._gen_id += 1
        self.impl.stop_generation()

    def shutdown(self) -> None:
        self.impl.shutdown()
