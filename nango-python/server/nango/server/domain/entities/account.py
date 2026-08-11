from datetime import datetime
from typing import Optional
from dataclasses import dataclass, field
from uuid import uuid4


@dataclass
class Account:
    id: Optional[int] = None
    name: str = ''
    owner: Optional[str] = None
    secret_hash: Optional[str] = None
    uuid: str = field(default_factory=lambda: str(uuid4()))
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    @staticmethod
    def create(name: str, owner: Optional[str] = None) -> 'Account':
        return Account(
            name=name,
            owner=owner,
            uuid=str(uuid4()),
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow()
        )


@dataclass
class Environment:
    id: Optional[int] = None
    account_id: int = 0
    name: str = ''
    secret_key: Optional[str] = None
    public_key: Optional[str] = None
    callback_url: Optional[str] = None
    webhooks: Optional[str] = None
    host: Optional[str] = None
    port: Optional[int] = None
    ssl: bool = False
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    @staticmethod
    def create(account_id: int, name: str, callback_url: Optional[str] = None) -> 'Environment':
        return Environment(
            account_id=account_id,
            name=name,
            callback_url=callback_url,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow()
        )