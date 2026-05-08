from __future__ import annotations


def test_imports():
    import duckdb  # noqa: F401
    import pandas as pd  # noqa: F401
    import pyarrow as pa  # noqa: F401
    import numpy as np  # noqa: F401
    from scipy.stats import spearmanr  # noqa: F401
    # openbb / akshare are heavy; smoke import only
    import openbb  # noqa: F401
    import akshare  # noqa: F401
