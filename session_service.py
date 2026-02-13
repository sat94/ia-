"""Service de gestion des sessions persistantes pour les catégories avec mémoire"""
import logging
import uuid
from typing import Optional, List, Dict
from datetime import datetime
import psycopg2
from psycopg2.extras import RealDictCursor
from config import DB_NAME, DB_USER, DB_PASSWORD, DB_HOST, DB_PORT, SESSION_CATEGORIES

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class SessionService:
    """Service pour gérer les sessions de coaching persistantes"""

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
            logger.info("✅ SessionService connecté à PostgreSQL")
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

        create_sessions_table = """
        CREATE TABLE IF NOT EXISTS coaching_sessions (
            id SERIAL PRIMARY KEY,
            session_id VARCHAR(64) UNIQUE NOT NULL,
            user_id INTEGER NOT NULL,
            expert_id VARCHAR(50) NOT NULL,
            category VARCHAR(50) NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            is_active BOOLEAN DEFAULT TRUE,
            summary TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_sessions_user_id ON coaching_sessions(user_id);
        CREATE INDEX IF NOT EXISTS idx_sessions_session_id ON coaching_sessions(session_id);
        """

        create_exchanges_table = """
        CREATE TABLE IF NOT EXISTS session_exchanges (
            id SERIAL PRIMARY KEY,
            session_id VARCHAR(64) NOT NULL REFERENCES coaching_sessions(session_id),
            user_message TEXT NOT NULL,
            assistant_response TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            tokens_used INTEGER DEFAULT 0
        );
        CREATE INDEX IF NOT EXISTS idx_exchanges_session_id ON session_exchanges(session_id);
        """

        try:
            with self.conn.cursor() as cursor:
                cursor.execute(create_sessions_table)
                cursor.execute(create_exchanges_table)
                self.conn.commit()
                logger.info("✅ Tables de sessions créées/vérifiées")
        except Exception as e:
            logger.error(f"❌ Erreur création tables: {e}")
            self.conn.rollback()

    async def get_or_create_session(
        self,
        user_id: int,
        expert_id: str,
        category: str
    ) -> str:
        """
        Récupère la session active ou en crée une nouvelle
        
        Args:
            user_id: ID de l'utilisateur
            expert_id: ID de l'expert
            category: Catégorie de la session
            
        Returns:
            str: session_id
        """
        self._ensure_connection()
        if not self.conn:
            return self._generate_session_id()

        try:
            with self.conn.cursor(cursor_factory=RealDictCursor) as cursor:
                cursor.execute(
                    """
                    SELECT session_id FROM coaching_sessions 
                    WHERE user_id = %s AND expert_id = %s AND is_active = TRUE
                    ORDER BY updated_at DESC LIMIT 1
                    """,
                    (user_id, expert_id)
                )
                result = cursor.fetchone()

                if result:
                    session_id = result["session_id"]
                    cursor.execute(
                        "UPDATE coaching_sessions SET updated_at = CURRENT_TIMESTAMP WHERE session_id = %s",
                        (session_id,)
                    )
                    self.conn.commit()
                    logger.info(f"📂 Session existante récupérée: {session_id}")
                    return session_id

                session_id = self._generate_session_id()
                cursor.execute(
                    """
                    INSERT INTO coaching_sessions (session_id, user_id, expert_id, category)
                    VALUES (%s, %s, %s, %s)
                    """,
                    (session_id, user_id, expert_id, category)
                )
                self.conn.commit()
                logger.info(f"📁 Nouvelle session créée: {session_id}")
                return session_id

        except Exception as e:
            logger.error(f"❌ Erreur get_or_create_session: {e}")
            self.conn.rollback()
            return self._generate_session_id()

    def _generate_session_id(self) -> str:
        """Génère un ID de session unique"""
        return f"session_{uuid.uuid4().hex[:16]}"

    async def get_session_history(
        self,
        session_id: str,
        limit: int = 10
    ) -> List[Dict]:
        """
        Récupère l'historique des échanges d'une session
        
        Args:
            session_id: ID de la session
            limit: Nombre max d'échanges à récupérer
            
        Returns:
            List[Dict]: Liste des échanges
        """
        self._ensure_connection()
        if not self.conn:
            return []

        try:
            with self.conn.cursor(cursor_factory=RealDictCursor) as cursor:
                cursor.execute(
                    """
                    SELECT user_message as user, assistant_response as assistant, created_at
                    FROM session_exchanges
                    WHERE session_id = %s
                    ORDER BY created_at DESC
                    LIMIT %s
                    """,
                    (session_id, limit)
                )
                results = cursor.fetchall()
                return list(reversed([dict(r) for r in results]))

        except Exception as e:
            logger.error(f"❌ Erreur get_session_history: {e}")
            return []

    async def add_exchange(
        self,
        session_id: str,
        user_message: str,
        assistant_response: str,
        expert_id: str,
        tokens_used: int = 0
    ):
        """
        Ajoute un échange à la session
        
        Args:
            session_id: ID de la session
            user_message: Message de l'utilisateur
            assistant_response: Réponse de l'assistant
            expert_id: ID de l'expert
            tokens_used: Nombre de tokens utilisés
        """
        self._ensure_connection()
        if not self.conn:
            return

        try:
            with self.conn.cursor() as cursor:
                cursor.execute(
                    """
                    INSERT INTO session_exchanges 
                    (session_id, user_message, assistant_response, tokens_used)
                    VALUES (%s, %s, %s, %s)
                    """,
                    (session_id, user_message, assistant_response, tokens_used)
                )
                cursor.execute(
                    "UPDATE coaching_sessions SET updated_at = CURRENT_TIMESTAMP WHERE session_id = %s",
                    (session_id,)
                )
                self.conn.commit()
                logger.info(f"💬 Échange ajouté à la session {session_id}")

        except Exception as e:
            logger.error(f"❌ Erreur add_exchange: {e}")
            self.conn.rollback()

    async def get_user_sessions(
        self,
        user_id: int,
        expert_id: Optional[str] = None,
        active_only: bool = True
    ) -> List[Dict]:
        """
        Récupère toutes les sessions d'un utilisateur
        
        Args:
            user_id: ID de l'utilisateur
            expert_id: Filtrer par expert (optionnel)
            active_only: Ne retourner que les sessions actives
            
        Returns:
            List[Dict]: Liste des sessions
        """
        self._ensure_connection()
        if not self.conn:
            return []

        try:
            with self.conn.cursor(cursor_factory=RealDictCursor) as cursor:
                query = """
                    SELECT cs.*, 
                           (SELECT COUNT(*) FROM session_exchanges WHERE session_id = cs.session_id) as exchange_count
                    FROM coaching_sessions cs
                    WHERE cs.user_id = %s
                """
                params = [user_id]

                if expert_id:
                    query += " AND cs.expert_id = %s"
                    params.append(expert_id)

                if active_only:
                    query += " AND cs.is_active = TRUE"

                query += " ORDER BY cs.updated_at DESC"

                cursor.execute(query, tuple(params))
                return [dict(r) for r in cursor.fetchall()]

        except Exception as e:
            logger.error(f"❌ Erreur get_user_sessions: {e}")
            return []

    async def close_session(self, session_id: str, summary: Optional[str] = None):
        """
        Ferme une session et optionnellement ajoute un résumé
        
        Args:
            session_id: ID de la session
            summary: Résumé de la session (optionnel)
        """
        self._ensure_connection()
        if not self.conn:
            return

        try:
            with self.conn.cursor() as cursor:
                cursor.execute(
                    """
                    UPDATE coaching_sessions 
                    SET is_active = FALSE, summary = %s, updated_at = CURRENT_TIMESTAMP
                    WHERE session_id = %s
                    """,
                    (summary, session_id)
                )
                self.conn.commit()
                logger.info(f"🔒 Session fermée: {session_id}")

        except Exception as e:
            logger.error(f"❌ Erreur close_session: {e}")
            self.conn.rollback()

    async def get_session_summary(self, session_id: str) -> str:
        """
        Génère un résumé de la session pour le contexte
        
        Args:
            session_id: ID de la session
            
        Returns:
            str: Résumé textuel de la session
        """
        history = await self.get_session_history(session_id, limit=20)
        
        if not history:
            return ""

        summary_parts = []
        for i, exchange in enumerate(history[-5:], 1):
            summary_parts.append(f"Échange {i}:")
            summary_parts.append(f"  User: {exchange['user'][:100]}...")
            summary_parts.append(f"  Assistant: {exchange['assistant'][:100]}...")

        return "\n".join(summary_parts)

    def requires_session(self, category: str) -> bool:
        """Vérifie si une catégorie nécessite une session"""
        return category in SESSION_CATEGORIES


_session_instance = None


def get_session_service():
    """Retourne l'instance singleton du service de sessions"""
    global _session_instance
    if _session_instance is None:
        _session_instance = SessionService()
    return _session_instance
