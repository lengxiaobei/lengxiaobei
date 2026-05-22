import json
import random
from pathlib import Path
from typing import Dict, Optional
from dataclasses import dataclass, field
from enum import Enum


class Rarity(Enum):
    COMMON = "common"
    UNCOMMON = "uncommon"
    RARE = "rare"
    EPIC = "epic"
    LEGENDARY = "legendary"


class Species(Enum):
    DOG = "dog"
    CAT = "cat"
    BIRD = "bird"
    RABBIT = "rabbit"
    FOX = "fox"
    PANDA = "panda"
    DRAGON = "dragon"
    UNICORN = "unicorn"


class Eye(Enum):
    NORMAL = "normal"
    BIG = "big"
    SMALL = "small"
    GLASSY = "glassy"
    SPARKLE = "sparkle"
    ANGRY = "angry"
    SLEEPY = "sleepy"


class Hat(Enum):
    NONE = "none"
    TOP_HAT = "top_hat"
    CAP = "cap"
    CROWN = "crown"
    WIZARD_HAT = "wizard_hat"
    SANTA_HAT = "santa_hat"
    COWBOY_HAT = "cowboy_hat"


@dataclass
class Companion:
    rarity: Rarity
    species: Species
    eye: Eye
    hat: Hat
    shiny: bool = False
    stats: Dict[str, int] = field(default_factory=dict)
    name: str = ""
    personality: str = ""
    level: int = 1
    experience: int = 0
    mood: str = "happy"


RARITY_WEIGHTS = {Rarity.COMMON: 60, Rarity.UNCOMMON: 25, Rarity.RARE: 10, Rarity.EPIC: 4, Rarity.LEGENDARY: 1}
RARITY_FLOOR = {Rarity.COMMON: 5, Rarity.UNCOMMON: 15, Rarity.RARE: 25, Rarity.EPIC: 35, Rarity.LEGENDARY: 50}

STAT_NAMES = ["happiness", "energy", "curiosity", "friendship", "intelligence"]

SPECIES_NAMES = {
    Species.DOG: ["旺财", "小白", "小黑", "贝贝", "欢欢"],
    Species.CAT: ["咪咪", "喵喵", "花花", "橘橘", "雪球"],
    Species.BIRD: ["小鸟", "飞飞", "喳喳", "啾啾", "鹦鹉"],
    Species.RABBIT: ["兔兔", "白白", "跳跳", "萝卜", "兔子"],
    Species.FOX: ["小狐", "红红", "狐狸", "阿狸", "狐狐"],
    Species.PANDA: ["熊猫", "盼盼", "滚滚", "黑白", "国宝"],
    Species.DRAGON: ["小龙", "神龙", "龙龙", "火焰", "飞天龙"],
    Species.UNICORN: ["独角兽", "独角", "彩虹", "神马", "天马"],
}

PERSONALITIES = ["活泼开朗", "安静内向", "聪明伶俐", "贪吃", "粘人", "勇敢", "温柔", "调皮"]

SALT = "lengxiaobei-buddy-2026"


def _mulberry32(seed: int):
    a = seed & 0xffffffff
    while True:
        a |= 0
        a = (a + 0x6d2b79f5) & 0xffffffff
        t = (a ^ (a >> 15)) * (1 | a)
        t = (t + (t ^ (t >> 7)) * 61) ^ t
        yield ((t ^ (t >> 14)) & 0xffffffff) / 4294967296


def _hash_str(s: str) -> int:
    h = 2166136261
    for c in s:
        h ^= ord(c)
        h = (h * 16777619) & 0xffffffff
    return h


def _pick(rng, items: list):
    return items[int(next(rng) * len(items))]


def _roll_rarity(rng) -> Rarity:
    total = sum(RARITY_WEIGHTS.values())
    roll = next(rng) * total
    for rarity in Rarity:
        roll -= RARITY_WEIGHTS[rarity]
        if roll < 0:
            return rarity
    return Rarity.COMMON


def _roll_stats(rng, rarity: Rarity) -> Dict[str, int]:
    floor = RARITY_FLOOR[rarity]
    peak = _pick(rng, STAT_NAMES)
    dump = _pick(rng, STAT_NAMES)
    while dump == peak:
        dump = _pick(rng, STAT_NAMES)
    stats = {}
    for stat in STAT_NAMES:
        if stat == peak:
            stats[stat] = min(100, floor + 50 + int(next(rng) * 30))
        elif stat == dump:
            stats[stat] = max(1, floor - 10 + int(next(rng) * 15))
        else:
            stats[stat] = floor + int(next(rng) * 40)
    return stats


class BuddyManager:
    def __init__(self, project_root: str):
        self.project_root = Path(project_root)
        self.buddy_dir = self.project_root / "buddy"
        self.buddy_dir.mkdir(exist_ok=True)
        self.data_file = self.buddy_dir / "buddy_data.json"
        self.companion: Optional[Companion] = None
        self._buddy_prompt: Optional[str] = None
        self._load_data()

    def _load_buddy_prompt(self) -> str:
        if self._buddy_prompt:
            return self._buddy_prompt
        prompt_file = self.project_root / "prompts" / "BUDDY.md"
        if prompt_file.exists():
            self._buddy_prompt = prompt_file.read_text(encoding="utf-8")
        else:
            self._buddy_prompt = ""
        return self._buddy_prompt

    def _load_data(self):
        if not self.data_file.exists():
            return
        try:
            with open(self.data_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            if data:
                self.companion = Companion(
                    rarity=Rarity(data.get("rarity", "common")),
                    species=Species(data.get("species", "dog")),
                    eye=Eye(data.get("eye", "normal")),
                    hat=Hat(data.get("hat", "none")),
                    shiny=data.get("shiny", False),
                    stats=data.get("stats", {}),
                    name=data.get("name", ""),
                    personality=data.get("personality", ""),
                    level=data.get("level", 1),
                    experience=data.get("experience", 0),
                    mood=data.get("mood", "happy"),
                )
        except Exception as e:
            print(f"[Buddy] 加载数据失败: {e}")

    def _save_data(self):
        if not self.companion:
            return
        data = {
            "name": self.companion.name, "personality": self.companion.personality,
            "level": self.companion.level, "experience": self.companion.experience,
            "mood": self.companion.mood,
            "rarity": self.companion.rarity.value, "species": self.companion.species.value,
            "eye": self.companion.eye.value, "hat": self.companion.hat.value,
            "shiny": self.companion.shiny, "stats": self.companion.stats,
        }
        with open(self.data_file, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def get_companion(self, user_id: str = "default") -> Companion:
        if self.companion:
            return self.companion
        seed = _hash_str(user_id + SALT)
        rng = _mulberry32(seed)
        rarity = _roll_rarity(rng)
        species = _pick(rng, list(Species))
        eye = _pick(rng, list(Eye))
        hat = Hat.NONE if rarity == Rarity.COMMON else _pick(rng, list(Hat))
        shiny = next(rng) < 0.01
        stats = _roll_stats(rng, rarity)
        name = random.choice(SPECIES_NAMES[species])
        personality = random.choice(PERSONALITIES)

        self.companion = Companion(rarity=rarity, species=species, eye=eye, hat=hat,
                                   shiny=shiny, stats=stats, name=name, personality=personality)
        self._save_data()
        return self.companion

    def interact(self, action: str) -> str:
        if not self.companion:
            return "你还没有宠物，先获取一个吧！"
        effects = {"feed": (20, 10, 5, "开心地吃着食物"), "play": (-15, 25, 10, "玩得跑来跑去"),
                   "pet": (0, 15, 3, "享受地闭上眼睛"), "talk": (0, 0, 2, "歪着头看着你")}
        if action not in effects:
            return "试试 feed、play、pet 或 talk 吧！"
        energy_delta, happiness_delta, exp, response = effects[action]
        c = self.companion
        c.stats.setdefault("energy", 50)
        c.stats.setdefault("happiness", 50)
        c.stats.setdefault("friendship", 50)
        c.stats.setdefault("intelligence", 50)
        c.stats.setdefault("curiosity", 50)
        c.stats["energy"] = max(0, min(100, c.stats["energy"] + energy_delta))
        c.stats["happiness"] = min(100, c.stats["happiness"] + happiness_delta)
        c.experience += exp
        c.mood = "happy"
        if c.experience >= 100:
            c.level += 1
            c.experience -= 100
            for k in c.stats:
                c.stats[k] = min(100, c.stats[k] + 5)
        self._save_data()
        return f"宠物{response}！"

    def get_status(self) -> str:
        if not self.companion:
            return "你还没有宠物。"
        c = self.companion
        lines = [f"🐾 {c.name} | {c.species.value} | {c.rarity.value}",
                 f"等级: {c.level} | 经验: {c.experience}/100 | 心情: {c.mood}",
                 f"性格: {c.personality}",
                 f"属性: " + " | ".join(f"{k}: {v}" for k, v in c.stats.items())]
        return "\n".join(lines)


def create_buddy_manager(project_root: str) -> BuddyManager:
    return BuddyManager(project_root)
