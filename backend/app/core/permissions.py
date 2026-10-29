from typing import Literal

Role = Literal["owner", "administrator", "analyst", "viewer"]

ROLE_PERMISSIONS: dict[str, frozenset[str]] = {
    "owner": frozenset({"business:read", "business:write", "team:read", "team:write", "audit:read"}),
    "administrator": frozenset({"business:read", "business:write", "team:read", "team:write", "audit:read"}),
    "analyst": frozenset({"business:read", "team:read"}),
    "viewer": frozenset({"business:read"}),
}
for _role in ROLE_PERMISSIONS:
    ROLE_PERMISSIONS[_role] = ROLE_PERMISSIONS[_role] | {"data:read", "documents:read", "ml:read", "twin:read", "simulation:read", "analyst:read", "graph:read", "reports:read"}
for _role in ("owner", "administrator"):
    ROLE_PERMISSIONS[_role] = ROLE_PERMISSIONS[_role] | {"data:write", "documents:write", "ml:deploy", "graph:build"}


def may_manage_role(actor: str, target: str) -> bool:
    return actor == "owner" or (actor == "administrator" and target in {"analyst", "viewer"})

for _role in ("owner", "administrator", "analyst"):
    ROLE_PERMISSIONS[_role] = ROLE_PERMISSIONS[_role] | {"ml:train", "twin:write", "simulation:run", "analyst:ask", "reports:create"}
