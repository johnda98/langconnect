"""
Maintenance script for cleaning up orphaned data in Postgres.

Current behavior:
- Delete embeddings whose collection_id no longer exists in langchain_pg_collection.

Usage:
    python -m langconnect.maintenance.cleanup
    python -m langconnect.maintenance.cleanup --dry-run
"""

from __future__ import annotations

import argparse
import asyncio
import logging

from langconnect.database.connection import (
    close_db_pool,
    get_db_connection,
)

logger = logging.getLogger(__name__)


async def _count_orphan_embeddings(conn) -> int:
    """Return how many embeddings reference a missing collection."""
    return await conn.fetchval(
        """
        SELECT count(*)
          FROM langchain_pg_embedding e
         WHERE NOT EXISTS (
               SELECT 1
                 FROM langchain_pg_collection c
                WHERE c.uuid = e.collection_id
         );
        """
    )


async def remove_orphan_embeddings(dry_run: bool = False) -> int:
    """
    Delete embeddings whose collection_id no longer exists.

    Args:
        dry_run: If True, only count rows; do not delete.

    Returns:
        Number of embeddings that would be / were deleted.
    """
    async with get_db_connection() as conn:
        orphan_count = await _count_orphan_embeddings(conn)
        if dry_run or orphan_count == 0:
            return orphan_count

        result = await conn.execute(
            """
            DELETE FROM langchain_pg_embedding e
             WHERE NOT EXISTS (
                   SELECT 1
                     FROM langchain_pg_collection c
                    WHERE c.uuid = e.collection_id
             );
            """
        )
        # asyncpg returns strings like "DELETE 42"
        deleted = int(result.split()[-1])
        return deleted


async def main(args: argparse.Namespace) -> None:
    deleted = await remove_orphan_embeddings(dry_run=args.dry_run)
    if args.dry_run:
        logger.info("Dry run: %s orphan embeddings would be deleted.", deleted)
    else:
        logger.info("Deleted %s orphan embeddings.", deleted)
    await close_db_pool()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Cleanup orphaned embeddings whose collections were deleted."
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Only report how many rows would be deleted; do not delete.",
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
        help="Set log level (default: INFO).",
    )
    return parser.parse_args()


if __name__ == "__main__":
    cli_args = parse_args()
    logging.basicConfig(
        level=getattr(logging, cli_args.log_level),
        format="%(asctime)s %(levelname)s %(message)s",
    )
    asyncio.run(main(cli_args))
