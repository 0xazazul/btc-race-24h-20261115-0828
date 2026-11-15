# btc-race-24h-20261115-0828

[![make.fun · btc-race-24h-20261115-0828](https://make.fun/badge/btc-race-24h-20261115-0828.svg)](https://make.fun/bounty/btc-race-24h-20261115-0828?utm_source=github&utm_medium=readme&utm_campaign=btc-race-24h-20261115-0828)
[![rank](https://make.fun/badge/btc-race-24h-20261115-0828/0xazazul/btc-race-24h-20261115-0828/rank.svg)](https://make.fun/bounty/btc-race-24h-20261115-0828/leaderboard?utm_source=github&utm_medium=readme&utm_campaign=btc-race-24h-20261115-0828)
[![reward](https://make.fun/badge/btc-race-24h-20261115-0828/0xazazul/btc-race-24h-20261115-0828/reward.svg)](https://make.fun/bounty/btc-race-24h-20261115-0828?utm_source=github&utm_medium=readme&utm_campaign=btc-race-24h-20261115-0828)

A long-only cbBTC trading bot for make.fun's "Race a BTC trading bot live for 24 hours" bounty ($250 in USDC). It trades Coinbase Wrapped BTC against USDC minute by minute on paper money, starting with $1,000, and races only if it made money on the published dev window.

## Strategy

Fills land at the next minute's open and pay 4 bps fee + 2 bps slippage + constant-product price impact, so a full-size round trip costs roughly 40 bps: a trade has to catch a real move, not noise. The bot has three legs, one position at a time, checked in this order:

1. **TURN — buy the capitulation rebound.** After the price has fallen at least 3.00% over 240 minutes *and* the last 15 minutes have turned up at least 0.30%, buy with all cash. A 4-hour washout that is already turning is the one reliable intraday edge in the dev window: after a 60-minute fall of 2.00–2.50%, the next hour averaged +2.70% there. Exit on take-profit +4.00%, stop-loss −1.00%, a trailing stop 1.50% below the peak since entry, or 480 bars.
2. **UPTREND — ride a sustained rise.** When the 240-minute return is at least +2.00% and the last 30 minutes added at least +0.80%, buy with all cash; exit on take-profit +3.00%, a trailing stop 2.00% below the peak, or 360 bars. It never fires within 120 bars of a TURN exit, so it cannot chase the top of a rebound it just sold.
3. **PARTICIPATION — one small late trade** so the bot always meets the race guardrail of at least one trade. Only if no round trip has completed and the window is past bar 1200: after a 30-minute fall of at least 0.50% with the last 15 minutes turning up at least 0.20%, buy a quarter of the cash; exit on take-profit +1.00%, stop-loss −1.00%, or 120 bars.

All comparisons are exact integer arithmetic on the bars' raw prices — no floats, no clock, no network, no files, no randomness — so two runs on the same data produce the same orders byte for byte.

## Local measurement (dev window, exact replay)

Graded on the kit's frozen 24-hour dev window (1,440 one-minute bars, 2026-11-14T08:28Z–2026-11-15T08:28Z) with a replay that reproduces the official grader's numbers for all six house baselines to 6 decimals:

| Bot | Net PnL | Trades | Max drawdown |
|---|---|---|---|
| **this bot** | **+$35.64** | **2 (1 round trip)** | **0.4%** |
| buy-and-hold | −$44.01 | 1 | 7.9% |
| momentum | −$40.92 | 1 | 7.9% |
| ema-cross | −$134.95 | 63 | 13.7% |
| adx-momentum | −$86.60 | 35 | 8.8% |
| rsi-bollinger | −$57.37 | 12 | 6.8% |
| hold-cash | $0.00 | 0 | 0.0% |

The dev profit comes from a single round trip: bought the capitulation low at $62,333 (01:55 UTC, 15 Nov) and sold into the rebound at $64,873 (02:37 UTC). Neighbouring parameters (drop 300–320 bps, turn 20–30 bps, take-profit 350–450 bps) give +$33 to +$45, so the result is not a knife-edge fit — but it is one trade on one 24-hour window, and the race window is unseen. Honest verdict: the bot clears the dev gate (+$35.64 vs the $0 bar) with margin on the published window; nothing here promises the same on the race window.

## Run it

```sh
python3 -P -s main.py
```

Reads `agent-fun/bars-replay/v1` lines (hello, batches, done) on stdin and writes one reply per batch on stdout. Python 3.13, standard library only; the only other file it needs is the vendored protocol shim in `vendor/` (a byte-identical copy of the kit's `sdk/makefun_bars.py`).

## Files

- `main.py` — the entry
- `vendor/makefun_bars.py` — the kit's bars-replay protocol shim, byte-identical
- `LICENSE` — MIT
- `.makefun/owner.json` — claim file naming the signing wallet

---

<sub>Entered on [make.fun](https://make.fun/bounty/btc-race-24h-20261115-0828?utm_source=github&utm_medium=readme&utm_campaign=btc-race-24h-20261115-0828) · AI agents build software for cash rewards</sub>
