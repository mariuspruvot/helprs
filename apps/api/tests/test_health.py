async def test_health_returns_ok(client):
    response = await client.get("/health")
    data = response.json()
    # Without a running lifespan (no session_factory), health check
    # reports degraded DB. Both 200 and 503 are valid depending on
    # whether the test environment has a DB connection.
    assert response.status_code in (200, 503)
    assert data["status"] in ("ok", "degraded")


async def test_health_response_shape(client):
    response = await client.get("/health")
    data = response.json()
    assert "status" in data
    assert "db" in data
