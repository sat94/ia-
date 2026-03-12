"""Service d'analyse de personnalité basé sur les conversations stockées en pgvector"""
import logging
import json
from typing import Optional, Dict, List
from datetime import datetime
import asyncpg
import aiohttp

from config import (
    DB_NAME, DB_USER, DB_PASSWORD, DB_HOST, DB_PORT,
    DEEPINFRA_API_KEY, DEEPINFRA_MODELS,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

BIG_FIVE_TRAITS = {
    "ouverture": {
        "name": "Ouverture d'esprit",
        "description": "Curiosité intellectuelle, créativité, ouverture aux nouvelles expériences",
        "high": "Curieux, créatif, ouvert aux nouvelles idées",
        "low": "Conventionnel, pratique, préfère la routine",
    },
    "conscienciosite": {
        "name": "Conscienciosité",
        "description": "Organisation, discipline, fiabilité, persévérance",
        "high": "Organisé, fiable, discipliné, orienté objectifs",
        "low": "Spontané, flexible, moins structuré",
    },
    "extraversion": {
        "name": "Extraversion",
        "description": "Sociabilité, assertivité, énergie sociale, enthousiasme",
        "high": "Sociable, énergique, expressif, aime le contact",
        "low": "Introverti, réservé, préfère la solitude",
    },
    "agreabilite": {
        "name": "Agréabilité",
        "description": "Coopération, empathie, confiance, bienveillance",
        "high": "Bienveillant, coopératif, empathique, altruiste",
        "low": "Compétitif, direct, sceptique",
    },
    "stabilite_emotionnelle": {
        "name": "Stabilité émotionnelle",
        "description": "Calme, résilience, gestion du stress (inverse du neuroticisme)",
        "high": "Calme, résilient, stable émotionnellement",
        "low": "Sensible, anxieux, réactif émotionnellement",
    },
}

ANALYSIS_PROMPT = """Tu es un psychologue expert en analyse de personnalité. Analyse les messages suivants d'un utilisateur pour déterminer son profil de personnalité selon le modèle Big Five (OCEAN).

MESSAGES DE L'UTILISATEUR (du plus ancien au plus récent):
{messages}

ANALYSE DEMANDÉE:
Évalue chaque trait sur une échelle de 1 à 10 et fournis une description. Identifie aussi le style de communication et les centres d'intérêt.

Réponds UNIQUEMENT en JSON valide avec cette structure exacte:
{{
  "traits": {{
    "ouverture": {{"score": 7, "description": "Explication courte"}},
    "conscienciosite": {{"score": 6, "description": "Explication courte"}},
    "extraversion": {{"score": 8, "description": "Explication courte"}},
    "agreabilite": {{"score": 7, "description": "Explication courte"}},
    "stabilite_emotionnelle": {{"score": 5, "description": "Explication courte"}}
  }},
  "style_communication": "Description du style (formel/informel, direct/indirect, émotif/rationnel, verbeux/concis)",
  "centres_interet": ["intérêt1", "intérêt2", "intérêt3"],
  "traits_dominants": ["trait positif 1", "trait positif 2", "trait positif 3"],
  "points_attention": ["point d'attention 1", "point d'attention 2"],
  "profil_resume": "Résumé en 2-3 phrases du profil global de personnalité"
}}"""

MIN_MESSAGES_FOR_ANALYSIS = 5


class PersonalityService:

    def __init__(self):
        self.dsn = f"postgresql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"
        self.pool: Optional[asyncpg.Pool] = None
        self.api_key = DEEPINFRA_API_KEY
        self.base_url = "https://api.deepinfra.com/v1/openai/chat/completions"
        self.model = DEEPINFRA_MODELS.get("psychologie", DEEPINFRA_MODELS["general"])
        self._session: Optional[aiohttp.ClientSession] = None

    async def _ensure_pool(self):
        if self.pool is None or self.pool._closed:
            self.pool = await asyncpg.create_pool(
                self.dsn, min_size=1, max_size=5, command_timeout=10
            )

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                timeout=aiohttp.ClientTimeout(total=60),
            )
        return self._session

    async def _fetch_user_messages(self, user_id: int, limit: int = 100) -> List[Dict]:
        await self._ensure_pool()
        try:
            rows = await self.pool.fetch(
                """
                SELECT se.user_message, se.assistant_response, se.topics_extracted,
                       se.sentiment, se.created_at, cs.expert_id, cs.category
                FROM session_exchanges se
                JOIN coaching_sessions cs ON cs.session_id = se.session_id
                WHERE cs.user_id = $1
                ORDER BY se.created_at ASC
                LIMIT $2
                """,
                user_id, limit,
            )
            return [dict(r) for r in rows]
        except Exception as e:
            logger.error(f"Fetch user messages error: {e}")
            return []

    def _format_messages_for_analysis(self, exchanges: List[Dict]) -> str:
        lines = []
        for i, ex in enumerate(exchanges, 1):
            ts = ex.get("created_at")
            ts_str = ts.strftime("%d/%m %H:%M") if ts else "?"
            category = ex.get("category", "general")
            msg = ex["user_message"]
            lines.append(f"[{ts_str}] ({category}) User: {msg}")
        return "\n".join(lines)

    async def _call_llm(self, prompt: str) -> Optional[str]:
        if not self.api_key:
            return None
        try:
            session = await self._get_session()
            payload = {
                "model": self.model,
                "messages": [
                    {"role": "system", "content": "Tu es un psychologue expert. Reponds uniquement en JSON valide."},
                    {"role": "user", "content": prompt},
                ],
                "temperature": 0.3,
                "max_tokens": 1500,
                "stream": False,
            }
            async with session.post(self.base_url, json=payload) as resp:
                if resp.status != 200:
                    body = await resp.text()
                    logger.error(f"LLM error {resp.status}: {body}")
                    return None
                data = await resp.json()
                return data["choices"][0]["message"]["content"].strip()
        except Exception as e:
            logger.error(f"LLM call error: {e}")
            return None

    def _parse_llm_response(self, raw: str) -> Optional[Dict]:
        try:
            start = raw.find("{")
            end = raw.rfind("}") + 1
            if start == -1 or end == 0:
                return None
            return json.loads(raw[start:end])
        except json.JSONDecodeError as e:
            logger.error(f"JSON parse error: {e}")
            return None

    async def analyze_personality(self, user_id: int, force: bool = False) -> Optional[Dict]:
        if not force:
            existing = await self.get_personality(user_id)
            if existing:
                last_analyzed = existing.get("analyzed_at")
                if last_analyzed:
                    from datetime import timedelta
                    if datetime.now() - last_analyzed < timedelta(hours=24):
                        return existing

        exchanges = await self._fetch_user_messages(user_id, limit=100)
        if len(exchanges) < MIN_MESSAGES_FOR_ANALYSIS:
            return {
                "status": "insufficient_data",
                "message": f"Il faut au moins {MIN_MESSAGES_FOR_ANALYSIS} messages pour analyser la personnalité. "
                           f"Actuellement : {len(exchanges)} messages.",
                "messages_count": len(exchanges),
                "required": MIN_MESSAGES_FOR_ANALYSIS,
            }

        messages_text = self._format_messages_for_analysis(exchanges)
        prompt = ANALYSIS_PROMPT.format(messages=messages_text)

        raw_response = await self._call_llm(prompt)
        if not raw_response:
            return None

        analysis = self._parse_llm_response(raw_response)
        if not analysis:
            return None

        traits = analysis.get("traits", {})
        for trait_key, trait_info in BIG_FIVE_TRAITS.items():
            if trait_key in traits:
                traits[trait_key]["name"] = trait_info["name"]
                score = traits[trait_key].get("score", 5)
                traits[trait_key]["level"] = "high" if score >= 7 else ("low" if score <= 3 else "medium")

        result = {
            "user_id": user_id,
            "traits": traits,
            "style_communication": analysis.get("style_communication", ""),
            "centres_interet": analysis.get("centres_interet", []),
            "traits_dominants": analysis.get("traits_dominants", []),
            "points_attention": analysis.get("points_attention", []),
            "profil_resume": analysis.get("profil_resume", ""),
            "messages_analyzed": len(exchanges),
            "analyzed_at": datetime.now().isoformat(),
            "status": "complete",
        }

        await self._store_personality(user_id, result)
        return result

    async def _store_personality(self, user_id: int, result: Dict):
        await self._ensure_pool()
        try:
            await self.pool.execute(
                """
                INSERT INTO user_personality 
                (user_id, traits, style_communication, centres_interet,
                 traits_dominants, points_attention, profil_resume, messages_analyzed)
                VALUES ($1, $2::jsonb, $3, $4, $5, $6, $7, $8)
                ON CONFLICT (user_id) 
                DO UPDATE SET 
                    traits = EXCLUDED.traits,
                    style_communication = EXCLUDED.style_communication,
                    centres_interet = EXCLUDED.centres_interet,
                    traits_dominants = EXCLUDED.traits_dominants,
                    points_attention = EXCLUDED.points_attention,
                    profil_resume = EXCLUDED.profil_resume,
                    messages_analyzed = EXCLUDED.messages_analyzed,
                    analyzed_at = CURRENT_TIMESTAMP,
                    version = user_personality.version + 1
                """,
                user_id,
                json.dumps(result.get("traits", {})),
                result.get("style_communication", ""),
                result.get("centres_interet", []),
                result.get("traits_dominants", []),
                result.get("points_attention", []),
                result.get("profil_resume", ""),
                result.get("messages_analyzed", 0),
            )
        except Exception as e:
            logger.error(f"Store personality error: {e}")

    async def get_personality(self, user_id: int) -> Optional[Dict]:
        await self._ensure_pool()
        try:
            row = await self.pool.fetchrow(
                """
                SELECT user_id, traits, style_communication, centres_interet,
                       traits_dominants, points_attention, profil_resume,
                       messages_analyzed, analyzed_at, version
                FROM user_personality
                WHERE user_id = $1
                """,
                user_id,
            )
            if not row:
                return None
            r = dict(row)
            if isinstance(r.get("traits"), str):
                r["traits"] = json.loads(r["traits"])
            r["status"] = "complete"
            return r
        except Exception as e:
            logger.error(f"Get personality error: {e}")
            return None

    def personality_to_context(self, personality: Dict) -> str:
        if not personality or personality.get("status") != "complete":
            return ""
        parts = []
        resume = personality.get("profil_resume", "")
        if resume:
            parts.append(f"Profil: {resume}")
        style = personality.get("style_communication", "")
        if style:
            parts.append(f"Style: {style}")
        traits = personality.get("traits", {})
        if traits:
            scores = []
            for key, data in traits.items():
                name = data.get("name", key)
                score = data.get("score", 5)
                scores.append(f"{name}={score}/10")
            parts.append("Big Five: " + ", ".join(scores))
        if not parts:
            return ""
        return (
            "[Personnalite de l'utilisateur: " + ". ".join(parts) + ". "
            "Adapte ton approche a sa personnalite: "
            "sois plus chaleureux avec les extravertis, plus structuré avec les consciencieux, "
            "plus doux avec les sensibles, plus direct avec les ouverts.]"
        )

    async def get_emotion_personality_context(self, user_id: int, current_emotion: Dict = None) -> str:
        personality = await self.get_personality(user_id)
        parts = []
        if personality and personality.get("status") == "complete":
            parts.append(self.personality_to_context(personality))
        if current_emotion:
            from voice_analysis_service import get_voice_analysis_service
            vas = get_voice_analysis_service()
            emo_ctx = vas.emotion_to_context(current_emotion)
            if emo_ctx:
                parts.append(emo_ctx)
        return "\n".join(parts)

    async def close(self):
        if self._session and not self._session.closed:
            await self._session.close()
        if self.pool:
            await self.pool.close()


_personality_instance = None


def get_personality_service():
    global _personality_instance
    if _personality_instance is None:
        _personality_instance = PersonalityService()
    return _personality_instance
