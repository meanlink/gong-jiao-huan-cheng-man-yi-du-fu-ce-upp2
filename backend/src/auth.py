import hashlib
import hmac
import os
import secrets
from datetime import datetime, timedelta, timezone

import jwt
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

bearer = HTTPBearer(auto_error=False)


def password_hash(password, salt=None):
    salt = salt or secrets.token_hex(16)
    digest = hashlib.scrypt(password.encode(), salt=salt.encode(), n=2**14, r=8, p=1).hex()
    return f'{salt}:{digest}'


def verify_password(password, stored):
    return hmac.compare_digest(password_hash(password, stored.split(':', 1)[0]), stored)


def passenger_key(token):
    return hmac.digest(os.environ['PASSENGER_SECRET'].encode(), token.strip().casefold().encode(), 'sha256').hex()


def issue_token(account):
    now = datetime.now(timezone.utc)
    claims = dict(sub=account['email'], role=account['role'], name=account['display_name'],
                  iss='bus-transfer-satisfaction', iat=now, exp=now + timedelta(hours=6))
    return jwt.encode(claims, os.environ['JWT_SECRET'], algorithm='HS256')


def identity(credentials: HTTPAuthorizationCredentials | None = Depends(bearer)):
    if credentials:
        try:
            return jwt.decode(credentials.credentials, os.environ['JWT_SECRET'], algorithms=['HS256'],
                              issuer='bus-transfer-satisfaction', options={'require': ['sub', 'role', 'exp']})
        except jwt.InvalidTokenError:
            pass
    raise HTTPException(401, '请登录或刷新已过期的会话', headers={'WWW-Authenticate': 'Bearer'})


def allowed(*roles):
    def check(user=Depends(identity)):
        if user['role'] not in roles:
            raise HTTPException(403, '该操作由负责此环节的岗位执行')
        return user
    return check
