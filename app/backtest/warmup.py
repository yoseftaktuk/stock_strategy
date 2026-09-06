from dataclasses import dataclass
from datetime import date
from typing import Literal

from app.backtest.data import warmup_history_start
from app.backtest.exceptions import BacktestConfigError

WarmupMode = Literal["legacy", "explicit_signal"]


@dataclass(frozen=True)
class WarmupBounds:
    """Resolved warmup / signal / performance boundaries.

    ``warmup_start``
        Calendar day history is loaded from (lookback buffer before ``--start``).
    ``calendar_start``
        Engine trading calendar start (``--start``).
    ``signal_start``
        First date signals may be evaluated. ``None`` in legacy mode: the
        in-window warmup gate still delays the first month-start rebalance.
    ``performance_start``
        First date that belongs to equity / metrics. Legacy: ``--start``.
        Explicit: ``--signal-start``.
    ``first_eligible_signal_date``
        Filled by the engine after the calendar is known: first month-start
        the strategy is allowed to evaluate.
    """

    warmup_start: date
    calendar_start: date
    signal_start: date | None
    performance_start: date
    end: date
    in_window_warmup_sessions: int
    mode: WarmupMode
    first_eligible_signal_date: date | None = None

    def with_first_eligible(self, session: date | None) -> "WarmupBounds":
        return WarmupBounds(
            warmup_start=self.warmup_start,
            calendar_start=self.calendar_start,
            signal_start=self.signal_start,
            performance_start=self.performance_start,
            end=self.end,
            in_window_warmup_sessions=self.in_window_warmup_sessions,
            mode=self.mode,
            first_eligible_signal_date=session,
        )


def resolve_warmup_bounds(
    *,
    start: date,
    end: date,
    lookback_days: int | None,
    signal_start: date | None,
    warmup_sessions: int,
) -> WarmupBounds:
    """Map CLI dates onto data / signal / performance boundaries.

    Legacy (``signal_start is None``): ``--start`` remains calendar start,
    performance start, and the in-window warmup gate (``lookback + 1``
    sessions inside ``[start, end]`` before the first month-start rebalance).
    Pre-start bars are still loaded for later lookback, matching today's
    ``load_market_data`` buffer.

    Explicit (``signal_start`` set): in-window session count is not applied.
    History before ``signal_start`` is warmup-only. The first eligible signal
    is the first month-start on or after ``signal_start``. Equity and metrics
    begin at ``signal_start``. No orders or fills are produced before it.
    """
    if start > end:
        raise BacktestConfigError("start_date must be <= end_date")
    if signal_start is not None:
        if signal_start < start:
            raise BacktestConfigError("signal_start must be >= start_date")
        if signal_start > end:
            raise BacktestConfigError("signal_start must be <= end_date")

    if lookback_days is not None and lookback_days > 0:
        warmup_start = warmup_history_start(start, lookback_days)
        legacy_sessions = lookback_days + 1
    else:
        warmup_start = start
        legacy_sessions = warmup_sessions

    if signal_start is None:
        return WarmupBounds(
            warmup_start=warmup_start,
            calendar_start=start,
            signal_start=None,
            performance_start=start,
            end=end,
            in_window_warmup_sessions=legacy_sessions,
            mode="legacy",
        )
    return WarmupBounds(
        warmup_start=warmup_start,
        calendar_start=start,
        signal_start=signal_start,
        performance_start=signal_start,
        end=end,
        in_window_warmup_sessions=1,
        mode="explicit_signal",
    )
