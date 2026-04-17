"""
McMinimap: AoE2 minimap renderer from recorded games (mgz-fast) or scenarios (DE / legacy).

Recorded games — parsed with mgz-fast:
  • Age of Kings (.mgl)
  • The Conquerors (.mgx)
  • Userpatch 1.4 / 1.5 (.mgz)
  • HD Edition >= 4.6 (.aoe2record)
  • Definitive Edition (.aoe2record)

Definitive Edition scenarios — AoE2ScenarioParser:
  • .aoe2scenario

Classic scenarios — McMinimapLegacy (AgeScx-derived):
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
import urllib.request

from mgz.fast.header import parse
from PIL import Image, ImageDraw

import McMinimapData  # type: ignore

# ---------------------------------------------------------------------------
# File-type routing (keep in sync with README "Input file support")
# ---------------------------------------------------------------------------

RECORDED_GAME_EXTENSIONS = frozenset({".mgl", ".mgx", ".mgz", ".aoe2record"})
DEFINITIVE_SCENARIO_EXTENSIONS = frozenset({".aoe2scenario"})
LEGACY_SCENARIO_EXTENSIONS = frozenset({".scn", ".scx"})

_ALL_SUPPORTED_EXTENSIONS = (
    RECORDED_GAME_EXTENSIONS | DEFINITIVE_SCENARIO_EXTENSIONS | LEGACY_SCENARIO_EXTENSIONS
)
SCENARIO_SOURCE_EXTENSIONS = DEFINITIVE_SCENARIO_EXTENSIONS | LEGACY_SCENARIO_EXTENSIONS


def _is_scenario_source(path: str) -> bool:
    return Path(path).suffix.lower() in SCENARIO_SOURCE_EXTENSIONS


# ---------------------------------------------------------------------------
# Reference data (civilization names for recorded-game headers)
# ---------------------------------------------------------------------------

AOC_DATASET_100_URL = (
    "https://raw.githubusercontent.com/SiegeEngineers/aoc-reference-data/master/data/datasets/100.json"
)
AOC_CONSTANTS_URL = (
    "https://raw.githubusercontent.com/SiegeEngineers/aoc-reference-data/master/data/constants.json"
)

_aoc_dataset_100 = None
_aoc_constants = None


def _load_aoc_reference_data():
    global _aoc_dataset_100, _aoc_constants
    if _aoc_dataset_100 is None:
        try:
            with urllib.request.urlopen(AOC_DATASET_100_URL, timeout=10) as r:
                _aoc_dataset_100 = json.loads(r.read().decode())
        except Exception as e:
            print(f"Warning: could not load aoc-reference dataset 100: {e}")
            _aoc_dataset_100 = {}
    if _aoc_constants is None:
        try:
            with urllib.request.urlopen(AOC_CONSTANTS_URL, timeout=10) as r:
                _aoc_constants = json.loads(r.read().decode())
        except Exception as e:
            print(f"Warning: could not load aoc-reference constants: {e}")
            _aoc_constants = {}
    return _aoc_dataset_100, _aoc_constants


def _civ_name_from_id(civilization_id):
    if civilization_id is None:
        return "Unknown"
    dataset, _ = _load_aoc_reference_data()
    civs = dataset.get("civilizations", {})
    entry = civs.get(str(civilization_id))
    return entry.get("name", "Unknown") if isinstance(entry, dict) else "Unknown"


TC_IDS = (71, 109, 141, 142)

player_colors = McMinimapData.player_colors
tiles_colors = McMinimapData.tiles_colors
wall_objects = McMinimapData.wall_objects
food_objects = McMinimapData.food_objects
stone_objects = McMinimapData.stone_objects
gold_objects = McMinimapData.gold_objects
relic_objects = McMinimapData.relic_objects
cliff_objects = McMinimapData.cliff_objects


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
    """Classic .scn / .scx via McMinimapLegacy."""
    from McMinimapLegacy import Scenario

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


def _adapter_from_header(header: dict):
    """Recorded game header from mgz-fast."""
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
    with open(input_file, "rb") as data:
        return _adapter_from_header(parse(data))


def get_match(input_file: str):
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

module_mode = False
manual_source_file_path = r"C:\Users\joemc\Github\Public\AOE2-McMinimap\input\CBA.scn"
object_mode = "square"
player_tc_marker = "none"
angle = 45
multiplier_integer = 9
orthographic_ratio = 2
border_spacing = 4

draw_cliffs = True
draw_walls = True
rotate_walls_with_canvas = True

draw_player_objects = False
draw_gaia_objects = True

additional_cliff_size = 1
additional_player_wall_size = 1
additional_relic_size = 4
additional_stone_size = 4
additional_gold_size = 4
additional_food_size = 4
additional_player_object_size = 20
additional_scenario_player_object_size = 4
additional_player_tc_size = 40

ObjectMode = Literal["square", "rotated"]
TcMarkerMode = Literal["none", "pixel", "emblem"]


@dataclass(frozen=True)
class RenderSettings:
    object_mode: ObjectMode = "square"
    player_tc_marker: TcMarkerMode = "none"
    angle: int = 45
    multiplier_integer: int = 9
    orthographic_ratio: int = 2
    border_spacing: int = 4

    draw_cliffs: bool = True
    draw_walls: bool = True
    rotate_walls_with_canvas: bool = True
    draw_player_objects: bool = False
    draw_gaia_objects: bool = True


@contextmanager
def _apply_settings(settings: RenderSettings):
    global object_mode
    global player_tc_marker
    global angle
    global multiplier_integer
    global orthographic_ratio
    global border_spacing
    global draw_cliffs
    global draw_walls
    global rotate_walls_with_canvas
    global draw_player_objects
    global draw_gaia_objects

    old = (
        object_mode,
        player_tc_marker,
        angle,
        multiplier_integer,
        orthographic_ratio,
        border_spacing,
        draw_cliffs,
        draw_walls,
        rotate_walls_with_canvas,
        draw_player_objects,
        draw_gaia_objects,
    )
    try:
        object_mode = settings.object_mode
        player_tc_marker = settings.player_tc_marker
        angle = int(settings.angle)
        multiplier_integer = int(settings.multiplier_integer)
        orthographic_ratio = int(settings.orthographic_ratio)
        border_spacing = int(settings.border_spacing)
        draw_cliffs = bool(settings.draw_cliffs)
        draw_walls = bool(settings.draw_walls)
        rotate_walls_with_canvas = bool(settings.rotate_walls_with_canvas)
        draw_player_objects = bool(settings.draw_player_objects)
        draw_gaia_objects = bool(settings.draw_gaia_objects)
        yield
    finally:
        (
            object_mode,
            player_tc_marker,
            angle,
            multiplier_integer,
            orthographic_ratio,
            border_spacing,
            draw_cliffs,
            draw_walls,
            rotate_walls_with_canvas,
            draw_player_objects,
            draw_gaia_objects,
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
# Render plan: recorded vs scenario
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class _RenderPlan:
    draw_player_objects_layer: bool
    player_object_size_addon: int
    draw_tc_pixel_markers: bool
    draw_civ_emblems: bool


def _build_render_plan(is_scenario: bool, players) -> _RenderPlan:
    if is_scenario:
        return _RenderPlan(
            draw_player_objects_layer=True,
            player_object_size_addon=additional_scenario_player_object_size,
            draw_tc_pixel_markers=False,
            draw_civ_emblems=False,
        )
    nomad_or_missing_tc = any(
        player.position.x is None or player.position.y is None for player in players
    )
    return _RenderPlan(
        draw_player_objects_layer=draw_player_objects or nomad_or_missing_tc,
        player_object_size_addon=additional_player_object_size,
        draw_tc_pixel_markers=player_tc_marker == "pixel",
        draw_civ_emblems=player_tc_marker == "emblem",
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
                s = additional_cliff_size
                draw.rectangle([cx - s, cy - s, cx + s, cy + s], fill="#714b33")

    if draw_walls and rotate_walls_with_canvas:
        bs = border_spacing
        s = additional_player_wall_size
        for player in players:
            col = to_rgb(player_colors[player.color_id][1:])
            for unit in player.objects:
                if unit.object_id in wall_objects:
                    cx = unit.position.x + bs
                    cy = unit.position.y + bs
                    draw.rectangle([cx - s, cy - s, cx + s, cy + s], fill=col)


def draw_gaia_objects_common(canvas, gaia, original_map_dimension, after_rotation):
    draw = ImageDraw.Draw(canvas)
    rules = (
        (food_objects, "#A5C46C", additional_food_size),
        (stone_objects, "#919191", additional_stone_size),
        (gold_objects, "#FFC700", additional_gold_size),
        (relic_objects, "#FFFFFF", additional_relic_size),
    )

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
                _draw_square_marker(draw, cx, cy, additional_player_wall_size, col)


def draw_player_tcs(canvas, players, original_map_dimension, after_rotation):
    draw = ImageDraw.Draw(canvas)

    for player in players:
        if player.position.x is None or player.position.y is None:
            continue
        col = to_rgb(player_colors[player.color_id][1:])
        cx, cy = _object_canvas_xy(
            player.position.x, player.position.y, original_map_dimension, canvas, after_rotation
        )
        _draw_square_marker(draw, cx, cy, additional_player_tc_size, col)


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


def write_combined_minimap(
    input_file: str,
    *,
    output_path: str | None = None,
    verbose: bool = False,
    final_size: tuple[int, int] = (1630, 815),
):
    if verbose:
        print(f"Input file: {input_file}")
    is_scenario = _is_scenario_source(input_file)
    match = get_match(input_file)
    map_obj = match.map
    players = match.players
    gaia = match.gaia
    original_map_dimension = map_obj.dimension

    plan = _build_render_plan(is_scenario, players)

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
        if draw_gaia_objects:
            draw_gaia_objects_common(canvas, gaia, original_map_dimension, after_rotation=False)

        if plan.draw_player_objects_layer:
            draw_player_objects_common(
                canvas,
                players,
                original_map_dimension,
                after_rotation=False,
                player_object_size_addon=plan.player_object_size_addon,
            )

        if draw_walls and not rotate_walls_with_canvas:
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

        if draw_gaia_objects:
            draw_gaia_objects_common(canvas, gaia, original_map_dimension, after_rotation=True)

        if plan.draw_player_objects_layer:
            draw_player_objects_common(
                canvas,
                players,
                original_map_dimension,
                after_rotation=True,
                player_object_size_addon=plan.player_object_size_addon,
            )

        if draw_walls and not rotate_walls_with_canvas:
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


def render_minimap_image(input_file: str, *, settings: RenderSettings | None = None):
    """Server-friendly entry point: render without touching local disk paths."""
    s = settings or RenderSettings()
    if s.player_tc_marker == "emblem":
        raise ValueError(
            "player_tc_marker='emblem' requires emblem assets; not enabled in server mode."
        )
    with _apply_settings(s):
        return write_combined_minimap(input_file, output_path=None, verbose=False)


def render_minimap_png_bytes(input_file: str, *, settings: RenderSettings | None = None) -> bytes:
    img = render_minimap_image(input_file, settings=settings)
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

        civ_image = Image.open("Z:/YouTube/Scripts/CivEmblems/" + player.civilization + ".png")

        image_width, image_height = civ_image.size
        top_left_coords = (
            math.floor(coords[0] - image_width / 2),
            math.floor(coords[1] - image_height / 2),
        )

        draw = ImageDraw.Draw(civ_emblem_canvas)
        radius = max(image_width, image_height) / 2 + additional_player_tc_size
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


if __name__ == "__main__" and module_mode is False:
    parser = argparse.ArgumentParser(description="Render an AoE2 minimap from a scenario/recording.")
    parser.add_argument("--input", required=False, help="Path to input file (.aoe2scenario/.scx/.mgz/etc)")
    parser.add_argument("--output", required=False, help="Output PNG path (optional; if omitted, no file is written)")
    parser.add_argument("--object_mode", choices=["square", "rotated"], default="square")
    parser.add_argument("--player_tc_marker", choices=["none", "pixel"], default="none")
    parser.add_argument("--angle", type=int, default=45)
    parser.add_argument("--multiplier_integer", type=int, default=9)
    parser.add_argument("--orthographic_ratio", type=int, default=2)
    parser.add_argument("--border_spacing", type=int, default=4)
    parser.add_argument("--draw_cliffs", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--draw_walls", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--rotate_walls_with_canvas", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--draw_gaia_objects", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--draw_player_objects", action=argparse.BooleanOptionalAction, default=False)
    args = parser.parse_args()

    input_path = args.input or manual_source_file_path
    settings = RenderSettings(
        object_mode=args.object_mode,
        player_tc_marker=args.player_tc_marker,
        angle=args.angle,
        multiplier_integer=args.multiplier_integer,
        orthographic_ratio=args.orthographic_ratio,
        border_spacing=args.border_spacing,
        draw_cliffs=args.draw_cliffs,
        draw_walls=args.draw_walls,
        rotate_walls_with_canvas=args.rotate_walls_with_canvas,
        draw_gaia_objects=args.draw_gaia_objects,
        draw_player_objects=args.draw_player_objects,
    )

    with _apply_settings(settings):
        write_combined_minimap(input_path, output_path=args.output, verbose=True)
