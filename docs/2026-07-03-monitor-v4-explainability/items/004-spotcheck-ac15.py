"""AC-15 throwaway spot-check: f184 byte-identity across BOTH perturbation axes."""
from pathlib import Path

import irc.monitor.flow_batch_fetch as fb
from irc.commands import monitor_cmd as mc
from irc.config_loader import load_monitor_config
from irc.http_proxy import resolve_cn_proxy
from irc.monitor.resolve import resolve_funds

root = Path(".")
funds = resolve_funds(load_monitor_config(root))

TOP5 = list(mc._capture_union_symbols(funds, root))
FULL = list(mc._full_basket_union_symbols(funds, root))
print(f"top5_union={len(TOP5)} full_union={len(FULL)}")

proxy = resolve_cn_proxy()
proxies = {"http": proxy, "https": proxy} if proxy else None
print(f"proxy={'set' if proxy else 'NONE (direct)'}")


def raw(secids, fields):
    return fb._default_http_get(
        fb._ULIST_URL,
        params={"ut": fb._UT, "fltt": "2", "invt": "2", "np": "1", "dect": "1",
                "secids": fb.build_secids(secids), "fields": fields},
        headers=fb._HEADERS, timeout=20, proxies=proxies)


resp_a = fb.parse_ulist(raw(TOP5, "f12,f14,f184"))
resp_b = fb.parse_ulist(raw(FULL, "f12,f14,f184,f127"))
a = {s: pair[0] for s, pair in resp_a.items()}
b = {s: pair[0] for s, pair in resp_b.items()}
common = set(a) & set(b)
bad = {s for s in common
       if (a[s] is None) != (b[s] is None)
       or (a[s] is not None and round(a[s], 4) != round(b[s], 4))}
ind_count = sum(1 for _, pair in resp_b.items() if pair[1])
print(f"intersection={len(common)} mismatches={sorted(bad)} f127_industries_on_full={ind_count}/{len(resp_b)}")
assert common and not bad, "AC-15 FAILED - do not merge"
print("AC-15 PASS")
