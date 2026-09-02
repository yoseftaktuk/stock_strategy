from app.broker.simulated import SimulatedBroker


def test_simulated_broker_connect() -> None:
    broker = SimulatedBroker()
    assert broker.is_connected() is False
    broker.connect()
    assert broker.is_connected() is True
    broker.disconnect()
    assert broker.is_connected() is False
