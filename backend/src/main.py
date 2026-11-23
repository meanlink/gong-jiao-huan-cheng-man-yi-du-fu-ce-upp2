import hashlib
import logging
import os
import uuid
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from redis import Redis, RedisError
from starlette.concurrency import run_in_threadpool

from scripts.seed_demo import seed
from . import conclusions, handover, plans, support_routes, surveys, walk_checks
from .auth import identity, issue_token, verify_password
from .db import connect, migrate
from .schemas import Credentials

log = logging.getLogger('transfer')
cache = Redis.from_url(os.environ.get('REDIS_URL', 'redis://localhost:6379/0'), socket_timeout=1)
limit_script = '''local n = redis.call('INCR', KEYS[1]);
if n == 1 then redis.call('EXPIRE', KEYS[1], 60) end; return n'''


@asynccontextmanager
async def lifespan(app):
    migrate()
    if os.environ.get('SEED_DEMO', '').lower() == 'true':
        try:
            seed()
        except Exception:
            log.exception('Demo seed failed')
    yield


app = FastAPI(title='公交换乘满意度复测', lifespan=lifespan)
app.include_router(plans.router)
app.include_router(surveys.router)
app.include_router(conclusions.router)
app.include_router(walk_checks.router)
app.include_router(handover.router)
app.include_router(support_routes.router)


@app.middleware('http')
async def login_throttle(request: Request, call_next):
    if request.method == 'POST' and request.url.path == '/auth/login':
        host = request.client.host if request.client else 'unknown'
        key = 'transfer:login:' + hashlib.sha256(host.encode()).hexdigest()
        try:
            count = await run_in_threadpool(cache.eval, limit_script, 1, key)
        except RedisError:
            return JSONResponse({'detail': '登录服务暂不可用，请稍后重试'}, status_code=503)
        if count > 40:
            return JSONResponse({'detail': '登录尝试过多，请稍后重试'}, status_code=429, headers={'Retry-After': '60'})
    return await call_next(request)


@app.middleware('http')
async def response_metadata(request: Request, call_next):
    response = await call_next(request)
    response.headers['X-Request-ID'] = uuid.uuid4().hex
    response.headers['Cache-Control'] = 'no-store'
    response.headers['X-Content-Type-Options'] = 'nosniff'
    return response


@app.exception_handler(RequestValidationError)
async def validation_error(request: Request, error: RequestValidationError):
    errors = [str(item['msg']).removeprefix('Value error, ') for item in error.errors()]
    return JSONResponse({'detail': '；'.join(errors)}, status_code=422)


@app.get('/health')
def health():
    with connect() as db:
        db.execute('SELECT 1')
    cache.ping()
    return {'status': 'ok'}


@app.post('/auth/login')
def login(data: Credentials):
    with connect() as db:
        account = db.execute('SELECT * FROM staff_account WHERE email=%s', (data.email.lower(),)).fetchone()
    if not account or not verify_password(data.password, account['password_hash']):
        raise HTTPException(401, '账号或密码不正确')
    return {'token': issue_token(account), 'user': {'email': account['email'], 'name': account['display_name'],
                                                    'role': account['role']}}


@app.get('/auth/me')
def who_am_i(user=Depends(identity)):
    return {'email': user['sub'], 'name': user['name'], 'role': user['role']}
