"""
Texas Hold'em — GUI Edition
----------------------------
A playable Texas Hold'em table: you vs. three AI opponents, built with
Tkinter so you get a real card table instead of console text.

Run it with: python texas_holdem.py

Rules implemented: standard No-Limit Hold'em betting (fold / check / call /
raise), blinds that rotate each hand, full 5-card-from-7 hand evaluation
(high card through straight flush), and simple heuristic AI opponents.

Simplification: side pots aren't tracked. If a player goes all-in for less
than the full bet, the whole pot (including any excess) still goes to the
showdown winner rather than being split into separate pots. Everything else
plays like a normal home game.
"""

import random
import tkinter as tk
from tkinter import font as tkfont
from itertools import combinations
from collections import Counter, deque

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

SUITS = ["♠", "♥", "♦", "♣"]
RED_SUITS = {"♥", "♦"}
RANKS = [("2", 2), ("3", 3), ("4", 4), ("5", 5), ("6", 6), ("7", 7),
          ("8", 8), ("9", 9), ("10", 10), ("J", 11), ("Q", 12), ("K", 13), ("A", 14)]
RANK_NAME = {2: "Two", 3: "Three", 4: "Four", 5: "Five", 6: "Six", 7: "Seven",
             8: "Eight", 9: "Nine", 10: "Ten", 11: "Jack", 12: "Queen",
             13: "King", 14: "Ace"}

STARTING_CHIPS = 1000
SMALL_BLIND = 10
BIG_BLIND = 20
AI_NAMES = ["Riley", "Sam", "Jordan"]

BG = "#0b5d33"          # felt green
CARD_BG = "#fbfbfb"
CARD_BACK = "#1c3f7a"
PANEL_BG = "#0a4a29"
TEXT_LIGHT = "#f5f5f5"
ACCENT = "#e0b93d"


# ---------------------------------------------------------------------------
# Cards & hand evaluation
# ---------------------------------------------------------------------------

class Card:
    def __init__(self, rank_str, rank_val, suit):
        self.rank_str = rank_str
        self.rank_val = rank_val
        self.suit = suit

    def __repr__(self):
        return f"{self.rank_str}{self.suit}"


def new_shuffled_deck():
    deck = [Card(r, v, s) for (r, v) in RANKS for s in SUITS]
    random.shuffle(deck)
    return deck


def evaluate_5(cards):
    """Rank a single 5-card hand. Returns a comparable tuple: bigger = better."""
    ranks = sorted((c.rank_val for c in cards), reverse=True)
    suits = [c.suit for c in cards]
    is_flush = len(set(suits)) == 1

    unique_ranks = sorted(set(ranks), reverse=True)
    is_straight, straight_high = False, None
    if len(unique_ranks) == 5:
        if unique_ranks[0] - unique_ranks[4] == 4:
            is_straight, straight_high = True, unique_ranks[0]
        elif unique_ranks == [14, 5, 4, 3, 2]:            # wheel: A-2-3-4-5
            is_straight, straight_high = True, 5

    counts = Counter(ranks)
    by_count = sorted(counts.items(), key=lambda kv: (-kv[1], -kv[0]))

    if is_straight and is_flush:
        return (8, straight_high)
    if by_count[0][1] == 4:
        four = by_count[0][0]
        kicker = max(r for r in ranks if r != four)
        return (7, four, kicker)
    if by_count[0][1] == 3 and by_count[1][1] >= 2:
        return (6, by_count[0][0], by_count[1][0])
    if is_flush:
        return (5,) + tuple(ranks)
    if is_straight:
        return (4, straight_high)
    if by_count[0][1] == 3:
        trip = by_count[0][0]
        kickers = sorted((r for r in ranks if r != trip), reverse=True)[:2]
        return (3, trip) + tuple(kickers)
    if by_count[0][1] == 2 and by_count[1][1] == 2:
        pairs = sorted([by_count[0][0], by_count[1][0]], reverse=True)
        kicker = max(r for r in ranks if r not in pairs)
        return (2,) + tuple(pairs) + (kicker,)
    if by_count[0][1] == 2:
        pair = by_count[0][0]
        kickers = sorted((r for r in ranks if r != pair), reverse=True)[:3]
        return (1, pair) + tuple(kickers)
    return (0,) + tuple(ranks)


def best_hand(cards):
    """Best 5-card rank tuple out of 5, 6, or 7 cards."""
    return max(evaluate_5(list(combo)) for combo in combinations(cards, 5))


def describe_hand(rank_tuple):
    cat = rank_tuple[0]
    names = {8: "Straight Flush", 7: "Four of a Kind", 6: "Full House",
             5: "Flush", 4: "Straight", 3: "Three of a Kind",
             2: "Two Pair", 1: "Pair", 0: "High Card"}
    label = names[cat]
    if cat == 7:
        return f"{label}, {RANK_NAME[rank_tuple[1]]}s"
    if cat == 6:
        return f"{label}, {RANK_NAME[rank_tuple[1]]}s over {RANK_NAME[rank_tuple[2]]}s"
    if cat == 3:
        return f"{label}, {RANK_NAME[rank_tuple[1]]}s"
    if cat == 2:
        return f"{label}, {RANK_NAME[rank_tuple[1]]}s and {RANK_NAME[rank_tuple[2]]}s"
    if cat == 1:
        return f"{label}, {RANK_NAME[rank_tuple[1]]}s"
    if cat in (8, 4):
        return f"{label}, {RANK_NAME[rank_tuple[1]]} high"
    return f"{label}, {RANK_NAME[rank_tuple[1]]} high"


def preflop_strength(hole):
    """Rough 0-1 strength estimate for two hole cards (no community cards yet)."""
    r1, r2 = sorted((c.rank_val for c in hole), reverse=True)
    suited = hole[0].suit == hole[1].suit
    pair = r1 == r2
    score = (r1 + r2) / 28.0
    if pair:
        score += 0.25
    if suited:
        score += 0.05
    if r1 - r2 == 1:
        score += 0.05
    return min(score, 1.0)


# ---------------------------------------------------------------------------
# Player
# ---------------------------------------------------------------------------

class Player:
    def __init__(self, name, chips, is_human=False):
        self.name = name
        self.chips = chips
        self.is_human = is_human
        self.reset_hand()

    def reset_hand(self):
        self.hole = []
        self.bet = 0            # chips committed this betting round
        self.folded = False
        self.all_in = False
        self.in_hand = True     # False once eliminated from the table entirely

    def strength(self, community):
        cards = self.hole + community
        if len(cards) < 5:
            return preflop_strength(self.hole)
        return best_hand(cards)[0] / 8.0


# ---------------------------------------------------------------------------
# Game engine + GUI
# ---------------------------------------------------------------------------

class HoldemTable:
    def __init__(self, root):
        self.root = root
        self.root.title("Texas Hold'em")
        self.root.configure(bg=BG)
        self.root.geometry("980x720")

        self.players = [Player("You", STARTING_CHIPS, is_human=True)]
        for name in AI_NAMES:
            self.players.append(Player(name, STARTING_CHIPS))

        self.dealer_index = 0
        self.community = []
        self.pot = 0
        self.current_bet = 0
        self.stage = None
        self.action_queue = deque()
        self.current_player = None

        self.card_font = tkfont.Font(family="Helvetica", size=16, weight="bold")
        self.label_font = tkfont.Font(family="Helvetica", size=11, weight="bold")
        self.small_font = tkfont.Font(family="Helvetica", size=9)

        self._build_ui()
        self.start_new_hand()

    # ---------------------------------------------------------- UI building

    def _build_ui(self):
        header = tk.Label(self.root, text="TEXAS HOLD'EM", font=("Helvetica", 20, "bold"),
                           bg=BG, fg=ACCENT)
        header.pack(pady=(10, 0))

        self.pot_label = tk.Label(self.root, text="Pot: 0", font=self.label_font,
                                   bg=BG, fg=TEXT_LIGHT)
        self.pot_label.pack(pady=(2, 6))

        self.community_frame = tk.Frame(self.root, bg=BG)
        self.community_frame.pack(pady=6)

        self.players_frame = tk.Frame(self.root, bg=BG)
        self.players_frame.pack(pady=6, fill="x")
        self.player_panels = []
        for p in self.players:
            panel = self._build_player_panel(p)
            self.player_panels.append(panel)

        self.log = tk.Text(self.root, height=8, width=100, bg="#062e1a", fg=TEXT_LIGHT,
                            font=self.small_font, state="disabled", wrap="word")
        self.log.pack(pady=8)

        self.action_frame = tk.Frame(self.root, bg=BG)
        self.action_frame.pack(pady=6)

        self.status_label = tk.Label(self.action_frame, text="", font=self.label_font,
                                      bg=BG, fg=ACCENT)
        self.status_label.grid(row=0, column=0, columnspan=4, pady=(0, 6))

        self.fold_btn = tk.Button(self.action_frame, text="Fold", width=10,
                                   command=self.on_fold, state="disabled")
        self.fold_btn.grid(row=1, column=0, padx=4)

        self.call_btn = tk.Button(self.action_frame, text="Check", width=10,
                                   command=self.on_call, state="disabled")
        self.call_btn.grid(row=1, column=1, padx=4)

        self.raise_entry = tk.Entry(self.action_frame, width=8, justify="center")
        self.raise_entry.grid(row=1, column=2, padx=4)

        self.raise_btn = tk.Button(self.action_frame, text="Raise to", width=10,
                                    command=self.on_raise, state="disabled")
        self.raise_btn.grid(row=1, column=3, padx=4)

        self.next_hand_btn = tk.Button(self.action_frame, text="Deal Next Hand",
                                        width=20, command=self.start_new_hand)
        # gridded only when a hand ends

    def _build_player_panel(self, player):
        panel = tk.Frame(self.players_frame, bg=PANEL_BG, bd=2, relief="ridge")
        panel.pack(side="left", expand=True, fill="both", padx=6, ipady=6)

        name_lbl = tk.Label(panel, text=player.name, font=self.label_font,
                             bg=PANEL_BG, fg=ACCENT)
        name_lbl.pack()

        chips_lbl = tk.Label(panel, text=f"{player.chips} chips", font=self.small_font,
                              bg=PANEL_BG, fg=TEXT_LIGHT)
        chips_lbl.pack()

        cards_frame = tk.Frame(panel, bg=PANEL_BG)
        cards_frame.pack(pady=4)

        status_lbl = tk.Label(panel, text="", font=self.small_font,
                               bg=PANEL_BG, fg=TEXT_LIGHT)
        status_lbl.pack()

        return {"player": player, "frame": panel, "chips": chips_lbl,
                "cards": cards_frame, "status": status_lbl}

    def _make_card_widget(self, parent, card, face_down=False):
        if face_down:
            lbl = tk.Label(parent, text="🂠", font=self.card_font, width=3, height=2,
                            bg=CARD_BACK, fg=CARD_BACK, relief="raised", bd=2)
        else:
            color = "#c21807" if card.suit in RED_SUITS else "#111111"
            lbl = tk.Label(parent, text=f"{card.rank_str}{card.suit}", font=self.card_font,
                            width=3, height=2, bg=CARD_BG, fg=color, relief="raised", bd=2)
        lbl.pack(side="left", padx=2)

    def log_msg(self, text):
        self.log.configure(state="normal")
        self.log.insert("end", text + "\n")
        self.log.see("end")
        self.log.configure(state="disabled")

    # ------------------------------------------------------------- display

    def refresh_display(self):
        for widget in self.community_frame.winfo_children():
            widget.destroy()
        for card in self.community:
            self._make_card_widget(self.community_frame, card)
        for _ in range(5 - len(self.community)):
            lbl = tk.Label(self.community_frame, text="", width=3, height=2,
                            bg=BG, relief="flat")
            lbl.pack(side="left", padx=2)

        self.pot_label.config(text=f"Pot: {self.pot}")

        for panel in self.player_panels:
            p = panel["player"]
            panel["chips"].config(text=f"{p.chips} chips")
            for w in panel["cards"].winfo_children():
                w.destroy()
            if p.hole:
                reveal = p.is_human or self.stage == "showdown"
                for card in p.hole:
                    self._make_card_widget(panel["cards"], card, face_down=not reveal)
            status_bits = []
            if p.folded:
                status_bits.append("Folded")
            elif p.all_in:
                status_bits.append("All-in")
            if p.bet:
                status_bits.append(f"Bet {p.bet}")
            if not p.in_hand:
                status_bits = ["Eliminated"]
            panel["status"].config(text=" | ".join(status_bits))
            border = ACCENT if p is self.current_player else PANEL_BG
            panel["frame"].config(highlightbackground=border, highlightthickness=2)

    # --------------------------------------------------------- hand setup

    def active_players(self):
        return [p for p in self.players if p.in_hand]

    def start_new_hand(self):
        self.next_hand_btn.grid_forget()
        table = self.active_players()
        if len(table) <= 1:
            winner = table[0].name if table else "No one"
            self.status_label.config(text=f"Game over — {winner} takes the table!")
            self.fold_btn.config(state="disabled")
            self.call_btn.config(state="disabled")
            self.raise_btn.config(state="disabled")
            return

        self.deck = new_shuffled_deck()
        self.community = []
        self.pot = 0
        for p in self.players:
            p.reset_hand()
            if p.chips <= 0:
                p.in_hand = False

        table = self.active_players()
        for p in table:
            p.hole = [self.deck.pop(), self.deck.pop()]

        self.dealer_index = self.dealer_index % len(self.players)
        while not self.players[self.dealer_index].in_hand:
            self.dealer_index = (self.dealer_index + 1) % len(self.players)

        order = self._seat_order_from(self.dealer_index, table)
        sb, bb = order[0], order[1 % len(order)]
        self._post_blind(sb, SMALL_BLIND)
        self._post_blind(bb, BIG_BLIND)
        self.current_bet = BIG_BLIND

        self.log_msg(f"\n--- New hand --- {self.players[self.dealer_index].name} deals. "
                      f"{sb.name} posts SB {SMALL_BLIND}, {bb.name} posts BB {BIG_BLIND}.")

        first = order[2 % len(order)] if len(order) > 2 else order[0]
        self.stage = "preflop"
        self.start_betting_round(first)

    def _seat_order_from(self, start_index, table):
        n = len(self.players)
        order = []
        i = start_index
        for _ in range(n):
            if self.players[i] in table:
                order.append(self.players[i])
            i = (i + 1) % n
        return order

    def _post_blind(self, player, amount):
        amount = min(amount, player.chips)
        player.chips -= amount
        player.bet += amount
        self.pot += amount
        if player.chips == 0:
            player.all_in = True

    # ------------------------------------------------------------ betting

    def can_act_players(self):
        return [p for p in self.active_players() if not p.folded and not p.all_in]

    def start_betting_round(self, first_player):
        can_act = self.can_act_players()
        if len(can_act) <= 1:
            self.root.after(600, self.advance_stage)
            return
        order = self._seat_order_from(self.players.index(first_player), can_act)
        self.action_queue = deque(order)
        self.process_next_turn()

    def process_next_turn(self):
        self.refresh_display()
        still_in = [p for p in self.active_players() if not p.folded]
        if len(still_in) == 1:
            self.award_pot([still_in[0]])
            return

        can_act = self.can_act_players()
        self.action_queue = deque([p for p in self.action_queue if p in can_act])

        if len(can_act) <= 1 or not self.action_queue:
            self.advance_stage()
            return

        player = self.action_queue.popleft()
        self.current_player = player
        self.refresh_display()

        to_call = self.current_bet - player.bet
        if player.is_human:
            self.status_label.config(
                text=f"Your turn — to call: {to_call}  |  pot: {self.pot}  |  your chips: {player.chips}")
            self.call_btn.config(text="Check" if to_call == 0 else f"Call {to_call}")
            self.fold_btn.config(state="normal")
            self.call_btn.config(state="normal")
            self.raise_btn.config(state="normal")
        else:
            self.status_label.config(text=f"{player.name} is thinking...")
            self.fold_btn.config(state="disabled")
            self.call_btn.config(state="disabled")
            self.raise_btn.config(state="disabled")
            self.root.after(900, lambda: self.take_ai_action(player))

    def apply_bet(self, player, amount):
        amount = min(amount, player.chips)
        player.chips -= amount
        player.bet += amount
        self.pot += amount
        if player.chips == 0:
            player.all_in = True

    def submit_action(self, player, action, raise_to=None):
        to_call = self.current_bet - player.bet
        if action == "fold":
            player.folded = True
            self.log_msg(f"{player.name} folds.")
        elif action == "call":
            self.apply_bet(player, to_call)
            if to_call == 0:
                self.log_msg(f"{player.name} checks.")
            else:
                self.log_msg(f"{player.name} calls {min(to_call, player.chips + to_call)}.")
        elif action == "raise":
            add = raise_to - player.bet
            self.apply_bet(player, add)
            self.current_bet = player.bet
            self.log_msg(f"{player.name} raises to {player.bet}.")
            others = [p for p in self.can_act_players() if p is not player]
            reordered = self._seat_order_from(self.players.index(player), others)
            self.action_queue = deque(reordered)

        self.current_player = None
        self.process_next_turn()

    # --------------------------------------------------------- human input

    def on_fold(self):
        self.submit_action(self.current_player, "fold")

    def on_call(self):
        self.submit_action(self.current_player, "call")

    def on_raise(self):
        player = self.current_player
        raw = self.raise_entry.get().strip()
        min_total = max(self.current_bet + BIG_BLIND, self.current_bet * 2 if self.current_bet else BIG_BLIND)
        if not raw.isdigit():
            self.log_msg("Enter a whole-number raise amount.")
            return
        target = int(raw)
        if target < min_total and target < player.chips + player.bet:
            self.log_msg(f"Raise must total at least {min_total} (or go all-in).")
            return
        target = min(target, player.chips + player.bet)
        self.raise_entry.delete(0, "end")
        self.submit_action(player, "raise", raise_to=target)

    # -------------------------------------------------------------- AI

    def take_ai_action(self, player):
        to_call = self.current_bet - player.bet
        strength = player.strength(self.community)
        roll = random.random()

        if to_call == 0:
            if strength > 0.72 and roll < 0.55 and player.chips > BIG_BLIND:
                target = player.bet + min(player.chips, max(BIG_BLIND * 2, int(self.pot * 0.6)))
                self.submit_action(player, "raise", raise_to=target)
            else:
                self.submit_action(player, "call")   # check
            return

        pot_odds_ok = to_call <= player.chips * 0.5
        if strength < 0.25 and roll < 0.65 and to_call > BIG_BLIND:
            self.submit_action(player, "fold")
        elif strength > 0.65 and roll < 0.45 and player.chips > to_call:
            target = player.bet + min(player.chips, to_call + max(BIG_BLIND * 2, int(self.pot * 0.5)))
            self.submit_action(player, "raise", raise_to=target)
        elif pot_odds_ok or strength > 0.35:
            self.submit_action(player, "call")
        else:
            self.submit_action(player, "fold")

    # --------------------------------------------------------- stage flow

    def advance_stage(self):
        for p in self.active_players():
            p.bet = 0
        self.current_bet = 0
        self.current_player = None

        if self.stage == "preflop":
            self.community += [self.deck.pop() for _ in range(3)]
            self.stage = "flop"
        elif self.stage == "flop":
            self.community.append(self.deck.pop())
            self.stage = "turn"
        elif self.stage == "turn":
            self.community.append(self.deck.pop())
            self.stage = "river"
        elif self.stage == "river":
            self.showdown()
            return

        self.log_msg(f"--- {self.stage.upper()}: {' '.join(repr(c) for c in self.community)} ---")
        first = self._seat_order_from((self.dealer_index + 1) % len(self.players),
                                       self.can_act_players() or self.active_players())
        if first:
            self.start_betting_round(first[0])
        else:
            self.advance_stage()

    def showdown(self):
        self.stage = "showdown"
        contenders = [p for p in self.active_players() if not p.folded]
        results = []
        for p in contenders:
            rank = best_hand(p.hole + self.community)
            results.append((rank, p))
        results.sort(key=lambda r: r[0], reverse=True)
        best_rank = results[0][0]
        winners = [p for rank, p in results if rank == best_rank]

        self.refresh_display()
        for rank, p in results:
            self.log_msg(f"{p.name}: {' '.join(repr(c) for c in p.hole)} — {describe_hand(rank)}")

        self.award_pot(winners)

    def award_pot(self, winners):
        share = self.pot // len(winners)
        remainder = self.pot - share * len(winners)
        for i, w in enumerate(winners):
            amount = share + (remainder if i == 0 else 0)
            w.chips += amount
        names = ", ".join(w.name for w in winners)
        self.log_msg(f"{names} win the pot of {self.pot}!\n")
        self.pot = 0
        self.stage = "done"
        self.current_player = None
        self.refresh_display()

        self.fold_btn.config(state="disabled")
        self.call_btn.config(state="disabled")
        self.raise_btn.config(state="disabled")

        for p in self.players:
            if p.chips <= 0:
                p.in_hand = False

        self.dealer_index = (self.dealer_index + 1) % len(self.players)

        if self.players[0].chips <= 0:
            self.status_label.config(text="You're out of chips. Game over!")
            return

        self.status_label.config(text="Hand complete.")
        self.next_hand_btn.grid(row=2, column=0, columnspan=4, pady=(8, 0))


if __name__ == "__main__":
    root = tk.Tk()
    app = HoldemTable(root)
    root.mainloop()
