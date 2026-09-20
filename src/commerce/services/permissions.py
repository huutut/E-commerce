from enum import StrEnum

from commerce.domain.models import AdminRole, AdminUser


class AdminPermission(StrEnum):
    VIEW_DASHBOARD = "view_dashboard"
    MANAGE_PRODUCTS = "manage_products"
    MANAGE_ORDERS = "manage_orders"
    MANAGE_CUSTOMERS = "manage_customers"
    MANAGE_REPORTS = "manage_reports"
    MANAGE_AUDIT = "manage_audit"
    MANAGE_ADMINS = "manage_admins"
    MANAGE_API_KEYS = "manage_api_keys"


ROLE_PERMISSIONS: dict[AdminRole, set[AdminPermission]] = {
    AdminRole.OWNER: set(AdminPermission),
    AdminRole.OPERATOR: {
        AdminPermission.VIEW_DASHBOARD,
        AdminPermission.MANAGE_PRODUCTS,
        AdminPermission.MANAGE_ORDERS,
        AdminPermission.MANAGE_CUSTOMERS,
        AdminPermission.MANAGE_REPORTS,
        AdminPermission.MANAGE_AUDIT,
    },
}


def admin_has_permission(admin: AdminUser, permission: AdminPermission) -> bool:
    return permission in ROLE_PERMISSIONS.get(admin.role, set())


def permissions_for_role(role: AdminRole) -> list[AdminPermission]:
    return sorted(ROLE_PERMISSIONS.get(role, set()), key=lambda item: item.value)
