"""
Serveur WebSocket MeetVoice avec IA multi-experts (DeepInfra uniquement)
Gère la classification d'intentions, le routage vers les experts, sessions et abonnements
"""
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import List, Dict, Optional
import json
import asyncio
import logging
from datetime import datetime

from intent_classifier import get_classifier
from ai_service import get_ai_service
from tts_service import get_tts_service
from external_api_service import ExternalAPIService
from db_service import get_db_service
from conversation_service import get_conversation_service
from matching_service import get_matching_service
from session_service import get_session_service
from subscription_service import get_subscription_service
from redis_memory_service import get_redis_memory_service
from config import WEBSOCKET_PORT, WEBSOCKET_HOST, EXPERTS, SESSION_CATEGORIES

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="MeetVoice API", version="2.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

classifier = None
ai_service = None
tts_service = None
api_service = None
db_service = None
conversation_service = None
matching_service = None
session_service = None
subscription_service = None
redis_memory = None


@app.on_event("startup")
async def startup_event():
    """Initialise les services au démarrage"""
    global classifier, ai_service, tts_service, api_service, db_service
    global conversation_service, matching_service, session_service, subscription_service, redis_memory

    logger.info("🚀 Initialisation des services...")

    classifier = get_classifier()
    ai_service = get_ai_service()
    tts_service = get_tts_service()
    api_service = ExternalAPIService()
    db_service = get_db_service()
    conversation_service = get_conversation_service()
    matching_service = get_matching_service()
    session_service = get_session_service()
    subscription_service = get_subscription_service()
    redis_memory = await get_redis_memory_service()

    ai_service.set_redis_memory(redis_memory)
    ai_service.set_api_service(api_service)

    logger.info("✅ Tous les services sont prêts!")


class ConnectionManager:
    """Gestionnaire de connexions WebSocket"""

    def __init__(self):
        self.active_connections: List[WebSocket] = []
        self.user_contexts: Dict[WebSocket, Dict] = {}

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)
        self.user_contexts[websocket] = {
            "history": [],
            "current_expert": None,
            "session_start": datetime.now(),
            "last_search_results": None,
            "last_search_type": None,
            "last_query": None,
            "conversation_history": [],
            "user_id": None,
            "active_sessions": {},
        }
        logger.info(f"✓ Client connecté. Total: {len(self.active_connections)}")

    def disconnect(self, websocket: WebSocket):
        self.active_connections.remove(websocket)
        if websocket in self.user_contexts:
            del self.user_contexts[websocket]
        logger.info(f"✗ Client déconnecté. Total: {len(self.active_connections)}")

    async def send_message(self, message: dict, websocket: WebSocket):
        await websocket.send_text(json.dumps(message, ensure_ascii=False))

    def get_context(self, websocket: WebSocket) -> Dict:
        return self.user_contexts.get(websocket, {})

    def update_context(self, websocket: WebSocket, key: str, value):
        if websocket in self.user_contexts:
            self.user_contexts[websocket][key] = value


manager = ConnectionManager()


@app.get("/")
async def root():
    """Endpoint racine"""
    return {
        "service": "MeetVoice API",
        "version": "2.0.0",
        "status": "running",
        "features": [
            "WebSocket Chat",
            "AI Multi-Experts (DeepInfra)",
            "Session Memory",
            "Subscription Tiers",
            "Profile Matching"
        ]
    }


async def check_subscription_limit(user_id: int, websocket: WebSocket) -> tuple:
    """Vérifie les limites d'abonnement avant de traiter un message"""
    can_send, error_msg = await subscription_service.check_can_send_message(user_id)
    if not can_send:
        await manager.send_message({
            "type": "subscription_limit",
            "message": error_msg,
            "upgrade_url": "/upgrade"
        }, websocket)
    return can_send, error_msg


async def get_or_create_expert_session(
    user_id: int,
    expert_id: str,
    category: str,
    websocket: WebSocket
) -> Optional[str]:
    """Récupère ou crée une session pour les catégories avec mémoire"""
    if category not in SESSION_CATEGORIES:
        return None

    has_memory = await subscription_service.has_session_memory(user_id)
    if not has_memory:
        return None

    context = manager.get_context(websocket)
    active_sessions = context.get("active_sessions", {})

    if expert_id in active_sessions:
        return active_sessions[expert_id]

    session_id = await session_service.get_or_create_session(user_id, expert_id, category)
    active_sessions[expert_id] = session_id
    manager.update_context(websocket, "active_sessions", active_sessions)

    return session_id


async def generate_expert_response(
    user_message: str,
    expert_id: str,
    user_id: int,
    websocket: WebSocket
) -> str:
    """Génère une réponse avec contexte de session si applicable"""
    expert_config = EXPERTS.get(expert_id, EXPERTS.get("general", {}))
    category = expert_config.get("category", "general")

    session_id = await get_or_create_expert_session(user_id, expert_id, category, websocket)

    if session_id:
        response = await ai_service.generate_with_context(
            user_message, expert_id, session_id, session_service, user_id
        )
    else:
        response = await ai_service.generate_response(user_message, expert_id, user_id)

    await subscription_service.increment_usage(user_id, tokens_used=len(response) // 4)

    return response


@app.websocket("/ws/sexologie")
async def websocket_sexologie(websocket: WebSocket):
    """WebSocket dédié à l'expert en sexologie"""
    await websocket_expert(websocket, "sexologie")


@app.websocket("/ws/psychologie")
async def websocket_psychologie(websocket: WebSocket):
    """WebSocket dédié à l'expert en psychologie"""
    await websocket_expert(websocket, "psychologie")


@app.websocket("/ws/developpement_personnel")
async def websocket_developpement(websocket: WebSocket):
    """WebSocket dédié à l'expert en développement personnel"""
    await websocket_expert(websocket, "developpement_personnel")


@app.websocket("/ws/seduction")
async def websocket_seduction(websocket: WebSocket):
    """WebSocket dédié à l'expert en séduction"""
    await websocket_expert(websocket, "seduction")


async def websocket_expert(websocket: WebSocket, expert_id: str):
    """Endpoint WebSocket pour un expert spécifique"""
    await manager.connect(websocket)

    expert_info = EXPERTS[expert_id]

    welcome_msg = expert_info.get('welcome_message', f"Bonjour, je suis {expert_info['name'].split(' - ')[0]}. Comment puis-je vous aider ?")
    
    await manager.send_message({
        "type": "welcome",
        "expert": {
            "id": expert_id,
            "name": expert_info['name'],
            "description": expert_info['description']
        },
        "message": welcome_msg
    }, websocket)

    try:
        while True:
            data = await websocket.receive_text()
            logger.info(f"📨 [{expert_info['name']}] Reçu: {data}")

            try:
                try:
                    message_data = json.loads(data)
                    user_message = message_data.get("message", data)
                    user_id = message_data.get("user_id", 1)
                except json.JSONDecodeError:
                    user_message = data
                    user_id = 1

                manager.update_context(websocket, "user_id", user_id)

                can_send, _ = await check_subscription_limit(user_id, websocket)
                if not can_send:
                    continue

                ai_response = await generate_expert_response(
                    user_message, expert_id, user_id, websocket
                )

                logger.info(f"✅ [{expert_info['name']}] Réponse générée")

                audio_base64 = await tts_service.text_to_speech_base64(
                    ai_response, expert_id
                )

                response = {
                    "type": "expert_response",
                    "message": ai_response,
                    "expert": {
                        "id": expert_id,
                        "name": expert_info['name'],
                        "voice": expert_info['voice']
                    },
                    "audio": audio_base64 if audio_base64 else None
                }

                await manager.send_message(response, websocket)

            except Exception as e:
                logger.error(f"❌ Erreur traitement message: {e}", exc_info=True)
                await manager.send_message({
                    "type": "error",
                    "message": "Oups, j'ai eu un petit souci. Tu peux reformuler ?"
                }, websocket)

    except WebSocketDisconnect:
        manager.disconnect(websocket)
        logger.info(f"[{expert_info['name']}] Client déconnecté")


async def handle_api_search(intention: str, query: str, websocket: WebSocket = None) -> tuple:
    """Gère les recherches via les APIs externes"""
    try:
        if intention == "recherche_evenement":
            city = "Paris"
            if "lyon" in query.lower():
                city = "Lyon"
            elif "marseille" in query.lower():
                city = "Marseille"

            events = api_service.search_events(city=city, limit=5)
            response_text = api_service.format_events_response(events)
            return (response_text, events, "events")

        elif intention == "recherche_cinema":
            movies = api_service.search_movies(limit=5)
            response_text = api_service.format_movies_response(movies)
            return (response_text, movies, "movies")

        elif intention == "recherche_musique":
            artist = ""
            if "de " in query.lower():
                parts = query.lower().split("de ")
                if len(parts) > 1:
                    artist = parts[-1].strip()

            tracks = api_service.search_music(artist=artist, limit=5)
            response_text = api_service.format_music_response(tracks)
            return (response_text, tracks, "music")

        elif intention == "recherche_video":
            videos = api_service.search_videos(query, limit=5)
            response_text = api_service.format_videos_response(videos)
            return (response_text, videos, "videos")

        else:
            return ("Je ne peux pas traiter cette recherche pour le moment.", None, None)

    except Exception as e:
        logger.error(f"❌ Erreur recherche API: {e}")
        return ("Désolé, la recherche n'a pas fonctionné. Réessaie !", None, None)


async def handle_followup_question(query: str, websocket: WebSocket) -> str:
    context = manager.get_context(websocket)
    last_results = context.get("last_search_results")
    last_type = context.get("last_search_type")

    if not last_results or not last_type:
        return "Je n'ai pas de résultats précédents. Tu veux que je cherche quelque chose ?"

    import re
    query_lower = query.lower()
    item_idx = -1

    number_match = re.search(r'(\d+|premier|deuxième|troisième|quatrième|cinquième|1er|2ème|3ème|4ème|5ème|second)', query_lower)
    if number_match:
        item_idx = conversation_service._parse_number(number_match.group(1))

    if item_idx == -1:
        for idx, item in enumerate(last_results):
            for key in ("name", "title", "artist"):
                if key in item and any(word in item[key].lower() for word in query_lower.split() if len(word) > 3):
                    item_idx = idx
                    break
            if item_idx != -1:
                break

    if item_idx == -1 or item_idx >= len(last_results):
        return "Je n'ai pas trouvé cet élément. Tu peux me donner le numéro ?"

    item = last_results[item_idx]
    return format_item_details(item, last_type, item_idx + 1)


async def save_to_conversation_history(
    websocket: WebSocket,
    user_message: str,
    bot_response: str,
    intention: str,
    score: float,
    metadata: dict = None
):
    """Sauvegarde un échange dans l'historique de conversation"""
    context = manager.get_context(websocket)
    conversation_service.add_to_history(
        context, user_message, bot_response, intention,
        metadata={"score": score, **(metadata or {})}
    )


def format_item_details(item: dict, search_type: str, position: int) -> str:
    """Formate les détails d'un item spécifique"""
    if search_type == "events":
        return f"""📍 **{item.get('name', 'N/A')}**

📅 {item.get('date', 'N/A')}
📍 {item.get('venue', 'N/A')}
🔗 {item.get('url', 'N/A')}
"""

    elif search_type == "movies":
        return f"""🎬 **{item.get('title', 'N/A')}**

⭐ {item.get('rating', 'N/A')}/10
📅 {item.get('release_date', 'N/A')}

{item.get('overview', 'N/A')}
"""

    elif search_type == "music":
        return f"""🎵 **{item.get('title', 'N/A')}** - {item.get('artist', 'N/A')}

💿 {item.get('album', 'N/A')}
🔗 {item.get('link', 'N/A')}
"""

    elif search_type == "videos":
        return f"""📺 **{item.get('title', 'N/A')}**

📺 {item.get('channel', 'N/A')}
🔗 {item.get('url', 'N/A')}
"""

    return "Détails non disponibles"


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """Endpoint WebSocket principal avec classification et IA"""
    await manager.connect(websocket)

    await manager.send_message({
        "type": "welcome",
        "message": "Salut ! Comment je peux t'aider ?",
        "experts_available": list(EXPERTS.keys())
    }, websocket)

    try:
        while True:
            data = await websocket.receive_text()
            logger.info(f"📨 Reçu: {data}")

            try:
                try:
                    message_data = json.loads(data)
                    user_message = message_data.get("message", data)
                    force_expert = message_data.get("expert", None)
                    user_id = message_data.get("user_id", 1)
                except json.JSONDecodeError:
                    user_message = data
                    force_expert = None
                    user_id = 1

                manager.update_context(websocket, "user_id", user_id)

                can_send, _ = await check_subscription_limit(user_id, websocket)
                if not can_send:
                    continue

                intent_result = classifier.classify(user_message)
                logger.info(f"🎯 Intention: {intent_result['intention']} (score: {intent_result['score']:.2%})")

                if intent_result['intention'] == 'question_suivi':
                    followup_response = await handle_followup_question(user_message, websocket)

                    response = {
                        "type": "followup_response",
                        "message": followup_response,
                        "intention": "question_suivi",
                        "score": intent_result['score']
                    }

                    await manager.send_message(response, websocket)
                    await save_to_conversation_history(
                        websocket, user_message, followup_response,
                        "question_suivi", intent_result['score']
                    )

                elif intent_result['intention'] == 'recherche_profil':
                    context = manager.get_context(websocket)
                    uid = context.get('user_id', user_id)

                    criteria = matching_service.parse_search_criteria(user_message)
                    matches = matching_service.find_matches(
                        user_id=uid,
                        max_distance_km=criteria.get('max_distance_km', 50),
                        min_age=criteria.get('min_age'),
                        max_age=criteria.get('max_age'),
                        limit=10
                    )

                    profile_response = matching_service.format_matches_response(matches)

                    manager.update_context(websocket, "last_search_results", matches)
                    manager.update_context(websocket, "last_search_type", "profiles")

                    response = {
                        "type": "profile_search",
                        "message": profile_response,
                        "intention": "recherche_profil",
                        "score": intent_result['score'],
                        "results_count": len(matches)
                    }

                    await manager.send_message(response, websocket)
                    await save_to_conversation_history(
                        websocket, user_message, profile_response,
                        "recherche_profil", intent_result['score']
                    )

                elif intent_result['intention'] == 'comparer':
                    context = manager.get_context(websocket)
                    last_results = context.get("last_search_results")
                    last_type = context.get("last_search_type")

                    if last_results and len(last_results) >= 2:
                        items = conversation_service.parse_comparison_request(user_message, last_results)

                        if items:
                            comparison_response = conversation_service.compare_items(
                                items[0], items[1], last_type
                            )
                        else:
                            comparison_response = "Dis-moi lesquels tu veux comparer, genre 'compare le 1 et le 2'"
                    else:
                        comparison_response = "J'ai rien à comparer pour l'instant. Fais une recherche d'abord !"

                    response = {
                        "type": "comparison",
                        "message": comparison_response,
                        "intention": "comparer",
                        "score": intent_result['score']
                    }

                    await manager.send_message(response, websocket)
                    await save_to_conversation_history(
                        websocket, user_message, comparison_response,
                        "comparer", intent_result['score']
                    )

                elif intent_result['intention'] == 'rappel_historique':
                    context = manager.get_context(websocket)
                    history_summary = conversation_service.get_history_summary(context, limit=5)

                    response = {
                        "type": "history_recall",
                        "message": history_summary,
                        "intention": "rappel_historique",
                        "score": intent_result['score']
                    }

                    await manager.send_message(response, websocket)
                    await save_to_conversation_history(
                        websocket, user_message, history_summary,
                        "rappel_historique", intent_result['score']
                    )

                elif intent_result['intention'] in ['recherche_evenement', 'recherche_cinema', 'recherche_musique', 'recherche_video']:
                    api_response, results_data, search_type = await handle_api_search(
                        intent_result['intention'], user_message, websocket
                    )

                    manager.update_context(websocket, "last_search_results", results_data)
                    manager.update_context(websocket, "last_search_type", search_type)
                    manager.update_context(websocket, "last_query", user_message)

                    response = {
                        "type": "api_response",
                        "message": api_response,
                        "intention": intent_result['intention'],
                        "score": intent_result['score']
                    }

                    await manager.send_message(response, websocket)
                    await save_to_conversation_history(
                        websocket, user_message, api_response,
                        intent_result['intention'], intent_result['score']
                    )

                elif intent_result['intention'] == 'salutation' and not force_expert:
                    expert_id = "general"
                    expert_info = EXPERTS.get(expert_id, EXPERTS["seduction"])

                    ai_response = await ai_service.generate_response(user_message, expert_id, user_id)

                    audio_base64 = await tts_service.text_to_speech_base64(ai_response, expert_id)

                    response = {
                        "type": "simple_response",
                        "message": ai_response,
                        "expert": {
                            "id": expert_id,
                            "name": expert_info['name'],
                            "voice": expert_info['voice']
                        },
                        "intention": intent_result['intention'],
                        "score": intent_result['score'],
                        "audio": audio_base64 if audio_base64 else None
                    }

                    await manager.send_message(response, websocket)
                    await subscription_service.increment_usage(user_id, len(ai_response) // 4)
                    await save_to_conversation_history(
                        websocket, user_message, ai_response,
                        intent_result['intention'], intent_result['score']
                    )

                elif not classifier.needs_expert(intent_result['intention']) and not force_expert:
                    expert_id = classifier.route_to_expert(intent_result['intention'])
                    expert_info = EXPERTS.get(expert_id, EXPERTS["general"])

                    ai_response = await generate_expert_response(
                        user_message, expert_id, user_id, websocket
                    )

                    audio_base64 = await tts_service.text_to_speech_base64(ai_response, expert_id)

                    response = {
                        "type": "simple_response",
                        "message": ai_response,
                        "expert": {
                            "id": expert_id,
                            "name": expert_info['name'],
                            "voice": expert_info['voice']
                        },
                        "intention": intent_result['intention'],
                        "score": intent_result['score'],
                        "audio": audio_base64 if audio_base64 else None
                    }

                    await manager.send_message(response, websocket)
                    await save_to_conversation_history(
                        websocket, user_message, ai_response,
                        intent_result['intention'], intent_result['score']
                    )

                else:
                    expert_id = force_expert or classifier.route_to_expert(intent_result['intention'])
                    expert_info = EXPERTS.get(expert_id, EXPERTS["general"])

                    logger.info(f"👤 Expert: {expert_info['name']}")

                    context = manager.get_context(websocket)
                    previous_expert = context.get("current_expert")
                    
                    if previous_expert != expert_id:
                        welcome_msg = expert_info.get(
                            'welcome_message', 
                            f"Bonjour, je suis {expert_info['name'].split(' - ')[0]}. Comment puis-je vous aider ?"
                        )
                        welcome_audio = await tts_service.text_to_speech_base64(welcome_msg, expert_id)
                        
                        msg_type = "expert_switch" if previous_expert else "expert_intro"
                        
                        await manager.send_message({
                            "type": msg_type,
                            "message": welcome_msg,
                            "expert": {
                                "id": expert_id,
                                "name": expert_info['name'],
                                "voice": expert_info['voice']
                            },
                            "previous_expert": previous_expert,
                            "audio": welcome_audio if welcome_audio else None
                        }, websocket)
                        
                        if previous_expert:
                            logger.info(f"🔄 Changement d'expert: {previous_expert} → {expert_id}")
                        else:
                            logger.info(f"👋 Premier expert: {expert_id}")

                    manager.update_context(websocket, "current_expert", expert_id)

                    ai_response = await generate_expert_response(
                        user_message, expert_id, user_id, websocket
                    )

                    logger.info(f"✅ Réponse IA générée ({len(ai_response)} caractères)")

                    audio_base64 = await tts_service.text_to_speech_base64(ai_response, expert_id)

                    response = {
                        "type": "expert_response",
                        "message": ai_response,
                        "expert": {
                            "id": expert_id,
                            "name": expert_info['name'],
                            "voice": expert_info['voice']
                        },
                        "intention": intent_result['intention'],
                        "score": intent_result['score'],
                        "audio": audio_base64 if audio_base64 else None
                    }

                    await manager.send_message(response, websocket)
                    await save_to_conversation_history(
                        websocket, user_message, ai_response,
                        intent_result['intention'], intent_result['score']
                    )

            except Exception as e:
                logger.error(f"❌ Erreur traitement message: {e}", exc_info=True)
                await manager.send_message({
                    "type": "error",
                    "message": "Oups, j'ai eu un souci. Tu peux reformuler ?"
                }, websocket)

    except WebSocketDisconnect:
        manager.disconnect(websocket)
        logger.info("Client déconnecté")


class ProfileSearchRequest(BaseModel):
    """Requête de recherche de profils"""
    user_id: str
    max_distance_km: Optional[int] = 50
    min_age: Optional[int] = None
    max_age: Optional[int] = None
    limit: Optional[int] = 10


class SubscriptionRequest(BaseModel):
    """Requête de mise à jour d'abonnement"""
    user_id: int
    tier: str


class ChatRequest(BaseModel):
    """Requête de chat"""
    message: str
    user_id: int = 1
    stream: bool = True


@app.get("/health")
async def health_check():
    """Vérification de santé du service"""
    return {
        "status": "healthy",
        "services": {
            "classifier": classifier is not None,
            "ai_service": ai_service is not None,
            "db_service": db_service is not None,
            "session_service": session_service is not None,
            "subscription_service": subscription_service is not None
        }
    }


@app.get("/api/usage/{user_id}")
async def get_usage(user_id: int):
    """Récupère l'utilisation et les limites d'un utilisateur"""
    try:
        usage = await subscription_service.get_usage_summary(user_id)
        return {"success": True, "usage": usage}
    except Exception as e:
        logger.error(f"❌ Erreur récupération usage: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/subscription")
async def update_subscription(request: SubscriptionRequest):
    """Met à jour l'abonnement d'un utilisateur"""
    try:
        await subscription_service.set_user_tier(request.user_id, request.tier)
        return {"success": True, "user_id": request.user_id, "tier": request.tier}
    except Exception as e:
        logger.error(f"❌ Erreur mise à jour abonnement: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/sessions/{user_id}")
async def get_user_sessions(user_id: int, expert_id: Optional[str] = None):
    """Récupère les sessions d'un utilisateur"""
    try:
        sessions = await session_service.get_user_sessions(user_id, expert_id)
        return {"success": True, "sessions": sessions}
    except Exception as e:
        logger.error(f"❌ Erreur récupération sessions: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/profiles/search")
async def search_profiles(request: ProfileSearchRequest):
    """Endpoint REST pour rechercher des profils"""
    try:
        matches = matching_service.find_matches(
            user_id=request.user_id,
            max_distance_km=request.max_distance_km,
            min_age=request.min_age,
            max_age=request.max_age,
            limit=request.limit
        )

        return {
            "success": True,
            "user_id": request.user_id,
            "matches_count": len(matches),
            "matches": matches
        }
    except Exception as e:
        logger.error(f"❌ Erreur recherche profils: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/profiles/{profile_id}")
async def get_profile(profile_id: str):
    """Récupère un profil par son ID"""
    try:
        profile = db_service.get_profile_by_id(profile_id)

        if not profile:
            raise HTTPException(status_code=404, detail="Profil non trouvé")

        return {"success": True, "profile": profile}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Erreur récupération profil: {e}")
        raise HTTPException(status_code=500, detail=str(e))


user_contexts_rest: Dict[int, Dict] = {}


def get_user_context(user_id: int) -> Dict:
    """Récupère ou crée le contexte utilisateur pour REST"""
    if user_id not in user_contexts_rest:
        user_contexts_rest[user_id] = {
            "current_expert": None,
            "session_start": datetime.now(),
        }
    return user_contexts_rest[user_id]


async def stream_expert_response(
    message: str,
    expert_id: str,
    user_id: int,
    include_welcome: bool = False
):
    """Générateur SSE pour le streaming de réponse"""
    expert_info = EXPERTS.get(expert_id, EXPERTS["general"])
    context = get_user_context(user_id)
    previous_expert = context.get("current_expert")
    
    if include_welcome and previous_expert != expert_id:
        welcome_msg = expert_info.get(
            'welcome_message',
            f"Bonjour, je suis {expert_info['name'].split(' - ')[0]}. Comment puis-je vous aider ?"
        )
        
        event_type = "expert_switch" if previous_expert else "expert_intro"
        welcome_data = {
            "type": event_type,
            "expert": {
                "id": expert_id,
                "name": expert_info['name'],
                "voice": expert_info['voice']
            },
            "message": welcome_msg,
            "previous_expert": previous_expert
        }
        yield f"event: {event_type}\ndata: {json.dumps(welcome_data, ensure_ascii=False)}\n\n"
        
        context["current_expert"] = expert_id

    category = expert_info.get("category", "general")
    session_id = None
    
    if category in SESSION_CATEGORIES:
        has_memory = await subscription_service.has_session_memory(user_id)
        if has_memory:
            session_id = await session_service.get_or_create_session(user_id, expert_id, category)

    yield f"event: start\ndata: {json.dumps({'expert_id': expert_id, 'expert_name': expert_info['name']}, ensure_ascii=False)}\n\n"

    full_response = ""
    
    if session_id:
        async for token in ai_service.generate_stream_with_context(
            message, expert_id, session_id, session_service, user_id
        ):
            full_response += token
            yield f"event: token\ndata: {json.dumps({'token': token}, ensure_ascii=False)}\n\n"
    else:
        async for token in ai_service.generate_response_stream(message, expert_id, user_id):
            full_response += token
            yield f"event: token\ndata: {json.dumps({'token': token}, ensure_ascii=False)}\n\n"

    await subscription_service.increment_usage(user_id, tokens_used=len(full_response) // 4)

    yield f"event: done\ndata: {json.dumps({'full_response': full_response, 'expert_id': expert_id}, ensure_ascii=False)}\n\n"


@app.post("/api/chat/{expert_id}")
async def chat_with_expert(expert_id: str, request: ChatRequest):
    """
    Chat avec un expert spécifique (streaming SSE)
    
    - **expert_id**: sexologie, psychologie, developpement_personnel, seduction, general
    - **message**: Message de l'utilisateur
    - **user_id**: ID utilisateur (défaut: 1)
    - **stream**: Activer le streaming (défaut: true)
    """
    if expert_id not in EXPERTS:
        raise HTTPException(status_code=404, detail=f"Expert '{expert_id}' non trouvé")

    can_send, reason = await subscription_service.check_can_send_message(request.user_id)
    if not can_send:
        raise HTTPException(status_code=429, detail=reason)

    logger.info(f"📨 [REST] {expert_id}: {request.message[:50]}...")

    if request.stream:
        return StreamingResponse(
            stream_expert_response(request.message, expert_id, request.user_id, include_welcome=True),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no"
            }
        )
    else:
        expert_info = EXPERTS[expert_id]
        category = expert_info.get("category", "general")
        
        if category in SESSION_CATEGORIES:
            session_id = await session_service.get_or_create_session(
                request.user_id, expert_id, category
            )
            response = await ai_service.generate_with_context(
                request.message, expert_id, session_id, session_service, request.user_id
            )
        else:
            response = await ai_service.generate_response(
                request.message, expert_id, request.user_id
            )

        await subscription_service.increment_usage(request.user_id, tokens_used=len(response) // 4)

        audio_base64 = await tts_service.text_to_speech_base64(response, expert_id)

        return {
            "success": True,
            "expert": {
                "id": expert_id,
                "name": expert_info['name'],
                "voice": expert_info['voice']
            },
            "message": response,
            "audio": audio_base64
        }


@app.post("/api/chat")
async def chat_auto_route(request: ChatRequest):
    """
    Chat avec routage automatique vers l'expert approprié (streaming SSE)
    
    Classifie l'intention et route vers le bon expert.
    """
    can_send, reason = await subscription_service.check_can_send_message(request.user_id)
    if not can_send:
        raise HTTPException(status_code=429, detail=reason)

    intent_result = classifier.classify(request.message)
    logger.info(f"🎯 [REST] Intention: {intent_result['intention']} ({intent_result['score']:.0%})")

    expert_id = classifier.route_to_expert(intent_result['intention'])
    
    logger.info(f"📨 [REST] Auto-route → {expert_id}: {request.message[:50]}...")

    if request.stream:
        return StreamingResponse(
            stream_expert_response(request.message, expert_id, request.user_id, include_welcome=True),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no"
            }
        )
    else:
        expert_info = EXPERTS.get(expert_id, EXPERTS["general"])
        category = expert_info.get("category", "general")
        
        if category in SESSION_CATEGORIES:
            session_id = await session_service.get_or_create_session(
                request.user_id, expert_id, category
            )
            response = await ai_service.generate_with_context(
                request.message, expert_id, session_id, session_service, request.user_id
            )
        else:
            response = await ai_service.generate_response(
                request.message, expert_id, request.user_id
            )

        await subscription_service.increment_usage(request.user_id, tokens_used=len(response) // 4)

        audio_base64 = await tts_service.text_to_speech_base64(response, expert_id)

        return {
            "success": True,
            "intention": intent_result['intention'],
            "score": intent_result['score'],
            "expert": {
                "id": expert_id,
                "name": expert_info['name'],
                "voice": expert_info['voice']
            },
            "message": response,
            "audio": audio_base64
        }


@app.get("/api/experts")
async def list_experts():
    """Liste tous les experts disponibles avec leurs infos"""
    experts_list = []
    for expert_id, info in EXPERTS.items():
        experts_list.append({
            "id": expert_id,
            "name": info['name'],
            "description": info['description'],
            "voice": info['voice'],
            "category": info.get('category', expert_id),
            "welcome_message": info.get('welcome_message', '')
        })
    return {"success": True, "experts": experts_list}


if __name__ == "__main__":
    import uvicorn
    logger.info("🚀 Démarrage du serveur MeetVoice...")
    logger.info(f"📡 WebSocket: ws://localhost:{WEBSOCKET_PORT}/ws")
    logger.info(f"🌐 REST API: http://localhost:{WEBSOCKET_PORT}")
    logger.info(f"📚 Experts disponibles: {', '.join(EXPERTS.keys())}")
    uvicorn.run(app, host=WEBSOCKET_HOST, port=WEBSOCKET_PORT)
