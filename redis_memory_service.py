"""Service de mémoire court terme avec Redis pour général et sexologie"""
import logging
import json
from typing import List, Dict
from datetime import datetime
import redis.asyncio as redis
from config import REDIS_URL

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

MEMORY_LIMIT = 5


class RedisMemoryService:
    """Service de mémoire court terme avec Redis"""

    def __init__(self):
        """Initialise la connexion Redis"""
        self.redis_url = REDIS_URL
        self.client = None
        self._connected = False

    async def connect(self):
        """Établit la connexion Redis"""
        if self._connected:
            return

        try:
            self.client = redis.from_url(self.redis_url, decode_responses=True)
            await self.client.ping()
            self._connected = True
            logger.info("✅ Redis connecté")
        except Exception as e:
            logger.warning(f"⚠️ Redis non disponible: {e} - Mode fallback mémoire locale")
            self.client = None
            self._connected = False

    async def _ensure_connection(self):
        """Vérifie la connexion"""
        if not self._connected:
            await self.connect()

    def _get_key(self, user_id: int, category: str) -> str:
        """Génère la clé Redis pour un utilisateur et une catégorie"""
        return f"memory:{user_id}:{category}"

    async def add_message(
        self,
        user_id: int,
        category: str,
        user_message: str,
        assistant_response: str
    ):
        """
        Ajoute un échange à la mémoire (limite 5 derniers)
        
        Args:
            user_id: ID de l'utilisateur
            category: Catégorie (general, sexologie)
            user_message: Message de l'utilisateur
            assistant_response: Réponse de l'assistant
        """
        await self._ensure_connection()
        
        exchange = {
            "user": user_message,
            "assistant": assistant_response,
            "timestamp": datetime.now().isoformat()
        }

        key = self._get_key(user_id, category)

        if self.client:
            try:
                await self.client.rpush(key, json.dumps(exchange))
                await self.client.ltrim(key, -MEMORY_LIMIT, -1)
                await self.client.expire(key, 3600 * 24)
                logger.info(f"💾 Message ajouté à Redis: {key}")
            except Exception as e:
                logger.error(f"❌ Erreur Redis add_message: {e}")

    async def get_history(
        self,
        user_id: int,
        category: str
    ) -> List[Dict]:
        """
        Récupère les derniers échanges
        
        Args:
            user_id: ID de l'utilisateur
            category: Catégorie
            
        Returns:
            List[Dict]: Liste des échanges
        """
        await self._ensure_connection()
        
        key = self._get_key(user_id, category)

        if self.client:
            try:
                messages = await self.client.lrange(key, 0, -1)
                return [json.loads(m) for m in messages]
            except Exception as e:
                logger.error(f"❌ Erreur Redis get_history: {e}")
                return []
        
        return []

    async def clear_history(self, user_id: int, category: str):
        """Efface l'historique d'un utilisateur pour une catégorie"""
        await self._ensure_connection()
        
        key = self._get_key(user_id, category)
        
        if self.client:
            try:
                await self.client.delete(key)
                logger.info(f"🗑️ Historique effacé: {key}")
            except Exception as e:
                logger.error(f"❌ Erreur Redis clear_history: {e}")

    async def close(self):
        """Ferme la connexion Redis"""
        if self.client:
            await self.client.close()
            self._connected = False


_redis_memory_instance = None


async def get_redis_memory_service() -> RedisMemoryService:
    """Retourne l'instance singleton du service Redis"""
    global _redis_memory_instance
    if _redis_memory_instance is None:
        _redis_memory_instance = RedisMemoryService()
        await _redis_memory_instance.connect()
    return _redis_memory_instance
