"""Service de gestion des abonnements et limites d'utilisation"""
import logging
from typing import Optional, Dict, Tuple
from datetime import datetime
import psycopg2
from psycopg2.extras import RealDictCursor
from config import DB_NAME, DB_USER, DB_PASSWORD, DB_HOST, DB_PORT, SUBSCRIPTION_TIERS

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class SubscriptionService:
    """Service pour gérer les abonnements et limites d'utilisation"""

    def __init__(self):
        """Initialise la connexion à PostgreSQL"""
        self.connection_params = {
            "dbname": DB_NAME,
            "user": DB_USER,
            "password": DB_PASSWORD,
            "host": DB_HOST,
            "port": DB_PORT,
        }
        self.conn = None
        self._connect()
        self._create_tables()

    def _connect(self):
        """Établit la connexion à la base de données"""
        try:
            self.conn = psycopg2.connect(**self.connection_params)
            logger.info("✅ SubscriptionService connecté à PostgreSQL")
        except Exception as e:
            logger.error(f"❌ Erreur connexion PostgreSQL: {e}")
            self.conn = None

    def _ensure_connection(self):
        """Vérifie et rétablit la connexion si nécessaire"""
        if self.conn is None or self.conn.closed:
            self._connect()

    def _create_tables(self):
        """Crée les tables nécessaires si elles n'existent pas"""
        self._ensure_connection()
        if not self.conn:
            return

        create_subscriptions_table = """
        CREATE TABLE IF NOT EXISTS user_subscriptions (
            id SERIAL PRIMARY KEY,
            user_id INTEGER UNIQUE NOT NULL,
            tier VARCHAR(20) NOT NULL DEFAULT 'free',
            started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            expires_at TIMESTAMP,
            is_active BOOLEAN DEFAULT TRUE
        );
        CREATE INDEX IF NOT EXISTS idx_subscriptions_user_id ON user_subscriptions(user_id);
        """

        create_usage_table = """
        CREATE TABLE IF NOT EXISTS user_daily_usage (
            id SERIAL PRIMARY KEY,
            user_id INTEGER NOT NULL,
            usage_date DATE NOT NULL DEFAULT CURRENT_DATE,
            messages_count INTEGER DEFAULT 0,
            tokens_used INTEGER DEFAULT 0,
            UNIQUE(user_id, usage_date)
        );
        CREATE INDEX IF NOT EXISTS idx_usage_user_date ON user_daily_usage(user_id, usage_date);
        """

        try:
            with self.conn.cursor() as cursor:
                cursor.execute(create_subscriptions_table)
                cursor.execute(create_usage_table)
                self.conn.commit()
                logger.info("✅ Tables d'abonnements créées/vérifiées")
        except Exception as e:
            logger.error(f"❌ Erreur création tables: {e}")
            self.conn.rollback()

    async def get_user_tier(self, user_id: int) -> str:
        """
        Récupère le tier d'abonnement d'un utilisateur
        
        Args:
            user_id: ID de l'utilisateur
            
        Returns:
            str: Tier d'abonnement (free, standard, premium, vip)
        """
        self._ensure_connection()
        if not self.conn:
            return "free"

        try:
            with self.conn.cursor(cursor_factory=RealDictCursor) as cursor:
                cursor.execute(
                    """
                    SELECT tier FROM user_subscriptions 
                    WHERE user_id = %s AND is_active = TRUE
                    AND (expires_at IS NULL OR expires_at > CURRENT_TIMESTAMP)
                    """,
                    (user_id,)
                )
                result = cursor.fetchone()
                return result["tier"] if result else "free"

        except Exception as e:
            logger.error(f"❌ Erreur get_user_tier: {e}")
            return "free"

    async def get_tier_limits(self, tier: str) -> Dict:
        """
        Récupère les limites d'un tier
        
        Args:
            tier: Nom du tier
            
        Returns:
            Dict: Limites du tier
        """
        return SUBSCRIPTION_TIERS.get(tier, SUBSCRIPTION_TIERS["free"])

    async def get_daily_usage(self, user_id: int) -> Dict:
        """
        Récupère l'utilisation quotidienne d'un utilisateur
        
        Args:
            user_id: ID de l'utilisateur
            
        Returns:
            Dict: Compteurs d'utilisation
        """
        self._ensure_connection()
        if not self.conn:
            return {"messages_count": 0, "tokens_used": 0}

        try:
            with self.conn.cursor(cursor_factory=RealDictCursor) as cursor:
                cursor.execute(
                    """
                    SELECT messages_count, tokens_used FROM user_daily_usage 
                    WHERE user_id = %s AND usage_date = CURRENT_DATE
                    """,
                    (user_id,)
                )
                result = cursor.fetchone()
                if result:
                    return dict(result)
                return {"messages_count": 0, "tokens_used": 0}

        except Exception as e:
            logger.error(f"❌ Erreur get_daily_usage: {e}")
            return {"messages_count": 0, "tokens_used": 0}

    async def check_can_send_message(self, user_id: int) -> Tuple[bool, str]:
        """
        Vérifie si un utilisateur peut envoyer un message
        
        Args:
            user_id: ID de l'utilisateur
            
        Returns:
            Tuple[bool, str]: (peut envoyer, message d'erreur si non)
        """
        tier = await self.get_user_tier(user_id)
        limits = await self.get_tier_limits(tier)
        usage = await self.get_daily_usage(user_id)

        max_messages = limits["max_messages"]
        max_tokens = limits["max_tokens_per_day"]

        if max_messages != -1 and usage["messages_count"] >= max_messages:
            tier_name = limits["name"]
            return False, (
                f"Tu as atteint ta limite de {max_messages} messages pour aujourd'hui "
                f"avec l'abonnement {tier_name}. Passe à un abonnement supérieur pour continuer !"
            )

        if max_tokens != -1 and usage["tokens_used"] >= max_tokens:
            return False, (
                f"Tu as atteint ta limite de tokens pour aujourd'hui. "
                "Reviens demain ou passe à un abonnement supérieur !"
            )

        return True, ""

    async def increment_usage(self, user_id: int, tokens_used: int = 0):
        """
        Incrémente l'utilisation quotidienne d'un utilisateur
        
        Args:
            user_id: ID de l'utilisateur
            tokens_used: Nombre de tokens utilisés pour ce message
        """
        self._ensure_connection()
        if not self.conn:
            return

        try:
            with self.conn.cursor() as cursor:
                cursor.execute(
                    """
                    INSERT INTO user_daily_usage (user_id, usage_date, messages_count, tokens_used)
                    VALUES (%s, CURRENT_DATE, 1, %s)
                    ON CONFLICT (user_id, usage_date) 
                    DO UPDATE SET 
                        messages_count = user_daily_usage.messages_count + 1,
                        tokens_used = user_daily_usage.tokens_used + %s
                    """,
                    (user_id, tokens_used, tokens_used)
                )
                self.conn.commit()
                logger.info(f"📊 Usage incrémenté pour user {user_id}")

        except Exception as e:
            logger.error(f"❌ Erreur increment_usage: {e}")
            self.conn.rollback()

    async def get_usage_summary(self, user_id: int) -> Dict:
        """
        Récupère un résumé de l'utilisation et des limites
        
        Args:
            user_id: ID de l'utilisateur
            
        Returns:
            Dict: Résumé d'utilisation
        """
        tier = await self.get_user_tier(user_id)
        limits = await self.get_tier_limits(tier)
        usage = await self.get_daily_usage(user_id)

        max_messages = limits["max_messages"]
        max_tokens = limits["max_tokens_per_day"]

        return {
            "tier": tier,
            "tier_name": limits["name"],
            "messages_used": usage["messages_count"],
            "messages_limit": max_messages if max_messages != -1 else "Illimité",
            "messages_remaining": (
                max_messages - usage["messages_count"]
                if max_messages != -1
                else "Illimité"
            ),
            "tokens_used": usage["tokens_used"],
            "tokens_limit": max_tokens if max_tokens != -1 else "Illimité",
            "session_memory_enabled": limits["session_memory"],
        }

    async def set_user_tier(
        self,
        user_id: int,
        tier: str,
        expires_at: Optional[datetime] = None
    ):
        """
        Définit le tier d'abonnement d'un utilisateur
        
        Args:
            user_id: ID de l'utilisateur
            tier: Nouveau tier
            expires_at: Date d'expiration (optionnel)
        """
        if tier not in SUBSCRIPTION_TIERS:
            logger.error(f"❌ Tier inconnu: {tier}")
            return

        self._ensure_connection()
        if not self.conn:
            return

        try:
            with self.conn.cursor() as cursor:
                cursor.execute(
                    """
                    INSERT INTO user_subscriptions (user_id, tier, expires_at)
                    VALUES (%s, %s, %s)
                    ON CONFLICT (user_id) 
                    DO UPDATE SET 
                        tier = %s,
                        expires_at = %s,
                        started_at = CURRENT_TIMESTAMP,
                        is_active = TRUE
                    """,
                    (user_id, tier, expires_at, tier, expires_at)
                )
                self.conn.commit()
                logger.info(f"✅ Tier {tier} défini pour user {user_id}")

        except Exception as e:
            logger.error(f"❌ Erreur set_user_tier: {e}")
            self.conn.rollback()

    async def has_session_memory(self, user_id: int) -> bool:
        """
        Vérifie si un utilisateur a accès à la mémoire de session
        
        Args:
            user_id: ID de l'utilisateur
            
        Returns:
            bool: True si mémoire de session activée
        """
        tier = await self.get_user_tier(user_id)
        limits = await self.get_tier_limits(tier)
        return limits.get("session_memory", False)


_subscription_instance = None


def get_subscription_service():
    """Retourne l'instance singleton du service d'abonnements"""
    global _subscription_instance
    if _subscription_instance is None:
        _subscription_instance = SubscriptionService()
    return _subscription_instance
