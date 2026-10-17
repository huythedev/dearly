"""Wire identifiers and permission definitions shared by the API."""

from __future__ import annotations

SWIFT_EPOCH = 978307200  # Swift JSONEncoder default: seconds since 2001-01-01 UTC.
SESSION_LIFETIME = 30 * 86400
SUPPORT = frozenset({"listen", "relate", "brainstorm"})
LEGACY_SUPPORT = {
    "Chỉ cần lắng nghe": "listen",
    "Chia sẻ trải nghiệm": "relate",
    "Cùng nghĩ cách": "brainstorm",
}
ROLE_PERMISSIONS = {
    "user": frozenset(),
    "moderator": frozenset({"reports.read", "reports.review", "reports.hide", "users.read", "users.verify_age"}),
    "admin": frozenset(
        {
            "reports.read",
            "reports.review",
            "reports.hide",
            "users.read",
            "users.suspend",
            "users.verify_age",
            "roles.manage",
            "audit.read",
        }
    ),
}
STAFF_ACTIONS = {
    "staff.report.review": "reports.review",
    "staff.report.hide": "reports.hide",
    "staff.report.restore": "reports.hide",
    "staff.user.suspend": "users.suspend",
    "staff.user.verify_age": "users.verify_age",
    "staff.user.role": "roles.manage",
}
PRIVATE_HEADERS = {"Cache-Control": "no-store", "Vary": "Authorization"}
