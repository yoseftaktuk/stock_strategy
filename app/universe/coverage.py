from collections.abc import Mapping, Sequence


def missing_market_data_symbols(
    universe_symbols: Sequence[str],
    market_data: Mapping[str, Sequence[object]],
) -> list[str]:
    """Symbols that are universe members but have no loaded price bars.

    Universe membership is independent of market-data availability. Callers must
    report these names rather than dropping them from the historical universe.
    """
    missing: list[str] = []
    for symbol in universe_symbols:
        bars = market_data.get(symbol)
        if not bars:
            missing.append(symbol)
    return sorted(set(missing))
