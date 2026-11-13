"""Validate the portal session locally; one DB query, no user-info HTTP round trip."""
from __future__ import annotations

import hashlib
import os

import jwt
from fastapi import HTTPException

from .database import database_transaction


def local_session_enabled() -> bool:
    mode = os.getenv('WEBGAL_SSO_VALIDATION', 'auto').strip().lower()
    if mode not in {'auto', 'database', 'remote'}:
        raise HTTPException(503, 'Invalid WEBGAL_SSO_VALIDATION')
    secret = os.getenv('WEBGAL_SSO_JWT_SECRET') or os.getenv('AUTH_SECRET')
    if mode == 'database' and not secret:
        raise HTTPException(503, 'Local SSO validation requires the portal signing secret')
    return mode == 'database' or (mode == 'auto' and bool(secret))


def session_user(token: str) -> dict:
    secret = os.getenv('WEBGAL_SSO_JWT_SECRET') or os.getenv('AUTH_SECRET')
    if not secret:
        raise HTTPException(503, 'Local SSO validation requires the portal signing secret')
    try:
        claims = jwt.decode(token, secret, algorithms=['HS256'], options={'require': ['exp', 'iat', 'sub', 'jti']})
        if not isinstance(claims['sub'], str) or not isinstance(claims['jti'], str) or not claims['jti']:
            raise jwt.InvalidTokenError('Invalid identity')
    except jwt.InvalidTokenError as exc:
        raise HTTPException(401, 'SSO session is invalid or expired') from exc
    try:
        with database_transaction() as cursor:
            cursor.execute("""SELECT u.id,u.email,u.nickname,u.avatar_url,a.provider,COALESCE(c.blocked,0) AS blocked
                FROM auth_sessions s JOIN users u ON u.id=s.user_id
                LEFT JOIN accounts a ON a.user_id=u.id
                LEFT JOIN platform_resource_controls c ON c.resource_type='USER' AND c.resource_id=u.id
                WHERE s.token_hash=%s AND s.user_id=%s AND s.expires_at>CURRENT_TIMESTAMP(3)""",
                (hashlib.sha256(claims['jti'].encode()).hexdigest(), claims['sub']))
            rows = cursor.fetchall()
    except Exception as exc:
        raise HTTPException(503, 'SSO session database is unavailable') from exc
    if not rows:
        raise HTTPException(401, 'SSO session is invalid or expired')
    row = rows[0]
    if row['blocked']:
        raise HTTPException(403, '此账号已被禁止使用本平台')
    return {'id': row['id'], 'email': row['email'], 'nickname': row['nickname'],
            'avatar_url': row['avatar_url'], 'providers': list(dict.fromkeys(r['provider'] for r in rows if r['provider'])),
            'auth_type': 'sso'}
