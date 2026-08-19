"""Registration, verification, login, logout, profile, and password routes.

Enumeration posture
-------------------
Registration, forgotten-password, and verification-resend all return the same
generic acknowledgement whether or not the address exists. Login returns one
generic credential error for unknown addresses, wrong passwords, and unverified
accounts alike. Suspension is reported explicitly, because a suspended user
needs to know why they cannot get in and the account's existence is already
known to them.
"""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Request, Response, status
from sqlalchemy import select

from app.api.deps import (
    CurrentUserDep,
    DbDep,
    SettingsDep,
    client_identifier,
    enforce_rate_limit,
)
from app.api.schemas import (
    ChangePasswordRequest,
    ForgotPasswordRequest,
    LoginRequest,
    MessageResponse,
    RegisterRequest,
    ResendVerificationRequest,
    ResetPasswordRequest,
    UserProfile,
    VerifyEmailRequest,
)
from app.auth.sessions import (
    CSRF_COOKIE,
    SESSION_COOKIE,
    cookie_kwargs,
    create_session,
    load_session,
    revoke_all_for_user,
    revoke_session,
)
from app.auth.tokens import consume_token, issue_token
from app.core.errors import (
    InvalidCredentials,
    PermissionDenied,
    ValidationFailed,
)
from app.core.ratelimit import identifier_digest, reset_policy
from app.core.security import hash_password, password_needs_rehash, verify_password
from app.db.models import TokenPurpose, User, UserRole, UserStatus
from app.services import audit
from app.services.email import send_password_reset_email, send_verification_email

router = APIRouter(prefix="/auth", tags=["auth"])

#: One acknowledgement for every outcome, so the response cannot be used to
#: test whether an address is registered.
GENERIC_ACK = "If that address can receive this message, we have sent it. Check your inbox."


def _normalise_email(email: str) -> str:
    return email.strip().lower()


def _user_agent_family(request: Request) -> str | None:
    """A coarse client descriptor. Deliberately not a fingerprint."""
    agent = request.headers.get("user-agent", "")
    for family in ("Firefox", "Edg", "Chrome", "Safari", "curl"):
        if family in agent:
            return "Edge" if family == "Edg" else family
    return "Other" if agent else None


def _issue_session_cookies(
    response: Response, db: DbDep, user: User, settings: SettingsDep, request: Request
) -> None:
    issued = create_session(db, user, settings, user_agent_family=_user_agent_family(request))
    response.set_cookie(
        SESSION_COOKIE,
        issued.token,
        **cookie_kwargs(settings, max_age=settings.session_ttl_seconds),  # type: ignore[arg-type]
    )
    # Readable by the frontend so it can echo the value in the CSRF header.
    csrf_kwargs = cookie_kwargs(settings, max_age=settings.session_ttl_seconds)
    csrf_kwargs["httponly"] = False
    response.set_cookie(CSRF_COOKIE, issued.csrf_token, **csrf_kwargs)  # type: ignore[arg-type]


def _clear_session_cookies(response: Response, settings: SettingsDep) -> None:
    for name in (SESSION_COOKIE, CSRF_COOKIE):
        response.delete_cookie(
            name,
            path="/",
            domain=settings.cookie_domain or None,
        )


@router.post("/register", response_model=MessageResponse, status_code=status.HTTP_202_ACCEPTED)
def register(
    body: RegisterRequest, request: Request, db: DbDep, settings: SettingsDep
) -> MessageResponse:
    """Create an account and send a verification link."""
    enforce_rate_limit("register", request)
    email = _normalise_email(body.email)

    existing = db.execute(select(User).where(User.email == email)).scalar_one_or_none()
    if existing is None:
        user = User(
            email=email,
            password_hash=hash_password(body.password),
            role=UserRole.USER,
            status=UserStatus.PENDING,
        )
        db.add(user)
        db.flush()
        token = issue_token(db, user, TokenPurpose.EMAIL_VERIFICATION)
        audit.record(
            db,
            "user.registered",
            actor_user_id=user.id,
            target_type="user",
            target_id=str(user.id),
            actor_identifier_hash=identifier_digest(client_identifier(request)),
        )
        db.commit()
        send_verification_email(settings, email, token)
    else:
        # Same work-shaped delay and the same response, so timing and body do
        # not distinguish a taken address from a free one.
        hash_password(body.password)

    return MessageResponse(message=GENERIC_ACK)


@router.post("/verify", response_model=MessageResponse)
def verify_email(body: VerifyEmailRequest, db: DbDep) -> MessageResponse:
    """Consume a verification token and activate the account."""
    token = consume_token(db, body.token, TokenPurpose.EMAIL_VERIFICATION)
    if token is None:
        raise ValidationFailed("This verification link is invalid or has expired.")

    user = db.get(User, token.user_id)
    if user is None:
        raise ValidationFailed("This verification link is invalid or has expired.")

    if user.status == UserStatus.PENDING:
        user.status = UserStatus.ACTIVE
    user.email_verified_at = datetime.now(UTC)
    db.add(user)
    audit.record(
        db,
        "user.verified",
        actor_user_id=user.id,
        target_type="user",
        target_id=str(user.id),
    )
    db.commit()
    return MessageResponse(message="Your email address is confirmed. You can sign in.")


@router.post("/verify/resend", response_model=MessageResponse)
def resend_verification(
    body: ResendVerificationRequest, request: Request, db: DbDep, settings: SettingsDep
) -> MessageResponse:
    enforce_rate_limit("verification_resend", request)
    email = _normalise_email(body.email)
    user = db.execute(select(User).where(User.email == email)).scalar_one_or_none()

    if user is not None and user.status == UserStatus.PENDING:
        token = issue_token(db, user, TokenPurpose.EMAIL_VERIFICATION)
        db.commit()
        send_verification_email(settings, email, token)

    return MessageResponse(message=GENERIC_ACK)


@router.post("/login", response_model=UserProfile)
def login(
    body: LoginRequest,
    request: Request,
    response: Response,
    db: DbDep,
    settings: SettingsDep,
) -> UserProfile:
    """Authenticate and issue a fresh session (fixation protection)."""
    # Fail closed: a Redis outage must not open an unlimited guessing window.
    enforce_rate_limit("login", request, fail_closed=True)

    email = _normalise_email(body.email)
    user = db.execute(select(User).where(User.email == email)).scalar_one_or_none()

    if user is None:
        # Spend comparable work so the response time does not reveal existence.
        hash_password(body.password)
        raise InvalidCredentials()

    if not verify_password(body.password, user.password_hash):
        user.failed_login_count += 1
        db.add(user)
        db.commit()
        raise InvalidCredentials()

    if user.status == UserStatus.SUSPENDED:
        raise PermissionDenied(
            "This account is suspended. Contact support if you believe this is an error."
        )
    if user.status == UserStatus.PENDING:
        # Generic on purpose: this response is reachable without proving control
        # of the address, so it must not confirm that the account exists.
        raise InvalidCredentials()

    if password_needs_rehash(user.password_hash):
        user.password_hash = hash_password(body.password)

    user.failed_login_count = 0
    user.last_login_at = datetime.now(UTC)
    db.add(user)

    _issue_session_cookies(response, db, user, settings, request)
    audit.record(
        db,
        "user.login",
        actor_user_id=user.id,
        target_type="user",
        target_id=str(user.id),
        actor_identifier_hash=identifier_digest(client_identifier(request)),
    )
    db.commit()
    reset_policy("login", client_identifier(request))
    return UserProfile.model_validate(user)


@router.post("/logout", response_model=MessageResponse)
def logout(
    request: Request, response: Response, db: DbDep, settings: SettingsDep
) -> MessageResponse:
    """Revoke the current session server-side and clear its cookies."""
    # Resolve the session directly: this route must work even for a session
    # whose user is suspended or unverified.
    token = request.cookies.get(SESSION_COOKIE)
    session = load_session(db, token) if token else None
    if session is not None:
        from app.auth.csrf import validate_csrf
        from app.auth.sessions import CSRF_HEADER

        if not validate_csrf(session, request.headers.get(CSRF_HEADER)):
            from app.core.errors import CsrfFailed

            raise CsrfFailed()
        revoke_session(db, session)
        db.commit()

    _clear_session_cookies(response, settings)
    return MessageResponse(message="Signed out.")


@router.get("/session", response_model=UserProfile)
def current_session(user: CurrentUserDep) -> UserProfile:
    """Return the signed-in profile."""
    return UserProfile.model_validate(user)


@router.post("/password/forgot", response_model=MessageResponse)
def forgot_password(
    body: ForgotPasswordRequest, request: Request, db: DbDep, settings: SettingsDep
) -> MessageResponse:
    enforce_rate_limit("password_reset", request)
    email = _normalise_email(body.email)
    user = db.execute(select(User).where(User.email == email)).scalar_one_or_none()

    if user is not None and user.status != UserStatus.SUSPENDED:
        token = issue_token(db, user, TokenPurpose.PASSWORD_RESET)
        db.commit()
        send_password_reset_email(settings, email, token)

    return MessageResponse(message=GENERIC_ACK)


@router.post("/password/reset", response_model=MessageResponse)
def reset_password(body: ResetPasswordRequest, request: Request, db: DbDep) -> MessageResponse:
    """Consume a reset token, set the password, and revoke every session."""
    token = consume_token(db, body.token, TokenPurpose.PASSWORD_RESET)
    if token is None:
        raise ValidationFailed("This reset link is invalid or has expired.")

    user = db.get(User, token.user_id)
    if user is None:
        raise ValidationFailed("This reset link is invalid or has expired.")

    user.password_hash = hash_password(body.password)
    user.failed_login_count = 0
    if user.status == UserStatus.PENDING:
        # Completing a reset proves control of the address.
        user.status = UserStatus.ACTIVE
        user.email_verified_at = datetime.now(UTC)
    db.add(user)

    revoked = revoke_all_for_user(db, user.id)
    audit.record(
        db,
        "user.password_reset",
        actor_user_id=user.id,
        target_type="user",
        target_id=str(user.id),
        actor_identifier_hash=identifier_digest(client_identifier(request)),
        context={"sessions_revoked": revoked},
    )
    db.commit()
    return MessageResponse(message="Your password has been changed. Sign in again.")


@router.post("/password/change", response_model=MessageResponse)
def change_password(
    body: ChangePasswordRequest,
    request: Request,
    response: Response,
    user: CurrentUserDep,
    db: DbDep,
    settings: SettingsDep,
) -> MessageResponse:
    """Change the password, then rotate the session and revoke the others."""
    if not verify_password(body.current_password, user.password_hash):
        raise InvalidCredentials("Your current password is incorrect.")
    if body.current_password == body.new_password:
        raise ValidationFailed("The new password must differ from the current one.")

    user.password_hash = hash_password(body.new_password)
    db.add(user)

    revoke_all_for_user(db, user.id)
    _issue_session_cookies(response, db, user, settings, request)
    audit.record(
        db,
        "user.password_changed",
        actor_user_id=user.id,
        target_type="user",
        target_id=str(user.id),
    )
    db.commit()
    return MessageResponse(message="Your password has been changed.")


@router.delete("/account", response_model=MessageResponse)
def delete_account(
    response: Response, user: CurrentUserDep, db: DbDep, settings: SettingsDep
) -> MessageResponse:
    """Delete the account and every dependent record."""
    user_id = user.id
    db.delete(user)
    audit.record(db, "user.deleted", target_type="user", target_id=str(user_id))
    db.commit()
    _clear_session_cookies(response, settings)
    return MessageResponse(message="Your account and all associated data were deleted.")
