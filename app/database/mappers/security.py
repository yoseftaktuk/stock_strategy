from app.database.models import SecurityIdentifierModel, SecurityModel, SecurityTickerModel
from app.domain.models.security import Security, SecurityIdentifier, SecurityTicker


def security_to_domain(model: SecurityModel) -> Security:
    return Security(
        seed_key=model.seed_key,
        display_name=model.display_name,
        security_type=model.security_type,
        currency=model.currency,
        status=model.status,
        notes=model.notes,
        security_id=model.id,
    )


def security_to_row(security: Security) -> dict[str, object]:
    return {
        "seed_key": security.seed_key,
        "display_name": security.display_name,
        "security_type": security.security_type,
        "currency": security.currency,
        "status": security.status,
        "notes": security.notes,
    }


def ticker_to_domain(model: SecurityTickerModel, *, seed_key: str) -> SecurityTicker:
    return SecurityTicker(
        seed_key=seed_key,
        scheme=model.scheme,
        ticker=model.ticker,
        valid_from=model.valid_from,
        valid_to=model.valid_to,
        continuity=model.continuity,
        source=model.source,
        source_version=model.source_version,
    )


def ticker_to_row(ticker: SecurityTicker, *, security_id: int) -> dict[str, object]:
    return {
        "security_id": security_id,
        "scheme": ticker.scheme,
        "ticker": ticker.ticker,
        "valid_from": ticker.valid_from,
        "valid_to": ticker.valid_to,
        "continuity": ticker.continuity,
        "source": ticker.source,
        "source_version": ticker.source_version,
    }


def identifier_to_domain(model: SecurityIdentifierModel, *, seed_key: str) -> SecurityIdentifier:
    return SecurityIdentifier(
        seed_key=seed_key,
        id_type=model.id_type,
        id_value=model.id_value,
        valid_from=model.valid_from,
        valid_to=model.valid_to,
    )


def identifier_to_row(identifier: SecurityIdentifier, *, security_id: int) -> dict[str, object]:
    return {
        "security_id": security_id,
        "id_type": identifier.id_type,
        "id_value": identifier.id_value,
        "valid_from": identifier.valid_from,
        "valid_to": identifier.valid_to,
    }
