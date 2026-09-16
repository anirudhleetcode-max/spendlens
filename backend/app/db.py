from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase, AsyncIOMotorGridFSBucket

from .config import get_settings

_client: AsyncIOMotorClient | None = None


def get_client() -> AsyncIOMotorClient:
    global _client
    if _client is None:
        _client = AsyncIOMotorClient(get_settings().mongo_uri, serverSelectionTimeoutMS=4000, tz_aware=True)
    return _client


def get_db() -> AsyncIOMotorDatabase:
    return get_client()[get_settings().mongo_db]


def get_bucket() -> AsyncIOMotorGridFSBucket:
    """GridFS bucket holding the (resized) receipt images."""
    return AsyncIOMotorGridFSBucket(get_db(), bucket_name="receipts")


async def close_client() -> None:
    global _client
    if _client is not None:
        _client.close()
        _client = None


async def ensure_indexes() -> None:
    db = get_db()
    await db.users.create_index("email", unique=True)
    # ledger listing / month filters / aggregations all start with user_id + date
    await db.expenses.create_index([("user_id", 1), ("date", -1)])
    await db.expenses.create_index([("user_id", 1), ("category", 1), ("date", -1)])
    await db.expenses.create_index([("user_id", 1), ("merchant_key", 1)])
    await db.budgets.create_index([("user_id", 1), ("category", 1)], unique=True)
    await db.merchant_overrides.create_index([("user_id", 1), ("merchant_key", 1)], unique=True)
    await db.category_feedback.create_index([("created_at", -1)])
    await db["receipts.files"].create_index([("metadata.user_id", 1)])
