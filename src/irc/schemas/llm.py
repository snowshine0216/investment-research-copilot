from __future__ import annotations
import ipaddress
from urllib.parse import urlparse
from pydantic import Field, field_validator, model_validator
from ._types import FrozenModel


REQUIRED_TASKS: tuple[str, ...] = (
    "memo_synthesis",
    "memo_audit",
)

# Private/link-local ranges that are blocked to prevent SSRF.
# localhost (127.x, ::1) are explicitly allowed for dev mock servers.
# Note: the guard checks IP literals only. DNS names that resolve to blocked IPs
# at runtime are not caught here — this is a parse-time guard, not a connection-time guard.
_BLOCKED_NETWORKS: tuple[ipaddress.IPv4Network | ipaddress.IPv6Network, ...] = (
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("169.254.0.0/16"),   # AWS/Azure metadata
    ipaddress.ip_network("100.64.0.0/10"),     # Carrier-grade NAT
    ipaddress.ip_network("fd00::/8"),          # IPv6 ULA
    ipaddress.ip_network("fe80::/10"),         # IPv6 link-local
)


class _PrivateIPError(ValueError):
    """Raised when base_url points to a blocked private/reserved IP range."""


def _validate_base_url(value: str) -> str:
    """Reject URLs that point to private/link-local IP ranges (SSRF guard).
    Localhost (127.x, ::1) are explicitly allowed for dev mock servers.

    Limitation: only IP literals are checked; DNS names are not resolved.
    """
    parsed = urlparse(value)
    if parsed.scheme not in ("http", "https"):
        raise ValueError(f"base_url must use http or https scheme, got: {parsed.scheme!r}")
    host = parsed.hostname or ""
    if not host:
        raise ValueError("base_url must have a non-empty host")
    try:
        addr = ipaddress.ip_address(host)
        # Allow loopback (127.x, ::1) explicitly for local dev mock servers
        if addr.is_loopback:
            return value
        for net in _BLOCKED_NETWORKS:
            if addr in net:
                raise _PrivateIPError(
                    f"base_url host {host!r} is in a private/reserved IP range; "
                    "use a public hostname or localhost for dev mock servers"
                )
    except _PrivateIPError:
        raise
    except ValueError:
        # host is a DNS name (not an IP literal) — allowed
        pass
    return value


class ProviderConfig(FrozenModel):
    base_url: str | None = None
    base_url_env: str | None = None
    api_key_env: str = Field(min_length=1)
    default_model_env: str | None = None

    @field_validator("base_url")
    @classmethod
    def _check_base_url(cls, v: str | None) -> str | None:
        return _validate_base_url(v) if v else v

    @model_validator(mode="after")
    def _exactly_one_base(self) -> "ProviderConfig":
        if (self.base_url is None) == (self.base_url_env is None):
            raise ValueError("provider needs exactly one of base_url / base_url_env")
        return self


class TaskRoute(FrozenModel):
    provider: str
    model: str | None = None  # None => resolve from provider.default_model_env at call edge


class LLMConfig(FrozenModel):
    providers: dict[str, ProviderConfig] = Field(min_length=1)
    tasks: dict[str, TaskRoute] = Field(min_length=1)

    @model_validator(mode="after")
    def _validate_routes(self) -> "LLMConfig":
        for task_name, route in self.tasks.items():
            if route.provider not in self.providers:
                raise ValueError(
                    f"task '{task_name}' references unknown provider '{route.provider}'"
                )
            if route.model is None and self.providers[route.provider].default_model_env is None:
                raise ValueError(
                    f"task '{task_name}' omits model but provider "
                    f"'{route.provider}' has no default_model_env to resolve it"
                )
        missing = [t for t in REQUIRED_TASKS if t not in self.tasks]
        if missing:
            raise ValueError(f"required tasks missing: {missing}")
        return self
