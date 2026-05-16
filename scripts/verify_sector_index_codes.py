"""One-shot verification: confirm each tentative CSI sector index code
returns constituents via fetch_cn_index_constituents. Run once before
locking codes into _TARGET_REGISTRY. Not part of the test suite.

Usage:
    .venv/bin/python scripts/verify_sector_index_codes.py
"""
from __future__ import annotations

from irc.fundamentals.akshare_fundamentals import fetch_cn_index_constituents


_CANDIDATES: tuple[tuple[str, str, str], ...] = (
    ("半导体", "中证全指半导体", "H30184"),
    ("医药", "中证医药卫生", "000933"),
    ("新能源", "中证新能源", "399808"),
    ("消费", "中证主要消费", "000932"),
    ("金融", "中证金融", "000934"),
    ("军工", "中证军工", "399967"),
    ("有色金属", "中证有色金属", "H30202"),
    ("房地产", "中证全指房地产", "000952"),
    ("国企改革", "央企创新驱动", "000861"),
    ("科技", "中证科技龙头", "931087"),
)


def main() -> int:
    failures: list[tuple[str, str, str]] = []
    for theme, name, code in _CANDIDATES:
        constituents = fetch_cn_index_constituents(code, top_n=10)
        status = "OK" if constituents else "EMPTY"
        print(f"{theme:8s} {name:14s} {code:8s} {status:6s} (got {len(constituents)} names)")
        if not constituents:
            failures.append((theme, name, code))
    if failures:
        print("\nFailures:")
        for theme, name, code in failures:
            print(f"  {theme} → {name} ({code})")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
