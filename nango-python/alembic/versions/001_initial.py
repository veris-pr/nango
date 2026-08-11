"""Initial migration - create all tables

Revision ID: 001
Revises:
Create Date: 2024-01-01 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '001'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Accounts table
    op.create_table(
        'accounts',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('owner', sa.String(length=255), nullable=True),
        sa.Column('secret_hash', sa.String(length=255), nullable=True),
        sa.Column('uuid', sa.String(length=36), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('idx_accounts_uuid', 'accounts', ['uuid'], unique=True)

    # Environments table
    op.create_table(
        'environments',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('account_id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('secret_key', sa.String(length=255), nullable=True),
        sa.Column('public_key', sa.String(length=255), nullable=True),
        sa.Column('secret_key_iv', sa.String(length=255), nullable=True),
        sa.Column('secret_key_tag', sa.String(length=255), nullable=True),
        sa.Column('callback_url', sa.String(length=512), nullable=True),
        sa.Column('webhooks', sa.Text(), nullable=True),
        sa.Column('host', sa.String(length=255), nullable=True),
        sa.Column('port', sa.Integer(), nullable=True),
        sa.Column('ssl', sa.Boolean(), nullable=True),
        sa.Column('ssl_cert', sa.Text(), nullable=True),
        sa.Column('ssl_key', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['account_id'], ['accounts.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('idx_environment_account_id', 'environments', ['account_id'])

    # Users table
    op.create_table(
        'users',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('account_id', sa.Integer(), nullable=False),
        sa.Column('email', sa.String(length=255), nullable=False),
        sa.Column('name', sa.String(length=255), nullable=True),
        sa.Column('password_hash', sa.String(length=255), nullable=True),
        sa.Column('reset_token', sa.String(length=255), nullable=True),
        sa.Column('reset_token_expires_at', sa.DateTime(), nullable=True),
        sa.Column('email_verified', sa.Boolean(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['account_id'], ['accounts.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('idx_user_account_id', 'users', ['account_id'])
    op.create_index('idx_users_email', 'users', ['email'], unique=True)

    # Configs table
    op.create_table(
        'configs',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('account_id', sa.Integer(), nullable=False),
        sa.Column('unique_key', sa.String(length=255), nullable=False),
        sa.Column('provider', sa.String(length=255), nullable=False),
        sa.Column('provider_config_key', sa.String(length=255), nullable=False),
        sa.Column('environment_id', sa.Integer(), nullable=False),
        sa.Column('oauth_client_id', sa.String(length=255), nullable=True),
        sa.Column('oauth_client_secret', sa.Text(), nullable=True),
        sa.Column('oauth_client_secret_iv', sa.String(length=255), nullable=True),
        sa.Column('oauth_client_secret_tag', sa.String(length=255), nullable=True),
        sa.Column('scopes', sa.String(length=1000), nullable=True),
        sa.Column('custom', sa.Text(), nullable=True),
        sa.Column('connection_config', sa.Text(), nullable=True),
        sa.Column('secret', sa.Text(), nullable=True),
        sa.Column('secret_iv', sa.String(length=255), nullable=True),
        sa.Column('secret_tag', sa.String(length=255), nullable=True),
        sa.Column('metadata', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['account_id'], ['accounts.id'], ),
        sa.ForeignKeyConstraint(['environment_id'], ['environments.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('idx_config_account_id', 'configs', ['account_id'])
    op.create_index('idx_config_environment_id', 'configs', ['environment_id'])
    op.create_index('idx_config_unique_key', 'configs', ['unique_key'])

    # Connections table
    op.create_table(
        'connections',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('connection_id', sa.String(length=255), nullable=False),
        sa.Column('environment_id', sa.Integer(), nullable=False),
        sa.Column('config_id', sa.Integer(), nullable=False),
        sa.Column('account_id', sa.Integer(), nullable=False),
        sa.Column('provider', sa.String(length=255), nullable=True),
        sa.Column('provider_config_key', sa.String(length=255), nullable=True),
        sa.Column('access_token', sa.Text(), nullable=True),
        sa.Column('access_token_iv', sa.String(length=255), nullable=True),
        sa.Column('access_token_tag', sa.String(length=255), nullable=True),
        sa.Column('refresh_token', sa.Text(), nullable=True),
        sa.Column('refresh_token_iv', sa.String(length=255), nullable=True),
        sa.Column('refresh_token_tag', sa.String(length=255), nullable=True),
        sa.Column('expires_at', sa.DateTime(), nullable=True),
        sa.Column('token_type', sa.String(length=50), nullable=True),
        sa.Column('id_token', sa.Text(), nullable=True),
        sa.Column('api_key', sa.Text(), nullable=True),
        sa.Column('api_key_iv', sa.String(length=255), nullable=True),
        sa.Column('api_key_tag', sa.String(length=255), nullable=True),
        sa.Column('basic_username', sa.String(length=255), nullable=True),
        sa.Column('basic_password', sa.Text(), nullable=True),
        sa.Column('basic_password_iv', sa.String(length=255), nullable=True),
        sa.Column('basic_password_tag', sa.String(length=255), nullable=True),
        sa.Column('private_key', sa.Text(), nullable=True),
        sa.Column('private_key_iv', sa.String(length=255), nullable=True),
        sa.Column('private_key_tag', sa.String(length=255), nullable=True),
        sa.Column('connection_config', sa.Text(), nullable=True),
        sa.Column('metadata', sa.Text(), nullable=True),
        sa.Column('errors', sa.Text(), nullable=True),
        sa.Column('last_refreshed_at', sa.DateTime(), nullable=True),
        sa.Column('failed_stored_refresh', sa.Boolean(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['account_id'], ['accounts.id'], ),
        sa.ForeignKeyConstraint(['config_id'], ['configs.id'], ),
        sa.ForeignKeyConstraint(['environment_id'], ['environments.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('idx_connection_environment_id', 'connections', ['environment_id'])
    op.create_index('idx_connection_config_id', 'connections', ['config_id'])
    op.create_index('idx_connection_account_id', 'connections', ['account_id'])
    op.create_index('idx_connection_connection_id', 'connections', ['connection_id'])

    # Flows table
    op.create_table(
        'flows',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('flow_type', sa.String(length=50), nullable=False),
        sa.Column('environment_id', sa.Integer(), nullable=False),
        sa.Column('account_id', sa.Integer(), nullable=False),
        sa.Column('provider_config_key', sa.String(length=255), nullable=False),
        sa.Column('status', sa.String(length=50), nullable=True),
        sa.Column('runs', sa.String(length=50), nullable=True),
        sa.Column('auto_start', sa.Boolean(), nullable=True),
        sa.Column('track_cursors', sa.Boolean(), nullable=True),
        sa.Column('enabled', sa.Boolean(), nullable=True),
        sa.Column('input_schema', postgresql.JSON(astext_type=sa.Text()), nullable=True),
        sa.Column('output_schema', postgresql.JSON(astext_type=sa.Text()), nullable=True),
        sa.Column('version', sa.String(length=50), nullable=True),
        sa.Column('metadata', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['account_id'], ['accounts.id'], ),
        sa.ForeignKeyConstraint(['environment_id'], ['environments.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('idx_flow_environment_id', 'flows', ['environment_id'])

    # OAuth sessions table
    op.create_table(
        'oauth_sessions',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('connection_id', sa.String(length=255), nullable=False),
        sa.Column('environment_id', sa.Integer(), nullable=False),
        sa.Column('provider_config_key', sa.String(length=255), nullable=False),
        sa.Column('oauth_token', sa.String(length=255), nullable=True),
        sa.Column('oauth_token_secret', sa.String(length=255), nullable=True),
        sa.Column('oauth_verifier', sa.String(length=255), nullable=True),
        sa.Column('state', sa.String(length=255), nullable=True),
        sa.Column('code_verifier', sa.Text(), nullable=True),
        sa.Column('redirect_uri', sa.String(length=512), nullable=True),
        sa.Column('scope', sa.String(length=1000), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('expires_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('idx_oauth_sessions_state', 'oauth_sessions', ['state'])
    op.create_index('idx_oauth_sessions_connection_id', 'oauth_sessions', ['connection_id'])


def downgrade() -> None:
    op.drop_index('idx_oauth_sessions_connection_id', table_name='oauth_sessions')
    op.drop_index('idx_oauth_sessions_state', table_name='oauth_sessions')
    op.drop_table('oauth_sessions')
    op.drop_index('idx_flow_environment_id', table_name='flows')
    op.drop_table('flows')
    op.drop_index('idx_connection_connection_id', table_name='connections')
    op.drop_index('idx_connection_account_id', table_name='connections')
    op.drop_index('idx_connection_config_id', table_name='connections')
    op.drop_index('idx_connection_environment_id', table_name='connections')
    op.drop_table('connections')
    op.drop_index('idx_config_unique_key', table_name='configs')
    op.drop_index('idx_config_environment_id', table_name='configs')
    op.drop_index('idx_config_account_id', table_name='configs')
    op.drop_table('configs')
    op.drop_index('idx_users_email', table_name='users')
    op.drop_index('idx_user_account_id', table_name='users')
    op.drop_table('users')
    op.drop_index('idx_environment_account_id', table_name='environments')
    op.drop_table('environments')
    op.drop_index('idx_accounts_uuid', table_name='accounts')
    op.drop_table('accounts')