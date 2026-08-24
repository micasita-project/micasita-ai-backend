from fastapi import APIRouter, Depends, HTTPException, status, BackgroundTasks
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.models.user import User
from app.schemas.user import (
    UserCreate, UserResponse, Token,
    UserHomeUpdate, UserProfileUpdate,
    ForgotPasswordRequest, ResetPasswordRequest,
    VerifyEmailRequest, ResendVerificationRequest,
    ChangePasswordRequest,
)
from app.core.security import get_password_hash, verify_password, create_access_token, get_current_user
from app.core.geo import is_within_lima, LIMA_LOCATION_ERROR
from app.core.config import settings
from app.core.email import email_service
from app.core.email_templates import get_otp_template
from app.core.otp import password_reset_store, email_verify_store
from datetime import timedelta
from fastapi.security import OAuth2PasswordRequestForm

router = APIRouter(prefix="/auth", tags=["Authentication"])


def _send_verification_email(email: str, name: str | None):
    code = email_verify_store.generate(email)
    html = get_otp_template("verify_email", code, name)
    email_service.send_email(
        to_address=email,
        subject="Verifica tu correo — MiCasita",
        html_content=html,
    )


@router.post(
    "/register",
    response_model=UserResponse,
    summary="Registrar usuario",
    response_description="Usuario creado; se enviará un OTP al email para verificarlo",
    responses={400: {"description": "El email ya está registrado"}},
)
def register_user(user: UserCreate, background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    """
    Crea una nueva cuenta de usuario con rol `user` por defecto.

    La cuenta queda con `email_verified=False` hasta que el usuario confirme
    el código enviado a su correo. El login requiere verificación previa.

    Si ya existe un registro previo con este correo pero nunca se verificó,
    se reemplaza (nueva contraseña, nuevo OTP) en vez de bloquear el intento:
    de lo contrario, no completar la verificación deja el correo inutilizable
    para siempre, sin forma de volver a intentarlo.
    """
    db_user = db.query(User).filter(User.email == user.email).first()
    if db_user:
        if db_user.email_verified:
            raise HTTPException(status_code=400, detail="El email ya está registrado")
        db_user.hashed_password = get_password_hash(user.password)
        db_user.name = user.name
        db_user.last_name = user.last_name
        db.commit()
        db.refresh(db_user)
        background_tasks.add_task(_send_verification_email, db_user.email, db_user.name)
        return db_user

    hashed_password = get_password_hash(user.password)
    new_user = User(
        email=user.email,
        hashed_password=hashed_password,
        role="user",
        name=user.name,
        last_name=user.last_name,
        email_verified=False,
    )
    db.add(new_user)
    db.commit()
    db.refresh(new_user)

    background_tasks.add_task(_send_verification_email, new_user.email, new_user.name)
    return new_user


@router.post(
    "/login",
    response_model=Token,
    summary="Iniciar sesión",
    response_description="Token JWT Bearer",
    responses={
        401: {"description": "Email o contraseña incorrectos"},
        403: {"description": "Cuenta bloqueada o email no verificado"},
    },
)
def login(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == form_data.username).first()
    if not user or not verify_password(form_data.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Email o contraseña incorrectos",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Esta cuenta ha sido bloqueada o suspendida por un administrador.",
        )

    if not user.email_verified:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Por favor verifica tu correo electrónico antes de iniciar sesión. Revisa tu bandeja de entrada.",
        )

    access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": user.email}, expires_delta=access_token_expires
    )
    return {"access_token": access_token, "token_type": "bearer"}


@router.get(
    "/me",
    response_model=UserResponse,
    summary="Obtener perfil propio",
    response_description="Perfil del usuario autenticado",
)
def get_me(current_user: User = Depends(get_current_user)):
    """Devuelve el perfil completo del usuario autenticado."""
    return current_user


@router.patch(
    "/me",
    response_model=UserResponse,
    summary="Actualizar perfil",
    response_description="Perfil actualizado",
)
def update_profile(profile_data: UserProfileUpdate, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Actualiza el nombre y/o apellido del usuario. Solo los campos enviados se modifican."""
    if profile_data.name is not None:
        current_user.name = profile_data.name
    if profile_data.last_name is not None:
        current_user.last_name = profile_data.last_name

    db.commit()
    db.refresh(current_user)
    return current_user


@router.put(
    "/me/home",
    response_model=UserResponse,
    summary="Actualizar ubicación de casa actual",
    response_description="Perfil con nueva ubicación de casa",
)
def update_user_home(home_data: UserHomeUpdate, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """
    Guarda la ubicación de la vivienda actual del usuario.

    Esta coordenada se usa para calcular `time_saved_mins` en las recomendaciones.
    """
    if not is_within_lima(home_data.home_lat, home_data.home_lon):
        raise HTTPException(status_code=400, detail=LIMA_LOCATION_ERROR)

    current_user.home_lat = home_data.home_lat
    current_user.home_lon = home_data.home_lon
    current_user.home_address = home_data.home_address
    db.commit()
    db.refresh(current_user)
    return current_user


@router.post(
    "/me/change-password",
    summary="Cambiar contraseña (sesión activa)",
    response_description="Contraseña actualizada",
    responses={400: {"description": "Contraseña actual incorrecta o nueva inválida"}},
)
def change_password(
    data: ChangePasswordRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Permite a un usuario autenticado cambiar su contraseña verificando la actual."""
    if not verify_password(data.current_password, current_user.hashed_password):
        raise HTTPException(status_code=400, detail="La contraseña actual es incorrecta.")

    if verify_password(data.new_password, current_user.hashed_password):
        raise HTTPException(status_code=400, detail="La nueva contraseña debe ser distinta a la actual.")

    current_user.hashed_password = get_password_hash(data.new_password)
    db.commit()
    return {"message": "Contraseña actualizada correctamente."}


# ── Email verification ────────────────────────────────────────────────────────

@router.post(
    "/verify-email",
    summary="Verificar correo con OTP",
    response_description="Correo verificado correctamente",
    responses={
        400: {"description": "Código incorrecto o expirado"},
        404: {"description": "Usuario no encontrado"},
    },
)
def verify_email(data: VerifyEmailRequest, db: Session = Depends(get_db)):
    """Confirma el OTP enviado al registrarse y activa la cuenta."""
    user = db.query(User).filter(User.email == data.email).first()
    if not user:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")

    if not email_verify_store.verify(data.email, data.otp):
        raise HTTPException(status_code=400, detail="Código incorrecto o expirado")

    user.email_verified = True
    db.commit()
    return {"message": "Correo verificado correctamente. Ya puedes iniciar sesión."}


@router.post(
    "/resend-verification",
    summary="Reenviar OTP de verificación",
    response_description="OTP reenviado al correo",
    responses={
        400: {"description": "El correo ya está verificado"},
        404: {"description": "Usuario no encontrado"},
    },
)
def resend_verification(data: ResendVerificationRequest, background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    """Reenvía el código de verificación. Útil si el email anterior expiró."""
    user = db.query(User).filter(User.email == data.email).first()
    if not user:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")

    if user.email_verified:
        raise HTTPException(status_code=400, detail="Este correo ya está verificado")

    background_tasks.add_task(_send_verification_email, user.email, user.name)
    return {"message": "Se ha enviado un nuevo código de verificación a tu correo."}


# ── Forgot password ───────────────────────────────────────────────────────────

@router.post(
    "/forgot-password",
    summary="Solicitar restablecimiento de contraseña",
    response_description="OTP enviado si el email existe",
)
def forgot_password(data: ForgotPasswordRequest, background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    """
    Genera un OTP de 6 dígitos (válido 15 min) y lo envía al correo.

    Por seguridad devuelve siempre el mismo mensaje aunque el email no exista.
    """
    user = db.query(User).filter(User.email == data.email).first()
    if user:
        def send_reset(email: str, name: str | None):
            code = password_reset_store.generate(email)
            html = get_otp_template("reset_password", code, name)
            email_service.send_email(
                to_address=email,
                subject="Restablecer contraseña — MiCasita",
                html_content=html,
            )
        background_tasks.add_task(send_reset, user.email, user.name)

    return {"message": "Si ese correo está registrado, recibirás un código en breve."}


@router.post(
    "/reset-password",
    summary="Restablecer contraseña con OTP",
    response_description="Contraseña actualizada",
    responses={400: {"description": "Código incorrecto, expirado o contraseña inválida"}},
)
def reset_password(data: ResetPasswordRequest, db: Session = Depends(get_db)):
    """Verifica el OTP y actualiza la contraseña del usuario."""
    if not password_reset_store.verify(data.email, data.otp):
        raise HTTPException(status_code=400, detail="Código incorrecto o expirado")

    user = db.query(User).filter(User.email == data.email).first()
    if not user:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")

    user.hashed_password = get_password_hash(data.new_password)
    db.commit()
    return {"message": "Contraseña actualizada correctamente. Ya puedes iniciar sesión."}
