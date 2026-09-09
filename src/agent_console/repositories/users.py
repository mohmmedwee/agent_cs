"""User lookups and creation."""

from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from agent_console.db.models import User

__all__ = ["EmailTakenError", "UserRepository"]


class EmailTakenError(ValueError):
    """That email already has an account."""


def normalise_email(email: str) -> str:
    return email.strip().lower()


class UserRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def by_email(self, email: str) -> User | None:
        result = await self._session.execute(
            select(User).where(User.email == normalise_email(email))
        )
        return result.scalar_one_or_none()

    async def by_id(self, user_id: UUID | str) -> User | None:
        return await self._session.get(User, UUID(str(user_id)))

    async def count(self) -> int:
        result = await self._session.execute(select(func.count()).select_from(User))
        return int(result.scalar_one())

    async def create(
        self, email: str, display_name: str, password_hash: str, is_admin: bool = False
    ) -> User:
        address = normalise_email(email)
        if await self.by_email(address):
            raise EmailTakenError(f"{address} already has an account")

        user = User(
            email=address,
            display_name=display_name.strip() or address.split("@")[0],
            password_hash=password_hash,
            is_admin=is_admin,
        )
        self._session.add(user)
        await self._session.flush()
        return user

    async def list_all(self) -> list[User]:
        result = await self._session.execute(select(User).order_by(User.created_at))
        return list(result.scalars())
