import yaml
from pathlib import Path
from typing import Optional

from pydantic import BaseModel


class ProviderCredentials(BaseModel):
    type: str
    title: str
    description: str
    secret: bool = False
    doc_section: Optional[str] = None


class ProviderConnectionConfig(BaseModel):
    type: str
    title: str
    description: str
    example: Optional[str] = None
    pattern: Optional[str] = None
    prefix: Optional[str] = None
    format: Optional[str] = None
    order: Optional[int] = None
    doc_section: Optional[str] = None


class ProviderProxy(BaseModel):
    base_url: str
    headers: Optional[dict] = None
    verification: Optional[dict] = None


class Provider(BaseModel):
    display_name: str
    categories: list[str]
    auth_mode: str
    proxy: Optional[ProviderProxy] = None
    docs: Optional[str] = None
    docs_connect: Optional[str] = None
    connection_config: Optional[dict[str, ProviderConnectionConfig]] = None
    credentials: Optional[dict[str, ProviderCredentials]] = None
    token_url: Optional[str] = None
    token_headers: Optional[dict] = None
    token_params: Optional[dict] = None
    token_response: Optional[dict] = None
    token_expires_in_ms: Optional[int] = None
    authorization_url: Optional[str] = None
    authorization_params: Optional[dict] = None
    body_format: Optional[str] = None
    token_request_auth_method: Optional[str] = None
    scope_separator: Optional[str] = None


class Providers:
    def __init__(self, providers_file: Optional[Path] = None):
        self.providers: dict[str, Provider] = {}
        if providers_file is None:
            providers_file = Path(__file__).parent.parent.parent / 'packages' / 'providers' / 'providers.yaml'
        self.load(providers_file)

    def load(self, path: Path) -> None:
        if not path.exists():
            return

        with open(path, 'r') as f:
            data = yaml.safe_load(f)

        for name, config in data.items():
            try:
                self.providers[name] = Provider(**config)
            except Exception as e:
                print(f'Failed to parse provider {name}: {e}')

    def get(self, name: str) -> Optional[Provider]:
        return self.providers.get(name)

    def list_all(self) -> dict[str, Provider]:
        return self.providers

    def list_by_category(self, category: str) -> dict[str, Provider]:
        return {
            name: p for name, p in self.providers.items()
            if category in p.categories
        }

    def list_categories(self) -> set[str]:
        categories = set()
        for p in self.providers.values():
            categories.update(p.categories)
        return categories


_providers: Optional[Providers] = None


def get_providers() -> Providers:
    global _providers
    if _providers is None:
        _providers = Providers()
    return _providers