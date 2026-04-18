"""
McMinimap: AoE2 minimap renderer from recorded games or scenarios (DE / legacy).

Recorded games (``.mgl``, ``.mgx``, ``.mgz``, ``.aoe2record``):
  1) Vendored happyleaves [aoc-mgz](https://github.com/happyleavesaoc/aoc-mgz) **header-only** path in ``legacy.mgz_legacy.summary.mcminimap_light`` (tiles + initial objects + roster; no body scan).
  2) Happyleaves ``FullSummary`` (construct header + ``fast`` body walk — same as ``legacy.mgz_legacy.summary.Summary`` today).
  3) Pip [mgz-fast](https://github.com/AoEInsights/mgz-fast) ``mgz.fast.header.parse``. See ``requirements.txt``.

Definitive Edition scenarios — AoE2ScenarioParser:
  • .aoe2scenario

Classic scenarios — ``legacy.agescx_legacy`` (AgeScx-derived):
  • Age of Kings (.scn)
  • The Conquerors (.scx)
"""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
import argparse
import io
import json
import math
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Literal

PACKAGE_DIR = Path(__file__).resolve().parent
DATA_DIR = PACKAGE_DIR / "data"
AOC_DATASET_100_PATH = DATA_DIR / "aoc_dataset_100.json"
AOC_CONSTANTS_PATH = DATA_DIR / "aoc_constants.json"
MCMINIMAP_CONSTANTS_PATH = DATA_DIR / "mcminimap_constants.json"
AOC_DATASET_100_URL = (
    "https://raw.githubusercontent.com/SiegeEngineers/aoc-reference-data/master/data/datasets/100.json"
)
AOC_CONSTANTS_URL = (
    "https://raw.githubusercontent.com/SiegeEngineers/aoc-reference-data/master/data/constants.json"
)

_UPDATE_HINT = "Run: py McMinimap.py --updateconstants"


def _require_local_data_json() -> None:
    missing = [
        p
        for p in (AOC_DATASET_100_PATH, AOC_CONSTANTS_PATH, MCMINIMAP_CONSTANTS_PATH)
        if not p.is_file()
    ]
    if missing:
        lines = "\n".join(f"  - {p}" for p in missing)
        raise RuntimeError(
            f"Missing required local JSON data file(s):\n{lines}\n\n{_UPDATE_HINT}"
        )


if "--updateconstants" not in sys.argv:
    _require_local_data_json()

from PIL import Image, ImageDraw

DEFAULT_EMBLEMS_DIR = PACKAGE_DIR / "emblems"


def _load_mcminimap_tables():
    """Load terrain colors and object ID sets from ``data/mcminimap_constants.json``.

    Includes ``town_center_position_object_ids`` (TC location in header adapters) and
    ``town_center_objects`` (skip as generic player-object squares).
    """
    with open(MCMINIMAP_CONSTANTS_PATH, encoding="utf-8") as f:
        raw = json.load(f)

    def _int_key_str_dict(d):
        return {int(k): str(v) for k, v in d.items()}

    def _int_key_tile_dict(d):
        return {int(k): dict(v) for k, v in d.items()}

    tc_pos = raw["town_center_position_object_ids"]
    tc_pos_tuple = tuple(int(x) for x in tc_pos)
    town_center_skip = frozenset(int(k) for k in raw["town_center_objects"])
    return (
        tuple(raw["player_colors"]),
        _int_key_tile_dict(raw["tiles_colors"]),
        _int_key_str_dict(raw["wall_objects"]),
        _int_key_str_dict(raw["food_objects"]),
        _int_key_str_dict(raw["stone_objects"]),
        _int_key_str_dict(raw["gold_objects"]),
        _int_key_str_dict(raw["relic_objects"]),
        _int_key_str_dict(raw["cliff_objects"]),
        tc_pos_tuple,
        town_center_skip,
    )


def _resolve_emblems_dir(configured: Path | str | None) -> Path:
    if configured is None:
        return DEFAULT_EMBLEMS_DIR
    return Path(configured).expanduser().resolve()


# ---------------------------------------------------------------------------
# File-type routing (keep in sync with README "Input file support")
# ---------------------------------------------------------------------------

RECORDED_GAME_EXTENSIONS = frozenset({".mgl", ".mgx", ".mgz", ".aoe2record"})
# Parser order: happyleaves header-only → ``FullSummary`` → AoEInsights ``mgz.fast.header.parse``.
DEFINITIVE_SCENARIO_EXTENSIONS = frozenset({".aoe2scenario"})
LEGACY_SCENARIO_EXTENSIONS = frozenset({".scn", ".scx"})

_ALL_SUPPORTED_EXTENSIONS = (
    RECORDED_GAME_EXTENSIONS | DEFINITIVE_SCENARIO_EXTENSIONS | LEGACY_SCENARIO_EXTENSIONS
)
_SUPPORTED_INPUT_SUFFIXES = frozenset(ext.lower() for ext in _ALL_SUPPORTED_EXTENSIONS)


def _cli_collect_batch_jobs(input_dir: Path, output_dir: Path) -> list[tuple[Path, Path]]:
    """Pair each supported file under input_dir with a mirrored .png path under output_dir."""
    jobs: list[tuple[Path, Path]] = []
    for path in sorted(input_dir.rglob("*")):
        if not path.is_file():
            continue
        if path.suffix.lower() not in _SUPPORTED_INPUT_SUFFIXES:
            continue
        rel = path.relative_to(input_dir)
        jobs.append((path, output_dir / rel.with_suffix(".png")))
    return jobs


# ---------------------------------------------------------------------------
# Reference data (civilization names for recorded-game headers)
# ---------------------------------------------------------------------------

_aoc_dataset_100 = None
_aoc_constants = None


def _load_aoc_reference_data():
    """Load SiegeEngineers aoc-reference-data from local data/*.json (no network)."""
    global _aoc_dataset_100, _aoc_constants
    if _aoc_dataset_100 is not None:
        return _aoc_dataset_100, _aoc_constants

    try:
        with open(AOC_DATASET_100_PATH, encoding="utf-8") as f:
            _aoc_dataset_100 = json.load(f)
        with open(AOC_CONSTANTS_PATH, encoding="utf-8") as f:
            _aoc_constants = json.load(f)
    except OSError as e:
        raise RuntimeError(
            f"Could not read AoE reference JSON ({e}).\n{_UPDATE_HINT}"
        ) from e

    return _aoc_dataset_100, _aoc_constants


def update_aoc_reference_cache() -> None:
    """Download aoc_dataset_100.json and aoc_constants.json from SiegeEngineers aoc-reference-data."""
    import urllib.request

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    for url, path in (
        (AOC_DATASET_100_URL, AOC_DATASET_100_PATH),
        (AOC_CONSTANTS_URL, AOC_CONSTANTS_PATH),
    ):
        print(f"Fetching {url} ...")
        with urllib.request.urlopen(url, timeout=120) as r:
            path.write_bytes(r.read())
        print(f"Wrote {path} ({path.stat().st_size} bytes)")

    if not MCMINIMAP_CONSTANTS_PATH.is_file():
        raise RuntimeError(
            f"After download, {MCMINIMAP_CONSTANTS_PATH} is still missing. "
            "That file is project data (not downloaded); restore it from the repository."
        )

    global _aoc_dataset_100, _aoc_constants
    _aoc_dataset_100 = None
    _aoc_constants = None


def _civ_name_from_id(civilization_id):
    if civilization_id is None:
        return "Unknown"
    dataset, _ = _load_aoc_reference_data()
    civs = dataset.get("civilizations", {})
    entry = civs.get(str(civilization_id))
    return entry.get("name", "Unknown") if isinstance(entry, dict) else "Unknown"


(
    player_colors,
    tiles_colors,
    wall_objects,
    food_objects,
    stone_objects,
    gold_objects,
    relic_objects,
    cliff_objects,
    TC_IDS,
    TOWN_CENTER_OBJECT_IDS,
) = _load_mcminimap_tables()


@contextmanager
def _suppress_aoe2scenario_parser_output():
    try:
        import AoE2ScenarioParser.helper.printers as printers  # type: ignore
    except Exception:
        printers = None

    try:
        if hasattr(sys.stdout, "reconfigure"):
            sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

    if printers is None:
        yield
        return

    old_rprint = getattr(printers, "rprint", None)
    old_s_print = getattr(printers, "s_print", None)

    def _noop(*_args, **_kwargs):
        return None

    try:
        printers.rprint = _noop  # type: ignore
        printers.s_print = _noop  # type: ignore
        yield
    finally:
        if old_rprint is not None:
            printers.rprint = old_rprint  # type: ignore
        if old_s_print is not None:
            printers.s_print = old_s_print  # type: ignore


# ---------------------------------------------------------------------------
# Loaders → common match shape: .map, .players, .gaia
# ---------------------------------------------------------------------------


def _adapter_from_scenario(input_file: str):
    """Definitive Edition .aoe2scenario via AoE2ScenarioParser."""
    from AoE2ScenarioParser.scenarios.aoe2_de_scenario import AoE2DEScenario  # type: ignore

    with _suppress_aoe2scenario_parser_output():
        scn = AoE2DEScenario.from_file(input_file)

    mm = scn.map_manager
    dim = int(mm.map_width)

    tiles = [
        SimpleNamespace(
            position=SimpleNamespace(x=int(t.x), y=int(t.y)),
            terrain=int(t.terrain_id),
            elevation=int(t.elevation),
        )
        for t in mm.terrain
    ]
    map_obj = SimpleNamespace(dimension=dim, tiles=tiles)

    um = scn.unit_manager
    pm = scn.player_manager

    gaia = []
    player_units = {pid: [] for pid in range(1, 9)}

    for u in um.get_all_units():
        obj_id = int(u.unit_const)
        x, y = int(u.x), int(u.y)
        unit_ns = SimpleNamespace(
            object_id=obj_id,
            class_id=80 if obj_id in wall_objects else 0,
            position=SimpleNamespace(x=x, y=y),
        )
        if int(u.player) == 0:
            gaia.append(SimpleNamespace(object_id=obj_id, position=SimpleNamespace(x=x, y=y)))
        else:
            pid = int(u.player)
            if pid in player_units:
                player_units[pid].append(unit_ns)

    players = []
    for pid in range(1, 9):
        civ_name = "Unknown"
        try:
            p = pm.players[pid]
            civ = getattr(p, "civilization", None)
            if civ is not None and hasattr(civ, "name"):
                civ_name = str(civ.name).replace("_", " ").title()
        except Exception:
            pass

        players.append(
            SimpleNamespace(
                color_id=min(max(0, pid - 1), 7),
                objects=player_units[pid],
                position=SimpleNamespace(x=None, y=None),
                civilization=civ_name,
            )
        )

    return SimpleNamespace(map=map_obj, players=players, gaia=gaia)


def _adapter_from_agescx(input_file: str):
    """Classic .scn / .scx via ``legacy.agescx_legacy``."""
    from legacy.agescx_legacy import Scenario

    scn = Scenario(input_file)

    width = int(scn.tiles.width)
    height = int(scn.tiles.height)
    if width != height:
        raise ValueError(f"AgeScx scenario map is not square: {width}x{height}")
    dim = width

    tiles = []
    for y in range(height):
        for x in range(width):
            t = scn.tiles[y][x]
            tiles.append(
                SimpleNamespace(
                    position=SimpleNamespace(x=int(t.x), y=int(t.y)),
                    terrain=int(t.type),
                    elevation=int(t.elevation),
                )
            )
    map_obj = SimpleNamespace(dimension=dim, tiles=tiles)

    gaia = []
    player_units = {pid: [] for pid in range(1, 9)}

    for owner in range(0, 9):
        try:
            units = scn.units[owner]
        except Exception:
            continue

        for u in units:
            obj_id = int(u.type)
            x, y = int(u.x), int(u.y)

            if owner == 0:
                gaia.append(SimpleNamespace(object_id=obj_id, position=SimpleNamespace(x=x, y=y)))
                continue

            unit_ns = SimpleNamespace(
                object_id=obj_id,
                class_id=80 if obj_id in wall_objects else 0,
                position=SimpleNamespace(x=x, y=y),
            )
            if owner in player_units:
                player_units[owner].append(unit_ns)

    players = []
    for pid in range(1, 9):
        players.append(
            SimpleNamespace(
                color_id=min(max(0, pid - 1), 7),
                objects=player_units[pid],
                position=SimpleNamespace(x=None, y=None),
                civilization="Unknown",
            )
        )

    return SimpleNamespace(map=map_obj, players=players, gaia=gaia)


def _adapter_from_aoc_mgz_summary(s) -> SimpleNamespace:
    """Match shape from happyleaves [aoc-mgz](https://github.com/happyleavesaoc/aoc-mgz) Summary."""
    m = s.get_map()
    dim = int(m["dimension"])
    tiles = [
        SimpleNamespace(
            position=SimpleNamespace(x=int(t["x"]), y=int(t["y"])),
            terrain=int(t["terrain_id"]),
            elevation=int(t["elevation"]),
        )
        for t in m["tiles"]
    ]
    map_obj = SimpleNamespace(dimension=dim, tiles=tiles)

    od = s.get_objects()
    gaia = []
    player_units = {pid: [] for pid in range(1, 9)}
    for o in od["objects"]:
        oid = o.get("object_id")
        if oid is None:
            continue
        cid = o.get("class_id")
        if cid is None:
            cid = 80 if oid in wall_objects else 0
        x, y = int(o["x"]), int(o["y"])
        pn = o.get("player_number")
        if pn is None or pn == 0:
            gaia.append(SimpleNamespace(object_id=oid, position=SimpleNamespace(x=x, y=y)))
            continue
        pid = int(pn)
        if pid not in player_units:
            continue
        player_units[pid].append(
            SimpleNamespace(
                object_id=oid,
                class_id=cid,
                position=SimpleNamespace(x=x, y=y),
            )
        )

    players = []
    for pdata in sorted(s.get_players(), key=lambda r: r.get("number", 0)):
        num = int(pdata["number"])
        if num < 1 or num > 8:
            continue
        civ_raw = pdata.get("civilization")
        if isinstance(civ_raw, int):
            civ_name = _civ_name_from_id(civ_raw)
        elif civ_raw is not None:
            civ_name = str(civ_raw)
        else:
            civ_name = "Unknown"
        pos = pdata.get("position")
        pos_x, pos_y = None, None
        if pos and isinstance(pos, (list, tuple)) and len(pos) >= 2:
            pos_x, pos_y = pos[0], pos[1]
        raw_color = pdata.get("color_id", 0)
        color_id = min(max(0, int(raw_color) if raw_color is not None else 0), 7)
        players.append(
            SimpleNamespace(
                color_id=color_id,
                objects=player_units.get(num, []),
                position=SimpleNamespace(x=pos_x, y=pos_y),
                civilization=civ_name,
            )
        )

    return SimpleNamespace(map=map_obj, players=players, gaia=gaia)


def _adapter_from_mgz_fast_header(header: dict):
    """Match shape from AoEInsights mgz-fast: ``mgz.fast.header.parse`` header dict (fallback path)."""
    m = header["map"]
    dim = m["dimension"]
    raw_tiles = m["tiles"]

    tiles = []
    for i in range(len(raw_tiles)):
        t = raw_tiles[i]
        if isinstance(t, (list, tuple)):
            terrain, elevation = t[0], t[1]
        elif isinstance(t, dict):
            terrain = t.get("terrain_id", t.get("terrain", 0))
            elevation = t.get("elevation", 0)
        else:
            terrain = getattr(t, "terrain", getattr(t, "terrain_id", 0))
            elevation = getattr(t, "elevation", 0)
        x = i % dim
        y = i // dim
        tiles.append(
            SimpleNamespace(
                position=SimpleNamespace(x=x, y=y),
                terrain=terrain,
                elevation=elevation,
            )
        )
    map_obj = SimpleNamespace(dimension=dim, tiles=tiles)

    gaia = []
    for o in header["players"][0].get("objects", []):
        pos = o.get("position", {})
        gaia.append(
            SimpleNamespace(
                object_id=o.get("object_id"),
                position=SimpleNamespace(x=pos.get("x", 0), y=pos.get("y", 0)),
            )
        )

    de_players_by_number = {}
    if header.get("de") and header["de"].get("players"):
        de_players_by_number = {p["number"]: p for p in header["de"]["players"]}

    players = []
    for p in header["players"][1:]:
        de_p = de_players_by_number.get(p.get("number")) or {}
        pos_x, pos_y = None, None
        for o in p.get("objects", []):
            if o.get("object_id") in TC_IDS:
                pos = o.get("position", {})
                pos_x, pos_y = pos.get("x"), pos.get("y")
                break
        objs = [
            SimpleNamespace(
                object_id=o.get("object_id"),
                class_id=o.get("class_id"),
                position=SimpleNamespace(
                    x=o.get("position", {}).get("x", 0), y=o.get("position", {}).get("y", 0)
                ),
            )
            for o in p.get("objects", [])
        ]
        civ_id = de_p.get("civilization_id") if de_p else p.get("civilization_id", 0)
        raw_color_id = de_p.get("color_id") if de_p else p.get("color_id", 0)
        color_id = min(max(0, int(raw_color_id) if raw_color_id is not None else 0), 7)
        players.append(
            SimpleNamespace(
                color_id=color_id,
                objects=objs,
                position=SimpleNamespace(x=pos_x, y=pos_y),
                civilization=_civ_name_from_id(civ_id),
            )
        )

    return SimpleNamespace(map=map_obj, players=players, gaia=gaia)


def get_mgz(input_file: str):
    """Load a recorded game: happyleaves header-only → FullSummary → AoEInsights mgz-fast."""
    with open(input_file, "rb") as fh:
        raw = fh.read()

    tried: list[str] = []

    try:
        from legacy.mgz_legacy.summary.mcminimap_light import McMinimapLightSummary  # noqa: PLC0415

        return _adapter_from_aoc_mgz_summary(McMinimapLightSummary(io.BytesIO(raw)))
    except BaseException as e:  # noqa: BLE001 — any failure tries slower paths
        tried.append(f"happyleaves header-only: {e!s}")

    try:
        from legacy.mgz_legacy.summary import Summary  # type: ignore  # noqa: PLC0415
    except ImportError as e:
        tried.append(f"happyleaves Summary import: {e!s}")
    else:
        try:
            return _adapter_from_aoc_mgz_summary(Summary(io.BytesIO(raw)))
        except BaseException as e:  # noqa: BLE001
            tried.append(f"happyleaves FullSummary: {e!s}")

    try:
        from mgz.fast.header import parse as _parse  # type: ignore  # noqa: PLC0415
    except ImportError as e:
        raise RuntimeError(
            "Recorded games need vendored ``legacy.mgz_legacy`` and, when that fails, "
            "AoEInsights ``mgz-fast`` (``mgz.fast.header.parse``). "
            "Install: ``pip install -r requirements.txt``. "
            "See https://github.com/happyleavesaoc/aoc-mgz and https://github.com/AoEInsights/mgz-fast"
        ) from e
    try:
        return _adapter_from_mgz_fast_header(_parse(io.BytesIO(raw)))
    except BaseException as e2:  # noqa: BLE001
        detail = "; ".join(tried)
        raise RuntimeError(
            f"Could not parse recording: mgz-fast fallback failed ({e2!s}). Tried: {detail}"
        ) from e2


def read_map(input_file: str):
    """Load map/player data. Raises ValueError for unknown extensions."""
    suffix = Path(input_file).suffix.lower()
    if not suffix:
        raise ValueError(
            f"No file extension: {input_file!r}. "
            f"Supported: {', '.join(sorted(_ALL_SUPPORTED_EXTENSIONS))}"
        )
    if suffix in DEFINITIVE_SCENARIO_EXTENSIONS:
        return _adapter_from_scenario(input_file)
    if suffix in LEGACY_SCENARIO_EXTENSIONS:
        return _adapter_from_agescx(input_file)
    if suffix in RECORDED_GAME_EXTENSIONS:
        return get_mgz(input_file)
    raise ValueError(
        f"Unsupported file type {suffix!r} for {input_file!r}. "
        f"Supported extensions: {', '.join(sorted(_ALL_SUPPORTED_EXTENSIONS))}"
    )


# ---------------------------------------------------------------------------
# User-tunable rendering globals
# ---------------------------------------------------------------------------

object_mode = "square"
town_center = "pixel"
_render_emblems_dir: Path | str | None = None
angle = 45
multiplier_integer = 9
orthographic_ratio = 2
border_spacing = 4

draw_cliffs = True
draw_walls = True
smooth_walls = True

draw_players = True
draw_gaia = True
draw_food = True
draw_gold = True
draw_stone = True
draw_relics = True

cliff_size = 1
player_wall_size = 1
relic_size = 4
stone_size = 4
gold_size = 4
food_size = 4
player_object_size = 4
town_center_size = 4
# Extra radius (px, post-enlarge canvas) around pasted civ PNGs in emblem mode.
civ_emblem_halo = 40

ObjectMode = Literal["square", "rotated"]
TownCenterMode = Literal["none", "pixel", "emblem"]


@dataclass(frozen=True)
class MinimapSettings:
    object_mode: ObjectMode = "square"
    town_center: TownCenterMode = "pixel"
    angle: int = 45
    multiplier_integer: int = 9
    orthographic_ratio: int = 2
    border_spacing: int = 4

    draw_players: bool = True
    draw_gaia: bool = True
    draw_food: bool = True
    draw_gold: bool = True
    draw_stone: bool = True
    draw_relics: bool = True
    draw_cliffs: bool = True
    draw_walls: bool = True
    smooth_walls: bool = True
    emblems_dir: Path | str | None = None


@contextmanager
def _apply_settings(settings: MinimapSettings):
    global object_mode
    global town_center
    global angle
    global multiplier_integer
    global orthographic_ratio
    global border_spacing
    global draw_players
    global draw_gaia
    global draw_food
    global draw_gold
    global draw_stone
    global draw_relics
    global draw_cliffs
    global draw_walls
    global smooth_walls
    global _render_emblems_dir

    old = (
        object_mode,
        town_center,
        angle,
        multiplier_integer,
        orthographic_ratio,
        border_spacing,
        draw_players,
        draw_gaia,
        draw_food,
        draw_gold,
        draw_stone,
        draw_relics,
        draw_cliffs,
        draw_walls,
        smooth_walls,
        _render_emblems_dir,
    )
    try:
        object_mode = settings.object_mode
        town_center = settings.town_center
        angle = int(settings.angle)
        multiplier_integer = int(settings.multiplier_integer)
        orthographic_ratio = int(settings.orthographic_ratio)
        border_spacing = int(settings.border_spacing)
        draw_players = bool(settings.draw_players)
        draw_gaia = bool(settings.draw_gaia)
        draw_food = bool(settings.draw_food)
        draw_gold = bool(settings.draw_gold)
        draw_stone = bool(settings.draw_stone)
        draw_relics = bool(settings.draw_relics)
        draw_cliffs = bool(settings.draw_cliffs)
        draw_walls = bool(settings.draw_walls)
        smooth_walls = bool(settings.smooth_walls)
        _render_emblems_dir = settings.emblems_dir
        yield
    finally:
        (
            object_mode,
            town_center,
            angle,
            multiplier_integer,
            orthographic_ratio,
            border_spacing,
            draw_players,
            draw_gaia,
            draw_food,
            draw_gold,
            draw_stone,
            draw_relics,
            draw_cliffs,
            draw_walls,
            smooth_walls,
            _render_emblems_dir,
        ) = old


# ---------------------------------------------------------------------------
# Geometry helpers
# ---------------------------------------------------------------------------


def rotate_coordinates(
    pixel_coordinates_x,
    pixel_coordinates_y,
    original_map_dimension,
    new_canvas_dimension,
    performed_after_enlargement,
):
    mi = multiplier_integer
    x_centered = pixel_coordinates_x - (original_map_dimension / 2)
    y_centered = pixel_coordinates_y - (original_map_dimension / 2)
    x_transformed = x_centered * math.cos(math.radians(-angle)) - y_centered * math.sin(
        math.radians(-angle)
    )
    y_transformed = x_centered * math.sin(math.radians(-angle)) + y_centered * math.cos(
        math.radians(-angle)
    )
    x_transformed += new_canvas_dimension / 2
    y_transformed += new_canvas_dimension / 2
    if performed_after_enlargement is False:
        mi = 1
    x_transformed = x_transformed * mi + (new_canvas_dimension - new_canvas_dimension * mi) / 2
    y_transformed = y_transformed * mi + (new_canvas_dimension - new_canvas_dimension * mi) / 2
    return math.floor(x_transformed), math.floor(y_transformed)


def to_rgb(farbe: str) -> tuple[int, int, int]:
    return tuple(int(farbe[i : i + 2], 16) for i in (0, 2, 4))


def _object_canvas_xy(tile_x, tile_y, original_map_dimension, canvas, after_rotation):
    if after_rotation:
        coords = rotate_coordinates(
            tile_x,
            tile_y,
            original_map_dimension,
            canvas.height * orthographic_ratio,
            performed_after_enlargement=True,
        )
        return coords[0], coords[1] / orthographic_ratio
    mi = multiplier_integer
    yooo = border_spacing * mi
    return tile_x * mi + yooo, tile_y * mi + yooo


def _draw_square_marker(draw, cx, cy, size_addon, fill):
    offset = 1 if multiplier_integer % 2 == 0 else 0
    half = math.floor(multiplier_integer / 2) + size_addon
    draw.rectangle(
        [cx - half, cy - half, cx + (half - offset), cy + (half - offset)],
        fill=fill,
    )


# ---------------------------------------------------------------------------
# Render plan: layers derived from settings (same for all input types)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class _RenderPlan:
    draw_player_objects_layer: bool
    player_object_size_addon: int
    draw_tc_pixel_markers: bool
    draw_civ_emblems: bool


def _build_render_plan() -> _RenderPlan:
    return _RenderPlan(
        draw_player_objects_layer=draw_players,
        player_object_size_addon=player_object_size,
        draw_tc_pixel_markers=town_center == "pixel",
        draw_civ_emblems=town_center == "emblem",
    )


# ---------------------------------------------------------------------------
# Drawing
# ---------------------------------------------------------------------------


def draw_terrain_straight(canvas, map_obj):
    default_terrain_color = {"normal": "#339727", "shady": "#008d00", "sunny": "#00a900"}
    unknown_terrain_ids: set = set()
    dim = map_obj.dimension
    tiles = map_obj.tiles
    bs = border_spacing
    px = canvas.load()
    d1 = dim + bs - 1

    for i in range(dim * dim):
        t = tiles[i]
        x = t.position.x + bs
        y = t.position.y + bs
        terrain = t.terrain

        if terrain not in tiles_colors:
            if terrain not in unknown_terrain_ids:
                unknown_terrain_ids.add(terrain)
                print(
                    f"Warning: Terrain ID {terrain} not found in tiles_colors dictionary. Using default color."
                )
            terrain_color = default_terrain_color
        else:
            terrain_color = tiles_colors[terrain]

        r, g, b = to_rgb(terrain_color["normal"][1:])
        px[x, y] = (r, g, b, 255)

        if x < d1 and y < d1:
            br = tiles[i + dim + 1]
            if br.elevation < t.elevation:
                r, g, b = to_rgb(terrain_color["sunny"][1:])
                px[x, y] = (r, g, b, 255)
            elif br.elevation > t.elevation:
                r, g, b = to_rgb(terrain_color["shady"][1:])
                px[x, y] = (r, g, b, 255)


def draw_permenant_objects(canvas, gaia, players):
    draw = ImageDraw.Draw(canvas)

    if draw_cliffs:
        bs = border_spacing
        for unit in gaia:
            if unit.object_id in cliff_objects:
                cx = unit.position.x + bs
                cy = unit.position.y + bs
                s = cliff_size
                draw.rectangle([cx - s, cy - s, cx + s, cy + s], fill="#714b33")

    if draw_walls and smooth_walls:
        bs = border_spacing
        s = player_wall_size
        for player in players:
            col = to_rgb(player_colors[player.color_id][1:])
            for unit in player.objects:
                if unit.object_id in wall_objects:
                    cx = unit.position.x + bs
                    cy = unit.position.y + bs
                    draw.rectangle([cx - s, cy - s, cx + s, cy + s], fill=col)


def draw_gaia_objects_common(canvas, gaia, original_map_dimension, after_rotation):
    if not draw_gaia:
        return
    draw = ImageDraw.Draw(canvas)
    rules = []
    if draw_food:
        rules.append((food_objects, "#A5C46C", food_size))
    if draw_stone:
        rules.append((stone_objects, "#919191", stone_size))
    if draw_gold:
        rules.append((gold_objects, "#FFC700", gold_size))
    if draw_relics:
        rules.append((relic_objects, "#FFFFFF", relic_size))
    if not rules:
        return

    for unit in gaia:
        oid = unit.object_id
        for id_set, color, size_addon in rules:
            if oid in id_set:
                cx, cy = _object_canvas_xy(
                    unit.position.x, unit.position.y, original_map_dimension, canvas, after_rotation
                )
                _draw_square_marker(draw, cx, cy, size_addon, color)
                break


def draw_player_objects_common(
    canvas, players, original_map_dimension, after_rotation, player_object_size_addon: int
):
    draw = ImageDraw.Draw(canvas)

    for player in players:
        col = to_rgb(player_colors[player.color_id][1:])
        for unit in player.objects:
            if unit.object_id in TOWN_CENTER_OBJECT_IDS:
                continue
            if getattr(unit, "class_id", None) != 80 or unit.object_id not in wall_objects:
                cx, cy = _object_canvas_xy(
                    unit.position.x, unit.position.y, original_map_dimension, canvas, after_rotation
                )
                _draw_square_marker(draw, cx, cy, player_object_size_addon, col)


def draw_player_walls_common(canvas, players, original_map_dimension, after_rotation):
    draw = ImageDraw.Draw(canvas)

    for player in players:
        col = to_rgb(player_colors[player.color_id][1:])
        for unit in player.objects:
            if unit.object_id in wall_objects:
                cx, cy = _object_canvas_xy(
                    unit.position.x, unit.position.y, original_map_dimension, canvas, after_rotation
                )
                _draw_square_marker(draw, cx, cy, player_wall_size, col)


def draw_player_tcs(canvas, players, original_map_dimension, after_rotation):
    draw = ImageDraw.Draw(canvas)

    for player in players:
        if player.position.x is None or player.position.y is None:
            continue
        col = to_rgb(player_colors[player.color_id][1:])
        cx, cy = _object_canvas_xy(
            player.position.x, player.position.y, original_map_dimension, canvas, after_rotation
        )
        _draw_square_marker(draw, cx, cy, town_center_size, col)


def create_border_canvas(original_map_dimension):
    border_canvas = Image.new("RGBA", (original_map_dimension, original_map_dimension))
    draw = ImageDraw.Draw(border_canvas)
    w, h = border_canvas.width - 1, border_canvas.height - 1
    draw.rectangle([(0, 0), (w, h)], outline="rgb(0, 0, 0)", width=1)
    draw.rectangle([(1, 1), (w - 1, h - 1)], outline="rgb(157, 135, 114)", width=1)
    draw.rectangle([(2, 2), (w - 2, h - 2)], outline="rgb(215, 182, 151)", width=1)
    draw.rectangle([(3, 3), (w - 3, h - 3)], outline="rgb(31, 31, 31)", width=1)

    edge = (original_map_dimension + border_spacing * 2) * multiplier_integer
    border_canvas = border_canvas.resize(
        (edge, edge),
        resample=Image.Resampling.NEAREST,
    )
    border_canvas = border_canvas.rotate(angle, resample=Image.Resampling.BILINEAR, expand=True)
    border_canvas = border_canvas.resize(
        (border_canvas.size[0], border_canvas.size[1] // orthographic_ratio),
        resample=Image.Resampling.LANCZOS,
    )
    return border_canvas


def new_canvas(original_map_dimension):
    return Image.new(
        "RGBA",
        (original_map_dimension + 2 * border_spacing, original_map_dimension + 2 * border_spacing),
    )


def create_transparency_mask(canvas):
    return canvas.getchannel("A").point(lambda p: 255 if p == 0 else 0)


def save_minimap(
    input_file: str,
    *,
    output_path: str | None = None,
    verbose: bool = False,
    final_size: tuple[int, int] = (1630, 815),
):
    """Render a minimap from a recording or scenario. If ``output_path`` is set, write PNG there; always returns the PIL image."""
    if verbose:
        print(f"Input file: {input_file}")
    match = read_map(input_file)
    map_obj = match.map
    players = match.players
    gaia = match.gaia
    original_map_dimension = map_obj.dimension

    plan = _build_render_plan()

    canvas = new_canvas(original_map_dimension)
    draw_terrain_straight(canvas, map_obj)
    draw_permenant_objects(canvas, gaia, players)

    canvas = canvas.resize(
        (
            (original_map_dimension + border_spacing * 2) * multiplier_integer,
            (original_map_dimension + border_spacing * 2) * multiplier_integer,
        ),
        resample=Image.Resampling.NEAREST,
    )

    if object_mode == "rotated":
        draw_gaia_objects_common(canvas, gaia, original_map_dimension, after_rotation=False)

        if plan.draw_player_objects_layer:
            draw_player_objects_common(
                canvas,
                players,
                original_map_dimension,
                after_rotation=False,
                player_object_size_addon=plan.player_object_size_addon,
            )

        if draw_walls and not smooth_walls:
            draw_player_walls_common(canvas, players, original_map_dimension, after_rotation=False)

        if plan.draw_tc_pixel_markers:
            draw_player_tcs(canvas, players, original_map_dimension, after_rotation=False)

        canvas = canvas.rotate(angle, resample=Image.Resampling.BILINEAR, expand=True)
        canvas = canvas.resize(
            (canvas.size[0], canvas.size[1] // orthographic_ratio),
            resample=Image.Resampling.LANCZOS,
        )

    if object_mode == "square":
        canvas = canvas.rotate(angle, resample=Image.Resampling.BILINEAR, expand=True)
        canvas = canvas.resize(
            (canvas.size[0], canvas.size[1] // orthographic_ratio),
            resample=Image.Resampling.LANCZOS,
        )

        original_canvas = canvas.copy()
        transparency_mask = create_transparency_mask(original_canvas)

        draw_gaia_objects_common(canvas, gaia, original_map_dimension, after_rotation=True)

        if plan.draw_player_objects_layer:
            draw_player_objects_common(
                canvas,
                players,
                original_map_dimension,
                after_rotation=True,
                player_object_size_addon=plan.player_object_size_addon,
            )

        if draw_walls and not smooth_walls:
            draw_player_walls_common(canvas, players, original_map_dimension, after_rotation=True)

        if plan.draw_tc_pixel_markers:
            draw_player_tcs(canvas, players, original_map_dimension, after_rotation=True)

        canvas.paste(original_canvas, mask=transparency_mask)

    border_canvas = create_border_canvas(original_map_dimension)

    if plan.draw_civ_emblems:
        civ_emblem_canvas = create_civ_icon_canvas(players, original_map_dimension)
        canvas.paste(civ_emblem_canvas, civ_emblem_canvas)

    canvas.paste(border_canvas, border_canvas)

    canvas = canvas.resize(final_size, resample=Image.Resampling.LANCZOS)

    if output_path:
        canvas.save(output_path)

    return canvas


def to_image(input_file: str, *, settings: MinimapSettings | None = None):
    """Render to an in-memory PIL image. Uses ``emblems/`` beside this module unless overridden."""
    s = settings or MinimapSettings()
    with _apply_settings(s):
        return save_minimap(input_file, output_path=None, verbose=False)


def to_png_bytes(input_file: str, *, settings: MinimapSettings | None = None) -> bytes:
    img = to_image(input_file, settings=settings)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def create_civ_icon_canvas(players, original_map_dimension):
    civ_emblem_canvas = new_canvas(original_map_dimension)
    civ_emblem_canvas = civ_emblem_canvas.resize(
        (
            (original_map_dimension + border_spacing * 2) * multiplier_integer,
            (original_map_dimension + border_spacing * 2) * multiplier_integer,
        ),
        resample=Image.Resampling.NEAREST,
    )
    civ_emblem_canvas = civ_emblem_canvas.rotate(
        angle, resample=Image.Resampling.BILINEAR, expand=True
    )

    emblems_root = _resolve_emblems_dir(_render_emblems_dir)
    for player in players:
        if player.position.x is None or player.position.y is None:
            continue
        coords = rotate_coordinates(
            player.position.x,
            player.position.y,
            original_map_dimension,
            civ_emblem_canvas.height,
            performed_after_enlargement=True,
        )

        civ_path = emblems_root / f"{player.civilization}.png"
        if not civ_path.is_file():
            print(
                f"Warning: missing civ emblem {civ_path!s} (town_center=emblem); skipping marker for "
                f"{player.civilization!r}."
            )
            continue
        civ_image = Image.open(civ_path)

        image_width, image_height = civ_image.size
        top_left_coords = (
            math.floor(coords[0] - image_width / 2),
            math.floor(coords[1] - image_height / 2),
        )

        draw = ImageDraw.Draw(civ_emblem_canvas)
        radius = max(image_width, image_height) / 2 + civ_emblem_halo
        center = (
            top_left_coords[0] + image_width / 2,
            top_left_coords[1] + image_height / 2,
        )
        draw.ellipse(
            [
                (center[0] - radius, center[1] - radius),
                (center[0] + radius, center[1] + radius),
            ],
            outline=(0, 0, 0),
            fill=to_rgb(player_colors[player.color_id][1:]),
            width=2,
        )

        civ_emblem_canvas.paste(civ_image, top_left_coords, civ_image)

    civ_emblem_canvas = civ_emblem_canvas.resize(
        (civ_emblem_canvas.size[0], civ_emblem_canvas.size[1] // orthographic_ratio),
        resample=Image.Resampling.LANCZOS,
    )
    return civ_emblem_canvas


__all__ = [
    "MinimapSettings",
    "read_map",
    "to_image",
    "to_png_bytes",
    "save_minimap",
    "update_aoc_reference_cache",
    "RECORDED_GAME_EXTENSIONS",
    "DEFINITIVE_SCENARIO_EXTENSIONS",
    "LEGACY_SCENARIO_EXTENSIONS",
]


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Render an AoE2 minimap from a scenario/recording.")
    parser.add_argument(
        "--updateconstants",
        action="store_true",
        help="Download aoc-reference-data JSON into data/ (no render; no --input).",
    )
    parser.add_argument(
        "--input",
        required=False,
        help="Input file, or a directory (searched recursively for supported extensions).",
    )
    parser.add_argument(
        "--output",
        required=False,
        help="Output PNG file, or when --input is a directory, the output directory (required for directories).",
    )
    parser.add_argument("--object_mode", choices=["square", "rotated"], default="square")
    parser.add_argument(
        "--town-center",
        dest="town_center",
        choices=["none", "pixel", "emblem"],
        default="pixel",
        help="TC marker: none, pixel (default), or emblem (PNG from --emblems-dir or bundled emblems/).",
    )
    parser.add_argument(
        "--emblems-dir",
        type=Path,
        default=None,
        help=f"Directory of civ emblem PNGs (default: {DEFAULT_EMBLEMS_DIR}).",
    )
    parser.add_argument("--angle", type=int, default=45)
    parser.add_argument("--multiplier_integer", type=int, default=9)
    parser.add_argument("--orthographic_ratio", type=int, default=2)
    parser.add_argument("--border_spacing", type=int, default=4)
    parser.add_argument("--draw_cliffs", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--draw_walls", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--smooth-walls", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--draw-gaia", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--draw-players", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--draw-food", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--draw-gold", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--draw-stone", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--draw-relics", action=argparse.BooleanOptionalAction, default=True)
    args = parser.parse_args()

    if args.updateconstants:
        if args.input is not None or args.output is not None:
            parser.error("--updateconstants cannot be used with --input or --output")
        update_aoc_reference_cache()
        sys.exit(0)

    if not args.input:
        parser.error("--input is required (unless using --updateconstants)")

    input_path = Path(args.input).expanduser()
    if not input_path.exists():
        parser.error(f"Input path does not exist: {input_path}")

    settings = MinimapSettings(
        object_mode=args.object_mode,
        town_center=args.town_center,
        angle=args.angle,
        multiplier_integer=args.multiplier_integer,
        orthographic_ratio=args.orthographic_ratio,
        border_spacing=args.border_spacing,
        draw_players=args.draw_players,
        draw_gaia=args.draw_gaia,
        draw_food=args.draw_food,
        draw_gold=args.draw_gold,
        draw_stone=args.draw_stone,
        draw_relics=args.draw_relics,
        draw_cliffs=args.draw_cliffs,
        draw_walls=args.draw_walls,
        smooth_walls=args.smooth_walls,
        emblems_dir=args.emblems_dir,
    )

    with _apply_settings(settings):
        if input_path.is_dir():
            if not args.output:
                parser.error("When --input is a directory, --output must be the destination directory.")
            out_root = Path(args.output).expanduser().resolve()
            if out_root.exists() and not out_root.is_dir():
                parser.error("When --input is a directory, --output must be a directory path.")
            out_root.mkdir(parents=True, exist_ok=True)
            input_root = input_path.resolve()
            jobs = _cli_collect_batch_jobs(input_root, out_root)
            if not jobs:
                print(f"No supported files under {input_root} (extensions: {', '.join(sorted(_SUPPORTED_INPUT_SUFFIXES))}).")
                sys.exit(1)
            print(f"Rendering {len(jobs)} file(s) from {input_root} into {out_root}")
            failures: list[tuple[Path, str]] = []
            ok_count = 0
            for src, dest in jobs:
                dest.parent.mkdir(parents=True, exist_ok=True)
                try:
                    save_minimap(str(src), output_path=str(dest), verbose=True)
                    ok_count += 1
                except Exception as e:
                    err = f"{type(e).__name__}: {e}"
                    failures.append((src, err))
                    print(f"FAILED ({err})")
            print(f"\nBatch finished: {ok_count} succeeded, {len(failures)} failed (of {len(jobs)}).")
            if failures:
                print("Failed files:")
                for path, msg in failures:
                    print(f"  {path}\n    {msg}")
                sys.exit(1)
        else:
            save_minimap(str(input_path), output_path=args.output, verbose=True)
