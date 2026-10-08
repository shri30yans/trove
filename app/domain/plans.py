"""Server-owned storage plans and their hard quota limits."""

from dataclasses import dataclass
from typing import Literal

PlanId = Literal["free", "paid"]


@dataclass(frozen=True)
class StoragePlan:
    id: PlanId
    name: str
    limit_bytes: int


FREE_PLAN = StoragePlan(id="free", name="Free", limit_bytes=200_000_000)
PAID_PLAN = StoragePlan(id="paid", name="Paid", limit_bytes=1_000_000_000)
PLANS: dict[str, StoragePlan] = {FREE_PLAN.id: FREE_PLAN, PAID_PLAN.id: PAID_PLAN}


def get_storage_plan(plan_id: str) -> StoragePlan:
    """Fail closed if persisted plan data is not supported."""
    try:
        return PLANS[plan_id]
    except KeyError as error:
        raise ValueError("Unsupported storage plan.") from error


def storage_plan_payload(plan_id: str, used_bytes: int) -> dict[str, str | int]:
    plan = get_storage_plan(plan_id)
    return {
        "id": plan.id,
        "name": plan.name,
        "storageLimitBytes": plan.limit_bytes,
        "storageUsedBytes": used_bytes,
        "storageRemainingBytes": max(0, plan.limit_bytes - used_bytes),
    }
