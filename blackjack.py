"""
Blackjack Simulator
--------------------
A full console-playable Blackjack game with betting, splitting on blackjack
payouts, and a dealer that follows standard casino rules (hits on 16,
stands on 17+).

Run it with: python blackjack.py
"""

import random


# ---------------------------------------------------------------------------
# Card & Deck
# ---------------------------------------------------------------------------

SUITS = ["♠", "♥", "♦", "♣"]
RANKS = ["2", "3", "4", "5", "6", "7", "8", "9", "10", "J", "Q", "K", "A"]


class Card:
    def __init__(self, rank, suit):
        self.rank = rank
        self.suit = suit

    def value(self):
        """Blackjack value of a single card. Aces return 11 (adjusted later)."""
        if self.rank in ("J", "Q", "K"):
            return 10
        if self.rank == "A":
            return 11
        return int(self.rank)

    def __str__(self):
        return f"{self.rank}{self.suit}"


class Deck:
    def __init__(self, num_decks=1):
        self.cards = []
        self.num_decks = num_decks
        self.build()

    def build(self):
        self.cards = [
            Card(rank, suit)
            for _ in range(self.num_decks)
            for suit in SUITS
            for rank in RANKS
        ]
        random.shuffle(self.cards)

    def deal(self):
        # Reshuffle a fresh shoe if we run low.
        if len(self.cards) < 15:
            self.build()
        return self.cards.pop()


# ---------------------------------------------------------------------------
# Hand
# ---------------------------------------------------------------------------

class Hand:
    def __init__(self):
        self.cards = []

    def add(self, card):
        self.cards.append(card)

    def value(self):
        """Best hand value, treating Aces as 1 or 11 to avoid busting."""
        total = sum(card.value() for card in self.cards)
        aces = sum(1 for card in self.cards if card.rank == "A")
        while total > 21 and aces > 0:
            total -= 10
            aces -= 1
        return total

    def is_blackjack(self):
        return len(self.cards) == 2 and self.value() == 21

    def is_bust(self):
        return self.value() > 21

    def __str__(self):
        return " ".join(str(card) for card in self.cards)

    def display(self, hide_first=False):
        if hide_first:
            hidden = ["??"] + [str(c) for c in self.cards[1:]]
            return " ".join(hidden)
        return str(self)


# ---------------------------------------------------------------------------
# Game
# ---------------------------------------------------------------------------

class BlackjackGame:
    def __init__(self, starting_chips=100, num_decks=1):
        self.deck = Deck(num_decks)
        self.chips = starting_chips

    def get_bet(self):
        while True:
            raw = input(f"\nYou have {self.chips} chips. Bet how much? ").strip()
            if not raw.isdigit():
                print("Enter a whole number.")
                continue
            bet = int(raw)
            if bet <= 0:
                print("Bet must be positive.")
            elif bet > self.chips:
                print("You don't have that many chips.")
            else:
                return bet

    def deal_initial_hands(self):
        player = Hand()
        dealer = Hand()
        for _ in range(2):
            player.add(self.deck.deal())
            dealer.add(self.deck.deal())
        return player, dealer

    def player_turn(self, player):
        while True:
            print(f"\nYour hand: {player.display()}  (value: {player.value()})")
            if player.is_bust():
                print("Bust!")
                return
            choice = input("Hit or Stand? [h/s]: ").strip().lower()
            if choice == "h":
                card = self.deck.deal()
                player.add(card)
                print(f"You drew: {card}")
            elif choice == "s":
                return
            else:
                print("Type 'h' or 's'.")

    def dealer_turn(self, dealer):
        print(f"\nDealer reveals: {dealer.display()}  (value: {dealer.value()})")
        while dealer.value() < 17:
            card = self.deck.deal()
            dealer.add(card)
            print(f"Dealer draws: {card}  -> {dealer.display()} (value: {dealer.value()})")
        if dealer.is_bust():
            print("Dealer busts!")

    def resolve(self, player, dealer, bet):
        p_val, d_val = player.value(), dealer.value()
        p_bj, d_bj = player.is_blackjack(), dealer.is_blackjack()

        if p_bj and d_bj:
            print("Both have Blackjack — push.")
            return 0
        if p_bj:
            winnings = int(bet * 1.5)
            print(f"Blackjack! You win {winnings} chips.")
            return winnings
        if d_bj:
            print("Dealer has Blackjack. You lose.")
            return -bet
        if player.is_bust():
            print("You busted. You lose.")
            return -bet
        if dealer.is_bust():
            print(f"Dealer busted. You win {bet} chips!")
            return bet
        if p_val > d_val:
            print(f"You win {p_val} vs {d_val}! You win {bet} chips.")
            return bet
        if p_val < d_val:
            print(f"Dealer wins {d_val} vs {p_val}. You lose.")
            return -bet
        print(f"Push — both have {p_val}.")
        return 0

    def play_round(self):
        bet = self.get_bet()
        player, dealer = self.deal_initial_hands()

        print(f"\nDealer shows: {dealer.display(hide_first=True)}")
        print(f"Your hand:    {player.display()}  (value: {player.value()})")

        if player.is_blackjack() or dealer.is_blackjack():
            # Skip player decisions if either has natural blackjack.
            print(f"\nDealer's hand: {dealer.display()}  (value: {dealer.value()})")
        else:
            self.player_turn(player)
            if not player.is_bust():
                self.dealer_turn(dealer)

        net = self.resolve(player, dealer, bet)
        self.chips += net
        print(f"Chip total: {self.chips}")

    def run(self):
        print("=" * 40)
        print("        WELCOME TO BLACKJACK")
        print("=" * 40)
        while self.chips > 0:
            self.play_round()
            if self.chips <= 0:
                print("\nYou're out of chips. Game over!")
                break
            again = input("\nPlay another round? [y/n]: ").strip().lower()
            if again != "y":
                break
        print(f"\nFinal chip count: {self.chips}")
        print("Thanks for playing!")


if __name__ == "__main__":
    game = BlackjackGame(starting_chips=100, num_decks=1)
    game.run()
