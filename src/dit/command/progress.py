"""バイト転送用の alive-progress 表示."""

from __future__ import annotations

import threading
from typing import TYPE_CHECKING, Protocol

from alive_progress import alive_bar

if TYPE_CHECKING:
    from collections.abc import AbstractContextManager
    from types import TracebackType
    from typing import Self, TextIO

BYTE_UNIT = "byte"
BYTE_SCALE = "SI2"
BYTE_MONITOR = "{count}/{total}"


class _AliveHandle(Protocol):
    def __call__(self, amount: int = 1) -> None: ...

    def text(self, path: str) -> None: ...

    @property
    def current(self) -> int: ...


def _open_bar(
    total_bytes: int,
    title: str,
    stream: TextIO | None,
) -> AbstractContextManager[_AliveHandle]:
    extra: dict[str, object] = {}
    if stream is not None:
        extra = {"file": stream, "force_tty": True}
    return alive_bar(
        total_bytes,
        title=title,
        unit=BYTE_UNIT,
        scale=BYTE_SCALE,
        monitor=BYTE_MONITOR,
        **extra,
    )


class ByteTransferBar:
    """転送バイト量を K/M/Gbyte の N/N で表示する."""

    def __init__(
        self,
        total_bytes: int,
        title: str,
        *,
        stream: TextIO | None = None,
    ) -> None:
        """合計バイトとタイトルでバーを構成する."""
        self._lock = threading.Lock()
        self._cm = _open_bar(total_bytes, title, stream)
        self._bar: _AliveHandle | None = None

    def __enter__(self) -> Self:
        """バー表示を開始する."""
        self._bar = self._cm.__enter__()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> bool | None:
        """バー表示を終了する."""
        self._bar = None
        return self._cm.__exit__(exc_type, exc, tb)

    def add_bytes(self, amount: int) -> None:
        """転送増分をバーへ加算する."""
        if amount <= 0:
            return
        bar = self._require_bar()
        with self._lock:
            bar(amount)

    def set_path(self, path: str) -> None:
        """現在の転送パスをバー文言に出す."""
        bar = self._require_bar()
        with self._lock:
            bar.text(path)

    @property
    def current(self) -> int:
        """加算済みバイト数を返す."""
        return int(self._require_bar().current)

    def _require_bar(self) -> _AliveHandle:
        if self._bar is None:
            msg = "ByteTransferBar is not active"
            raise RuntimeError(msg)
        return self._bar
