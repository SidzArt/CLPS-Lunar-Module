"""Super-administrator RBAC, user lifecycle, credential reset, and session revocation routes."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.core.audit import log_audit
from app.core.auth_dependency import RequireRole, get_admin_roles
from app.core.security import hash_password, validate_password_policy
from app.db.session import get_db
from app.models.admin import Admin, AdminRoleLink, AdminSession, Role
from app.schemas.admin_portal import (
    AdminResetPasswordIn,
    AdminSessionRevokeOut,
    AdminUserCreateIn,
    AdminUserOut,
    AdminUserUpdateIn,
    RoleOut,
)

router = APIRouter(prefix="/admin", tags=["Admin Users & RBAC"])

SuperAdminUser = Annotated[Admin, Depends(RequireRole("super_admin"))]


def _serialize_admin_user(db: Session, user: Admin) -> AdminUserOut:
    roles = get_admin_roles(db, str(user.admin_id))
    active_sessions = (
        db.scalar(
            select(func.count())
            .select_from(AdminSession)
            .where(
                AdminSession.admin_id == user.admin_id,
                AdminSession.is_revoked.is_(False),
                AdminSession.expires_at > datetime.now(UTC),
            )
        )
        or 0
    )
    return AdminUserOut(
        admin_id=user.admin_id,
        username=user.username,
        display_name=user.display_name,
        is_active=user.is_active,
        failed_login_count=user.failed_login_count,
        locked_until=user.locked_until,
        password_updated_at=user.password_updated_at,
        password_must_rotate=bool(user.password_must_rotate),
        created_at=user.created_at,
        last_login_at=user.last_login_at,
        roles=sorted(roles),
        active_sessions_count=int(active_sessions),
    )


def _resolve_roles(db: Session, role_keys: list[str]) -> list[Role]:
    unique_keys = list(dict.fromkeys(k.strip() for k in role_keys if k.strip()))
    if not unique_keys:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="At least one valid role_key is required.",
        )
    roles = list(db.scalars(select(Role).where(Role.role_key.in_(unique_keys))).all())
    found = {r.role_key for r in roles}
    missing = [k for k in unique_keys if k not in found]
    if missing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unknown role key(s): {', '.join(missing)}",
        )
    return roles


def _count_other_active_super_admins(db: Session, exclude_admin_id: UUID) -> int:
    count = db.scalar(
        select(func.count(func.distinct(Admin.admin_id)))
        .select_from(Admin)
        .join(AdminRoleLink, Admin.admin_id == AdminRoleLink.admin_id)
        .join(Role, Role.role_id == AdminRoleLink.role_id)
        .where(
            Role.role_key == "super_admin",
            Admin.is_active.is_(True),
            Admin.admin_id != exclude_admin_id,
        )
    )
    return int(count or 0)


def _revoke_user_sessions(db: Session, admin_id: UUID) -> int:
    result = db.execute(
        update(AdminSession)
        .where(
            AdminSession.admin_id == admin_id,
            AdminSession.is_revoked.is_(False),
        )
        .values(is_revoked=True)
    )
    return int(getattr(result, "rowcount", 0) or 0)


@router.get(
    "/roles",
    response_model=list[RoleOut],
    summary="List registered RBAC roles",
)
def list_roles(
    _admin: SuperAdminUser,
    db: Annotated[Session, Depends(get_db)],
) -> list[RoleOut]:
    roles = list(db.scalars(select(Role).order_by(Role.role_id.asc())).all())
    return [
        RoleOut(role_id=r.role_id, role_key=r.role_key, description=r.description) for r in roles
    ]


@router.get(
    "/users",
    response_model=list[AdminUserOut],
    summary="List administrator accounts (credential hashes omitted)",
)
def list_admin_users(
    _admin: SuperAdminUser,
    db: Annotated[Session, Depends(get_db)],
) -> list[AdminUserOut]:
    users = list(db.scalars(select(Admin).order_by(Admin.username.asc())).all())
    return [_serialize_admin_user(db, u) for u in users]


@router.post(
    "/users",
    response_model=AdminUserOut,
    status_code=status.HTTP_201_CREATED,
    summary="Create administrator user and assign RBAC roles",
)
def create_admin_user(
    payload: AdminUserCreateIn,
    request: Request,
    current_admin: SuperAdminUser,
    db: Annotated[Session, Depends(get_db)],
) -> AdminUserOut:
    existing = db.scalar(select(Admin).where(Admin.username == payload.username))
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Administrator username '{payload.username}' already exists.",
        )

    try:
        validate_password_policy(payload.password)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(exc),
        ) from exc

    roles = _resolve_roles(db, payload.role_keys)
    user = Admin(
        username=payload.username,
        password_hash=hash_password(payload.password),
        display_name=payload.display_name or payload.username,
        is_active=payload.is_active,
        password_updated_at=datetime.now(UTC),
        password_must_rotate=payload.password_must_rotate,
    )
    db.add(user)
    db.flush()

    for role in roles:
        db.add(AdminRoleLink(admin_id=user.admin_id, role_id=role.role_id))
    db.flush()

    log_audit(
        db,
        action_key="ADMIN_USER_CREATE",
        entity_type="admins",
        entity_id=str(user.admin_id),
        admin_id=str(current_admin.admin_id),
        after_snapshot={
            "username": user.username,
            "is_active": user.is_active,
            "roles": sorted(r.role_key for r in roles),
        },
        ip_address=request.client.host if request.client else None,
    )
    db.commit()
    db.refresh(user)
    return _serialize_admin_user(db, user)


@router.patch(
    "/users/{admin_id}",
    response_model=AdminUserOut,
    summary="Update administrator profile, active status, role assignments, or lockout state",
)
def update_admin_user(
    admin_id: UUID,
    payload: AdminUserUpdateIn,
    request: Request,
    current_admin: SuperAdminUser,
    db: Annotated[Session, Depends(get_db)],
) -> AdminUserOut:
    target = db.get(Admin, admin_id)
    if not target:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Administrator {admin_id} was not found.",
        )

    current_roles = set(get_admin_roles(db, str(target.admin_id)))
    if target.admin_id == current_admin.admin_id and payload.is_active is False:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="You cannot deactivate your own active super_admin account.",
        )

    if (
        target.admin_id == current_admin.admin_id
        and payload.role_keys is not None
        and "super_admin" not in payload.role_keys
    ):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="You cannot remove the 'super_admin' role from your own active account.",
        )

    will_be_active = target.is_active if payload.is_active is None else payload.is_active
    next_roles = set(payload.role_keys) if payload.role_keys is not None else current_roles
    was_active_super = target.is_active and "super_admin" in current_roles
    remains_active_super = will_be_active and "super_admin" in next_roles
    if (
        was_active_super
        and not remains_active_super
        and _count_other_active_super_admins(db, target.admin_id) < 1
    ):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot deactivate or demote the last active super_admin account.",
        )

    before_snapshot = {
        "display_name": target.display_name,
        "is_active": target.is_active,
        "roles": sorted(current_roles),
        "failed_login_count": target.failed_login_count,
    }

    if payload.display_name is not None:
        target.display_name = payload.display_name
    if payload.is_active is not None:
        target.is_active = payload.is_active
    if payload.password_must_rotate is not None:
        target.password_must_rotate = payload.password_must_rotate
    if payload.unlock_account:
        target.failed_login_count = 0
        target.locked_until = None

    roles_changed = False
    if payload.role_keys is not None:
        resolved_roles = _resolve_roles(db, payload.role_keys)
        new_role_keys = {r.role_key for r in resolved_roles}
        if new_role_keys != current_roles:
            roles_changed = True
            existing_links = list(
                db.scalars(
                    select(AdminRoleLink).where(AdminRoleLink.admin_id == target.admin_id)
                ).all()
            )
            for link in existing_links:
                db.delete(link)
            db.flush()
            for role in resolved_roles:
                db.add(AdminRoleLink(admin_id=target.admin_id, role_id=role.role_id))
            db.flush()

    revoked_count = 0
    if (roles_changed or payload.is_active is False) and target.admin_id != current_admin.admin_id:
        revoked_count = _revoke_user_sessions(db, target.admin_id)

    log_audit(
        db,
        action_key="ADMIN_USER_UPDATE",
        entity_type="admins",
        entity_id=str(target.admin_id),
        admin_id=str(current_admin.admin_id),
        before_snapshot=before_snapshot,
        after_snapshot={
            "display_name": target.display_name,
            "is_active": target.is_active,
            "roles": sorted(next_roles),
            "unlocked": payload.unlock_account,
            "revoked_sessions": revoked_count,
        },
        ip_address=request.client.host if request.client else None,
    )
    db.commit()
    db.refresh(target)
    return _serialize_admin_user(db, target)


@router.post(
    "/users/{admin_id}/reset-password",
    response_model=AdminUserOut,
    summary="Reset an administrator password and revoke existing sessions",
)
def reset_admin_password(
    admin_id: UUID,
    payload: AdminResetPasswordIn,
    request: Request,
    current_admin: SuperAdminUser,
    db: Annotated[Session, Depends(get_db)],
) -> AdminUserOut:
    target = db.get(Admin, admin_id)
    if not target:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Administrator {admin_id} was not found.",
        )
    try:
        validate_password_policy(payload.new_password)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(exc),
        ) from exc

    target.password_hash = hash_password(payload.new_password)
    target.password_updated_at = datetime.now(UTC)
    target.password_must_rotate = payload.password_must_rotate
    target.failed_login_count = 0
    target.locked_until = None
    revoked_count = _revoke_user_sessions(db, target.admin_id)

    log_audit(
        db,
        action_key="ADMIN_PASSWORD_RESET",
        entity_type="admins",
        entity_id=str(target.admin_id),
        admin_id=str(current_admin.admin_id),
        after_snapshot={
            "username": target.username,
            "password_must_rotate": target.password_must_rotate,
            "revoked_sessions": revoked_count,
        },
        ip_address=request.client.host if request.client else None,
    )
    db.commit()
    db.refresh(target)
    return _serialize_admin_user(db, target)


@router.post(
    "/users/{admin_id}/revoke-sessions",
    response_model=AdminSessionRevokeOut,
    summary="Immediately revoke all active sessions belonging to an administrator",
)
def revoke_admin_user_sessions(
    admin_id: UUID,
    request: Request,
    current_admin: SuperAdminUser,
    db: Annotated[Session, Depends(get_db)],
) -> AdminSessionRevokeOut:
    target = db.get(Admin, admin_id)
    if not target:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Administrator {admin_id} was not found.",
        )

    revoked_count = _revoke_user_sessions(db, target.admin_id)
    log_audit(
        db,
        action_key="ADMIN_SESSIONS_REVOKE",
        entity_type="admin_sessions",
        entity_id=str(target.admin_id),
        admin_id=str(current_admin.admin_id),
        after_snapshot={"username": target.username, "revoked_sessions": revoked_count},
        ip_address=request.client.host if request.client else None,
    )
    db.commit()
    return AdminSessionRevokeOut(admin_id=target.admin_id, revoked_sessions_count=revoked_count)
