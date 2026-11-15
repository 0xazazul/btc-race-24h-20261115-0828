"""A cbBTC trading bot for make.fun's btc-race-24h-20261115-0828.

Speaks agent-fun/bars-replay/v1: one JSON line per minute (a 1-minute bar of
cbBTC priced in USDC from its Orca Whirlpool on Solana), one reply with buy
and sell orders. Long only, one position, starts with $1,000 of paper money.
Fills land at the next minute's open and pay 4 bps fee + 2 bps slippage +
constant-product price impact, so a full-size round trip costs roughly 40
bps: a trade has to catch a real move, not noise.

Strategy (three legs, one position at a time, checked in this order):

1. TURN — buy the capitulation rebound. After the price has fallen at
   least 3.00% over 240 minutes AND the last 15 minutes have turned up at
   least 0.30%, buy with all cash. A 4-hour washout that is already turning
   is the one reliable intraday edge in the dev window: after a 60-minute
   fall of 2.00-2.50%, the next hour averaged +2.70% there. Exit on
   take-profit +4.00%, stop-loss -1.00%, a trailing stop 1.50% below the
   peak since entry, or 480 bars.
2. UPTREND — ride a sustained rise. When the 240-minute return is at
   least +2.00% and the last 30 minutes added at least 0.80%, buy with
   all cash; exit on take-profit +3.00%, a trailing stop 2.00% below the
   peak, or 360 bars. It never fires within 120 bars of a TURN exit, so
   it cannot chase the top of a rebound it just sold.
3. PARTICIPATION — a small late trade so the bot always meets the race
   guardrail of at least one trade. Only if no round trip has completed
   and the window is past bar 1200: after a 30-minute fall of at least
   0.50% with the last 15 minutes turning up at least 0.20%, buy a
   quarter of the cash; exit on take-profit +1.00%, stop-loss -1.00%, or
   120 bars.

All comparisons are exact integer arithmetic on the bars' raw prices (no
floats, no clock, no network, no files, no randomness), so two runs on the
same data produce the same orders byte for byte.

Dev-window measurement (kit's frozen 24h window, exact replay): net PnL
+$35.64 on $1,000 (+3.56%), 1 round trip, 2 filled orders, max drawdown
0.4%, $0.81 of fees. The house baselines on the same window: buy-and-hold
-$44.01, momentum -$40.92, ema-cross -$134.95, adx-momentum -$86.60,
rsi-bollinger -$57.37, hold-cash $0.00 (no trade). The dev window is one
24-hour sample, so these numbers say the bot clears the dev gate with
margin on that window; they are not a promise about the unseen race
window.
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "vendor"))
import makefun_bars

SYMBOL = "CBBTC"
BPS = 10_000
MAX_SLIPPAGE_BPS = 10_000

# --- TURN leg: buy the capitulation rebound -------------------------------
TURN_LOOKBACK_BARS = 240
TURN_DROP_BPS = 300          # 240-minute fall of at least 3.00%
TURN_UP_WINDOW_BARS = 15
TURN_UP_BPS = 30             # ...with the last 15 minutes up 0.30%
TURN_TAKE_BPS = 400          # take profit +4.00%
TURN_STOP_BPS = 100          # stop loss -1.00%
TURN_TRAIL_BPS = 150         # trailing stop 1.50% below the peak
TURN_MAX_HOLD_BARS = 480

# --- UPTREND leg: ride a sustained rise -----------------------------------
UP_MIN_240_BPS = 200         # 240-minute return at least +2.00%
UP_MIN_30_BPS = 80           # ...with the last 30 minutes up 0.80%
UP_TAKE_BPS = 300            # take profit +3.00%
UP_TRAIL_BPS = 200           # trailing stop 2.00% below the peak
UP_MAX_HOLD_BARS = 360
UP_COOLDOWN_AFTER_TURN_BARS = 120  # never chase a TURN exit's rebound

# --- PARTICIPATION leg: one small late trade, for the >= 1 trade rule -----
PART_MIN_SEQ = 1200
PART_DROP_30_BPS = 50        # 30-minute fall of at least 0.50%
PART_UP_BPS = 20             # ...with the last 15 minutes up 0.20%
PART_TAKE_BPS = 100
PART_STOP_BPS = 100
PART_MAX_HOLD_BARS = 120

# Closes so far (raw price units, oldest first). Everything below reads
# only this list and the account the harness reports: no clock, no files.
closes = []
entry = None      # close at which the open position was decided
peak = 0          # highest close since entry
held = 0          # bars held (decisions since entry)
leg = None        # which leg opened the position: "turn" | "uptrend" | "part"
round_trips = 0   # completed round trips (sells)
last_turn_sell = -(10 ** 9)  # seq of the last TURN-leg sell


def _down_bps(i, window, bps):
    """True when closes[i] is at least `bps` below closes[i - window].

    Exact integer comparison: now * 10000 <= then * (10000 - bps).
    """
    if i - window < 0:
        return False
    return closes[i] * BPS <= closes[i - window] * (BPS - bps)


def _up_bps(i, window, bps):
    """True when closes[i] is at least `bps` above closes[i - window]."""
    if i - window < 0:
        return False
    return closes[i] * BPS >= closes[i - window] * (BPS + bps)


def _above(price, ref, bps):
    """True when price is at least `bps` above ref (exact integers)."""
    return price * BPS >= ref * (BPS + bps)


def _below(price, ref, bps):
    """True when price is at least `bps` below ref (exact integers)."""
    return price * BPS <= ref * (BPS - bps)


def _buy_all(state):
    return [{"side": "buy", "symbol": SYMBOL,
             "notional_quote_units": state.cash,
             "max_slippage_bps": MAX_SLIPPAGE_BPS}]


def _sell_all(state):
    holding = state.positions.get(SYMBOL)
    if holding is None:
        return []
    return [{"side": "sell", "symbol": SYMBOL, "qty": holding.qty,
             "max_slippage_bps": MAX_SLIPPAGE_BPS}]


def _open(state, which, price):
    global entry, peak, held, leg
    entry = price
    peak = price
    held = 0
    leg = which


def _close(state, seq):
    global entry, leg, round_trips, last_turn_sell
    if leg == "turn":
        last_turn_sell = seq
    entry = None
    leg = None
    round_trips += 1
    return _sell_all(state)


def on_batch(state, batch):
    """Decide this batch's orders. `state` is the SDK's BarsState: cash,
    equity, positions and the latest bar, current before this callback."""
    price = state.close(SYMBOL)
    if price is None:
        return []
    closes.append(price)
    i = len(closes) - 1
    seq = state.seq

    holding = state.positions.get(SYMBOL)
    if holding is None:
        # Flat: check the legs in priority order.
        if (_down_bps(i, TURN_LOOKBACK_BARS, TURN_DROP_BPS)
                and _up_bps(i, TURN_UP_WINDOW_BARS, TURN_UP_BPS)):
            _open(state, "turn", price)
            return _buy_all(state)
        if (_up_bps(i, TURN_LOOKBACK_BARS, UP_MIN_240_BPS)
                and _up_bps(i, 30, UP_MIN_30_BPS)
                and seq - last_turn_sell >= UP_COOLDOWN_AFTER_TURN_BARS):
            _open(state, "uptrend", price)
            return _buy_all(state)
        if (round_trips == 0 and seq >= PART_MIN_SEQ
                and _down_bps(i, 30, PART_DROP_30_BPS)
                and _up_bps(i, TURN_UP_WINDOW_BARS, PART_UP_BPS)):
            _open(state, "part", price)
            return [{"side": "buy", "symbol": SYMBOL,
                     "notional_quote_units": state.cash // 4,
                     "max_slippage_bps": MAX_SLIPPAGE_BPS}]
        return []

    # Holding: manage the exit.
    global held, peak
    held += 1
    if price > peak:
        peak = price
    sell = False
    if leg == "turn":
        sell = (_above(price, entry, TURN_TAKE_BPS)
                or _below(price, entry, TURN_STOP_BPS)
                or _below(price, peak, TURN_TRAIL_BPS)
                or held >= TURN_MAX_HOLD_BARS)
    elif leg == "uptrend":
        sell = (_above(price, entry, UP_TAKE_BPS)
                or _below(price, peak, UP_TRAIL_BPS)
                or held >= UP_MAX_HOLD_BARS)
    else:  # part
        sell = (_above(price, entry, PART_TAKE_BPS)
                or _below(price, entry, PART_STOP_BPS)
                or held >= PART_MAX_HOLD_BARS)
    if sell:
        return _close(state, seq)
    return []


makefun_bars.run(on_batch)
