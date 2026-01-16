"""Trading strategy modules for cryptocurrency backtesting.

This package provides modular, reusable strategy implementations:
- VBO (Volatility Breakout) - Long-only trend following
- Funding Arbitrage - Market-neutral funding rate harvesting
- Bidirectional VBO - Long in bull markets, short in bear markets
- Hybrid VBO+Funding - VBO in bull, Funding in bear (all-weather)

Each strategy is self-contained with clear interfaces for backtesting.
"""

from .vbo import VBOStrategy
from .funding import FundingStrategy
from .bidirectional_vbo import BidirectionalVBOStrategy
from .hybrid_vbo_funding import HybridVBOFundingStrategy

__all__ = [
    'VBOStrategy',
    'FundingStrategy',
    'BidirectionalVBOStrategy',
    'HybridVBOFundingStrategy',
]
