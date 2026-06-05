from __future__ import annotations
from datetime import date
from pydantic import Field, model_validator
from ._types import FrozenModel


class ModelPrice(FrozenModel):
    input_per_mtok: float = Field(ge=0)
    output_per_mtok: float = Field(ge=0)


class LLMProviderPricing(FrozenModel):
    currency: str = Field(min_length=1)
    models: dict[str, ModelPrice] = Field(min_length=1)


class SearchPricing(FrozenModel):
    currency: str = Field(min_length=1)
    per_query: float | None = None
    per_page: float | None = None

    @model_validator(mode="after")
    def _one_rate(self) -> "SearchPricing":
        if (self.per_query is None) == (self.per_page is None):
            raise ValueError("search pricing needs exactly one of per_query / per_page")
        return self


class TaskSeed(FrozenModel):
    calls: float = Field(ge=0)
    prompt_tokens: float = Field(ge=0)
    completion_tokens: float = Field(ge=0)


class SearchSeed(FrozenModel):
    units: float = Field(ge=0)   # expected queries (or pages) per run


class SpendPricingConfig(FrozenModel):
    margin: float = Field(default=1.2, gt=0)
    llm: dict[str, LLMProviderPricing] = Field(min_length=1)
    search: dict[str, SearchPricing] = Field(default_factory=dict)
    seeds: dict[str, TaskSeed] = Field(default_factory=dict)
    search_seeds: dict[str, SearchSeed] = Field(default_factory=dict)


class SpendBalanceEntry(FrozenModel):
    balance: float | None = None      # wallet
    as_of: date | None = None         # wallet
    quota: float | None = None        # quota
    reset: str | None = None          # quota: "monthly"
    reset_day: int = Field(default=1, ge=1, le=28)

    @model_validator(mode="after")
    def _wallet_xor_quota(self) -> "SpendBalanceEntry":
        is_wallet = self.balance is not None and self.as_of is not None
        is_quota = self.quota is not None and self.reset is not None
        if is_wallet == is_quota:
            raise ValueError(
                "balance entry must be EITHER a wallet (balance + as_of) "
                "OR a quota (quota + reset), not both/neither"
            )
        return self


class SpendBalancesConfig(FrozenModel):
    entries: dict[str, SpendBalanceEntry] = Field(default_factory=dict)
