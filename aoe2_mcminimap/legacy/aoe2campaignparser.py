"""RGE campaign container reader (AoC `.cpn`/`.cpx`, DE `.aoe2campaign`).

Ported from withmorten's ``rge_campaign`` (AoE/AoC/DE2 read path). DE1 ``.aoecpn``
is intentionally unsupported for McMinimap.
"""

from __future__ import annotations

import struct
from typing import Any

# Mirrors dev/rge_campaign-master/rge_campaign.h
RGE_MAX_CHAR = 255
RGE_DE2_MAX_CHAR = 256
RGE_STRING_ID = 0x0A60
RGE_CAMPAIGN_VERSION = 0x30302E31  # AoK–AoC .cpn / .cpx
RGE_CAMPAIGN_VERSION_DE1 = 0x30312E31  # DE1 — unsupported
RGE_CAMPAIGN_VERSION_DE2 = 0x30302E32  # DE2 .aoe2campaign

CAMPAIGN_EXTENSIONS = frozenset({".cpn", ".cpx", ".aoe2campaign"})

_MAX_SCENARIO_ROWS = 4096
_MAX_DE2_DEPS = 10_000


def _decode_text(raw: bytes) -> str:
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        try:
            return raw.decode("cp1252")
        except UnicodeDecodeError:
            return raw.decode("latin-1", errors="replace")


def _cstr_from_fixed(raw: bytes) -> str:
    end = raw.find(b"\x00")
    if end >= 0:
        raw = raw[:end]
    return _decode_text(raw).strip()


def _basename_only(name: str) -> str:
    s = (name or "").replace("\\", "/").strip()
    if "/" in s:
        s = s.rsplit("/", 1)[-1]
    return s or "scenario"


class _Reader:
    __slots__ = ("_mv", "_n", "_p")

    def __init__(self, data: bytes | memoryview):
        self._mv = memoryview(data) if isinstance(data, bytes) else data
        self._n = len(self._mv)
        self._p = 0

    def tell(self) -> int:
        return self._p

    def _need(self, k: int) -> None:
        if self._p + k > self._n:
            raise ValueError("Unexpected end of campaign file")

    def read(self, k: int) -> bytes:
        self._need(k)
        out = self._mv[self._p : self._p + k].tobytes()
        self._p += k
        return out

    def u8(self) -> int:
        self._need(1)
        b = int(self._mv[self._p])
        self._p += 1
        return b

    def i32(self) -> int:
        self._need(4)
        v = struct.unpack_from("<i", self._mv, self._p)[0]
        self._p += 4
        return v

    def u16(self) -> int:
        self._need(2)
        v = struct.unpack_from("<H", self._mv, self._p)[0]
        self._p += 2
        return v

    def expect_string_id(self) -> None:
        sid = self.u16()
        if sid != RGE_STRING_ID:
            raise ValueError(
                f"Invalid DE string id 0x{sid:04X} (expected 0x{RGE_STRING_ID:04X})"
            )


def _validate_slice(n: int, offset: int, size: int) -> None:
    if size < 0 or offset < 0:
        raise ValueError("Invalid scenario offset or size in campaign index")
    if offset > n or size > n - offset:
        raise ValueError("Scenario slice out of range for campaign file")


def parse_campaign_index(data: bytes) -> tuple[str, list[dict[str, Any]]]:
    """Parse campaign header and scenario index table.

    Returns ``(campaign_name, scenarios)`` where each scenario dict has:
    ``index``, ``offset``, ``size``, ``file_name`` (basename), ``label`` (UI).
    """
    if not data or len(data) < 4:
        raise ValueError("Campaign file is empty or too small")

    r = _Reader(data)
    version = r.i32()

    if version == RGE_CAMPAIGN_VERSION_DE1:
        raise ValueError(
            "DE1 / .aoecpn campaigns are not supported; use a .cpn, .cpx, or .aoe2campaign file"
        )

    if version == RGE_CAMPAIGN_VERSION:
        name_raw = r.read(RGE_MAX_CHAR)  # name_len + 1 with name_len = RGE_MAX_CHAR - 1
        campaign_name = _cstr_from_fixed(name_raw)
        r.u8()  # padding
        scenario_num = r.i32()
    elif version == RGE_CAMPAIGN_VERSION_DE2:
        dep_count = r.i32()
        if dep_count < 0 or dep_count > _MAX_DE2_DEPS:
            raise ValueError("Invalid DE2 dependency count in campaign header")
        r.read(dep_count * 4)
        name_raw = r.read(RGE_DE2_MAX_CHAR)  # RGE_DE2_MAX_CHAR - 1 + 1
        campaign_name = _cstr_from_fixed(name_raw)
        scenario_num = r.i32()
    else:
        raise ValueError(
            f"Not a supported RGE campaign (unknown version 0x{version & 0xFFFFFFFF:08X})"
        )

    if scenario_num < 0 or scenario_num > _MAX_SCENARIO_ROWS:
        raise ValueError("Invalid scenario count in campaign header")

    n = len(data)
    out: list[dict[str, Any]] = []

    for i in range(scenario_num):
        if version == RGE_CAMPAIGN_VERSION:
            size = r.i32()
            offset = r.i32()
            scen_name_raw = r.read(RGE_MAX_CHAR)
            file_name_raw = r.read(RGE_MAX_CHAR)
            r.u8()
            r.u8()
            scen_name = _cstr_from_fixed(scen_name_raw)
            file_name = _cstr_from_fixed(file_name_raw)
        else:  # DE2
            size = r.i32()
            offset = r.i32()
            r.expect_string_id()
            nl = r.u16()
            if nl < 0 or nl > 65535:
                raise ValueError("Invalid scenario name length")
            scen_name_raw = r.read(nl)
            r.expect_string_id()
            fl = r.u16()
            if fl < 0 or fl > 65535:
                raise ValueError("Invalid scenario file name length")
            file_name_raw = r.read(fl)
            scen_name = _decode_text(scen_name_raw).strip("\x00").strip()
            file_name = _decode_text(file_name_raw).strip("\x00").strip()

        _validate_slice(n, offset, size)
        base = _basename_only(file_name)
        label = scen_name if scen_name else base
        out.append(
            {
                "index": i,
                "offset": offset,
                "size": size,
                "file_name": base,
                "label": label,
            }
        )

    return campaign_name, out
