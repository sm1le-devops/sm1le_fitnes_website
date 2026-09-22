import re
from secrets import token_urlsafe

from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer
from passlib.context import CryptContext

from core.config import settings

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def get_csrf_serializer() -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(settings.csrf_secret)

def generate_csrf_token() -> str:
    return get_csrf_serializer().dumps(token_urlsafe(32))

def validate_csrf_token(token: str) -> bool:
    if not token:
        return False

    try:
        get_csrf_serializer().loads(token, max_age=3600)
        return True
    except (BadSignature, SignatureExpired):
        return False


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)

def get_password_hash(password: str) -> str:
    return pwd_context.hash(password)

def is_username_valid(username: str) -> bool:
    return bool(re.fullmatch(r"[a-zA-Z0-9_]+", username))