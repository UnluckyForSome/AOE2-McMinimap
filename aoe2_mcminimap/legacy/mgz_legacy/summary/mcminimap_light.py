"""McMinimap-only fast path: header parse + summary helpers, no body scan."""

from __future__ import annotations

import io

import legacy.mgz_legacy as hl_mgz


def profile_ids_for_header(header) -> dict:
    """DE/HD profile ids from header only (same logic as ``FullSummary.get_profile_ids``)."""
    from legacy.mgz_legacy.util import Version  # noqa: PLC0415

    if header.version == Version.DE:
        key = "de"
        field = "profile_id"
    elif header.version == Version.HD and header.save_version >= 12.49:
        key = "hd"
        field = "steam_id"
    else:
        return {}
    return {
        p.player_number: p[field]
        for p in header[key].players
        if p.player_number >= 0 and p[field] > 0
    }


class McMinimapLightSummary:
    """Parse compressed header only; exposes ``get_map`` / ``get_objects`` / ``get_players`` like ``FullSummary``."""

    __slots__ = ("_header", "_cache", "_reference")

    def __init__(self, handle: io.BytesIO):
        self._cache: dict = {
            "map": None,
            "encoding": None,
            "language": None,
            "dataset": None,
        }
        self._reference = None
        self._header = hl_mgz.header.parse_stream(handle)

    def get_map_id(self):
        h = self._header
        if h.hd:
            return h.hd.selected_map_id
        if h.de:
            return h.de.resolved_map_id
        return h.scenario.game_settings.map_id

    def get_dataset(self):
        if not self._cache["dataset"]:
            from legacy.mgz_legacy.summary.dataset import get_dataset_data  # noqa: PLC0415

            self._cache["dataset"] = get_dataset_data(self._header)
        self._reference = self._cache["dataset"][1]
        return self._cache["dataset"][0]

    def get_map(self):
        if self._cache["map"] is not None:
            return self._cache["map"]
        from legacy.mgz_legacy.common.map import get_map_data  # noqa: PLC0415

        h = self._header
        tiles = [(t.terrain_type, t.elevation) for t in h.map_info.tile]
        d0 = self.get_dataset()
        self._cache["map"], self._cache["encoding"], self._cache["language"] = get_map_data(
            self.get_map_id(),
            h.scenario.messages.instructions,
            h.map_info.size_x,
            h.version,
            d0["id"],
            self._reference,
            tiles,
            de_seed=h.lobby.de.map_seed if h.lobby.de else None,
            de_strings=h.de.rms_strings.strings if h.de else [],
        )
        return self._cache["map"]

    def get_encoding(self):
        if not self._cache["encoding"]:
            self.get_map()
        return self._cache["encoding"]

    def get_objects(self):
        from legacy.mgz_legacy.summary.objects import get_objects_data  # noqa: PLC0415

        return get_objects_data(self._header)

    def get_players(self):
        from legacy.mgz_legacy.summary.players import get_players_data  # noqa: PLC0415
        from legacy.mgz_legacy.summary.teams import get_teams_data  # noqa: PLC0415

        h = self._header
        return get_players_data(
            h,
            None,
            get_teams_data(h),
            set(),
            set(),
            profile_ids_for_header(h),
            {},
            self.get_encoding(),
            {},
        )
