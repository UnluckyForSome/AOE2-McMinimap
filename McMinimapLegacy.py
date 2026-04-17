"""AoE2 classic scenario loader (trimmed from AgeScx): Age of Kings `.scn`, The Conquerors `.scx`. Used by McMinimap.get_match()."""
import struct
import zlib
from itertools import chain


class Decoder:

    """Decoder create support dynamical reading and converting from a file"""

    def __init__(self, binaries):
        self.__pntr = 0
        self.__data = binaries

    """
        Todo:
            finish descriptions
    """

    def getStr32(self):
        self.__pntr += 4
        temp = struct.unpack('i', self.__data[self.__pntr - 4:self.__pntr])[0]
        self.__pntr += temp
        return self._decode_text(self.__data[self.__pntr - temp:self.__pntr])

    def getStr16(self):
        self.__pntr += 2
        temp = struct.unpack('h', self.__data[self.__pntr - 2:self.__pntr])[0]
        self.__pntr += temp
        return self._decode_text(self.__data[self.__pntr - temp:self.__pntr])

    def getDouble(self):
        self.__pntr += 8
        return struct.unpack('d', self.__data[self.__pntr - 8:self.__pntr])

    def getInt32(self):
        self.__pntr += 4
        return struct.unpack('i', self.__data[self.__pntr - 4:self.__pntr])[0]

    def getUInt32(self):
        self.__pntr += 4
        return struct.unpack('I', self.__data[self.__pntr - 4:self.__pntr])[0]

    def getInt16(self):
        self.__pntr += 2
        return struct.unpack('h', self.__data[self.__pntr - 2:self.__pntr])[0]

    def getUInt16(self):
        self.__pntr += 2
        return struct.unpack('H', self.__data[self.__pntr - 2:self.__pntr])[0]

    def getFloat(self):
        self.__pntr += 4
        return struct.unpack('f', self.__data[self.__pntr - 4:self.__pntr])[0]

    def getInt8(self):
        self.__pntr += 1
        return ord(self.__data[self.__pntr - 1:self.__pntr])

    def getAscii(self, length):
        self.__pntr += length
        return self._decode_text(self.__data[self.__pntr - length:self.__pntr]).replace('\x00', ' ')

    @staticmethod
    def _decode_text(b: bytes) -> str:
        """
        Scenario strings are not consistently UTF-8 in older formats; fall back to legacy encodings.
        """
        try:
            return b.decode('utf-8')
        except UnicodeDecodeError:
            try:
                return b.decode('cp1252')
            except UnicodeDecodeError:
                return b.decode('latin-1', errors='replace')

    def getBytes(self, length):
        self.__pntr += length
        return self.__data[self.__pntr - length:self.__pntr]

    def unpack(self, datatype):
        """Unpack datatypes from binarie file

        Args:
            datatype (str): datatype(s)

        Return:
            (tuple): converted datatypes
        """
        size = struct.calcsize(datatype)
        ret = struct.unpack(
            datatype, self.__data[self.__pntr:self.__pntr + size])
        self.__pntr += size
        return ret

    def offset(self):
        """Get decode position

        Return:
            (int): current position in file
        """
        return self.__pntr

    def decode(self, datatype):
        """Unpack datatypes from binarie file

        Args:
            datatype (str): datatype(s)

        Return:
            (tuple): converted datatypes
        """
        unpack = struct.unpack
        pntr = self.__pntr
        data = self.__data

        value = None
        temp = None

        datatypes = datatype.split('-')
        if len(datatypes) > 1:
            ret = tuple()
            for d in datatypes:
                ret += (self.decode(d),)
            return ret
        else:
            if 'ascii' in datatype:
                value = datatype.split()[1]
                self.__pntr += int(value)
                return data[self.__pntr - int(value):self.__pntr]
            if 'str' in datatype:
                if '32' in datatype:
                    value = self.decode('i')
                else:  # 16bit string
                    value = self.decode('h')
                temp = data[self.__pntr:self.__pntr + int(value)]
                self.__pntr += len(temp)
                return self._decode_text(temp)
            if datatype == 'i':  # integer
                value = unpack(datatype, data[pntr:pntr + 4])
                self.__pntr += 4
                return value[0]
            elif datatype == 'I':  # unsigned integer
                value = unpack(datatype, data[pntr:pntr + 4])
                self.__pntr += 4
                return value[0]
            elif datatype == 'h':  # short
                value = unpack(
                    datatype, self.__data[self.__pntr:self.__pntr + 2])
                self.__pntr += 2
                return value[0]
            elif datatype == 'H':  # unsigned short
                value = unpack(datatype, data[pntr:pntr + 2])
                self.__pntr += 2
                return value[0]
            elif datatype == 'f':  # 32b float
                value = unpack(datatype, data[pntr:pntr + 4])
                self.__pntr += 4
                return value[0]
            elif datatype == 'd':  # double
                value = unpack(datatype, data[pntr:pntr + 8])
                self.__pntr += 8
                return value[0]
            elif datatype == 'b':
                value = unpack(datatype, data[pntr:pntr + 1])
                self.__pntr += 1
                return value[0]

    def skip(self, size):
        """skip bytest in file

        Args:
            size (int): how many bytes to skip
        """
        self.__pntr += size


# --- debug / player satellite (format only) ---------------------------------


class Debug:
    def __init__(self):
        self.raw = None
        self.included = 0
        self.error = 0


class Resource:
    def __init__(self, food=0, wood=0, gold=0, stone=0, ore=0):
        self.food = food
        self.wood = wood
        self.gold = gold
        self.stone = stone
        self.ore = ore

    def __repr__(self):
        return f"Resource(food={self.food}, wood={self.wood}, gold={self.gold}, stone={self.stone})"

    def toJSON(self):
        return {"food": self.food, "wood": self.wood, "stone": self.stone, "gold": self.gold}


class Camera:
    def __init__(self, x=0.0, y=0.0, unknown1=0, unknown2=0):
        self.x = x
        self.y = y
        self.unknown1 = unknown1
        self.unknown2 = unknown2

    def __repr__(self):
        return f"Camera(x={self.x}, y={self.y})"

    def toJSON(self):
        return {"x": self.x, "y": self.y}


class AI:
    def __init__(self, name="", source="", type=0, unknown1=0, unknown2=0):
        self.name = name
        self.type = type
        self.source = source
        self.unknown1 = unknown1
        self.unknown2 = unknown2

    def __repr__(self):
        return f"AI(name={self.name!r}, type={self.type})"

    def toJSON(self):
        return {"name": self.name, "type": self.type}


class Diplomacy:
    def __init__(self, stances=None):
        self.stances = list(stances) if stances is not None else [0] * 8
        self.gaia = [0] * 9

    def __repr__(self):
        return f"Diplomacy({self.stances!r})"

    def __setitem__(self, playerIndex, stance):
        self.stances[playerIndex] = stance

    def __getitem__(self, playerIndex):
        return self.stances[playerIndex]

    def toJSON(self):
        return {i: self.stances[i] for i in range(len(self.stances))}


# --- map / units --------------------------------------------------------------


class Tile:
    @property
    def row(self):
        return self.__r

    @property
    def col(self):
        return self.__c

    @property
    def x(self):
        return self.__c

    @property
    def y(self):
        return self.__r

    def __init__(self, row, col, type=0, elevation=0, unknown=0):
        self.type = type
        self.elevation = elevation
        self.unknown = unknown
        self.__r = row
        self.__c = col

    def __repr__(self):
        return f"Tile(x={self.__c}, y={self.__r}, type={self.type}, elevation={self.elevation})"

    def toJSON(self):
        return {"type": self.type, "elevation": self.elevation}

    def position(self):
        return (self.__c, self.__r)

    def clear(self):
        self.type = 1

    def flat(self):
        self.elevation = 1

    def up(self, increase=1):
        self.elevation += increase

    def down(self, decrease=1):
        self.elevation -= decrease


class Unit:
    nextID = None

    @property
    def id(self):
        return self.__id

    @property
    def owner(self):
        return self.__owner

    def __init__(
        self,
        id=None,
        x=0,
        y=0,
        owner=0,
        type=0,
        angle=0,
        frame=0,
        inId=-1,
        unknown1=2,
        unknown2=2,
    ):
        if id is None:
            id = Unit.nextID()
        self.__owner, self.x, self.y = owner, x, y
        self.unknown1, self.unknown2 = unknown1, unknown2
        self.__id, self.type, self.angle = id, type, angle
        self.frame, self.inId = frame, inId

    def __repr__(self):
        return f"Unit(id={self.__id}, type={self.type}, x={self.x}, y={self.y}, owner={self.__owner})"

    def toJSON(self):
        return {
            "id": self.id,
            "owner": self.owner,
            "type": self.type,
            "x": self.x,
            "y": self.y,
            "angle": int(self.angle),
            "frame": self.frame,
            "inId": self.inId,
        }

    def move(self, dx, dy):
        self.x += dx
        self.y += dy


class PlayerUnits:
    @property
    def playerIndex(self):
        return self.__player

    def __init__(self, playerIndex):
        self.__units = {}
        self.__count = 0
        self.__player = playerIndex

    def __iter__(self):
        for units in self.__units.values():
            for unit in units:
                yield unit

    def __len__(self):
        return self.__count

    def existsId(self, id):
        return id in self.__units

    def delUnit(self, id):
        count = 0
        if self.existsId(id):
            count = len(self.__units[id])
            del self.__units[id]
        return count

    def delAll(self):
        count = len(self.__units)
        self.__units.clear()
        self.__count = 0
        return count

    def getById(self, id):
        return self.__units.get(id)

    def getByType(self, unitType):
        return [u for u in self if u.type == unitType]

    def new(self, **unitConfig):
        unitConfig["owner"] = self.__player
        unit = Unit(**unitConfig)
        if unit.id in self.__units:
            self.__units[unit.id].append(unit)
        else:
            self.__units[unit.id] = [unit]
        self.__count += 1
        return unit


class Units:
    @property
    def nextID(self):
        return self.__nextID

    @nextID.setter
    def nextID(self, value):
        self.__nextID = value

    def __init__(self):
        self.__playerUnits = [PlayerUnits(i) for i in range(9)]
        self.__nextID = 0
        Unit.nextID = self.getNextID

    def __iter__(self):
        for pUnits in self.__playerUnits:
            for unit in pUnits:
                yield unit

    def __len__(self):
        return sum(len(units) for units in self.__playerUnits)

    def __getitem__(self, index):
        if index > 9:
            raise IndexError()
        return self.__playerUnits[index]

    def __repr__(self):
        return f"UNITS:\n\tCOUNT: {len(self)}\n\tNEXTID: {self.nextID}"

    def getNextID(self):
        while self.existsId(self.__nextID):
            self.__nextID += 1
        return self.__nextID

    def toJSON(self):
        return {"units": [unit.toJSON() for unit in self]}

    def delUnit(self, id):
        return sum(pUnits.delUnit(id) for pUnits in self.__playerUnits)

    def delAll(self):
        return sum(pUnits.delAll() for pUnits in self.__playerUnits)

    def getById(self, id):
        result = []
        for pUnits in self.__playerUnits:
            units = pUnits.getById(id)
            if units:
                result.append(units)
        return result

    def existsId(self, id):
        return any(pUnits.existsId(id) for pUnits in self.__playerUnits)

    def new(self, **unitConfig):
        owner = unitConfig["owner"]
        if owner > 9 or owner < 0:
            raise IndexError()
        return self[owner].new(**unitConfig)


class Player:
    @property
    def name(self):
        return self._name.strip()

    @name.setter
    def name(self, value):
        self._name = value[:256]

    @property
    def diplomacy(self):
        return self._diplomacy

    @property
    def resource(self):
        return self._resource

    @property
    def ai(self):
        return self._ai

    @property
    def camera(self):
        return self._camera

    def __init__(
        self,
        name="",
        constName="",
        index=0,
        nameID=0,
        civilization=0,
        age=0,
        population=75,
        color=0,
        allyVictory=1,
        active=1,
        human=0,
        unknown1=4,
        unknown2="",
        unknown3=0,
        unknown4=0,
    ):
        self._name = name
        self.nameId = nameID
        self._constName = constName
        self.index = index
        self.civilization = civilization
        self.color = color
        self.allyVictory = allyVictory
        self.active = active
        self.human = human
        self.unknown1 = unknown1
        self.unknown2 = unknown2
        self.unknown3 = unknown3
        self.unknown4 = unknown4
        self.age = age
        self.population = population

        self.disabledTech = []
        self.disabledTechExtra = []
        self.disabledUnits = []
        self.disabledUnitsExtra = []
        self.disabledBuildings = []
        self.disabledBuildingsExtra = []

        self._diplomacy = Diplomacy()
        self._resource = Resource()
        self._ai = AI()
        self._camera = Camera()
        self.units = None

    def __repr__(self):
        tag = "GAIA" if self.index == 0 else str(self.index)
        return f"Player({tag}, name={self.name!r}, civ={self.civilization}, color={self.color})"

    def toJSON(self):
        return {
            "index": self.index,
            "name": self.name,
            "civilization": self.civilization,
            "color": self.color,
        }


# --- triggers (parser needs effects[].selectedCount + unitIds only) ------------


class Effect:
    __slots__ = ("selectedCount", "unitIds")

    def __init__(self, selectedCount=0, **_kwargs):
        self.selectedCount = int(selectedCount)
        self.unitIds = []

    def toJSON(self):
        return {}


class Condition:
    __slots__ = ()

    def __init__(self, **_kwargs):
        pass

    def toJSON(self):
        return {}


class Trigger:
    def __init__(
        self,
        name="",
        enable=True,
        loop=False,
        objective=True,
        objectiveOrd=0,
        text="",
        unknown1=0,
        unknown2=0,
        **_kwargs,
    ):
        self.name = name
        self.enable = enable
        self.loop = loop
        self.objective = objective
        self.objectiveOrder = objectiveOrd
        self.text = text
        self.unknown1 = unknown1
        self.unknown2 = unknown2
        self.__effects = []
        self.__conditions = []

    @property
    def effects(self):
        return self.__effects

    @property
    def conditions(self):
        return self.__conditions

    def __repr__(self):
        return f"Trigger(name={self.name!r})"

    def toJSON(self):
        return {"name": self.name}

    def newEffect(self, **config):
        self.__effects.append(Effect(**config))

    def newCondition(self, **config):
        self.__conditions.append(Condition(**config))


class Message:
    def __init__(self, text="", id=0):
        self._id = id
        self._text = text

    @property
    def id(self):
        return self._id

    @id.setter
    def id(self, value):
        self._id = value

    @property
    def text(self):
        return self._text

    @text.setter
    def text(self, value):
        self._text = value


class Messages:
    def __init__(self):
        self._briefing = Message()
        self._objectives = Message()
        self._hints = Message()
        self._victory = Message()
        self._loss = Message()
        self._history = Message()
        self._scouts = Message()

    @property
    def briefing(self):
        return self._briefing

    @property
    def objectives(self):
        return self._objectives

    @property
    def hints(self):
        return self._hints

    @property
    def victory(self):
        return self._victory

    @property
    def loss(self):
        return self._loss

    @property
    def history(self):
        return self._history

    @property
    def scouts(self):
        return self._scouts


class Goals:
    def __init__(
        self,
        conquest=0,
        unknown1=0,
        relics=0,
        unknown2=0,
        exploration=0,
        unknown3=0,
        all=0,
        mode=0,
        score=0,
        time=0,
    ):
        self.conquest = conquest
        self.unknown1 = unknown1
        self.relics = relics
        self.unknown2 = unknown2
        self.exploration = exploration
        self.unknown3 = unknown3
        self.all = all
        self.mode = mode
        self.score = score
        self.time = time


class Background:
    def __init__(
        self,
        filename="",
        included=0,
        size=0,
        width=0,
        height=0,
        include=0,
        planes=0,
        bitCount=0,
        compression=0,
        sizeImage=0,
        xPels=0,
        yPels=0,
        colors=0,
        iColors=0,
        colorTable=None,
        rawData=None,
    ):
        self.filename = filename
        self.included = included
        self.width = width
        self.height = height
        self.include = include
        self.size = size
        self.planes, self.bitCount = planes, bitCount
        self.compression, self.sizeImage = compression, sizeImage
        self.xPels, self.yPels, self.colors = xPels, yPels, colors
        self.iColors = iColors
        self.colorTable = [] if colorTable is None else colorTable
        self.rawData = [] if rawData is None else rawData


class Cinematics:
    def __init__(self):
        self.intro = ""
        self.defeat = ""
        self.victory = ""



class Tiles:

    """Holds tiles
        With this class you are able to manipulate with tiles in scenario
        There's som helpfull classes
    """

    @property
    def width(self):
        return self._width

    @property
    def height(self):
        return self._height

    def __init__(self, width, height):
        """create tiles

        Args:
            width (int, optional): default width, 32
            height (int, optional): default height, 32
        """
        self._tiles = list()
        self.__recreate(width, height)
        self._width = width
        self._height = height

    def __getitem__(self, r):
        """Get row of tiles

        Args:
            r (int): row tiles

        Return:
            (list): tiles
        """
        if (r < 0):
            raise ValueError("r can't be < 0")
        if (r > self._width - 1):
            raise ValueError("r can't be > map width")
        return self._tiles[r]

    def __iter__(self):
        """iterate over all tiles in scenario"""
        return iter(chain(*self._tiles))

    def __len__(self):
        """number of tiles

        Return:
            (int): number of tiles
        """
        return self._height * self._width

    def __repr__(self):
        name = "Tiles: \n"
        info = "\tRows:{} \tCollumns:{}\n".format(
            self._height, self._width)
        info2 = "\tTiles:{}".format(self._height * self._width)

        return name + info + info2

    def __recreate(self, width, height):
        self._tiles = list()
        for r in range(height):
            self._tiles.append(list())
            for c in range(width):
                self._tiles[r].append(Tile(r, c))
        self._height = height
        self._width = width

    def toJSON(self):
        """return JSON"""
        data = list()
        for h in range(self.height):
            data.append(list())
            for w in range(self.width):
                data[h].append(self[h][w].toJSON())
        return data

    def resize(self, newWidth, newHeight):
        """resize map

        Todo:
            add description
            if resize < new Size, shrink and delete tempory tiles
            clean section
        """
        width, height = self._width, self._height
        wDiff = abs(newWidth - width)
        hDiff = abs(newHeight - height)

        if newWidth > self._width:
            for r in range(height):
                for i in range(wDiff):
                    self._tiles[r].append(Tile(r, width + i))
            width = newWidth
        elif newWidth < self._width:
            for r in range(height):
                self._tiles[r] = self._tiles[r][:width - wDiff]
            width = newWidth

        if newHeight > self._height:
            for i in range(hDiff):
                l = [Tile(height + i, c) for c in range(width)]
                self._tiles.append(l)
        elif newHeight < self._height:
            self._tiles = self._tiles[:height - hDiff]

        self._height = newHeight
        self._width = newWidth

    def row(self, row):
        """Get Row or Y tiles

        Args:
            row (int): row

        Return:
            (list): tiles
        """
        if (row < 0):
            raise ValueError("row can't be < 0")
        if (row > self._height - 1):
            raise ValueError("row can't be > tiles rows")

        return self._tiles[row]

    def collumn(self, collumn):
        """Get Collumn or X tiles

        Args:
            collumn (int): collumn

        Return:
            (list): tiles
        """
        if (collumn < 0):
            raise ValueError("collumn can't be < 0")
        if (collumn > self._width):
            raise ValueError("collumn can't be > tiles collumns")

        return [row[collumn] for row in self._tiles]

    def clearTerrain(self, terrainType=0, safe=True):
        """clear all tiles

        Args:
            terrainType (int): type of terrain
            safe (boolean): throw exception on unexcepted behavior
        """
        if (safe):
            if (terrainType < 0):
                raise ValueError("terrainType can't be {}".format(terrainType))
        for tile in self:
            tile.type = terrainType

    def clearElevation(self, elevation=0, safe=True):
        """clear all elevation

        Args:
            elevation (int): elevation level
            safe (boolean): throw exception on unexcepted behavior
        """
        if (safe):
            if (elevation < 0):
                raise ValueError("elevation can't be {}".format(elevation))
        for tile in self:
            tile.elevation = elevation

    def size(self):
        """get map size

        Return:
            (tuple): width height
        """
        return (self._width, self._height)

    def getByTerrain(self, terrainType):
        """get all tiles by terrain type

        Args:
            terrainType (int): terrain type

        Return:
            (list): tiles
        """
        tiles = list()

        for tile in self:
            if tile.type == terrainType:
                tiles.append(tile)

        return tiles

    def getByElevation(self, elevation):
        """get all tiles by elevation level

        Args:
            elevation (int): elevation level

        Return:
            (list): tiles
        """
        tiles = list()

        for tile in self:
            if tile.elevation == elevation:
                tiles.append(tile)

        return tiles

    def getArea(self, x1, y1, x2, y2):
        """Get tiles from selected area

        Args:
            x1 (int): point 1 x
            y1 (int): point 1 y
            x2 (int): point 2 x
            y2 (int): point 2 y

        Return:
            (list): tiles

        Raises:
            IndexError: If points are outside map
        """
        if (x1 < 0) or (x2 < 0) or (y1 < 0) or (y2 < 0):
            raise IndexError("one of parameter is <0 ")
        if (x1 > self._width - 1) or (x2 > self._width - 1):
            raise IndexError("one of parameter is > map width or > map height")
        if (y1 > self._height) or (y2 > self._height):
            raise IndexError("one of parameter is > map width or > map height")
        result = list()
        nx, ny = 0, 0
        for y in range(0, abs(y2-y1)+1):
            ny = y1 + y
            for x in range(0, abs(x2-x1)+1):
                nx = x1 + x
                result.append(self[ny][nx])

        return result

    def replaceTerrain(self, terrainType, newType):
        """replace all terrain type with new type

        Args:
            terrainType (int): terrain you want replace
            newType (int): new terrain type

        Return:
            (int): number of replaced tiles
        """
        count = 0

        for tile in self:
            if tile.type == terrainType:
                tile.type = newType
                count += 1

        return count

    def incElevation(self, increase=1):
        """increase elevation on all tiles

        Args:
            increase (int): how much will be incresed
        """
        for tile in self:
            tile.up(increase)

    def decElevation(self, decrease=1):
        """decrease elevation on all tiles

        Args:
            decrease (int): how much will be decreased
        """
        for tile in self:
            tile.down(decrease)



class Map:

    """Map structure

    Attributes:
        width (int, readonly): map width
        height (int, readonly): map height
        camera (int, int): starting camera
        tiles (Tiles): tiles section
        aiType (int): type of AI on this map
    """

    @property
    def width(self):
        return self._width

    @property
    def height(self):
        return self._height

    def __init__(self, width=0, height=0, camera=(0, 0), aiType=0):
        self._width = width
        self._height = height
        self.camera = camera
        self.tiles = Tiles(width, height)
        self.aiType = aiType  # type of AI for this scenario

    def __repr__(self):
        name = "MAP INFO:\n"
        info1 = "\tSize: width:{} height:{}\n".format(self.width, self.height)
        info2 = "\tStarting Camera: x:{} y:{}\n".format(
            self.camera[0], self.camera[1])
        info3 = "\tAI Type: {}".format(self.aiType)
        return name + info1 + info2 + info3

    def centerCamera(self):
        """Starting camera will be at center of map

        Todo:
            check function
        """
        self.camera = (self.width / 2, self.height / 2)

    def resize(self, newWidth, newHeight):
        """Resize map

        Todo:
            if resizing, insert directions NE, NW, SE...
        """
        self._width = newWidth
        self._height = newHeight
        self.tiles.resize(newWidth, newHeight)



class Players:

    """Store players"""

    def __init__(self):
        """Create player controller"""
        self._players = list()
        for i in range(9):  # include gaia = player 0
            self._players.append(Player(index=i))

    def __len__(self):
        """Number of players

        Return:
            int: number of players, 9
        """
        return len(self._players)

    def __getitem__(self, index):
        """Get player with selected index

        Args:
            index (str): index of player

        Return:
            Player: player with index
        """
        return self._players[index]

    def __repr__(self):
        name = "Players: \n"
        active = sum(1 for p in self._players if p.active == 1)
        info1 = "\tCount:{} \tActive: {}\n".format(self.__len__(), active)
        return name + info1

    def toJSON(self):
        """return JSON"""
        data = dict()
        for pIndex in range(len(self)):
            data[pIndex] = self[pIndex].toJSON()
        return data

    def byColor(self, color):
        """return all players with specific color

        Args:
            color (int): color

        Return:
            list(Player): players
        """
        players = list()

        for player in self._players:
            if player.color == color:
                players.append(player)

        return players

    def byCivilization(self, civlization):
        """return all players with specific civlization

        Args:
            civlization (int): civlization

        Return:
            list(Player): players
        """
        players = list()

        for player in self._players:
            if player.civlization == civlization:
                players.append(player)

        return players

    def byAge(self, age):
        """return all players with specific age

        Args:
            age (int): age

        Return:
            list(Player): players
        """
        players = list()

        for player in self._players:
            if player.age == age:
                players.append(player)

        return players

    def humans(self):
        """return all human players

        Return:
            list(Player): players
        """
        players = list()

        for player in self._players:
            if player.human == 1:
                players.append(player)

        return players

    def computers(self):
        """return all computer players

        Return:
            list(Player): players
        """
        players = list()

        for player in self._players:
            if player.human == 0:
                players.append(player)

        return players

    def startResources(self, food=None, wood=None, gold=None, stone=None, ore=None):
        """Set starting resource for all players

        Args:
            food (int, optional): food
            wood (int, optional): wood
            gold (int, optional): gold
            stone (int, optional): stone
            ore (int, optional): ore
        """
        for player in self._players:
            if food:
                player.Resource.food = food
            if wood:
                player.Resource.wood = wood
            if gold:
                player.Resource.gold = gold
            if stone:
                player.Resource.stone = stone
            if ore:
                player.Resource.ore = ore

    def activeAll(self):
        """activate all players"""
        for player in self._players:
            player.active = 1

    def deactiveAll(self):
        """deactive all players"""
        for player in self._players:
            player.active = 1

    def active(self):
        """Return of active players

        Return:
            list(Player): active players
        """
        result = list()

        for player in self._players:
            if player.active == 1:
                result.append(player)

        return list()

    def inactive(self):
        """Return inactive players

        Return:
            list(Player): inactive players
        """
        result = list()

        for player in self._players:
            if player.active == 0:
                result.append(player)

        return list()



class Triggers:

    def __init__(self):
        self.__triggers = list()

    def __iter__(self):
        return iter(self.__triggers)

    def __len__(self):
        return len(self.__triggers)

    def __getitem__(self, index):
        if index >= len(self):
            raise IndexError()
        return self.__triggers[index]

    def __delitem__(self, index):
        if index >= len(self):
            raise IndexError()
        self.__triggers.pop(index)

    def __repr__(self):
        name = "TRIGGERS: \n"
        info1 = "\tCOUNT:{}".format(len(self))
        return name + info1

    def toJSON(self):
        """return JSON"""
        data = dict()
        data["triggers"] = list()
        for trigger in self.__triggers:
            data["triggers"].append(trigger.toJSON())
        return data

    def new(self, **config):
        """Create new trigger"""
        self.__triggers.append(Trigger(**config))

import zlib


class Decompress:

    def __init__(self, scenario, bData, version=1.21, temp=False):
        """!
        """
        self.scenario = scenario
        self.version = version
        headerLength = self.decompressHeader(bData)
        decompressed = self.unzip(bData[headerLength:])
        dataLenght = self.decompressData(decompressed)
        if temp:
            f = open('decompressed.temp', 'wb')
            f.write(decompressed)
            f.close()

    def decompressHeader(self, bData):
        decoder = Decoder(bData)
        decode, unpack, skip = decoder.decode, decoder.unpack, decoder.skip

        self.scenario.version = decode('ascii 4').decode('utf-8')  # scenario version
        version = float(self.scenario.version)
        length  = unpack('i')  # header length
        skip(4)  # skip Constant
        self.scenario.timestamp = unpack('i')[0]  # date of last save
        self.scenario.instructions = decode('str32')  # scenario instructions
        skip(4)  # skipt Constant and number of Players
        self.scenario.plrnumb = unpack('i')[0]

        return decoder.offset()

    def unzip(self, bytes):
        return zlib.decompress(bytes, -zlib.MAX_WBITS)

    def decompressData(self, bData):
        decoder = Decoder(bData)
        decode, unpack, skip = decoder.decode, decoder.unpack, decoder.skip

        # Shortcuts: Decoder
        getInt8 = decoder.getInt8
        getInt32 = decoder.getInt32
        getUInt32 = decoder.getUInt32
        getInt16 = decoder.getInt16
        getUInt16 = decoder.getUInt16
        getStr32 = decoder.getStr32
        getStr16 = decoder.getStr16
        getFloat = decoder.getFloat
        getBytes = decoder.getBytes
        getAscii = decoder.getAscii
        getDouble = decoder.getDouble

        # Shortcuts: Scenario
        scenario = self.scenario
        players = self.scenario.players
        messages = self.scenario.messages
        debug = self.scenario.debug
        triggers = self.scenario.triggers

        Units.nextID = getUInt32()

        self.version = getFloat()  # version 2
        self.scenario.version2 = self.version
        version = self.version

        for i in range(8):
            players[i+1].name = getAscii(256)
        skip(256*8)  # other player names 9-16

        if (self.version >= 1.18):
            for i in range(8):
                players[i+1].nameID = getInt32()
            skip(8*4)  # other player names string ID

        for i in range(8):
            players[i].active = getUInt32()
            players[i].human = getUInt32()
            players[i].civilization = getUInt32()
            players[i].unknown1 = getUInt32()
        skip(8*16)  # other players data

        decode('i')  # unk1
        decode('f')  # unk2
        skip(1)  # separator
        scenario.filename = getStr16()  # original filename

        # section: MESSAGES
        if (self.version >= 1.18):
            messages.objectives.id = getInt32()
            messages.hints.id = getInt32()
            messages.victory.id = getInt32()
            messages.loss.id = getInt32()
            messages.history.id = getInt32()
            if (self.version >= 1.22):
                messages.scouts.id = getInt32()
        messages.objectives.text = getStr16()
        messages.hints.text = getStr16()
        messages.victory.text = getStr16()
        messages.loss.text = getStr16()
        messages.history.text = getStr16()
        if (self.version >= 1.22):
            messages.scouts.text = getStr16()

        # section: CINEMATICS
        scenario.cinematics.intro = getStr16()
        scenario.cinematics.defeat = getStr16()
        scenario.cinematics.victory = getStr16()

        # section: BACKGROUND
        scenario.background.filename = getStr16()
        scenario.background.included = getInt32()
        scenario.background.width = getInt32()
        scenario.background.height = getInt32()

        self.scenario.background.include = getInt16()
        include = self.scenario.background.include
        if (include == -1 or include == 2):
            scenario.size = getUInt32()
            scenario.width = getInt32()
            scenario.height = getInt32()
            scenario.planes = getInt16()
            scenario.bitCount = getInt16()
            scenario.compression = getInt32()
            scenario.sizeImage = getInt32()
            scenario.xPels = getInt32()
            scenario.yPels = getInt32()
            scenario.colors = getUInt32()
            scenario.iColors = getInt32()
            scenario.colorTable = getBytes(scenario.colors*4)
            scenario.rawData = getBytes(scenario.sizeImage)

        # section: PLAYER DATA 2
        for i in range(16):
            getStr16()
            getStr16()

        for i in range(8):
            players[i+1].ai.name = getStr16()
        for i in range(8):
            getStr16()  # Other players ai names

        for i in range(8):
            getInt32()  # Unknown 1
            getInt32()  # Unknown 2
            players[i+1].ai.source = getStr32()
        for i in range(8):  # for another 8 players
            skip(8)
            getStr32()

        for i in range(8):
            players[i+1].ai.type = getInt8()
        skip(8)  # Other players AI TYPE
        skip(4)  # Separator 0xFFFFFF9D
        skip(16*24)  # Unused resources
        skip(4)  # another separator

        # section: Goals
        """!
            @todo optimize this section with 1 unpack
        """
        goals = scenario.goals
        goals.conquest = getInt32()
        goals.unknown1 = getInt32()
        goals.relics = getInt32()
        goals.unknown2 = getInt32()
        goals.exploration = getInt32()
        goals.unknown3 = getInt32()
        goals.all = getInt32()
        goals.mode = getInt32()
        goals.score = getInt32()
        goals.time = getInt32()

        # section: Diplomacy
        for i in range(8):
            for j in range(8):
                players[i].diplomacy[j] = getInt32()
            skip(8*4)  # skip another 8 unused players
        skip(8*16*4)  # skip another 8 unused player, with 16 dipls

        skip(11520)  # unused space
        skip(4)  # separator
        skip(16*4)  # allied victory, ignored

        skip(16*4)  # techs count
        for i in range(8):
            players[i].disabledTech = unpack('i'*30)
        skip(4*8*30)  # skip for another players
        if version >= 1.30:
            for i in range(8):
                players[i].disabledTechExtra = unpack('i'*30)
            skip(4*8*30)

        skip(16*4)  # units count
        for i in range(8):
            players[i].disabledUnits = unpack('i'*30)
        skip(4*8*30)  # skip for another players
        if version >= 1.30:
            for i in range(8):
                players[i].disabledUnitsExtra = unpack('i'*30)
            skip(4*8*30)

        skip(16*4)  # buildings count
        for i in range(8):
            players[i].disabledBuildings = unpack('i'*20)
        skip(4*8*20)  # skip for another players
        if version >= 1.30:
            for i in range(8):
                players[i].disabledBuildingsExtra = unpack('i'*40)
            skip(4*8*40)

        getInt32()  # unused
        getInt32()  # unused
        getInt32()  # All tech
        for i in range(8):
            players[i+1].age = getInt32()
        players[0].age = getUInt32()  # for gaia player
        skip(7*4)  # another players

        skip(4)  # separator
        x, y = getInt32(), getInt32()  # starting camera
        if version >= 1.21:
            scenario.map.aiType = getUInt32()
        w = getInt32()
        h = getInt32()
        scenario.map.camera = x, y
        scenario.map.resize(w, h)

        for tile in self.scenario.tiles:
            tile.type = getInt8()
            tile.elevation = getInt8()
            tile.unknown = getInt8()

        skip(4)  # number of units section

        for i in range(8):
            resource = players[i+1].resource
            resource.food = getFloat()
            resource.wood = getFloat()
            resource.gold = getFloat()
            resource.stone = getFloat()
            resource.ore = getFloat()
            getFloat()  # padding
            if version >= 1.21:
                players[i+1].population = getFloat()

        # Units section
        for i in range(9):
            units = getUInt32()
            newUnit = players[i].units.new
            for u in range(units):
                newUnit(x=getFloat(), y=getFloat(),
                     unknown1=getFloat(), id=getUInt32(), type=getUInt16(),
                     unknown2=getInt8(), angle=getFloat(), frame=getUInt16(),
                     inId=getInt32())

        skip(4)  # number of plyers, again
        for i in range(1, 9):  # only for playable players
            players[i].constName = getStr16()
            players[i].camera.x = getFloat()
            players[i].camera.y = getFloat()
            players[i].camera.unknown1 = getInt16()
            players[i].camera.unknown2 = getInt16()
            players[i].allyVictory = getInt8()
            dip = getUInt16()  # Player count for diplomacy
            skip(dip*1)  # 0 = allied, 1 = neutral, 2 = ? , 3 = enemy
            #  skip(dip*4)  # 0 = GAIA, 1 = self,
            #  2 = allied, 3 = neutral, 4 = enemy
            for j in range(9):
                players[i].diplomacy.gaia[j] = getInt32()
            players[i].color = getUInt32()
            unk1 = getFloat()
            unk2 = getUInt16()
            if unk1 == 2.0:
                skip(8*1)
            skip(unk2*44)
            skip(7*1)
            skip(4)
        skip(8)
        getInt8()  # unknown

        n = getUInt32()  # number of triggers
        for t in range(n):
            # print("Trigger: {}".format(t))
            triggers.new(
                    enable=getUInt32(),
                    loop=getUInt32(),
                    unknown1=getInt8(),
                    objective=getInt8(),
                    objectiveOrd=getUInt32(),
                    unknown2=getUInt32(),
                    text=getStr32(),
                    name=getStr32()
                )

            ne = getInt32()  # number of effects
            for e in range(ne):
                # print("\tEffect: {}".format(e))
                triggers[t].newEffect(
                    type=getInt32(),
                    check=getInt32(),
                    aiGoal=getInt32(),
                    amount=getInt32(),
                    resource=getInt32(),
                    state=getInt32(),
                    selectedCount=getInt32(),
                    unitId=getInt32(),
                    unitName=getInt32(),
                    sourcePlayer=getInt32(),
                    targetPlayer=getInt32(),
                    tech=getInt32(),
                    stringId=getInt32(),
                    unknown1=getInt32(),
                    time=getInt32(),
                    triggerId=getInt32(),
                    x=getInt32(), y=getInt32(),
                    x1=getInt32(), y1=getInt32(),
                    x2=getInt32(), y2=getInt32(),
                    unitGroup=getInt32(),
                    unitType=getInt32(),
                    instructionId=getInt32(),
                    text=getStr32(),
                    filename=getStr32()
                    )
                for k in range(triggers[t].effects[e].selectedCount):
                    triggers[t].effects[e].unitIds.append(getInt32())
            skip(ne*4)  # effects order

            nc = getInt32()  # number of conditions
            for c in range(nc):
                # print("\tCondition: {}".format(c))
                triggers[t].newCondition(
                    type=getUInt32(),
                    check=getInt32(),
                    amount=getInt32(),
                    resource=getInt32(),
                    unitObject=getInt32(),
                    unitId=getInt32(),
                    unitName=getInt32(),
                    sourcePlayer=getInt32(),
                    tech=getInt32(),
                    timer=getInt32(),
                    unknown1=getInt32(),
                    x1=getInt32(), y1=getInt32(),
                    x2=getInt32(), y2=getInt32(),
                    unitGroup=getInt32(),
                    unitType=getInt32(),
                    aiSignal=getInt32()
                    )
            skip(nc*4)  # conditions order
        skip(n*4)

        debug.included = getUInt32()
        debug.error = getUInt32()
        if debug.included:
            debug.raw = getBytes(396)  # AI DEBUG file
        """
        for i in range(1, 9):
            scenario.players[i].constName   = getStr16()
            scenario.players[i].cameraX     = getFloat()
            scenario.players[i].cameraY     = getFloat()
            scenario.players[i].cameraXX    = getInt16()
            scenario.players[i].cameraYY    = getInt16()
            scenario.players[i].allyVictory = getInt8()
        """



class Scenario:

    """ Scenario class """

    def __init__(self, filename=None, ver=1.21):
        """create scenario with defaults values,
            check default.txt for more information

            Args:
                filename (str, optional): load scenario from file
                version (float, optional): specific version"""
        self.version = ver
        if filename:
            self.load(filename)
        else:
            self._clear()

    def __repr__(self):
        name = "SCENARIO:{}\n".format(self.filename)
        info1 = "\tWIDTH:{} HEIGHT:{}\n".format(self.tiles.width, self.tiles.height)
        info2 = "\tUNITS:{}\n".format(len(self.units))
        info3 = "\tTRIGGERS:{}".format(len(self.triggers))
        return name + info1 + info2 + info3

    def load(self, filename, ver=1.21):
        """
            load scenario from file
            it doesn't save current scenario

            Args:
                filename (str): scenario filename
                ver (float, optional): version of scenario

            Raises:
                IOError: if file doesn't exits or is broken
        """
        self._clear()

        try:
            f = open(filename, 'rb')
        except:
            raise(IOError("File is broken or doesn't exists"))
        b = f.read()  # get bytes from file

        Decompress(self, b, ver, False)  # load data

    def new(self, filename):
        """create whole new blank scenario

            Args:
                terrainType (int, optional): starting terrain type, 0
                eleavtion (int, optional): starting elevation, 0
                filename (str, optional): if sets, it will create
                    new scenario file
                ver (float, optional): create version specific scenario

            Todo:
                finish starting terrainType and elevation
        """
        self._clear()

        self.version = "1.21"
        self.version2 = 1.22
        self.filename = filename

    def _clear(self):
        """clear all scenario data"""
        self.filename = None  # scenario filename
        self.version = None  # scenario version

        self.instructions = ""
        self.plrnumb = 8

        self.players = Players()    # initialize players
        self.messages = Messages()   #
        self.cinematics = Cinematics()  # movies
        self.background = Background()  # pre-game image
        self.map = Map()
        self.tiles = self.map.tiles
        self.goals = Goals()
        self.units = Units()
        self.triggers = Triggers()
        self.debug = Debug()

        for i in range(len(self.players)):
            self.players[i].units = self.units[i]

        self.timestamp = 0  # last save