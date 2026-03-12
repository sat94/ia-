"""Service de gestion des abonnements et limites d'utilisation - ASYNC avec asyncpg"""
import logging
from typing import Optional, Dict, Tuple
from datetime import datetime
import asyncpg
from config import DB_NAME, DB_USER, DB_PASSWORD, DB_HOST, DB_PORT, SUBSCRIPTION_TIERS

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class SubscriptionService:

    def __init__(self):
        self.dsn = f"postgresql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"
        self.pool: Optional[asyncpg.Pool] = None

    async def _ensure_pool(self):
        if self.pool is None or self.pool._closed:
            self.pool = await asyncpg.create_pool(
                self.dsn, min_size=2, max_size=10, command_timeout=10
            )
            await self._create_tables()
            logger.info("asyncpg pool created for SubscriptionService")

    async def _create_tables(self):
        try:
            await self.pool.execute("""
                CREATE TABLE IF NOT EXISTS user_subscriptions (
                    id SERIAL PRIMARY KEY,
                    user_id INTEGER UNIQUE NOT NULL,
                    tier VARCHAR(20) NOT NULL DEFAULT 'free',
                    started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    expires_at TIMESTAMP,
                    is_active BOOLEAN DEFAULT TRUE
                );
                CREATE INDEX IF NOT EXISTS idx_subscriptions_user_id ON user_subscriptions(user_id);
            """)
            await self.pool.execute("""
                CREATE TABLE IF NOT EXISTS user_daily_usage (
                    id SERIAL PRIMARY KEY,
                    user_id INTEGER NOT NULL,
                    usage_date DATE NOT NULL DEFAULT CURRENT_DATE,
                    messages_count INTEGER DEFAULT 0,
                    tokens_used INTEGER DEFAULT 0,
                    UNIQUE(user_id, usage_date)
                );
                CREATE INDEX IF NOT EXISTS idx_usage_user_date ON user_daily_usage(user_id, usage_date);
            """)
        except Exception as e:
            logger.error(f"Table creation error: {e}")

    async def get_user_tier(self, user_id: int) -> str:
        await self._ensure_pool()
        try:
            row = await self.pool.fetchrow(
                """
                SELECT tier FROM user_subscriptions
                WHERE user_id = $1 AND is_active = TRUE
                AND (expires_at IS NULL OR expires_at > CURRENT_TIMESTAMP)
                """,
                user_id
            )
            return row["tier"] if row else "free"
        except Exception as e:
            logger.error(f"get_user_tier error: {e}")
            return "free"

    async def get_tier_limits(self, tier: str) -> Dict:
        return SUBSCRIPTION_TIERS.get(tier, SUBSCRIPTION_TIERS["free"])

    async def get_daily_usage(self, user_id: int) -> Dict:
        await self._ensure_pool()
        try:
            row = await self.pool.fetchrow(
                """
                SELECT messages_count, tokens_used FROM user_daily_usage
                WHERE user_id = $1 AND usage_date = CURRENT_DATE
                """,
                user_id
            )
            if row:
                return dict(row)
            return {"messages_count": 0, "tokens_used": 0}
        except Exception as e:
            logger.error(f"get_daily_usage error: {e}")
            return {"messages_count": 0, "tokens_used": 0}

    async def check_can_send_message(self, user_id: int) -> Tuple[bool, str]:
        tier = await self.get_user_tier(user_id)
        limits = await self.get_tier_limits(tier)
        usage = await self.get_daily_usage(user_id)

        max_messages = limits["max_messages"]
        max_tokens = limits["max_tokens_per_day"]

        if max_messages != -1 and usage["messages_count"] >= max_messages:
            tier_name = limits["name"]
            return False, (
                f"Tu as atteint ta limite de {max_messages} messages pour aujourd'hui "
                f"avec l'abonnement {tier_name}. Passe a un abonnement superieur pour continuer !"
            )

        if max_tokens != -1 and usage["tokens_used"] >= max_tokens:
            return False, (
                "Tu as atteint ta limite de tokens pour aujourd'hui. "
                "Reviens demain ou passe a un abonnement superieur !"
            )

        return True, ""

    async def increment_usage(self, user_id: int, tokens_used: int = 0):
        await self._ensure_pool()
        try:
            await self.pool.execute(
                """
                INSERT INTO user_daily_usage (user_id, usage_date, messages_count, tokens_used)
                VALUES ($1, CURRENT_DATE, 1, $2)
                ON CONFLICT (user_id, usage_date)
                DO UPDATE SET
                    messages_count = user_daily_usage.messages_count + 1,
                    tokens_used = user_daily_usage.tokens_used + $3
                """,
                user_id, tokens_used, tokens_used
            )
        except Exception as e:
            logger.error(f"increment_usage error: {e}")

    async def get_usage_summary(self, user_id: int) -> Dict:
        tier = await self.get_user_tier(user_id)
        limits = await self.get_tier_limits(tier)
        usage = await self.get_daily_usage(user_id)

        max_messages = limits["max_messages"]
        max_tokens = limits["max_tokens_per_day"]

        return {
            "tier": tier,
            "tier_name": limits["name"],
            "messages_used": usage["messages_count"],
            "messages_limit": max_messages if max_messages != -1 else "Illimite",
            "messages_remaining": (
                max_messages - usage["messages_count"]
                if max_messages != -1
                else "Illimite"
            ),
            "tokens_used": usage["tokens_used"],
            "tokens_limit": max_tokens if max_tokens != -1 else "Illimite",
            "session_memory_enabled": limits["session_memory"],
        }

    async def set_user_tier(
        self, user_id: int, tier: str, expires_at: Optional[datetime] = None
    ):
        if tier not in SUBSCRIPTION_TIERS:
            logger.error(f"Unknown tier: {tier}")
            return

        await self._ensure_pool()
        try:
            await self.pool.execute(
                """
                INSERT INTO user_subscriptions (user_id, tier, expires_at)
                VALUES ($1, $2, $3)
                ON CONFLICT (user_id)
                DO UPDATE SET
                    tier = $4,
                    expires_at = $5,
                    started_at = CURRENT_TIMESTAMP,
                    is_active = TRUE
                """,
                user_id, tier, expires_at, tier, expires_at
            )
        except Exception as e:
            logger.error(f"set_user_tier error: {e}")

    async def has_session_memory(self, user_id: int) -> bool:
        tier = await self.get_user_tier(user_id)
        limits = await self.get_tier_limits(tier)
        return limits.get("session_memory", False)

    async def close(self):
        if self.pool:
            await self.pool.close()


_subscription_instance = None


def get_subscription_service():
    global _subscription_instance
    if _subscription_instance is None:
        _subscription_instance = SubscriptionService()
    return _subscription_instance
