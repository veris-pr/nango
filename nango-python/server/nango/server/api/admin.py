from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from nango.server.database import get_db
from nango.server.models import Connection, Config, Environment, Account
from nango.server.providers import get_providers

router = APIRouter()


def get_default_account(db: Session) -> Account:
    """Get or create the default account."""
    account = db.query(Account).first()
    if not account:
        account = Account(
            name='Default Account',
            uuid='default-0000-0000-0000-000000000001'
        )
        db.add(account)
        db.commit()
        db.refresh(account)

        environment = Environment(
            account_id=account.id,
            name='Development',
        )
        db.add(environment)
        db.commit()
    return account


@router.get('/', response_class=HTMLResponse)
async def dashboard(request: Request, db: Session = Depends(get_db)):
    integrations_count = db.query(Config).count()
    connections_count = db.query(Connection).count()
    providers = get_providers()
    providers_count = len(providers.list_all())

    recent = db.query(Connection).order_by(Connection.created_at.desc()).limit(5).all()
    recent_connections = [
        {
            'connection_id': c.connection_id,
            'provider': c.provider or 'unknown',
            'created_at': c.created_at.strftime('%Y-%m-%d') if c.created_at else 'N/A',
        }
        for c in recent
    ]

    return request.app.state.templates.TemplateResponse(
        'dashboard.html',
        {
            'request': request,
            'integrations_count': integrations_count,
            'connections_count': connections_count,
            'providers_count': providers_count,
            'jobs_count': 0,
            'recent_connections': recent_connections,
        }
    )


@router.get('/integrations', response_class=HTMLResponse)
async def integrations(request: Request, db: Session = Depends(get_db)):
    configs = db.query(Config).all()
    integrations = [
        {
            'id': c.id,
            'provider': c.provider,
            'provider_config_key': c.provider_config_key,
            'oauth_client_id': c.oauth_client_id,
            'created_at': c.created_at.strftime('%Y-%m-%d') if c.created_at else 'N/A',
        }
        for c in configs
    ]

    providers = get_providers()
    available_providers = sorted(providers.list_all().keys())

    return request.app.state.templates.TemplateResponse(
        'integrations.html',
        {'request': request, 'integrations': integrations, 'available_providers': available_providers, 'environment_id': 1}
    )


@router.post('/integrations/create')
async def create_integration(
    request: Request,
    provider: str,
    provider_config_key: str,
    oauth_client_id: str = '',
    oauth_client_secret: str = '',
    scopes: str = '',
    environment_id: int = 1,
    db: Session = Depends(get_db)
):
    from fastapi import HTTPException

    existing = db.query(Config).filter(
        Config.provider_config_key == provider_config_key,
        Config.environment_id == environment_id
    ).first()

    if existing:
        return request.app.state.templates.TemplateResponse(
            'integrations.html',
            {
                'request': request,
                'integrations': [],
                'available_providers': sorted(get_providers().list_all().keys()),
                'environment_id': environment_id,
                'error': f'Integration {provider_config_key} already exists',
            }
        )

    account = get_default_account(db)
    config = Config(
        provider=provider,
        provider_config_key=provider_config_key,
        environment_id=environment_id,
        account_id=account.id,
        unique_key=provider_config_key,
        oauth_client_id=oauth_client_id or None,
        oauth_client_secret=oauth_client_secret or None,
        scopes=scopes or None,
    )
    db.add(config)
    db.commit()

    configs = db.query(Config).all()
    return request.app.state.templates.TemplateResponse(
        'integrations.html',
        {
            'request': request,
            'integrations': [
                {
                    'id': c.id,
                    'provider': c.provider,
                    'provider_config_key': c.provider_config_key,
                    'oauth_client_id': c.oauth_client_id,
                    'created_at': c.created_at.strftime('%Y-%m-%d') if c.created_at else 'N/A',
                }
                for c in configs
            ],
            'available_providers': sorted(get_providers().list_all().keys()),
            'environment_id': environment_id,
            'success': f'Integration {provider_config_key} created successfully',
        }
    )


@router.post('/integrations/delete')
async def delete_integration(
    request: Request,
    provider_config_key: str,
    environment_id: int = 1,
    db: Session = Depends(get_db)
):
    config = db.query(Config).filter(
        Config.provider_config_key == provider_config_key,
        Config.environment_id == environment_id
    ).first()

    if config:
        db.delete(config)
        db.commit()

    configs = db.query(Config).all()
    return request.app.state.templates.TemplateResponse(
        'integrations.html',
        {
            'request': request,
            'integrations': [
                {
                    'id': c.id,
                    'provider': c.provider,
                    'provider_config_key': c.provider_config_key,
                    'oauth_client_id': c.oauth_client_id,
                    'created_at': c.created_at.strftime('%Y-%m-%d') if c.created_at else 'N/A',
                }
                for c in configs
            ],
            'available_providers': sorted(get_providers().list_all().keys()),
            'environment_id': environment_id,
            'success': f'Integration {provider_config_key} deleted',
        }
    )


@router.get('/connections', response_class=HTMLResponse)
async def connections(request: Request, db: Session = Depends(get_db)):
    conns = db.query(Connection).all()
    connections = [
        {
            'id': c.id,
            'connection_id': c.connection_id,
            'provider': c.provider or 'unknown',
            'provider_config_key': c.provider_config_key,
            'created_at': c.created_at.strftime('%Y-%m-%d') if c.created_at else 'N/A',
        }
        for c in conns
    ]
    return request.app.state.templates.TemplateResponse(
        'connections.html',
        {'request': request, 'connections': connections}
    )


@router.get('/providers', response_class=HTMLResponse)
async def providers_list(request: Request):
    providers = get_providers()
    all_providers = [
        {'name': name, 'display_name': p.display_name, 'categories': p.categories, 'auth_mode': p.auth_mode}
        for name, p in providers.list_all().items()
    ]
    categories = sorted(providers.list_categories())
    return request.app.state.templates.TemplateResponse(
        'providers.html',
        {'request': request, 'providers': all_providers, 'categories': categories}
    )


@router.get('/settings', response_class=HTMLResponse)
async def settings_page(request: Request):
    return request.app.state.templates.TemplateResponse(
        'settings.html',
        {'request': request}
    )