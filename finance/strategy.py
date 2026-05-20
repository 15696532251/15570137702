from abc import ABC, abstractmethod
import pandas as pd


class Strategy(ABC):
    """Base contract for all trading strategies.

    The optimizer mutates `params` between runs — no re-instantiation needed.
    """

    params: dict = {}

    @abstractmethod
    def generate_signals(self, data: pd.DataFrame) -> pd.Series:
        """Return a Series of {-1, 0, 1} indexed by DatetimeIndex.

        +1 = enter long, -1 = exit/short signal, 0 = no action.
        Signals must NOT use future data (no look-ahead bias).
        """

    def name(self) -> str:
        return self.__class__.__name__
