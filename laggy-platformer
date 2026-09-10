#!/usr/bin/env python3
"""
pyplatformer.py -- a 2D platformer with hand-written physics.

Requires: pygame  ->  pip install pygame
Run:      python3 pyplatformer.py
Selftest: python3 pyplatformer.py --selftest   (headless physics check, no window)

ARCHITECTURE
------------
Input     : a plain snapshot of what the player is pressing this frame.
Level     : the static tile grid (walls, one-way platforms, coins, spawn).
MovingPlatform : a solid box that moves along a line and carries the player.
Player    : position/velocity + all the physics and collision resolution.
World     : owns everything, has update(dt, inp) -- pure logic, zero drawing.
Renderer  : owns the camera and draws a World. Zero logic.

The split matters: because World.update() never touches the screen, the
physics can be tested headlessly (see selftest()) and you could swap the
renderer for a different one without touching a single line of game rules.
"""

from __future__ import annotations

import math
import random
import sys

import pygame

# ============================================================================
# TUNABLES -- everything you would ever want to fiddle with lives here.
# All units are pixels and seconds. px/s = velocity, px/s^2 = acceleration.
# ============================================================================

TILE = 32
SCREEN_W, SCREEN_H = 960, 640
FPS = 60

# If the game hitches (window drag, breakpoint), dt could spike to 2 seconds
# and the player would teleport through the floor. Clamping dt trades a tiny
# slow-motion effect for never tunneling through geometry.
MAX_DT = 1.0 / 30.0

# --- gravity ---------------------------------------------------------------
GRAVITY = 2200.0        # downward acceleration
MAX_FALL = 900.0        # terminal velocity, so long falls stay survivable

# --- horizontal movement ---------------------------------------------------
MAX_RUN = 320.0         # top running speed
RUN_ACCEL = 2400.0      # how hard you accelerate on the ground
RUN_DECEL = 3200.0      # ground friction when you let go
AIR_ACCEL = 1600.0      # weaker steering in the air...
AIR_DECEL = 500.0       # ...and much less drag, so you keep your momentum
TURN_BOOST = 1.8        # extra accel when reversing direction (feels snappy)

# --- jumping ---------------------------------------------------------------
# Jump height h = JUMP_SPEED^2 / (2 * GRAVITY)
#              = 660^2 / (2 * 2200) = 99px  ~= 3.1 tiles
JUMP_SPEED = 660.0
JUMP_CUT = 0.45         # vy multiplier when you release jump while rising
COYOTE_TIME = 0.10      # grace period to jump after leaving a ledge
JUMP_BUFFER = 0.12      # grace period to queue a jump before landing
DROP_TIME = 0.18        # how long one-way platforms stay disabled after down+jump

# --- camera ----------------------------------------------------------------
CAM_LERP = 7.0          # higher = snappier camera
CAM_LOOKAHEAD = 90.0    # camera leads the player in the direction they face

# --- palette ---------------------------------------------------------------
C_BG_TOP = (16, 18, 30)
C_BG_BOT = (40, 46, 72)
C_FAR = (26, 30, 48)
C_NEAR = (33, 38, 60)
C_TILE = (58, 66, 92)
C_TILE_TOP = (100, 114, 154)
C_ONEWAY = (150, 110, 66)
C_ONEWAY_TOP = (198, 154, 94)
C_PLAT = (60, 112, 128)
C_PLAT_TOP = (118, 194, 206)
C_PLAYER = (232, 104, 88)
C_PLAYER_DK = (176, 66, 58)
C_EYE = (250, 244, 236)
C_COIN = (246, 202, 84)
C_COIN_DK = (198, 148, 44)
C_TEXT = (222, 228, 244)
C_DUST = (150, 160, 190)

# ============================================================================
# LEVEL
# Legend:  '#' solid   '-' one-way platform   'o' coin   'P' spawn   '.' air
# Every row must be the same length; the constructor asserts it.
# ============================================================================

LEVEL_ROWS = [
    "############################################################",
    "#..........................................................#",
    "#..........................................................#",
    "#..........................................................#",
    "#..........................................................#",
    "#..........................................................#",
    "#.........................................o................#",
    "#.........................o..............######............#",
    "#.......................-----..............................#",
    "#...................................o......................#",
    "#..................................#####...................#",
    "#...............o...................................o......#",
    "#.............-----...............................-----....#",
    "#..........................................................#",
    "#.......o...............o..................................#",
    "#.....######..........#####.............######...........o.#",
    "#.......................................................####",
    "#..P..........................####......................####",
    "#.......................................................####",
    "###############################################....#########",
]

SOLID = "#"
ONEWAY = "-"
COIN = "o"
SPAWN = "P"


def aabb(ax, ay, aw, ah, bx, by, bw, bh) -> bool:
    """Axis-aligned bounding box overlap test. The workhorse of 2D collision."""
    return ax < bx + bw and ax + aw > bx and ay < by + bh and ay + ah > by


class Level:
    def __init__(self, rows):
        w = len(rows[0])
        assert all(len(r) == w for r in rows), "all level rows must be equal length"
        self.rows = rows
        self.cols = w
        self.h_tiles = len(rows)
        self.px_w = w * TILE
        self.px_h = self.h_tiles * TILE
        self.spawn = (2 * TILE, 2 * TILE)
        self.coin_cells = []
        for r, row in enumerate(rows):
            for c, ch in enumerate(row):
                if ch == SPAWN:
                    self.spawn = (c * TILE, r * TILE)
                elif ch == COIN:
                    self.coin_cells.append((c, r))

    def cells_overlapping(self, left, top, right, bottom):
        """
        Broadphase: yield only the tiles whose grid cells touch this box.
        Checking all 1200 tiles every frame would work at this size, but the
        habit of narrowing to a candidate set is what lets levels get big.
        """
        c0 = max(0, int(left // TILE))
        c1 = min(self.cols - 1, int((right - 1e-9) // TILE))
        r0 = max(0, int(top // TILE))
        r1 = min(self.h_tiles - 1, int((bottom - 1e-9) // TILE))
        for r in range(r0, r1 + 1):
            row = self.rows[r]
            for c in range(c0, c1 + 1):
                yield c, r, row[c]


# ============================================================================
# MOVING PLATFORM
# Ping-pongs between two points. Reports how far it moved this frame (dx, dy)
# so a player standing on it can be carried along.
# ============================================================================

class MovingPlatform:
    def __init__(self, x0, y0, x1, y1, w_tiles, speed):
        self.p0 = (float(x0), float(y0))
        self.p1 = (float(x1), float(y1))
        self.w = w_tiles * TILE
        self.h = TILE // 2
        self.speed = speed
        self.t = 0.0          # 0..1 along the segment
        self.dir = 1.0
        self.length = math.dist(self.p0, self.p1) or 1.0
        self.x, self.y = self.p0
        self.dx = 0.0
        self.dy = 0.0

    def update(self, dt):
        px, py = self.x, self.y
        self.t += self.dir * (self.speed / self.length) * dt
        if self.t >= 1.0:
            self.t, self.dir = 1.0, -1.0
        elif self.t <= 0.0:
            self.t, self.dir = 0.0, 1.0
        self.x = self.p0[0] + (self.p1[0] - self.p0[0]) * self.t
        self.y = self.p0[1] + (self.p1[1] - self.p0[1]) * self.t
        # Remember the delta so riders can be moved by the same amount.
        self.dx = self.x - px
        self.dy = self.y - py


# ============================================================================
# INPUT -- a dumb snapshot. Decoupling this from pygame's key state is what
# makes the headless selftest possible.
# ============================================================================

class Input:
    __slots__ = ("left", "right", "down", "jump_pressed", "jump_released")

    def __init__(self, left=False, right=False, down=False,
                 jump_pressed=False, jump_released=False):
        self.left = left
        self.right = right
        self.down = down
        self.jump_pressed = jump_pressed      # edge: key went down this frame
        self.jump_released = jump_released    # edge: key came up this frame


# ============================================================================
# PLAYER
# ============================================================================

class Player:
    W, H = 22.0, 44.0

    def __init__(self, x, y):
        self.x = float(x)
        self.y = float(y)
        self.vx = 0.0
        self.vy = 0.0
        self.on_ground = False
        self.ground_kind = None    # "solid" | "oneway" | "platform"
        self.ride = None           # MovingPlatform we're standing on, if any
        self.coyote = 0.0
        self.buffer = 0.0
        self.drop = 0.0            # >0 means one-ways are temporarily disabled
        self.facing = 1
        self.just_landed = False   # one-frame flag the renderer uses for dust

    # -- helpers ------------------------------------------------------------

    @property
    def cx(self):
        return self.x + self.W / 2

    @property
    def cy(self):
        return self.y + self.H / 2

    def _solid_boxes(self, world, include_oneway_for_dy=None):
        """
        Collect every box the player could currently be overlapping, as
        (x, y, w, h, owner). owner is a MovingPlatform, or None for a tile.

        include_oneway_for_dy: pass the vertical delta when resolving Y so we
        can decide whether one-way platforms count this frame. Pass None on
        the X pass -- one-ways never block horizontal movement.
        """
        boxes = []
        left, top = self.x, self.y
        right, bottom = self.x + self.W, self.y + self.H

        for c, r, ch in world.level.cells_overlapping(left, top, right, bottom):
            if ch == SOLID:
                boxes.append((c * TILE, r * TILE, TILE, TILE, None))
            elif ch == ONEWAY and include_oneway_for_dy is not None:
                # A one-way platform only exists if ALL of these hold:
                #   1. we're moving downward (you pass up through it freely)
                #   2. we were fully above its top edge before this step
                #   3. we're not currently dropping through on purpose
                dy = include_oneway_for_dy
                top_edge = r * TILE
                was_above = (bottom - dy) <= top_edge + 1.0
                if dy > 0 and was_above and self.drop <= 0.0:
                    boxes.append((c * TILE, top_edge, TILE, TILE, None))

        for p in world.platforms:
            if aabb(left, top, self.W, self.H, p.x, p.y, p.w, p.h):
                boxes.append((p.x, p.y, p.w, p.h, p))
        return boxes

    # -- axis-separated movement -------------------------------------------

    def move_x(self, dx, world):
        """Apply horizontal movement, then push out of anything we hit."""
        self.x += dx
        if dx == 0.0:
            return
        for bx, by, bw, bh, _ in self._solid_boxes(world):
            # Re-test: an earlier resolution may already have freed us.
            if not aabb(self.x, self.y, self.W, self.H, bx, by, bw, bh):
                continue
            if dx > 0:
                self.x = bx - self.W       # snap our right edge to its left
            else:
                self.x = bx + bw           # snap our left edge to its right
            self.vx = 0.0

    def move_y(self, dy, world):
        """Apply vertical movement, push out, and derive on_ground from it."""
        self.y += dy
        was_on_ground = self.on_ground
        self.on_ground = False
        self.ground_kind = None
        self.ride = None

        for bx, by, bw, bh, owner in self._solid_boxes(world, include_oneway_for_dy=dy):
            if not aabb(self.x, self.y, self.W, self.H, bx, by, bw, bh):
                continue
            if dy > 0:
                self.y = by - self.H       # landed: our feet sit on its top
                self.on_ground = True
                self.ride = owner
                if owner is not None:
                    self.ground_kind = "platform"
                elif world.level.rows[int(by // TILE)][int(bx // TILE)] == ONEWAY:
                    self.ground_kind = "oneway"
                else:
                    self.ground_kind = "solid"
            elif dy < 0:
                self.y = by + bh           # bonked our head on its underside
            self.vy = 0.0

        self.just_landed = self.on_ground and not was_on_ground

    # -- the main per-frame physics step ------------------------------------

    def update(self, dt, inp, world):
        # (0) Ride any platform we were standing on BEFORE we do our own
        #     physics, so the ground under us is where we expect it to be.
        if self.ride is not None:
            self.x += self.ride.dx
            self.y += self.ride.dy

        # (1) Tick the forgiveness timers.
        self.coyote = COYOTE_TIME if self.on_ground else max(0.0, self.coyote - dt)
        self.buffer = max(0.0, self.buffer - dt)
        self.drop = max(0.0, self.drop - dt)
        if inp.jump_pressed:
            self.buffer = JUMP_BUFFER

        # (2) Drop through a one-way platform: down + jump while standing on one.
        if inp.jump_pressed and inp.down and self.ground_kind == "oneway":
            self.drop = DROP_TIME
            self.buffer = 0.0              # consume the press, don't also jump
            self.on_ground = False
            self.coyote = 0.0

        # (3) Jump. Buffered press + (grounded OR still inside coyote window).
        if self.buffer > 0.0 and (self.on_ground or self.coyote > 0.0):
            self.vy = -JUMP_SPEED
            self.buffer = 0.0
            self.coyote = 0.0
            self.on_ground = False
            self.ride = None
            world.spawn_dust(self.cx, self.y + self.H, 6, up=False)

        # (4) Variable jump height: cut the rise short if they let go early.
        #     This is why a tap is a hop and a hold is a full jump.
        if inp.jump_released and self.vy < 0.0:
            self.vy *= JUMP_CUT

        # (5) Horizontal acceleration. Ground and air use different numbers --
        #     that difference IS the feel of the character.
        want = (1 if inp.right else 0) - (1 if inp.left else 0)
        accel = RUN_ACCEL if self.on_ground else AIR_ACCEL
        decel = RUN_DECEL if self.on_ground else AIR_DECEL

        if want != 0:
            self.facing = want
            # Reversing? Push harder, so turning around feels immediate
            # instead of mushy.
            if want * self.vx < 0:
                accel *= TURN_BOOST
            self.vx += want * accel * dt
            self.vx = max(-MAX_RUN, min(MAX_RUN, self.vx))
        else:
            # Friction: reduce speed toward zero without overshooting past it.
            if self.vx > 0:
                self.vx = max(0.0, self.vx - decel * dt)
            else:
                self.vx = min(0.0, self.vx + decel * dt)

        # (6) Gravity, clamped at terminal velocity.
        self.vy = min(MAX_FALL, self.vy + GRAVITY * dt)

        # (7) THE IMPORTANT PART: move and resolve one axis at a time.
        self.move_x(self.vx * dt, world)
        self.move_y(self.vy * dt, world)

        if self.just_landed:
            world.spawn_dust(self.cx, self.y + self.H, 10, up=True)


# ============================================================================
# COINS + PARTICLES -- small stuff, purely for feel
# ============================================================================

class Coin:
    R = 9

    def __init__(self, col, row):
        self.x = col * TILE + TILE / 2
        self.y = row * TILE + TILE / 2
        self.phase = random.uniform(0, math.tau)
        self.taken = False

    def bob_y(self, t):
        return self.y + math.sin(t * 3.0 + self.phase) * 4.0


class Particle:
    __slots__ = ("x", "y", "vx", "vy", "life", "max_life")

    def __init__(self, x, y, vx, vy, life):
        self.x, self.y, self.vx, self.vy = x, y, vx, vy
        self.life = self.max_life = life


# ============================================================================
# WORLD -- owns state, updates it, draws nothing
# ============================================================================

class World:
    def __init__(self):
        self.level = Level(LEVEL_ROWS)
        self.platforms = [
            # horizontal ferry across the long gap in the middle
            MovingPlatform(27 * TILE, 14 * TILE, 37 * TILE, 14 * TILE, 3, 120.0),
            # vertical lift over the pit near the end
            MovingPlatform(48 * TILE, 17 * TILE, 48 * TILE, 11 * TILE, 3, 90.0),
        ]
        self.coins = [Coin(c, r) for c, r in self.level.coin_cells]
        self.particles: list[Particle] = []
        self.player = Player(*self.level.spawn)
        self.time = 0.0
        self.score = 0
        self.deaths = 0

    def spawn_dust(self, x, y, n, up=True):
        for _ in range(n):
            ang = random.uniform(-math.pi, 0) if up else random.uniform(0, math.pi)
            spd = random.uniform(40, 150)
            self.particles.append(
                Particle(x + random.uniform(-8, 8), y,
                         math.cos(ang) * spd, math.sin(ang) * spd * 0.6,
                         random.uniform(0.25, 0.5))
            )

    def respawn(self):
        p = self.player
        p.x, p.y = self.level.spawn
        p.vx = p.vy = 0.0
        p.ride = None
        p.on_ground = False
        self.deaths += 1

    def update(self, dt, inp):
        self.time += dt

        for plat in self.platforms:
            plat.update(dt)

        self.player.update(dt, inp, self)

        # Fell out of the world.
        if self.player.y > self.level.px_h + 240:
            self.respawn()

        # Coins: circle-vs-rect is overkill here, a distance check is plenty.
        px, py = self.player.cx, self.player.cy
        for coin in self.coins:
            if coin.taken:
                continue
            if abs(coin.x - px) < 22 and abs(coin.bob_y(self.time) - py) < 30:
                coin.taken = True
                self.score += 1
                self.spawn_dust(coin.x, coin.y, 8)

        # Particles: same integration as the player, just with no collisions.
        alive = []
        for pt in self.particles:
            pt.life -= dt
            if pt.life <= 0:
                continue
            pt.vy += 600.0 * dt
            pt.x += pt.vx * dt
            pt.y += pt.vy * dt
            alive.append(pt)
        self.particles = alive


# ============================================================================
# RENDERER -- owns the camera, draws a World, changes nothing
# ============================================================================

class Renderer:
    def __init__(self, screen):
        self.screen = screen
        self.cam_x = 0.0
        self.cam_y = 0.0
        self.bg = self._make_gradient()
        self.font = pygame.font.SysFont("monospace", 16, bold=True)
        self.big = pygame.font.SysFont("monospace", 13)
        self.debug = False

    def _make_gradient(self):
        surf = pygame.Surface((1, SCREEN_H))
        for y in range(SCREEN_H):
            t = y / (SCREEN_H - 1)
            surf.set_at((0, y), tuple(
                int(a + (b - a) * t) for a, b in zip(C_BG_TOP, C_BG_BOT)
            ))
        return pygame.transform.scale(surf, (SCREEN_W, SCREEN_H))

    def update_camera(self, world, dt, snap=False):
        p = world.player
        target_x = p.cx + p.facing * CAM_LOOKAHEAD - SCREEN_W / 2
        target_y = p.cy - SCREEN_H / 2
        # Exponential smoothing. The 1-exp(-k*dt) form is the framerate-correct
        # version of "move 10% of the way there each frame".
        k = 1.0 if snap else (1.0 - math.exp(-CAM_LERP * dt))
        self.cam_x += (target_x - self.cam_x) * k
        self.cam_y += (target_y - self.cam_y) * k
        self.cam_x = max(0.0, min(world.level.px_w - SCREEN_W, self.cam_x))
        self.cam_y = max(0.0, min(world.level.px_h - SCREEN_H, self.cam_y))

    def draw(self, world):
        s = self.screen
        cx, cy = self.cam_x, self.cam_y
        s.blit(self.bg, (0, 0))

        # Parallax: the further away, the less it scrolls.
        for depth, color, step, hgt in ((0.25, C_FAR, 260, 220), (0.5, C_NEAR, 180, 150)):
            off = -cx * depth
            x = (off % step) - step
            while x < SCREEN_W:
                pygame.draw.rect(s, color, (x, SCREEN_H - hgt, step * 0.62, hgt))
                x += step
        pygame.draw.rect(s, C_NEAR, (0, SCREEN_H - 40, SCREEN_W, 40))

        # Tiles -- only the ones on screen.
        lvl = world.level
        c0 = max(0, int(cx // TILE))
        c1 = min(lvl.cols - 1, int((cx + SCREEN_W) // TILE))
        r0 = max(0, int(cy // TILE))
        r1 = min(lvl.h_tiles - 1, int((cy + SCREEN_H) // TILE))
        for r in range(r0, r1 + 1):
            for c in range(c0, c1 + 1):
                ch = lvl.rows[r][c]
                x, y = c * TILE - cx, r * TILE - cy
                if ch == SOLID:
                    pygame.draw.rect(s, C_TILE, (x, y, TILE, TILE))
                    if r == 0 or lvl.rows[r - 1][c] != SOLID:
                        pygame.draw.rect(s, C_TILE_TOP, (x, y, TILE, 4))
                elif ch == ONEWAY:
                    pygame.draw.rect(s, C_ONEWAY, (x, y, TILE, 8))
                    pygame.draw.rect(s, C_ONEWAY_TOP, (x, y, TILE, 3))

        # Moving platforms.
        for p in world.platforms:
            pygame.draw.rect(s, C_PLAT, (p.x - cx, p.y - cy, p.w, p.h))
            pygame.draw.rect(s, C_PLAT_TOP, (p.x - cx, p.y - cy, p.w, 3))

        # Coins.
        for coin in world.coins:
            if coin.taken:
                continue
            x = coin.x - cx
            y = coin.bob_y(world.time) - cy
            pygame.draw.circle(s, C_COIN_DK, (x, y), Coin.R)
            pygame.draw.circle(s, C_COIN, (x, y), Coin.R - 3)

        # Particles.
        for pt in world.particles:
            a = pt.life / pt.max_life
            size = max(1, int(4 * a))
            pygame.draw.rect(s, C_DUST, (pt.x - cx, pt.y - cy, size, size))

        # Player: squash and stretch driven by vertical speed. Costs 3 lines,
        # does more for the feel than almost anything else on this screen.
        p = world.player
        stretch = max(-1.0, min(1.0, p.vy / MAX_FALL))
        h = p.H * (1.0 + 0.16 * abs(stretch))
        w = p.W * (1.0 - 0.14 * abs(stretch))
        px = p.x - cx - (w - p.W) / 2
        py = p.y - cy - (h - p.H)
        pygame.draw.rect(s, C_PLAYER_DK, (px, py, w, h), border_radius=6)
        pygame.draw.rect(s, C_PLAYER, (px + 2, py + 2, w - 4, h - 6), border_radius=5)
        eye_x = px + w / 2 + p.facing * 4
        pygame.draw.circle(s, C_EYE, (eye_x - 4, py + 14), 3)
        pygame.draw.circle(s, C_EYE, (eye_x + 4, py + 14), 3)

        # HUD.
        total = len(world.coins)
        hud = f"COINS {world.score}/{total}   DEATHS {world.deaths}"
        s.blit(self.font.render(hud, True, C_TEXT), (14, 12))
        tip = "A/D or arrows  |  SPACE jump (hold = higher)  |  DOWN+JUMP drop through  |  R reset  |  F1 debug"
        s.blit(self.big.render(tip, True, (150, 160, 190)), (14, 36))

        if self.debug:
            self._draw_debug(world)

    def _draw_debug(self, world):
        s, cx, cy = self.screen, self.cam_x, self.cam_y
        p = world.player
        pygame.draw.rect(s, (0, 255, 140), (p.x - cx, p.y - cy, p.W, p.H), 1)
        pygame.draw.line(s, (255, 80, 80),
                         (p.cx - cx, p.cy - cy),
                         (p.cx - cx + p.vx * 0.15, p.cy - cy + p.vy * 0.15), 2)
        lines = [
            f"vx {p.vx:8.1f}   vy {p.vy:8.1f}",
            f"pos {p.x:8.1f} {p.y:8.1f}",
            f"ground {str(p.on_ground):5} ({p.ground_kind})",
            f"coyote {p.coyote:.3f}  buffer {p.buffer:.3f}  drop {p.drop:.3f}",
            f"riding {'yes' if p.ride else 'no'}",
        ]
        for i, ln in enumerate(lines):
            s.blit(self.big.render(ln, True, (140, 255, 190)), (14, 64 + i * 16))


# ============================================================================
# MAIN LOOP
# ============================================================================

JUMP_KEYS = (pygame.K_SPACE, pygame.K_w, pygame.K_UP, pygame.K_z)


def main():
    pygame.init()
    screen = pygame.display.set_mode((SCREEN_W, SCREEN_H))
    pygame.display.set_caption("pyplatformer")
    clock = pygame.time.Clock()

    world = World()
    renderer = Renderer(screen)
    renderer.update_camera(world, 0.0, snap=True)

    running = True
    while running:
        dt = min(clock.tick(FPS) / 1000.0, MAX_DT)

        jump_pressed = False
        jump_released = False
        for e in pygame.event.get():
            if e.type == pygame.QUIT:
                running = False
            elif e.type == pygame.KEYDOWN:
                if e.key == pygame.K_ESCAPE:
                    running = False
                elif e.key == pygame.K_r:
                    world = World()
                    renderer.update_camera(world, 0.0, snap=True)
                elif e.key == pygame.K_F1:
                    renderer.debug = not renderer.debug
                elif e.key in JUMP_KEYS:
                    jump_pressed = True
            elif e.type == pygame.KEYUP and e.key in JUMP_KEYS:
                jump_released = True

        keys = pygame.key.get_pressed()
        inp = Input(
            left=keys[pygame.K_a] or keys[pygame.K_LEFT],
            right=keys[pygame.K_d] or keys[pygame.K_RIGHT],
            down=keys[pygame.K_s] or keys[pygame.K_DOWN],
            jump_pressed=jump_pressed,
            jump_released=jump_released,
        )

        world.update(dt, inp)
        renderer.update_camera(world, dt)
        renderer.draw(world)
        pygame.display.flip()

    pygame.quit()


# ============================================================================
# SELFTEST -- runs the physics with scripted input and no window at all.
# This is only possible because World.update() never touches the screen.
# ============================================================================

def selftest():
    world = World()
    dt = 1.0 / 60.0
    p = world.player

    # Settle onto the floor.
    for _ in range(60):
        world.update(dt, Input())
    assert p.on_ground, "player should be resting on the floor"
    floor_y = p.y
    print(f"  rest        y={p.y:.1f} vy={p.vy:.1f} ground={p.ground_kind}")

    # Full jump: measure the apex and compare against v^2 / 2g.
    world.update(dt, Input(jump_pressed=True))
    apex = p.y
    for _ in range(120):
        world.update(dt, Input())
        apex = min(apex, p.y)
        if p.on_ground:
            break
    measured = floor_y - apex
    predicted = JUMP_SPEED ** 2 / (2 * GRAVITY)
    print(f"  full jump   height={measured:.1f}px  predicted={predicted:.1f}px")
    assert abs(measured - predicted) < 12, "jump height should match the formula"

    # Cut jump: releasing early must produce a clearly smaller hop.
    for _ in range(30):
        world.update(dt, Input())
    world.update(dt, Input(jump_pressed=True))
    world.update(dt, Input(jump_released=True))
    apex2 = p.y
    for _ in range(120):
        world.update(dt, Input())
        apex2 = min(apex2, p.y)
        if p.on_ground:
            break
    print(f"  cut jump    height={floor_y - apex2:.1f}px")
    assert (floor_y - apex2) < measured * 0.6, "jump cut should shorten the hop"

    # Coyote time: walk off a ledge, then jump a few frames later.
    world2 = World()
    q = world2.player
    q.x, q.y = 31 * TILE, 16 * TILE - Player.H   # standing on the row-17 block
    for _ in range(20):
        world2.update(dt, Input())
    for _ in range(40):
        world2.update(dt, Input(right=True))
        if not q.on_ground:
            break
    world2.update(dt, Input(right=True, jump_pressed=True))
    print(f"  coyote      vy after late jump = {q.vy:.1f}")
    assert q.vy < -300, "coyote time should still allow a jump just after a ledge"

    # Walls: run into one and stop dead, no tunneling.
    world3 = World()
    w = world3.player
    for _ in range(300):
        world3.update(dt, Input(left=True))
    print(f"  wall        x={w.x:.1f} vx={w.vx:.1f}")
    assert w.x >= TILE - 0.5, "player must not pass through the left wall"

    # Pit: fall through the gap in the floor and get respawned.
    world4 = World()
    f = world4.player
    # Col 47 is the one pit column the vertical lift (cols 48-50) never covers.
    f.x, f.y = 47 * TILE + 4, 2 * TILE
    seen_max_vy = 0.0
    for _ in range(400):
        world4.update(dt, Input())
        seen_max_vy = max(seen_max_vy, f.vy)
        if world4.deaths:
            break
    print(f"  pit/respawn deaths={world4.deaths} peak_vy={seen_max_vy:.1f}")
    assert world4.deaths == 1, "falling into the pit should respawn the player"
    assert seen_max_vy <= MAX_FALL + 1, "vertical speed must be clamped at terminal velocity"

    print("selftest: all checks passed")


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        selftest()
    else:
        main()
