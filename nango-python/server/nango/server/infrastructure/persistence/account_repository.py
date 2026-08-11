from typing import Optional, List

from sqlalchemy.orm import Session

from nango.server.domain.entities import Account, Environment
from nango.server.domain.repositories import AccountRepository as DomainAccountRepository
from nango.server.models import Account as AccountModel, Environment as EnvironmentModel


class SQLAlchemyAccountRepository(DomainAccountRepository):
    def __init__(self, session: Session):
        self.session = session

    def get_by_id(self, account_id: int) -> Optional[Account]:
        model = self.session.get(AccountModel, account_id)
        if not model:
            return None
        return self._to_entity(model)

    def get_by_uuid(self, uuid: str) -> Optional[Account]:
        model = self.session.query(AccountModel).filter(
            AccountModel.uuid == uuid
        ).first()
        if not model:
            return None
        return self._to_entity(model)

    def save(self, account: Account) -> Account:
        if account.id:
            model = self.session.get(AccountModel, account.id)
            if model:
                model.name = account.name
                model.owner = account.owner
                model.secret_hash = account.secret_hash
        else:
            model = AccountModel(
                name=account.name,
                owner=account.owner,
                secret_hash=account.secret_hash,
                uuid=account.uuid,
            )
            self.session.add(model)

        self.session.commit()
        self.session.refresh(model)
        return self._to_entity(model)

    def delete(self, account_id: int) -> None:
        model = self.session.get(AccountModel, account_id)
        if model:
            self.session.delete(model)
            self.session.commit()

    def _to_entity(self, model: AccountModel) -> Account:
        return Account(
            id=model.id,
            name=model.name,
            owner=model.owner,
            secret_hash=model.secret_hash,
            uuid=model.uuid,
            created_at=model.created_at,
            updated_at=model.updated_at,
        )


class SQLAlchemyEnvironmentRepository(DomainAccountRepository):
    def __init__(self, session: Session):
        self.session = session

    def get_by_id(self, environment_id: int) -> Optional[Environment]:
        model = self.session.get(EnvironmentModel, environment_id)
        if not model:
            return None
        return self._to_entity(model)

    def get_by_uuid(self, uuid: str) -> Optional[Environment]:
        return None

    def save(self, environment: Environment) -> Environment:
        if environment.id:
            model = self.session.get(EnvironmentModel, environment.id)
            if model:
                model.name = environment.name
                model.secret_key = environment.secret_key
                model.public_key = environment.public_key
                model.callback_url = environment.callback_url
                model.webhooks = environment.webhooks
        else:
            model = EnvironmentModel(
                account_id=environment.account_id,
                name=environment.name,
                secret_key=environment.secret_key,
                public_key=environment.public_key,
                callback_url=environment.callback_url,
                webhooks=environment.webhooks,
                host=environment.host,
                port=environment.port,
                ssl=environment.ssl,
            )
            self.session.add(model)

        self.session.commit()
        self.session.refresh(model)
        return self._to_entity(model)

    def delete(self, environment_id: int) -> None:
        model = self.session.get(EnvironmentModel, environment_id)
        if model:
            self.session.delete(model)
            self.session.commit()

    def get_by_account_id(self, account_id: int) -> List[Environment]:
        models = self.session.query(EnvironmentModel).filter(
            EnvironmentModel.account_id == account_id
        ).all()
        return [self._to_entity(m) for m in models]

    def get_default(self, account_id: int) -> Optional[Environment]:
        model = self.session.query(EnvironmentModel).filter(
            EnvironmentModel.account_id == account_id
        ).first()
        if not model:
            return None
        return self._to_entity(model)

    def _to_entity(self, model: EnvironmentModel) -> Environment:
        return Environment(
            id=model.id,
            account_id=model.account_id,
            name=model.name,
            secret_key=model.secret_key,
            public_key=model.public_key,
            callback_url=model.callback_url,
            webhooks=model.webhooks,
            host=model.host,
            port=model.port,
            ssl=model.ssl,
            created_at=model.created_at,
            updated_at=model.updated_at,
        )