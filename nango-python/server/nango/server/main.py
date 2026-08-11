from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from nango.server.config import get_settings
from nango.server.database import init_db, create_tables
from nango.server.providers import get_providers

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db(settings.database_url)
    create_tables()
    app.state.providers = get_providers()
    app.state.templates = Jinja2Templates(directory='nango/server/templates')
    yield


app = FastAPI(
    title='Nango',
    description='Open-source integration platform',
    version='0.1.0',
    lifespan=lifespan,
)

app.mount('/static', StaticFiles(directory='nango/server/static'), name='static')


@app.get('/health')
async def health_check():
    return {'status': 'ok'}


@app.get('/ready')
async def ready():
    return {'status': 'ready'}


from nango.server.api.v1 import router as v1_router
from nango.server.api.v1 import oauth, proxy
from nango.server.api import admin

app.include_router(v1_router, prefix='/api/v1')
app.include_router(oauth.router, prefix='/oauth')
app.include_router(proxy.router, prefix='/api/v1')
app.include_router(admin.router)

from nango.server.transport.handlers import connection, config, oauth as transport_oauth

app.add_api_route(
    '/api/v1/connections',
    connection.list_connections,
    methods=['GET'],
    name='list_connections'
)
app.add_api_route(
    '/api/v1/connections/{connection_id}',
    connection.get_connection,
    methods=['GET'],
    name='get_connection'
)
app.add_api_route(
    '/api/v1/connections/{connection_id}',
    connection.delete_connection,
    methods=['DELETE'],
    name='delete_connection'
)
app.add_api_route(
    '/api/v1/configs',
    config.list_configs,
    methods=['GET'],
    name='list_configs'
)
app.add_api_route(
    '/api/v1/configs/{provider_config_key}',
    config.get_config,
    methods=['GET'],
    name='get_config'
)
app.add_api_route(
    '/api/v1/configs',
    config.create_config,
    methods=['POST'],
    name='create_config'
)
app.add_api_route(
    '/api/v1/configs/{provider_config_key}',
    config.delete_config,
    methods=['DELETE'],
    name='delete_config'
)
app.add_api_route(
    '/oauth/authorize/{provider_config_key}',
    transport_oauth.authorize,
    methods=['GET'],
    name='oauth_authorize'
)
app.add_api_route(
    '/oauth/callback',
    transport_oauth.oauth_callback,
    methods=['GET'],
    name='oauth_callback'
)


def main():
    import uvicorn
    uvicorn.run(
        'nango.server.main:app',
        host=settings.server_host,
        port=settings.server_port,
        reload=True,
    )


if __name__ == '__main__':
    main()