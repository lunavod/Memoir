"""Reader and writer for Memoir binary .meta files."""

from __future__ import annotations

import os
import struct
import time
from typing import TYPE_CHECKING

from memoir._types import MetaFile, MetaHeader, MetaKeyEntry, MetaRow

if TYPE_CHECKING:
    from typing import BinaryIO

# Binary format constants (must match include/memoir/meta_format.h)
_HEADER_FMT = "<8sII Q II"
_HEADER_SIZE = struct.calcsize(_HEADER_FMT)

_KEY_FMT = "<II 32s"
_KEY_SIZE = struct.calcsize(_KEY_FMT)

_ROW_FMT = "<QQ qq Q II II"
_ROW_SIZE = struct.calcsize(_ROW_FMT)


class MetaReader:
    """Read Memoir .meta files."""

    @staticmethod
    def read(path: str | os.PathLike) -> MetaFile:
        """Read and parse an entire .meta file into a MetaFile dataclass."""
        with open(path, "rb") as f:
            header = MetaReader._read_header(f)
            keys = [MetaReader._read_key(f) for _ in range(header.key_count)]
            rows: list[MetaRow] = []
            while True:
                row = MetaReader._read_row(f)
                if row is None:
                    break
                rows.append(row)
        return MetaFile(header=header, keys=keys, rows=rows)

    @staticmethod
    def _read_header(f: BinaryIO) -> MetaHeader:
        data = f.read(_HEADER_SIZE)
        if len(data) < _HEADER_SIZE:
            raise ValueError(f"Header too short ({len(data)} bytes)")
        magic, version, _r0, created_ns, key_count, _r1 = struct.unpack(
            _HEADER_FMT, data
        )
        if magic != b"RCMETA1\x00":
            raise ValueError(f"Bad magic: {magic!r}")
        return MetaHeader(
            magic=magic, version=version,
            created_unix_ns=created_ns, key_count=key_count,
        )

    @staticmethod
    def _read_key(f: BinaryIO) -> MetaKeyEntry:
        data = f.read(_KEY_SIZE)
        if len(data) < _KEY_SIZE:
            raise ValueError("Truncated key entry")
        bit_idx, vk, name_bytes = struct.unpack(_KEY_FMT, data)
        name = name_bytes.split(b"\x00", 1)[0].decode("ascii")
        return MetaKeyEntry(bit_index=bit_idx, virtual_key=vk, name=name)

    @staticmethod
    def _read_row(f: BinaryIO) -> MetaRow | None:
        data = f.read(_ROW_SIZE)
        if len(data) < _ROW_SIZE:
            return None
        fid, rfi, cqpc, hqpc, kbm, w, h, stride, flags = struct.unpack(
            _ROW_FMT, data
        )
        return MetaRow(
            frame_id=fid, record_frame_index=rfi,
            capture_qpc=cqpc, host_accept_qpc=hqpc,
            keyboard_mask=kbm, width=w, height=h,
            analysis_stride=stride, flags=flags,
        )


class MetaWriter:
    """Write Memoir .meta files.

    Usage::

        keys = [MetaKeyEntry(0, 0x57, "W"), MetaKeyEntry(1, 0x41, "A")]
        with MetaWriter("session.meta", keys) as w:
            w.write_row(MetaRow(frame_id=0, record_frame_index=0, ...))
            w.write_row(MetaRow(frame_id=1, record_frame_index=1, ...))
    """

    def __init__(
        self,
        path: str | os.PathLike,
        keys: list[MetaKeyEntry],
        created_unix_ns: int | None = None,
    ) -> None:
        self._path = path
        self._keys = keys
        self._created_ns = created_unix_ns or time.time_ns()
        self._file: BinaryIO | None = None
        self._row_count = 0

    # -- context manager --

    def __enter__(self) -> MetaWriter:
        self.open()
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    # -- public API --

    def open(self) -> None:
        """Open the file and write the header + key table."""
        self._file = open(self._path, "wb")
        self._write_header()
        self._write_keys()

    def write_row(self, row: MetaRow) -> None:
        """Append a single per-frame metadata row."""
        if self._file is None:
            raise RuntimeError("Writer not open")
        self._file.write(struct.pack(
            _ROW_FMT,
            row.frame_id, row.record_frame_index,
            row.capture_qpc, row.host_accept_qpc,
            row.keyboard_mask, row.width, row.height,
            row.analysis_stride, row.flags,
        ))
        self._row_count += 1

    def close(self) -> None:
        """Flush and close the file."""
        if self._file is not None:
            self._file.close()
            self._file = None

    @property
    def row_count(self) -> int:
        return self._row_count

    # -- internals --

    def _write_header(self) -> None:
        assert self._file is not None
        self._file.write(struct.pack(
            _HEADER_FMT,
            b"RCMETA1\x00", 1, 0,
            self._created_ns,
            len(self._keys), 0,
        ))

    def _write_keys(self) -> None:
        assert self._file is not None
        for k in self._keys:
            name_bytes = k.name.encode("ascii")[:31].ljust(32, b"\x00")
            self._file.write(struct.pack(
                _KEY_FMT, k.bit_index, k.virtual_key, name_bytes,
            ))
