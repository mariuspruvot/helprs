"""Re-encrypt every stored credential under the primary Fernet key.

The step that makes key rotation finish. ``FERNET_KEY_FALLBACKS`` keeps old
ciphertext readable, but a retired key can only actually be dropped once
nothing is still encrypted with it -- otherwise the fallback list grows
forever and the "retired" key stays as sensitive as the live one.

    # 1. generate a key and put it in front
    FERNET_KEY=<new>  FERNET_KEY_FALLBACKS='["<old>"]'
    # 2. deploy; new writes use <new>, old values still decrypt
    # 3. rewrite the old values
    uv run python -m helprs.scripts.rotate_credentials
    # 4. drop FERNET_KEY_FALLBACKS and deploy again

Safe to re-run: rotating a value already under the primary key just rewrites
it. Run it against a database you can restore, like any bulk rewrite.
"""

import asyncio
import sys

from cryptography.fernet import InvalidToken
from sqlalchemy.ext.asyncio import AsyncSession

from helprs.core.config import get_settings
from helprs.core.database import create_engine, create_session_factory
from helprs.core.security import fernet_rotate
from helprs.modules.identity import repository as identity_repository
from helprs.modules.installation import repository as installation_repository


class RotationReport:
    """What happened, per credential kind."""

    def __init__(self) -> None:
        self.rotated = 0
        self.failed: list[str] = []

    def record(self, label: str, *, ok: bool) -> None:
        if ok:
            self.rotated += 1
        else:
            self.failed.append(label)


async def _rotate_github_tokens(session: AsyncSession, fernet_keys: list[str], report: RotationReport) -> None:
    for user in await identity_repository.list_all(session):
        try:
            user.github_access_token_enc = fernet_rotate(user.github_access_token_enc, fernet_keys)
        except InvalidToken:
            # No key in the set can read it. Reported rather than raised: one
            # unreadable row must not stop the rest from being rewritten.
            report.record(f"user {user.id} ({user.github_login})", ok=False)
        else:
            report.record(f"user {user.id}", ok=True)


async def _rotate_byok_keys(session: AsyncSession, fernet_keys: list[str], report: RotationReport) -> None:
    for config in await installation_repository.list_all_byok_configs(session):
        try:
            config.encrypted_api_key = fernet_rotate(config.encrypted_api_key, fernet_keys)
        except InvalidToken:
            report.record(f"byok {config.id} (installation {config.installation_id})", ok=False)
        else:
            report.record(f"byok {config.id}", ok=True)


async def rotate_all() -> RotationReport:
    """Rewrite every stored credential with the primary key."""
    settings = get_settings()
    report = RotationReport()

    engine = create_engine()
    try:
        session_factory = create_session_factory(engine)
        async with session_factory() as session:
            await _rotate_github_tokens(session, settings.fernet_keys, report)
            await _rotate_byok_keys(session, settings.fernet_keys, report)
            # One transaction: a partial rewrite would leave the operator
            # unable to tell which key each row is under.
            await session.commit()
    finally:
        await engine.dispose()

    return report


def main() -> int:
    report = asyncio.run(rotate_all())
    print(f"re-encrypted {report.rotated} credential(s) with the primary key")

    if report.failed:
        print(f"\n{len(report.failed)} could not be read by any configured key:", file=sys.stderr)
        for label in report.failed:
            print(f"  - {label}", file=sys.stderr)
        print(
            "\nThe key they were written with is missing from FERNET_KEY_FALLBACKS. "
            "Add it and re-run, or those credentials have to be re-entered.",
            file=sys.stderr,
        )
        return 1

    print("FERNET_KEY_FALLBACKS can now be emptied.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
