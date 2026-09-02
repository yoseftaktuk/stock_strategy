"""Pure execution helpers used by SimulatedBroker.

Financial formulas live in ``app.domain.execution`` so application and broker
code do not depend on the backtest package.
"""

from app.domain.execution import apply_slippage, commission_on

__all__ = ["apply_slippage", "commission_on"]
