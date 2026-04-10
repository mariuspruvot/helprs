import os

# Set test environment variables BEFORE any app imports
os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://helprs:helprs@localhost:5432/helprs_test")
os.environ.setdefault("SECRET_KEY", "test-secret-key-for-testing")
os.environ.setdefault("GITHUB_APP_ID", "000000")
os.environ.setdefault("ENVIRONMENT", "test")
os.environ.setdefault("GITHUB_WEBHOOK_SECRET", "test-webhook-secret")
os.environ.setdefault("APP_BASE_URL", "http://test.local")

# Generate a valid Fernet key for tests
from cryptography.fernet import Fernet

os.environ.setdefault("FERNET_KEY", Fernet.generate_key().decode())

import pytest
from httpx import ASGITransport, AsyncClient

from helprs.main import create_app


@pytest.fixture
async def client():
    app = create_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac
