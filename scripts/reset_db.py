import asyncio
from database import engine, Base
import models

async def reset():
    print("Connecting to DB to reset schemas...")
    async with engine.begin() as conn:
        print("Dropping all tables...")
        await conn.run_sync(Base.metadata.drop_all)
        print("Recreating all tables from freshly updated SQLAlchemy models...")
        await conn.run_sync(Base.metadata.create_all)
    print("Database reset successfully complete!")
    await engine.dispose()

if __name__ == "__main__":
    asyncio.run(reset())
