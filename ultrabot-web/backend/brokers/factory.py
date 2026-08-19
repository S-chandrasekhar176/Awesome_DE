from typing import Any, Dict, Optional

from brokers.base import BaseBroker
from brokers.paper_broker import PaperBroker
from brokers.angel_one import AngelOneBroker
from brokers.shoonya import ShoonyaBroker
from brokers.dhan import DhanBroker
from brokers.fyers import FyersBroker
from brokers.kite import KiteBroker
from fees.nse_fee_calculator import NSEFeeCalculator


class BrokerFactory:
    """Factory for creating broker instances.

    Usage:
        broker = BrokerFactory.create('paper', mode='paper', initial_capital=100000)
        broker = BrokerFactory.create('zerodha', mode='live', api_key='...', access_token='...')
        broker = BrokerFactory.create('dhan', mode='live', client_id='...', access_token='...')
        broker = BrokerFactory.create('fyers', mode='live', app_id='...', access_token='...')
    """

    _ALIAS_MAP: Dict[str, str] = {
        'angelone': 'angel_one',
        'angel-one': 'angel_one',
        'angel_one': 'angel_one',
        'shoonya': 'shoonya',
        'finvasia': 'shoonya',
        'zerodha': 'zerodha',
        'kite': 'zerodha',
        'dhan': 'dhan',
        'fyers': 'fyers',
        'paper': 'paper',
    }

    _registry: Dict[str, type] = {
        'paper': PaperBroker,
        'angel_one': AngelOneBroker,
        'angelone': AngelOneBroker,
        'shoonya': ShoonyaBroker,
        'dhan': DhanBroker,
        'fyers': FyersBroker,
        'zerodha': KiteBroker,
        'kite': KiteBroker,
    }

    @staticmethod
    def create(broker_name: str, mode: str = 'paper', **kwargs: Any) -> BaseBroker:
        """Create a broker instance.

        Args:
            broker_name: One of 'paper', 'angel_one', 'angelone', 'shoonya', 'dhan', 'fyers', 'zerodha'.
            mode: 'paper' or 'live'.
            **kwargs: Additional kwargs passed to the broker constructor.

        Returns:
            An instance of the requested broker.

        Raises:
            ValueError: If broker_name is not recognized.
        """
        normalized = BrokerFactory._ALIAS_MAP.get(str(broker_name).lower().strip(), str(broker_name).lower().strip())
        broker_cls = BrokerFactory._registry.get(normalized)
        if broker_cls is None:
            available = ', '.join(BrokerFactory._registry.keys())
            raise ValueError(f"Unknown broker: {broker_name}. Available: {available}")

        # For paper mode without explicit force_live, return PaperBroker
        if mode == 'paper' and broker_name != 'paper' and not kwargs.pop('force_live', False):
            fee_calc = kwargs.pop('fee_calculator', NSEFeeCalculator())
            repo = kwargs.pop('repository', None)
            capital = kwargs.pop('initial_capital', 100000.0)
            broker = PaperBroker(
                initial_capital=capital,
                fee_calculator=fee_calc,
                repository=repo,
            )
            return broker

        if broker_name == 'paper':
            fee_calc = kwargs.pop('fee_calculator', NSEFeeCalculator())
            repo = kwargs.pop('repository', None)
            capital = kwargs.pop('initial_capital', 100000.0)
            return PaperBroker(
                initial_capital=capital,
                fee_calculator=fee_calc,
                repository=repo,
            )

        if broker_name == 'angel_one':
            return AngelOneBroker(**kwargs)

        if broker_name == 'shoonya':
            return ShoonyaBroker(**kwargs)

        return broker_cls(**kwargs)

    @staticmethod
    def register(name: str, cls: type) -> None:
        """Register a custom broker class."""
        BrokerFactory._registry[name] = cls

    @staticmethod
    def available_brokers() -> list:
        """Return list of registered broker names."""
        return list(BrokerFactory._registry.keys())
