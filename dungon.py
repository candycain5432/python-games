#!/usr/bin/env python3
"""
dungeon.py -- a text adventure / dungeon crawler.

Pure standard library. No dependencies.

Run:      python3 dungeon.py
Selftest: python3 dungeon.py --selftest    (scripted playthrough, asserts a win)

ARCHITECTURE
------------
DATA (top of file)   ITEMS / MONSTERS / ROOMS -- the whole dungeon, as dicts.
                     Nothing below this section names a specific room.

STATE (Game.state)   One nested dict of primitives. No object references,
                     no cycles. That single constraint is why save/load is
                     literally json.dump(self.state, f).

ENGINE (class Game)  Game.do(line) -> str. Takes a command, returns the text
                     to show. It never calls print() and never calls input().
                     The REPL at the bottom does the I/O; selftest() drives
                     the exact same method with a scripted list of commands.

The engine/IO split is the same idea as separating physics from rendering:
if the logic never touches the terminal, you can test the whole game
without one.
"""

from __future__ import annotations

import json
import os
import random
import sys
import textwrap

SAVE_FILE = "dungeon_save.json"
WRAP = 76

# ============================================================================
# DATA: ITEMS
# kind drives behaviour. The engine switches on kind, never on item id.
#   weapon  -> dmg (lo, hi)      wieldable
#   armor   -> defense           wearable
#   potion  -> heal              drinkable
#   light   -> can be lit
#   key     -> opens a matching locked exit
#   treasure-> value in gold when you carry it out
#   quest   -> the win condition
# ============================================================================

ITEMS = {
    "lantern": {
        "name": "brass lantern",
        "desc": "A dented brass lantern with a stub of candle in it. Still has a wick.",
        "kind": "light",
    },
    "potion": {
        "name": "vial of red liquid",
        "desc": "Sharp-smelling and faintly warm. Almost certainly a healing draught.",
        "kind": "potion", "heal": 25,
    },
    "rusty_sword": {
        "name": "rusty sword",
        "desc": "Pitted and blunt, but it is a great deal better than your knuckles.",
        "kind": "weapon", "dmg": (3, 7),
    },
    "steel_sword": {
        "name": "steel longsword",
        "desc": "Oiled, unblemished, and far too well kept for a place this dead.",
        "kind": "weapon", "dmg": (7, 13),
    },
    "bone_axe": {
        "name": "bone axe",
        "desc": "A crude thing lashed together from a femur and a wedge of flint.",
        "kind": "weapon", "dmg": (5, 9),
    },
    "leather_vest": {
        "name": "leather vest",
        "desc": "Cracked with age, but the stitching holds.",
        "kind": "armor", "defense": 1,
    },
    "chainmail": {
        "name": "chainmail hauberk",
        "desc": "Heavy, cold, and mercifully free of rust.",
        "kind": "armor", "defense": 3,
    },
    "iron_key": {
        "name": "iron key",
        "desc": "Black iron, warm to the touch. The bit is shaped like a tooth.",
        "kind": "key",
    },
    "brass_key": {
        "name": "brass key",
        "desc": "Small and bright, hanging from a scrap of green ribbon.",
        "kind": "key",
    },
    "silver_pearl": {
        "name": "silver pearl",
        "desc": "It sits in your palm like a drop of frozen moonlight.",
        "kind": "treasure", "value": 60,
    },
    "gold_circlet": {
        "name": "gold circlet",
        "desc": "Thin, plain, and worth more than the house you grew up in.",
        "kind": "treasure", "value": 120,
    },
    "amulet": {
        "name": "Amulet of Dun Morrah",
        "desc": ("A black stone in a claw of silver. Looking at it too long makes "
                 "the back of your skull ache. This is what you came for."),
        "kind": "quest",
    },
    "cheese": {
        "name": "mouldy cheese",
        "desc": "Green. Furry. Assertive.",
        "kind": "junk",
    },
}

# ============================================================================
# DATA: MONSTERS
#   hp      starting hit points
#   dmg     (lo, hi) damage roll
#   defense subtracted from incoming damage
#   acc     chance to hit you, 0..1
#   xp      awarded on kill
#   drops   item ids added to the room when it dies
# ============================================================================

MONSTERS = {
    "skeleton": {
        "name": "rattling skeleton",
        "desc": "Yellowed bones held together by nothing you care to think about.",
        "hp": 20, "dmg": (2, 5), "defense": 0, "acc": 0.65, "xp": 20,
        "drops": ["iron_key"],
    },
    "rat": {
        "name": "bloated rat",
        "desc": "Wet fur, too many teeth, and an air of grievance.",
        "hp": 12, "dmg": (1, 4), "defense": 0, "acc": 0.55, "xp": 10,
        "drops": ["cheese"],
    },
    "ghoul": {
        "name": "grave ghoul",
        "desc": "Long-armed and grey, crouched over something it does not want to share.",
        "hp": 34, "dmg": (4, 9), "defense": 1, "acc": 0.70, "xp": 40,
        "drops": ["brass_key"],
    },
    "goblin_chief": {
        "name": "goblin chieftain",
        "desc": "Squat, scarred, and wearing a crown made of cutlery.",
        "hp": 46, "dmg": (5, 11), "defense": 2, "acc": 0.70, "xp": 60,
        "drops": ["bone_axe", "gold_circlet"],
    },
    "lich": {
        "name": "Lich of Dun Morrah",
        "desc": ("What is left of a king, wrapped in a robe that moves when the air "
                 "does not. The amulet at its throat is the only thing in the room "
                 "with any colour."),
        "hp": 80, "dmg": (8, 15), "defense": 3, "acc": 0.75, "xp": 200,
        "drops": ["amulet"],
    },
}

# ============================================================================
# DATA: ROOMS -- the entire map. Note that nothing outside this dict knows
# any of these ids exist.
#   exits   direction -> room id
#   locked  direction -> key item id (auto-opens if you are carrying it)
#   items   visible on the floor
#   hidden  revealed by SEARCH
#   monster monster id, or None
#   dark    True means you need a lit light source to see anything
#   heal    a one-shot full heal (shrine)
# ============================================================================

ROOMS = {
    "entrance": {
        "name": "Crumbling Entrance",
        "desc": ("Daylight leaks through a collapsed archway behind you. Ahead, a "
                 "throat of worked stone descends north into the dark. Someone has "
                 "scratched a warning into the lintel in a language you do not read, "
                 "which is probably for the best."),
        "exits": {"north": "hall", "south": "OUT"},
        "items": ["lantern", "potion", "rusty_sword", "leather_vest"],
    },
    "hall": {
        "name": "Hall of Broken Pillars",
        "desc": ("Six pillars, four of them stumps. The floor is a mosaic of some "
                 "coronation, worn down to grout and suggestion. Air moves here, "
                 "which means this place is not sealed."),
        "exits": {"south": "entrance", "east": "guardroom", "west": "cistern",
                  "north": "gallery"},
    },
    "guardroom": {
        "name": "Guard Room",
        "desc": ("A rack of rotted spear-shafts. A stool. A bowl with something in it "
                 "that stopped being soup a long time ago."),
        "exits": {"west": "hall"},
        "items": ["potion"],
        "monster": "skeleton",
    },
    "cistern": {
        "name": "Flooded Cistern",
        "desc": ("Ankle-deep water, black and perfectly still until you disturb it. "
                 "The ceiling is lost somewhere above. Every sound you make comes "
                 "back three times."),
        "exits": {"east": "hall"},
        "dark": True,
        "monster": "rat",
        "hidden": ["silver_pearl"],
    },
    "gallery": {
        "name": "Gallery of Statues",
        "desc": ("Two rows of kneeling figures, faces filed smooth. They are all "
                 "facing east, toward a low door bound in black iron."),
        "exits": {"south": "hall", "east": "crypt", "north": "shrine"},
        "locked": {"east": "iron_key"},
    },
    "crypt": {
        "name": "Bone Crypt",
        "desc": ("Shelves cut into the rock, each with an occupant, none of them "
                 "tidy. Something has been through here sorting the remains by size."),
        "exits": {"west": "gallery"},
        "monster": "ghoul",
    },
    "shrine": {
        "name": "Drowned Shrine",
        "desc": ("A basin of clear water fed by nothing, set before a god whose name "
                 "has been chiselled out. The water is the only clean thing you have "
                 "seen since the entrance."),
        "exits": {"south": "gallery", "north": "chasm", "east": "armory"},
        "locked": {"east": "brass_key"},
        "heal": True,
    },
    "chasm": {
        "name": "Chasm Bridge",
        "desc": ("A slab of stone spans a gap you cannot see the bottom of. There is "
                 "no rail. There is a draught coming up, which is somehow worse than "
                 "if there were not."),
        "exits": {"south": "shrine", "north": "warren"},
        "dark": True,
        "hidden": ["potion"],
    },
    "warren": {
        "name": "Goblin Warren",
        "desc": ("Bedding, bones, and a firepit still warm. Someone has been living "
                 "down here, and living reasonably well, by the standards of a hole."),
        "exits": {"south": "chasm", "north": "stair"},
        "monster": "goblin_chief",
    },
    "armory": {
        "name": "Sealed Armory",
        "desc": ("Racks, mostly empty, but the air is dry and someone has kept the "
                 "oil topped up. Two things here are still worth carrying."),
        "exits": {"west": "shrine"},
        "items": ["steel_sword", "chainmail"],
    },
    "stair": {
        "name": "Spiral Stair",
        "desc": ("Steps worn into shallow bowls, winding down further than they have "
                 "any business going. The cold coming up them is not the cold of stone."),
        "exits": {"south": "warren", "north": "throne"},
    },
    "throne": {
        "name": "Throne of Dun Morrah",
        "desc": ("A vaulted hall, and at the end of it a seat of black stone. The "
                 "torches burn without heat and cast no shadow whatsoever, which you "
                 "notice a moment before you notice the thing sitting on the throne."),
        "exits": {"south": "stair"},
        "monster": "lich",
    },
}

DIRECTIONS = ("north", "south", "east", "west", "up", "down")

# Synonym table: many words in, one canonical verb out. Growing the game's
# vocabulary means adding a line here, never touching the parser.
SYNONYMS = {
    "n": "north", "s": "south", "e": "east", "w": "west",
    "u": "up", "d": "down",
    "l": "look", "examine": "look", "x": "look", "inspect": "look", "read": "look",
    "get": "take", "grab": "take", "pick": "take",
    "i": "inventory", "inv": "inventory", "items": "inventory",
    "wield": "equip", "hold": "equip", "wear": "equip", "don": "equip",
    "drink": "use", "quaff": "use", "eat": "use", "light": "use", "apply": "use",
    "hit": "attack", "fight": "attack", "kill": "attack", "a": "attack",
    "run": "flee", "escape": "flee", "retreat": "flee",
    "walk": "go", "move": "go", "head": "go", "travel": "go",
    "stats": "status", "hp": "status", "me": "status",
    "h": "help", "?": "help", "commands": "help",
    "q": "quit", "exit": "quit",
    "wait": "rest", "z": "rest",
}

# Words that carry no meaning and are stripped before parsing.
NOISE = {"the", "a", "an", "at", "to", "on", "with", "my", "of", "into", "up"}

FISTS = {"name": "bare fists", "dmg": (1, 4)}


def wrap(text: str) -> str:
    """Wrap a paragraph to a readable width. Blank lines are preserved."""
    out = []
    for para in text.split("\n"):
        out.append(textwrap.fill(para, WRAP) if para.strip() else "")
    return "\n".join(out)


def roll(lo: int, hi: int) -> int:
    return random.randint(lo, hi)


def xp_for_level(level: int) -> int:
    """
    XP needed to reach the NEXT level.

    This started out quadratic (30 * level^2) and it was wrong: the player
    was still level 2 when they reached the boss, so none of the level-up
    rewards ever landed where they mattered. Linear puts level 3 right
    before the throne room, which is where the extra HP is needed.
    """
    return 40 * level


class Game:
    # ------------------------------------------------------------------ setup

    def __init__(self):
        self.state = self.new_state()
        self.running = True
        self.won = False
        # The dispatch table. A verb is a dict key, not an elif branch.
        self.commands = {
            "look": self.cmd_look,
            "go": self.cmd_go,
            "take": self.cmd_take,
            "drop": self.cmd_drop,
            "inventory": self.cmd_inventory,
            "equip": self.cmd_equip,
            "use": self.cmd_use,
            "attack": self.cmd_attack,
            "flee": self.cmd_flee,
            "search": self.cmd_search,
            "status": self.cmd_status,
            "map": self.cmd_map,
            "rest": self.cmd_rest,
            "help": self.cmd_help,
            "save": self.cmd_save,
            "load": self.cmd_load,
            "quit": self.cmd_quit,
        }

    @staticmethod
    def new_state() -> dict:
        """
        Build the mutable world from the immutable templates above.

        Everything here is a dict, list, str, int or bool -- deliberately.
        That is the whole reason save/load is a one-liner.
        """
        rooms = {}
        for rid, tpl in ROOMS.items():
            room = {
                "items": list(tpl.get("items", [])),
                "hidden": list(tpl.get("hidden", [])),
                "searched": False,
                "visited": False,
                "unlocked": [],
                "monster": None,
            }
            mid = tpl.get("monster")
            if mid:
                m = dict(MONSTERS[mid])
                m["id"] = mid
                m["max_hp"] = m["hp"]
                room["monster"] = m
            rooms[rid] = room

        return {
            "rooms": rooms,
            "player": {
                "room": "entrance",
                "prev_room": "entrance",
                "hp": 40, "max_hp": 40,
                "level": 1, "xp": 0, "gold": 0,
                "inventory": [],
                "weapon": None,
                "armor": None,
                "lit": False,
            },
            "flags": {},
            "turns": 0,
        }

    # -------------------------------------------------------------- accessors

    @property
    def p(self) -> dict:
        return self.state["player"]

    @property
    def room(self) -> dict:
        """Mutable per-playthrough room state."""
        return self.state["rooms"][self.p["room"]]

    @property
    def tpl(self) -> dict:
        """Immutable room template (name, desc, exits, locks)."""
        return ROOMS[self.p["room"]]

    def monster(self):
        """The living monster in this room, or None."""
        m = self.room["monster"]
        return m if m and m["hp"] > 0 else None

    def is_dark(self) -> bool:
        return bool(self.tpl.get("dark")) and not self.p["lit"]

    def defense(self) -> int:
        a = self.p["armor"]
        return ITEMS[a]["defense"] if a else 0

    def weapon(self) -> dict:
        w = self.p["weapon"]
        return ITEMS[w] if w else FISTS

    # ---------------------------------------------------------- name matching

    def item_name(self, iid: str) -> str:
        return ITEMS[iid]["name"]

    def match_item(self, noun: str, pool) -> str | None:
        """
        Fuzzy-match typed words against a pool of item ids.

        Exact id and exact name win first; then any-word-substring. This is why
        'take sword', 'take rusty', and 'take rusty_sword' all work, and why you
        never have to learn the internal ids.
        """
        if not noun:
            return None
        noun = noun.strip().lower()
        pool = list(pool)
        for iid in pool:
            if noun == iid or noun == ITEMS[iid]["name"].lower():
                return iid
        for iid in pool:
            if noun in ITEMS[iid]["name"].lower() or noun in iid.replace("_", " "):
                return iid
        words = noun.split()
        for iid in pool:
            hay = (ITEMS[iid]["name"] + " " + iid.replace("_", " ")).lower()
            if any(w in hay for w in words):
                return iid
        return None

    # ------------------------------------------------------------ description

    def describe_room(self, brief: bool = False) -> str:
        if self.is_dark():
            return wrap("It is pitch black. You can feel walls, and a floor, and "
                        "very little enthusiasm. You need a light down here.")

        r, t = self.room, self.tpl
        out = [f"== {t['name']} =="]
        if not brief or not r["visited"]:
            out.append(wrap(t["desc"]))

        if r["items"]:
            names = [self.item_name(i) for i in r["items"]]
            out.append(wrap("You can see: " + ", ".join(names) + "."))

        m = self.monster()
        if m:
            out.append(wrap(f"A {m['name']} is here. {m['desc']}"))
            out.append(wrap(f"It blocks your way. ({m['hp']}/{m['max_hp']} hp)"))

        exits = []
        for d, dest in t.get("exits", {}).items():
            if dest == "OUT":
                exits.append(f"{d} (out of the dungeon)")
            elif d in t.get("locked", {}) and d not in r["unlocked"]:
                exits.append(f"{d} (locked)")
            else:
                exits.append(d)
        out.append("Exits: " + (", ".join(exits) if exits else "none"))
        return "\n".join(out)

    # ----------------------------------------------------------------- parser

    def do(self, line: str) -> str:
        """
        Take one line of player input, return the text to display.

        Never prints. Never reads stdin. That is what makes selftest() possible
        and what would let you drop a different front end on top of this.
        """
        self.state["turns"] += 1
        tokens = [w for w in line.strip().lower().replace(",", " ").split()]
        tokens = [SYNONYMS.get(w, w) for w in tokens]
        tokens = [w for i, w in enumerate(tokens) if w not in NOISE or i == 0]
        if not tokens:
            return "Say something."

        verb, noun = tokens[0], " ".join(tokens[1:])

        # A bare direction is shorthand for "go <direction>".
        if verb in DIRECTIONS:
            return self.cmd_go(verb)
        if verb == "go" and not noun:
            return "Go where?"

        fn = self.commands.get(verb)
        if fn is None:
            return f"I don't know how to '{verb}'. Try HELP."
        return fn(noun)

    # --------------------------------------------------------------- commands

    def cmd_look(self, noun: str) -> str:
        if not noun:
            return self.describe_room()
        if self.is_dark():
            return "You can't see a thing."

        m = self.monster()
        if m and (noun in m["name"].lower() or noun in m["id"]):
            return wrap(f"{m['desc']} It has {m['hp']} of {m['max_hp']} hit points left.")

        iid = self.match_item(noun, self.room["items"] + self.p["inventory"])
        if not iid:
            return f"You don't see any {noun} here."

        it = ITEMS[iid]
        bits = [it["desc"]]
        if it["kind"] == "weapon":
            bits.append(f"Damage {it['dmg'][0]}-{it['dmg'][1]}.")
        elif it["kind"] == "armor":
            bits.append(f"Defense {it['defense']}.")
        elif it["kind"] == "potion":
            bits.append(f"Restores {it['heal']} hit points.")
        elif it["kind"] == "treasure":
            bits.append(f"Worth about {it['value']} gold.")
        return wrap(" ".join(bits))

    def cmd_go(self, noun: str) -> str:
        d = SYNONYMS.get(noun, noun).strip()
        if d not in DIRECTIONS:
            return f"'{noun}' is not a direction."

        m = self.monster()
        if m:
            return wrap(f"The {m['name']} blocks your way. Fight it or FLEE.")

        dest = self.tpl.get("exits", {}).get(d)
        if dest is None:
            return "You can't go that way."

        # Auto-unlock: carrying the key IS opening the door. A separate UNLOCK
        # verb would add a step that never has an interesting wrong answer.
        need = self.tpl.get("locked", {}).get(d)
        if need and d not in self.room["unlocked"]:
            if need in self.p["inventory"]:
                self.room["unlocked"].append(d)
                unlocked = wrap(f"You fit the {self.item_name(need)} to the lock. "
                                f"It turns with a sound like a swallowed cough.\n")
            else:
                return wrap("That way is locked. Something with a proper key has "
                            "been through here before you.")
        else:
            unlocked = ""

        if dest == "OUT":
            return unlocked + self.leave_dungeon()

        self.p["prev_room"] = self.p["room"]
        self.p["room"] = dest
        first = not self.room["visited"]
        self.room["visited"] = True

        out = unlocked + self.describe_room(brief=not first)
        out += self.check_shrine()
        return out

    def leave_dungeon(self) -> str:
        """South from the entrance. Winning requires the amulet."""
        loot = sum(ITEMS[i].get("value", 0) for i in self.p["inventory"])
        if "amulet" not in self.p["inventory"]:
            return wrap("You could walk out. The archway is right there, and the "
                        "daylight past it is real. But you came for the amulet, and "
                        "without it this was just a long walk in a cold building. "
                        "(Get the amulet first.)")
        self.won = True
        self.running = False
        total = self.p["gold"] + loot
        return wrap(
            "You climb out into a morning that has been going on without you.\n\n"
            "The amulet is heavy in your pack and quieter up here, as if it is "
            "waiting to see what you do next. Behind you, Dun Morrah settles a "
            "little further into the hill.\n\n"
            f"*** YOU WIN ***\n"
            f"Level {self.p['level']} | {total} gold | {self.state['turns']} turns"
        )

    def check_shrine(self) -> str:
        """One-shot full heal. The flag is what makes it one-shot."""
        if not self.tpl.get("heal"):
            return ""
        key = "shrine_used_" + self.p["room"]
        if self.state["flags"].get(key):
            return "\n" + wrap("The basin is empty now. Whatever was in it, you had it.")
        self.state["flags"][key] = True
        self.p["hp"] = self.p["max_hp"]
        return "\n" + wrap("You drink. The cold goes all the way down and keeps "
                           f"going, and when it stops you are whole again. "
                           f"({self.p['hp']}/{self.p['max_hp']} hp)")

    def cmd_take(self, noun: str) -> str:
        if self.is_dark():
            return "You grope around and find nothing but wet stone."
        if not noun:
            return "Take what?"
        if noun in ("all", "everything"):
            if not self.room["items"]:
                return "There is nothing here to take."
            got = [self.item_name(i) for i in self.room["items"]]
            self.p["inventory"].extend(self.room["items"])
            self.room["items"] = []
            return wrap("Taken: " + ", ".join(got) + ".")

        iid = self.match_item(noun, self.room["items"])
        if not iid:
            return f"There is no {noun} here."
        self.room["items"].remove(iid)
        self.p["inventory"].append(iid)
        return f"Taken: {self.item_name(iid)}."

    def cmd_drop(self, noun: str) -> str:
        iid = self.match_item(noun, self.p["inventory"])
        if not iid:
            return f"You aren't carrying a {noun}."
        self.p["inventory"].remove(iid)
        self.room["items"].append(iid)
        if self.p["weapon"] == iid:
            self.p["weapon"] = None
        if self.p["armor"] == iid:
            self.p["armor"] = None
        if ITEMS[iid]["kind"] == "light":
            self.p["lit"] = False
        return f"Dropped: {self.item_name(iid)}."

    def cmd_inventory(self, noun: str) -> str:
        if not self.p["inventory"]:
            return "You are carrying nothing at all. Bold."
        lines = ["You are carrying:"]
        for iid in self.p["inventory"]:
            tag = ""
            if iid == self.p["weapon"]:
                tag = "  (wielded)"
            elif iid == self.p["armor"]:
                tag = "  (worn)"
            elif ITEMS[iid]["kind"] == "light" and self.p["lit"]:
                tag = "  (lit)"
            lines.append(f"  - {self.item_name(iid)}{tag}")
        lines.append(f"Gold: {self.p['gold']}")
        return "\n".join(lines)

    def cmd_equip(self, noun: str) -> str:
        iid = self.match_item(noun, self.p["inventory"])
        if not iid:
            return f"You aren't carrying a {noun}."
        kind = ITEMS[iid]["kind"]
        if kind == "weapon":
            self.p["weapon"] = iid
            lo, hi = ITEMS[iid]["dmg"]
            return f"You wield the {self.item_name(iid)}. (damage {lo}-{hi})"
        if kind == "armor":
            self.p["armor"] = iid
            return (f"You put on the {self.item_name(iid)}. "
                    f"(defense {ITEMS[iid]['defense']})")
        return f"You can't wear or wield the {self.item_name(iid)}."

    def cmd_use(self, noun: str) -> str:
        iid = self.match_item(noun, self.p["inventory"])
        if not iid:
            return f"You aren't carrying a {noun}."
        it = ITEMS[iid]

        if it["kind"] == "potion":
            before = self.p["hp"]
            self.p["hp"] = min(self.p["max_hp"], self.p["hp"] + it["heal"])
            self.p["inventory"].remove(iid)
            gained = self.p["hp"] - before
            out = wrap(f"You drink it. It tastes of hot iron. (+{gained} hp, now "
                       f"{self.p['hp']}/{self.p['max_hp']})")
            return out + self.monster_turn()

        if it["kind"] == "light":
            if self.p["lit"]:
                self.p["lit"] = False
                return "You shutter the lantern."
            self.p["lit"] = True
            out = "You light the lantern. The dark backs off, reluctantly."
            if self.tpl.get("dark"):
                out += "\n\n" + self.describe_room()
            return out

        return f"You can't think of anything to do with the {self.item_name(iid)}."

    def cmd_search(self, noun: str) -> str:
        if self.is_dark():
            return "You'd need to see to search."
        r = self.room
        if r["searched"]:
            return "You have already been over this room. There is nothing else."
        r["searched"] = True
        if not r["hidden"]:
            return "You turn the place over and find nothing worth the effort."
        found = r["hidden"]
        r["items"].extend(found)
        r["hidden"] = []
        names = ", ".join(self.item_name(i) for i in found)
        return wrap(f"You dig through the mess and turn up: {names}.")

    def cmd_status(self, noun: str) -> str:
        p = self.p
        w = self.weapon()
        need = xp_for_level(p["level"])
        return "\n".join([
            f"HP      {p['hp']}/{p['max_hp']}",
            f"Level   {p['level']}   XP {p['xp']}/{need}",
            f"Weapon  {w['name']} ({w['dmg'][0]}-{w['dmg'][1]} damage, "
            f"+{p['level'] - 1} from level)",
            f"Armor   {ITEMS[p['armor']]['name'] if p['armor'] else 'none'} "
            f"(defense {self.defense()})",
            f"Gold    {p['gold']}",
            f"Turns   {self.state['turns']}",
        ])

    def cmd_map(self, noun: str) -> str:
        """
        Lists visited rooms and their known connections.

        No ASCII map: the world is a graph, and graphs do not have a canonical
        2D layout. An honest list beats a diagram that lies about geometry.
        """
        lines = ["Places you have been:"]
        for rid, r in self.state["rooms"].items():
            if not r["visited"] and rid != self.p["room"]:
                continue
            here = "  <- you are here" if rid == self.p["room"] else ""
            lines.append(f"\n  {ROOMS[rid]['name']}{here}")
            for d, dest in ROOMS[rid].get("exits", {}).items():
                if dest == "OUT":
                    label = "the way out"
                elif self.state["rooms"].get(dest, {}).get("visited"):
                    label = ROOMS[dest]["name"]
                else:
                    label = "somewhere you haven't been"
                lock = ""
                if d in ROOMS[rid].get("locked", {}) and d not in r["unlocked"]:
                    lock = " [locked]"
                lines.append(f"      {d:<6} -> {label}{lock}")
        return "\n".join(lines)

    def cmd_rest(self, noun: str) -> str:
        if self.monster():
            return wrap("Not with that thing in the room with you.")
        healed = min(4, self.p["max_hp"] - self.p["hp"])
        self.p["hp"] += healed
        if healed:
            return f"You sit a while. (+{healed} hp, now {self.p['hp']}/{self.p['max_hp']})"
        return "You rest. Nothing improves, because nothing needed to."

    def cmd_help(self, noun: str) -> str:
        return "\n".join([
            "Commands (most have short forms and synonyms):",
            "  LOOK / L                  describe the room",
            "  LOOK <thing> / X <thing>  examine an item or monster",
            "  NORTH SOUTH EAST WEST     move (or N/S/E/W, or GO NORTH)",
            "  TAKE <item> / TAKE ALL    pick things up",
            "  DROP <item>               put something down",
            "  INVENTORY / I             what you're carrying",
            "  EQUIP <item>              wield a weapon or wear armor",
            "  USE <item>                drink a potion, light the lantern",
            "  ATTACK                    swing at whatever is in the room",
            "  FLEE                      try to get out of a fight",
            "  SEARCH                    turn the room over for hidden things",
            "  REST                      recover a little health",
            "  STATUS / MAP              your sheet, and where you've been",
            "  SAVE / LOAD / QUIT",
            "",
            "Locked doors open on their own if you are carrying the right key.",
        ])

    # ----------------------------------------------------------- save / load
    # This is the payoff for keeping every piece of state as plain data.

    def cmd_save(self, noun: str) -> str:
        try:
            with open(SAVE_FILE, "w") as f:
                json.dump(self.state, f, indent=1)
            return f"Saved to {SAVE_FILE}."
        except OSError as e:
            return f"Couldn't save: {e}"

    def cmd_load(self, noun: str) -> str:
        if not os.path.exists(SAVE_FILE):
            return "There is no save file."
        try:
            with open(SAVE_FILE) as f:
                self.state = json.load(f)
            return "Loaded.\n\n" + self.describe_room()
        except (OSError, ValueError) as e:
            return f"Couldn't load: {e}"

    def cmd_quit(self, noun: str) -> str:
        self.running = False
        return "You turn back. The dungeon does not object."

    # ---------------------------------------------------------------- combat
    # Resolution and narration are separate on purpose: resolve_hit() returns
    # a number and mutates nothing you can't test, and the cmd_* functions
    # decide what to say about it.

    @staticmethod
    def resolve_hit(dmg_lo: int, dmg_hi: int, bonus: int, defense: int) -> int:
        """Roll damage, subtract armor, never go below 1. Pure arithmetic."""
        return max(1, roll(dmg_lo, dmg_hi) + bonus - defense)

    def cmd_attack(self, noun: str) -> str:
        m = self.monster()
        if not m:
            return "There is nothing here to fight."

        w = self.weapon()
        lines = []
        if random.random() < 0.85:
            dmg = self.resolve_hit(w["dmg"][0], w["dmg"][1],
                                   self.p["level"] - 1, m["defense"])
            m["hp"] -= dmg
            lines.append(wrap(f"You strike the {m['name']} with your {w['name']} "
                              f"for {dmg} damage."))
        else:
            lines.append(wrap(f"You swing and the {m['name']} isn't where you "
                              f"aimed."))

        if m["hp"] <= 0:
            m["hp"] = 0
            lines.append(self.kill(m))
            return "\n".join(lines)

        lines.append(f"({m['name']}: {m['hp']}/{m['max_hp']} hp)")
        lines.append(self.monster_turn().lstrip("\n"))
        return "\n".join(x for x in lines if x)

    def monster_turn(self) -> str:
        """The monster's free swing. Called after any action that costs a turn."""
        m = self.monster()
        if not m:
            return ""
        if random.random() >= m["acc"]:
            return "\n" + wrap(f"The {m['name']} comes at you and misses.")
        dmg = self.resolve_hit(m["dmg"][0], m["dmg"][1], 0, self.defense())
        self.p["hp"] -= dmg
        out = "\n" + wrap(f"The {m['name']} hits you for {dmg}. "
                          f"({max(0, self.p['hp'])}/{self.p['max_hp']} hp)")
        if self.p["hp"] <= 0:
            out += "\n" + self.die()
        elif self.p["hp"] <= self.p["max_hp"] * 0.25:
            out += "\n" + wrap("You are badly hurt. Consider a potion, or the door.")
        return out

    def kill(self, m: dict) -> str:
        lines = [wrap(f"The {m['name']} comes apart and stays down.")]
        self.p["xp"] += m["xp"]
        lines.append(f"(+{m['xp']} xp)")
        if m["drops"]:
            self.room["items"].extend(m["drops"])
            names = ", ".join(self.item_name(i) for i in m["drops"])
            lines.append(wrap(f"It leaves behind: {names}."))
        lines.append(self.check_level())
        return "\n".join(x for x in lines if x)

    def check_level(self) -> str:
        """Loop, not if -- a big kill can carry you through two levels at once."""
        out = []
        while self.p["xp"] >= xp_for_level(self.p["level"]):
            self.p["xp"] -= xp_for_level(self.p["level"])
            self.p["level"] += 1
            self.p["max_hp"] += 12
            self.p["hp"] = self.p["max_hp"]
            out.append(wrap(f"*** You reach level {self.p['level']}. "
                            f"Max HP {self.p['max_hp']}, damage +1, and you feel "
                            f"briefly immortal. ***"))
        return "\n".join(out)

    def cmd_flee(self, noun: str) -> str:
        m = self.monster()
        if not m:
            return "There is nothing to flee from."
        if random.random() < 0.6:
            self.p["room"], self.p["prev_room"] = self.p["prev_room"], self.p["room"]
            return (wrap(f"You break away from the {m['name']} and get clear.")
                    + "\n\n" + self.describe_room(brief=True))
        return wrap("You turn to run and think better of it a moment too late.") \
            + self.monster_turn()

    def die(self) -> str:
        self.running = False
        return wrap(
            "Your legs go, and the floor is closer than you expected.\n\n"
            "*** YOU HAVE DIED ***\n"
            f"Level {self.p['level']} | {self.p['gold']} gold | "
            f"{self.state['turns']} turns"
        )


# ============================================================================
# REPL -- the only part of this file that does input/output
# ============================================================================

BANNER = """
  ____                   __  __                      _
 |  _ \\ _   _ _ __      |  \\/  | ___  _ __ _ __ __ _| |__
 | | | | | | | '_ \\     | |\\/| |/ _ \\| '__| '__/ _` | '_ \\
 | |_| | |_| | | | |    | |  | | (_) | |  | | | (_| | | | |
 |____/ \\__,_|_| |_|    |_|  |_|\\___/|_|  |_|  \\__,_|_| |_|

 Something down there is wearing the Amulet of Dun Morrah.
 Go and take it off him, then walk back out the way you came.

 Type HELP for commands.
"""


def main():
    game = Game()
    print(BANNER)
    game.state["rooms"]["entrance"]["visited"] = True
    print(game.describe_room())

    while game.running:
        try:
            line = input("\n> ")
        except (EOFError, KeyboardInterrupt):
            print("\nYou turn back.")
            break
        print()
        print(game.do(line))


# ============================================================================
# SELFTEST -- drives Game.do() with a scripted playthrough and asserts a win.
# Possible only because the engine never touches stdin or stdout.
# ============================================================================

# The route through the dungeon. FIGHT is not a game command -- it tells the
# test bot below to keep swinging until the room is clear, which is a far more
# honest test than hardcoding "attack" thirteen times and hoping.
WALKTHROUGH = [
    "take all", "equip rusty sword", "equip leather vest",
    "north", "east", "FIGHT", "take all",          # guardroom: skeleton
    "west", "west", "use lantern", "FIGHT",        # cistern: dark, rat
    "search", "take all",
    "east", "north", "east", "FIGHT", "take all",  # crypt (iron key): ghoul
    "west", "north",                               # shrine: full heal
    "east", "take all",                            # armory (brass key)
    "equip steel", "equip chainmail",
    "west", "north", "search", "take all",         # chasm
    "north", "FIGHT", "take all",                  # warren: goblin chieftain
    "north", "north", "FIGHT", "take amulet",      # stair -> throne: lich
    # Seven souths walks you from the throne back to the entrance; the eighth
    # is the one that actually takes you outside.
    "south", "south", "south", "south", "south", "south", "south", "south",
]


def bot_turn(g) -> str:
    """
    Decide one action the way a cautious player would: drink first if you are
    about to die and have something to drink, otherwise hit it.
    """
    if g.p["hp"] < g.p["max_hp"] * 0.35 and "potion" in g.p["inventory"]:
        return "use potion"
    return "attack"


def run_script(g, script, log=None):
    for cmd in script:
        if not g.running:
            break
        if cmd == "FIGHT":
            guard = 0
            while g.monster() and g.running:
                guard += 1
                assert guard < 200, "fight did not terminate -- check the damage math"
                out = g.do(bot_turn(g))
                if log is not None:
                    log.append(out)
        else:
            out = g.do(cmd)
            if log is not None:
                log.append(f"> {cmd}\n{out}")
    return g


def selftest():
    random.seed(20260910)
    g = Game()
    g.state["rooms"]["entrance"]["visited"] = True

    log = []
    run_script(g, WALKTHROUGH, log)

    print("--- final turns of the scripted run ---")
    print("\n".join(log[-4:]))
    print("---------------------------------------")

    p = g.p
    print(f"  won         {g.won}")
    print(f"  level       {p['level']}   hp {p['hp']}/{p['max_hp']}")
    print(f"  turns       {g.state['turns']}")
    print(f"  inventory   {[ITEMS[i]['name'] for i in p['inventory']]}")

    assert g.won, "the scripted walkthrough should finish the game"
    assert "amulet" in p["inventory"], "should be carrying the amulet at the end"

    # Parser: synonyms, noise words, casing and fuzzy nouns all land on the
    # same canonical command.
    g2 = Game()
    for phrasing in ["take the lantern", "GET LANTERN", "grab  brass  lantern",
                     "pick up the lantern"]:
        g3 = Game()
        assert "Taken" in g3.do(phrasing), f"parser failed on: {phrasing}"
    assert "brass lantern" in g2.do("take lantern")
    assert g2.do("x lantern").startswith("A dented"), "X should examine"
    assert "don't know how" in g2.do("xyzzy"), "unknown verbs should be handled"
    assert g2.do("go").startswith("Go where"), "bare GO should ask for a direction"
    print("  parser      synonyms, noise words, fuzzy nouns, bad verbs: OK")

    # Locked doors: blocked without the key, open with it, no UNLOCK needed.
    g4 = Game()
    g4.p["room"] = "gallery"
    assert "locked" in g4.do("east").lower(), "should be locked without the key"
    g4.p["inventory"].append("iron_key")
    assert g4.p["room"] == "gallery"
    g4.do("east")
    assert g4.p["room"] == "crypt", "the key should open the door automatically"
    print("  locked door blocked without key, auto-opened with it: OK")

    # Dark rooms.
    g5 = Game()
    g5.p["room"] = "cistern"
    assert "pitch black" in g5.do("look"), "dark room should hide its description"
    g5.p["inventory"].append("lantern")
    g5.do("use lantern")
    assert "Flooded Cistern" in g5.do("look"), "light should reveal the room"
    print("  darkness    hidden until lit: OK")

    # Save/load round trip through real JSON.
    g6 = Game()
    g6.p["room"] = "shrine"
    g6.p["gold"] = 77
    g6.p["inventory"] = ["potion", "steel_sword"]
    blob = json.dumps(g6.state)
    g7 = Game()
    g7.state = json.loads(blob)
    assert g7.p["room"] == "shrine" and g7.p["gold"] == 77
    assert g7.p["inventory"] == ["potion", "steel_sword"]
    print("  save/load   full state survives a JSON round trip: OK")

    # Every exit points at a room that exists, and every referenced item and
    # monster id is real. Catches typos in the data before a player does.
    for rid, t in ROOMS.items():
        for d, dest in t.get("exits", {}).items():
            assert dest == "OUT" or dest in ROOMS, f"{rid}.{d} -> missing room {dest}"
            assert d in DIRECTIONS, f"{rid} has a non-direction exit {d!r}"
        for d, key in t.get("locked", {}).items():
            assert d in t.get("exits", {}), f"{rid} locks a nonexistent exit {d}"
            assert key in ITEMS, f"{rid} needs a nonexistent key {key}"
        for iid in t.get("items", []) + t.get("hidden", []):
            assert iid in ITEMS, f"{rid} contains a nonexistent item {iid}"
        if t.get("monster"):
            assert t["monster"] in MONSTERS, f"{rid} has a nonexistent monster"
    for mid, m in MONSTERS.items():
        for iid in m["drops"]:
            assert iid in ITEMS, f"{mid} drops a nonexistent item {iid}"
    reachable, stack = {"entrance"}, ["entrance"]
    while stack:
        for dest in ROOMS[stack.pop()].get("exits", {}).values():
            if dest != "OUT" and dest not in reachable:
                reachable.add(dest)
                stack.append(dest)
    assert reachable == set(ROOMS), f"unreachable rooms: {set(ROOMS) - reachable}"
    print(f"  data        {len(ROOMS)} rooms, all links valid, all reachable: OK")

    print("\nselftest: all checks passed")


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        selftest()
    else:
        main()
