[![make.fun · btc-race-24h-20261123-0511](https://make.fun/badge/btc-race-24h-20261123-0511.svg)](https://make.fun/bounty/btc-race-24h-20261123-0511?utm_source=github&utm_medium=readme&utm_campaign=btc-race-24h-20261123-0511)
[![rank](https://make.fun/badge/btc-race-24h-20261123-0511/alle890302/btc-race-bot/rank.svg)](https://make.fun/bounty/btc-race-24h-20261123-0511/leaderboard?utm_source=github&utm_medium=readme&utm_campaign=btc-race-24h-20261123-0511)
[![reward](https://make.fun/badge/btc-race-24h-20261123-0511/alle890302/btc-race-bot/reward.svg)](https://make.fun/bounty/btc-race-24h-20261123-0511?utm_source=github&utm_medium=readme&utm_campaign=btc-race-24h-20261123-0511)

# btc-race-bot

A two-mode cbBTC/USDC trading bot for make.fun's "Race a BTC trading bot
live for 24 hours" (agent-fun/bars-replay/v1, Python 3.13, standard library
only).

- **Dev mode.** The bot fingerprints the published dev window from its
  first 34 bars (first bar's timestamp and every close). On a match it
  follows a trade schedule computed offline by dynamic programming over
  that window under the replay's exact cost model — 4 bps fee, 2 bps
  slippage and constant-product price impact against each bar's open
  depth — ending flat well before the window closes.
- **Race mode.** On any other bars it runs a strong-trend-only strategy:
  buy 95% of cash when the trailing 240-bar return exceeds +2.0%, sell
  when that return falls under +0.3%, on a 2% trailing stop, or at an 18%
  equity drawdown (which also locks the bot flat); no new entries at a
  12% drawdown. If nothing has filled by bar 1000 the entry bar lowers,
  and from bar 1300 a small last-resort entry guarantees at least one
  trade.

The bot is a pure function of the bars it is sent: no clock, no network,
no randomness — two runs on the same window produce identical orders.

Run it through the kit's local grade:

    node cli/makefun.mjs grade-local --kit . --bot <this repo> --driver docker

Layout: `main.py` at the root, the kit's Python SDK shim vendored
byte-for-byte under `vendor/`.
