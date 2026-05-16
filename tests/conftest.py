"""共有フィクスチャ（ネットワーク不使用）"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest


@pytest.fixture
def sample_ohlcv_and_topix() -> tuple[pd.DataFrame, pd.DataFrame]:
    """130 営業日の単調上昇に近い OHLCV と TOPIX 代理"""
    n = 130
    rng = pd.date_range("2024-01-02", periods=n, freq="B")
    np.random.seed(7)
    drift = np.linspace(0, 25, n)
    noise = np.random.randn(n) * 0.4
    close = pd.Series(100.0 + drift + noise, index=rng)
    high = close + 0.8
    low = close - 0.8
    open_ = close.shift(1).fillna(close.iloc[0])
    volume = np.clip(np.random.lognormal(14, 0.35, n), 5e5, 5e7).astype(int)
    ohlcv = pd.DataFrame(
        {"open": open_, "high": high, "low": low, "close": close, "volume": volume},
        index=rng,
    )
    topix = pd.DataFrame({"close": close * 0.998 + np.random.randn(n) * 0.05}, index=rng)
    return ohlcv, topix
