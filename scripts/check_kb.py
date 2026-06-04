"""Check knowledge base documents in the database."""

import asyncio

from sqlalchemy import select

from autonomous_agent_builder.db.models import DesignDocument
from autonomous_agent_builder.db.session import get_db_session


async def main():
    async with get_db_session() as db:
        result = await db.execute(select(DesignDocument))
        docs = result.scalars().all()
        print(f"Knowledge Base Documents: {len(docs)}")
        for doc in docs:
            print(f"  - {doc.doc_type}: {doc.title} (v{doc.version})")


if __name__ == "__main__":
    asyncio.run(main())
