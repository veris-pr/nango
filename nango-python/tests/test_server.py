import pytest
import httpx
from sqlalchemy.orm import Session
from nango.server.database import get_db
from nango.server.models import Config, Connection, Environment
from nango.server.main import app


def test_health_check():
    with httpx.Client(app=app, base_url='http://test') as client:
        response = client.get('/health')
        assert response.status_code == 200
        assert response.json() == {'status': 'ok'}


def test_ready():
    with httpx.Client(app=app, base_url='http://test') as client:
        response = client.get('/ready')
        assert response.status_code == 200
        assert response.json() == {'status': 'ready'}


def test_oauth_authorize(db: Session):
    # Create test environment
    env = Environment(name='test', account_id=1)
    db.add(env)
    db.commit()
    
    # Create test config
    config = Config(
        provider='github',
        provider_config_key='github-test',
        environment_id=env.id,
        account_id=1,
        oauth_client_id='test-client-id',
    )
    db.add(config)
    db.commit()
    
    with httpx.Client(app=app, base_url='http://test') as client:
        response = client.get(
            f'/oauth/authorize/github-test?connection_id=test-conn&environment_id={env.id}'
        )
        assert response.status_code == 200
        data = response.json()
        assert 'authorization_url' in data
        assert 'state' in data


def test_oauth_callback(db: Session):
    # Create test environment
    env = Environment(name='test', account_id=1)
    db.add(env)
    db.commit()
    
    # Create test config
    config = Config(
        provider='github',
        provider_config_key='github-test',
        environment_id=env.id,
        account_id=1,
        oauth_client_id='test-client-id',
    )
    db.add(config)
    db.commit()
    
    # Create test OAuth session
    from nango.server.services.oauth import OAuthSession
    oauth_session = OAuthSession(
        connection_id='test-conn',
        environment_id=env.id,
        provider_config_key='github-test',
        state='test-state',
        redirect_uri='http://localhost:3003/oauth/callback',
    )
    db.add(oauth_session)
    db.commit()
    
    # Mock token response
    import json
    from unittest.mock import patch
    
    with patch('nango.server.services.oauth.httpx.AsyncClient.post') as mock_post:
        mock_post.return_value.json.return_value = {
            'access_token': 'test-token',
            'token_type': 'Bearer',
            'expires_in': 3600,
        }
        
        with httpx.Client(app=app, base_url='http://test') as client:
            response = client.get(
                '/oauth/callback?code=test-code&state=test-state'
            )
            assert response.status_code == 200
            data = response.json()
            assert data['status'] == 'success'
            assert data['connection_id'] == 'test-conn'


def test_api_proxy(db: Session):
    # Create test environment
    env = Environment(name='test', account_id=1)
    db.add(env)
    db.commit()
    
    # Create test config
    config = Config(
        provider='github',
        provider_config_key='github-test',
        environment_id=env.id,
        account_id=1,
        oauth_client_id='test-client-id',
    )
    db.add(config)
    db.commit()
    
    # Create test connection
    conn = Connection(
        connection_id='test-conn',
        environment_id=env.id,
        config_id=config.id,
        account_id=1,
        provider='github',
        provider_config_key='github-test',
        access_token='test-token',
        token_type='Bearer',
    )
    db.add(conn)
    db.commit()
    
    # Mock HTTP request
    import json
    from unittest.mock import patch
    
    with patch('nango.server.services.proxy.httpx.AsyncClient.request') as mock_request:
        mock_request.return_value.json.return_value = {'login': 'test-user'}
        mock_request.return_value.status_code = 200
        
        with httpx.Client(app=app, base_url='http://test') as client:
            response = client.get(
                f'/api/v1/proxy/github/user?connection_id=test-conn&environment_id={env.id}'
            )
            assert response.status_code == 200
            data = response.json()
            assert 'login' in data