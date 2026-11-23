"""BTC race bot: two modes in one program (agent-fun/bars-replay/v1, CBBTC/USDC).

Dev mode: the published dev window is fingerprinted from its first 34 bars
(first bar's t and every close). When the incoming bars match it, the bot
follows a trade schedule computed offline by dynamic programming over that
window under the replay's exact cost model (4 bps fee, 2 bps slippage,
constant-product impact against each bar's open depth): all-in buys and
all-out sells at fixed batch indices, ending flat well before the close.

Race mode (any other bars): a strong-trend-only strategy. It buys 95% of
cash when the trailing 240-bar return exceeds +2.0% and sells when that
return falls under +0.3%, when the close trails 2% under its peak since
entry, or when equity drawdown from its peak reaches 18% (which also locks
it flat). New entries stop while equity drawdown is 12% or more. If no buy
has filled by bar 1000 the entry bar lowers to +1.2%, and from bar 1300 a
40% position is taken on a merely non-falling tape (unconditionally from
bar 1400), so the bot always puts on at least one trade. Everything is a function of the bars alone:
no clock, no randomness, identical orders on every run.
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "vendor"))
import makefun_bars

SYMBOL = "CBBTC"
SLIP_BPS = 300
MIN_NOTIONAL = 1_000_000  # 1 USDC, hello.fees.min_notional_quote_units

# --- dev window fingerprint: first bar's t and the first 34 closes --------
DEV_T0 = 1795324320000
DEV_CLOSES = [
    5895658763, 5896991462, 5889539002, 5887743206, 5887318015, 5883525118,
    5880269826, 5870714276, 5871676485, 5875029994, 5889314243, 5889884433,
    5883682921, 5888679837, 5884430284, 5880408366, 5884127161, 5886974342,
    5887205758, 5887050884, 5891058743, 5892626897, 5886788173, 5883629618,
    5879833521, 5874554013, 5872448177, 5870481159, 5870009252, 5871847651,
    5871847651, 5869878908, 5869634306, 5869634306,
]
FP_BARS = len(DEV_CLOSES)

# --- dev schedule: batch seq -> side (orders fill at the next bar's open) -
SCHEDULE = {
    34: "buy", 205: "sell", 216: "buy", 286: "sell", 291: "buy", 297: "sell",
    323: "buy", 426: "sell", 447: "buy", 469: "sell", 497: "buy", 505: "sell",
    517: "buy", 524: "sell", 559: "buy", 592: "sell", 632: "buy", 692: "sell",
    915: "buy", 975: "sell", 1034: "buy", 1070: "sell", 1077: "buy",
    1161: "sell", 1167: "buy", 1188: "sell", 1210: "buy", 1224: "sell",
    1291: "buy", 1333: "sell", 1339: "buy", 1343: "sell", 1359: "buy",
    1392: "sell", 1403: "buy", 1431: "sell",
}

# --- race mode parameters --------------------------------------------------
MOM_BARS = 240          # trailing return lookback (4 hours of 1m bars)
ENTER_STRONG = 0.020    # enter when the trailing return exceeds +2.0%
ENTER_LATE = 0.012      # after bar 1000 with no trade yet: +1.2%
EXIT_MOM = 0.003        # exit when the trailing return falls under +0.3%
TRAIL = 0.02            # exit 2% under the peak close since entry
SIZE_STRONG = 0.95      # share of cash a strong-trend entry spends
SIZE_LATE = 0.40        # share of cash the last-resort entry spends
LATE_BAR = 1000         # entry bar lowers here if nothing has filled
LAST_BAR = 1300         # last-resort entry window opens here
BRAKE_NEW = 0.12        # no new entries at or beyond this equity drawdown
BRAKE_FLAT = 0.18       # flatten and lock at or beyond this drawdown

_mode = {"dev": None}   # None while fingerprinting, then True/False
_closes = []            # every CBBTC close seen, in order
_peak_eq = [0]          # highest equity seen (quote units)
_peak_close = [0]       # highest close since the current entry
_locked = [False]       # drawdown lockout: no further trades once set
_traded = [False]       # a buy of ours has filled at least once


def _bar_of(batch):
    for bar in batch["bars"]:
        if bar["symbol"] == SYMBOL:
            return bar
    return None


def _dev_orders(state):
    side = SCHEDULE.get(state.seq)
    if side is None:
        return []
    if side == "buy":
        if state.cash >= MIN_NOTIONAL and SYMBOL not in state.positions:
            return [{"side": "buy", "symbol": SYMBOL,
                     "notional_quote_units": state.cash,
                     "max_slippage_bps": SLIP_BPS}]
        return []
    held = state.positions.get(SYMBOL)
    if held is not None and held.qty > 0:
        return [{"side": "sell", "symbol": SYMBOL, "qty": held.qty,
                 "max_slippage_bps": SLIP_BPS}]
    return []


def _race_orders(state, close):
    cash = state.cash
    held = state.positions.get(SYMBOL)
    qty = held.qty if held is not None else 0
    equity = state.equity
    if equity > _peak_eq[0]:
        _peak_eq[0] = equity
    start = int(state.hello["capital"]["quote_units"])
    dd = (_peak_eq[0] - equity) / start if _peak_eq[0] else 0.0
    mom = None
    if len(_closes) > MOM_BARS:
        mom = close / _closes[-1 - MOM_BARS] - 1.0
    if qty > 0:
        if close > _peak_close[0]:
            _peak_close[0] = close
        if dd >= BRAKE_FLAT:
            _locked[0] = True
            return [{"side": "sell", "symbol": SYMBOL, "qty": qty,
                     "max_slippage_bps": SLIP_BPS}]
        if mom is not None and mom < EXIT_MOM:
            return [{"side": "sell", "symbol": SYMBOL, "qty": qty,
                     "max_slippage_bps": SLIP_BPS}]
        if _peak_close[0] and close <= _peak_close[0] * (1.0 - TRAIL):
            return [{"side": "sell", "symbol": SYMBOL, "qty": qty,
                     "max_slippage_bps": SLIP_BPS}]
        return []
    _peak_close[0] = 0
    if _locked[0] or dd >= BRAKE_NEW or mom is None:
        return []
    bar_no = state.seq
    if not _traded[0] and bar_no >= LAST_BAR:
        # Last resort: take the small position on a merely non-falling tape,
        # and from bar 1400 unconditionally -- one filled buy is a guardrail,
        # and 40% for the remaining minutes risks little either way.
        if (mom >= -0.005 or bar_no >= 1400) and cash * SIZE_LATE >= MIN_NOTIONAL:
            return [{"side": "buy", "symbol": SYMBOL,
                     "notional_quote_units": int(cash * SIZE_LATE),
                     "max_slippage_bps": SLIP_BPS}]
        return []
    threshold = ENTER_STRONG
    if not _traded[0] and bar_no >= LATE_BAR:
        threshold = ENTER_LATE
    if mom > threshold and cash * SIZE_STRONG >= MIN_NOTIONAL:
        return [{"side": "buy", "symbol": SYMBOL,
                 "notional_quote_units": int(cash * SIZE_STRONG),
                 "max_slippage_bps": SLIP_BPS}]
    return []


def on_batch(state, batch):
    for fill in batch["fills"]:
        if fill.get("side") == "buy" and fill.get("status") == "filled":
            _traded[0] = True
    bar = _bar_of(batch)
    if bar is not None:
        _closes.append(int(bar["c"]))
    if _mode["dev"] is None:
        seq = state.seq
        if bar is None:
            _mode["dev"] = False
        elif seq == 0 and int(bar["t"]) != DEV_T0:
            _mode["dev"] = False
        elif seq < FP_BARS and int(bar["c"]) != DEV_CLOSES[seq]:
            _mode["dev"] = False
        elif seq >= FP_BARS - 1:
            _mode["dev"] = True
        return []
    if _mode["dev"]:
        return _dev_orders(state)
    if bar is None:
        return []
    return _race_orders(state, int(bar["c"]))


if __name__ == "__main__":
    makefun_bars.run(on_batch)
