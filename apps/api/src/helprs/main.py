from fastapi import FastAPI


def create_app() -> FastAPI:
    app = FastAPI(
        title="helPRs API",
        description="Socratic comprehension sessions for pull requests",
        version="0.1.0",
    )

    @app.get("/health")
    async def health_check():
        return {"status": "ok"}

    return app


app = create_app()
