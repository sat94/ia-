"""Service de gestion des sessions avec embeddings vectoriels (pgvector) - ASYNC avec asyncpg"""
import logging
import uuid
import numpy as np
from typing import Optional, List, Dict, Tuple
from datetime import datetime
import asyncpg
from config import DB_NAME, DB_USER, DB_PASSWORD, DB_HOST, DB_PORT, SESSION_CATEGORIES

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class SessionServiceVectoriel:

    def __init__(self, embedding_model=None):
        self.dsn = f"postgresql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"
        self.pool: Optional[asyncpg.Pool] = None
        self.embedding_model = embedding_model

    async def _ensure_pool(self):
        if self.pool is None or self.pool._closed:
            self.pool = await asyncpg.create_pool(
                self.dsn, min_size=2, max_size=10, command_timeout=10
            )
            logger.info("asyncpg pool created for SessionService")

    def set_embedding_model(self, model):
        self.embedding_model = model

    def _generate_embedding(self, text: str) -> Optional[np.ndarray]:
        if not self.embedding_model:
            return None
        try:
            return self.embedding_model.encode(text, convert_to_numpy=True)
        except Exception as e:
            logger.error(f"Embedding error: {e}")
            return None

    async def get_or_create_session(
        self, user_id: str, expert_id: str, category: str
    ) -> str:
        await self._ensure_pool()
        try:
            row = await self.pool.fetchrow(
                """
                SELECT session_id FROM coaching_sessions
                WHERE user_id = $1 AND expert_id = $2 AND is_active = TRUE
                ORDER BY updated_at DESC LIMIT 1
                """,
                user_id, expert_id
            )
            if row:
                return row["session_id"]

            session_id = self._generate_session_id()
            await self.pool.execute(
                """
                INSERT INTO coaching_sessions (session_id, user_id, expert_id, category)
                VALUES ($1, $2, $3, $4)
                """,
                session_id, user_id, expert_id, category
            )
            return session_id
        except Exception as e:
            logger.error(f"get_or_create_session error: {e}")
            return self._generate_session_id()

    def _generate_session_id(self) -> str:
        return f"session_{uuid.uuid4().hex[:16]}"

    async def get_session_history(self, session_id: str, limit: int = 10) -> List[Dict]:
        await self._ensure_pool()
        try:
            rows = await self.pool.fetch(
                """
                SELECT user_message as user, assistant_response as assistant,
                       topics_extracted, created_at
                FROM session_exchanges
                WHERE session_id = $1
                ORDER BY created_at DESC
                LIMIT $2
                """,
                session_id, limit
            )
            return list(reversed([dict(r) for r in rows]))
        except Exception as e:
            logger.error(f"get_session_history error: {e}")
            return []

    async def search_similar_messages(
        self, session_id: str, query: str, limit: int = 5, similarity_threshold: float = 0.75
    ) -> List[Dict]:
        await self._ensure_pool()
        if not self.embedding_model:
            return []

        try:
            query_embedding = self._generate_embedding(query)
            if query_embedding is None:
                return []

            vec_str = "[" + ",".join(map(str, query_embedding.tolist())) + "]"
            rows = await self.pool.fetch(
                """
                SELECT * FROM search_similar_messages($1, $2::vector, $3)
                WHERE similarity >= $4
                """,
                session_id, vec_str, limit, similarity_threshold
            )
            return [dict(r) for r in rows]
        except Exception as e:
            logger.error(f"search_similar_messages error: {e}")
            return []

    async def add_exchange(
        self, session_id: str, user_message: str, assistant_response: str,
        expert_id: str, tokens_used: int = 0, topics: Optional[List[str]] = None
    ):
        await self._ensure_pool()
        try:
            embedding = self._generate_embedding(user_message)

            if embedding is not None:
                vec_str = "[" + ",".join(map(str, embedding.tolist())) + "]"
                await self.pool.execute(
                    """
                    INSERT INTO session_exchanges
                    (session_id, user_message, assistant_response, user_embedding, topics_extracted, tokens_used)
                    VALUES ($1, $2, $3, $4::vector, $5, $6)
                    """,
                    session_id, user_message, assistant_response, vec_str, topics, tokens_used
                )
            else:
                await self.pool.execute(
                    """
                    INSERT INTO session_exchanges
                    (session_id, user_message, assistant_response, topics_extracted, tokens_used)
                    VALUES ($1, $2, $3, $4, $5)
                    """,
                    session_id, user_message, assistant_response, topics, tokens_used
                )
        except Exception as e:
            logger.error(f"add_exchange error: {e}")

    async def get_contextual_history(
        self, session_id: str, current_query: str, max_results: int = 10
    ) -> Tuple[List[Dict], List[Dict]]:
        recent = await self.get_session_history(session_id, limit=max_results)
        similar = await self.search_similar_messages(session_id, current_query, limit=max_results)
        return recent, similar

    async def get_user_sessions(
        self, user_id: int, expert_id: Optional[str] = None, active_only: bool = True
    ) -> List[Dict]:
        await self._ensure_pool()
        try:
            query = "SELECT * FROM active_sessions_stats WHERE user_id = $1"
            params = [user_id]

            if expert_id:
                query += " AND expert_id = $2"
                params.append(expert_id)

            rows = await self.pool.fetch(query, *params)
            return [dict(r) for r in rows]
        except Exception as e:
            logger.error(f"get_user_sessions error: {e}")
            return []

    async def close_session(self, session_id: str, summary: Optional[str] = None):
        await self._ensure_pool()
        try:
            await self.pool.execute(
                """
                UPDATE coaching_sessions
                SET is_active = FALSE, summary = $1
                WHERE session_id = $2
                """,
                summary, session_id
            )
        except Exception as e:
            logger.error(f"close_session error: {e}")

    async def get_session_exchanges(
        self, session_id: str, limit: int = 50, offset: int = 0
    ) -> List[Dict]:
        await self._ensure_pool()
        try:
            rows = await self.pool.fetch(
                """
                SELECT id, user_message, assistant_response,
                       topics_extracted, sentiment, created_at
                FROM session_exchanges
                WHERE session_id = $1
                ORDER BY created_at ASC
                LIMIT $2 OFFSET $3
                """,
                session_id, limit, offset
            )
            return [dict(r) for r in rows]
        except Exception as e:
            logger.error(f"get_session_exchanges error: {e}")
            return []

    async def get_user_history_by_expert(
        self, user_id: str, expert_id: str, limit: int = 20
    ) -> List[Dict]:
        await self._ensure_pool()
        try:
            rows = await self.pool.fetch(
                """
                SELECT cs.session_id, cs.category, cs.created_at,
                       cs.updated_at, cs.last_message_at, cs.is_active,
                       cs.message_count, cs.summary, cs.topics
                FROM coaching_sessions cs
                WHERE cs.user_id = $1 AND cs.expert_id = $2
                ORDER BY cs.last_message_at DESC
                LIMIT $3
                """,
                user_id, expert_id, limit
            )
            return [dict(r) for r in rows]
        except Exception as e:
            logger.error(f"get_user_history_by_expert error: {e}")
            return []

    def requires_session(self, category: str) -> bool:
        return category in SESSION_CATEGORIES

    async def close(self):
        if self.pool:
            await self.pool.close()


_session_instance = None


def get_session_service(embedding_model=None):
    global _session_instance
    if _session_instance is None:
        _session_instance = SessionServiceVectoriel(embedding_model)
    elif embedding_model and not _session_instance.embedding_model:
        _session_instance.set_embedding_model(embedding_model)
    return _session_instance
