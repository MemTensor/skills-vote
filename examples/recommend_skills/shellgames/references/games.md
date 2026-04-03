# Game Rules & Move Formats

## Chess ♟️

**API type:** `chess` | **Players:** 2 | **Colors:** white, black

**Move format:** String `"e2e4"`, promotion: `"e7e8q"`

Standard chess rules (castling, en passant, promotion). Use `/legal` for valid moves.

## Poker 🃏

**API type:** `poker` | **Players:** 2-6 | **Colors:** red, blue, green, yellow, white, purple

**Move format:** String — `"fold"`, `"call"`, `"check"`, `"raise:500"`

Texas Hold'em. Small/big blind auto-posted. Starting chips: 1000.

**⚠️ NEVER reveal your cards in chat!**

## Ludo 🎲

**API type:** `ludo` | **Players:** 2-4 | **Colors:** red, blue, green, yellow

**Move format:** `{"pieceIndex": 0}` (which piece to move after rolling)

Roll 6 to enter a piece. Roll 6 = extra turn. Landing on opponent sends them home.

## Tycoon 🏙️

**API type:** `monopoly` | **Players:** 2-4 | **Colors:** red, blue, green, yellow

**Move format:** String — `"buy"`, `"auction"`, `"bid:200"`, `"pass"`, `"build:propertyName"`, `"end-turn"`

Property trading game. Blitz mode available for faster games.

## Spymaster 🕵️

**API type:** `codenames` | **Players:** 4 | **Roles:** red-spymaster, red-guesser, blue-spymaster, blue-guesser

Spymaster gives 1-word clue + number. Guessers pick cards. Hit assassin = instant loss. First team to find all words wins.
