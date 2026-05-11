from __future__ import annotations

from collections import Counter
from pathlib import Path
import sys

import yaml

from irc.data.akshare_client import fetch_open_fund_catalog
from irc.discovery.cn_fund_universe import build_cn_fund_universe, serialize_universe
from irc.io_utils import atomic_write_text
from irc.schemas.universe import UniverseConfig


def _theme_label(value: str | None) -> str:
    return value if value is not None else "none"


def _counts_text(config: UniverseConfig) -> str:
    counts = Counter(
        (instrument.asset_class, _theme_label(instrument.theme))
        for instrument in config.instruments
    )
    return "\n".join(
        f"  {asset_class}/{theme}: {count}"
        for (asset_class, theme), count in sorted(counts.items())
    )


def _yaml_text(config: UniverseConfig) -> str:
    raw = serialize_universe(config.instruments)
    return yaml.safe_dump(raw, allow_unicode=True, sort_keys=False)


def run_build_cn_funds(repo_root: str) -> int:
    root = Path(repo_root)
    generated_path = root / "config" / "universe" / "cn_funds.generated.yaml"
    try:
        catalog = fetch_open_fund_catalog()
        instruments = build_cn_fund_universe(catalog.to_dict("records"))
        config = UniverseConfig.model_validate(serialize_universe(instruments))
        text = _yaml_text(config)
    except Exception as exc:  # noqa: BLE001 - command must preserve previous generated file on any failure
        print(f"ERROR: failed to build generated CN fund universe: {exc}", file=sys.stderr)
        return 1

    atomic_write_text(generated_path, text)
    print(f"universe build-cn-funds OK: {len(config.instruments)} instruments -> {generated_path}")
    counts = _counts_text(config)
    if counts:
        print(counts)
    return 0
