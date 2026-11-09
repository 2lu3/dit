"""転送計画とバイト転送用の alive-progress 表示."""

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


def _open_planning_bar(
    title: str,
    stream: TextIO | None,
) -> AbstractContextManager[_AliveHandle]:
    extra: dict[str, object] = {}
    if stream is not None:
        extra = {"file": stream, "force_tty": True}
    return alive_bar(title=title, **extra)


def _open_file_count_bar(
    total_files: int,
    title: str,
    stream: TextIO | None,
) -> AbstractContextManager[_AliveHandle]:
    extra: dict[str, object] = {}
    if stream is not None:
        extra = {"file": stream, "force_tty": True}
    return alive_bar(
        total_files,
        title=title,
        unit="file",
        monitor="{count}/{total}",
        **extra,
    )


class PlanProgressBar:
    """対象一覧の作成中はスピナー、その後は確認済み件数を表示する."""

    def __init__(self, title: str, *, stream: TextIO | None = None) -> None:
        """転送計画のタイトルと任意の出力先を設定する."""
        self._title = f"{title} plan"
        self._stream = stream
        self._cm: AbstractContextManager[_AliveHandle] | None = None
        self._bar: _AliveHandle | None = None

    def __enter__(self) -> Self:
        """ファイル数が分かるまでスピナーを表示する."""
        self._cm = _open_planning_bar(self._title, self._stream)
        self._bar = self._cm.__enter__()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> bool | None:
        """現在の計画表示を終了する."""
        if self._cm is None:
            return None
        cm = self._cm
        self._cm = None
        self._bar = None
        return cm.__exit__(exc_type, exc, tb)

    def set_total(self, total_files: int) -> None:
        """一覧件数が確定したらスピナーを件数バーへ切り替える."""
        self._close_active()
        if total_files == 0:
            return
        self._cm = _open_file_count_bar(total_files, self._title, self._stream)
        self._bar = self._cm.__enter__()

    def advance(self) -> None:
        """確認済みファイルを 1 件加算する."""
        if self._bar is not None:
            self._bar()

    def _close_active(self) -> None:
        if self._cm is None:
            return
        cm = self._cm
        self._cm = None
        self._bar = None
        cm.__exit__(None, None, None)


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
