"""
MeetVoice WebSocket Server - 100% WebSocket, streaming token-by-token
Intent classification (SVM+LR) → Direct response OU Expert AI (DeepInfra)
TTS lancé en parallèle du streaming pour que l'audio arrive en même temps que le texte
"""
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Dict, Optional
import json
import asyncio
import logging
import re
import random
import urllib.parse
import aiohttp
from datetime import datetime

from ai_service import get_ai_service
from tts_service import get_tts_service
from external_api_service import ExternalAPIService
from db_service import get_db_service
from conversation_service import get_conversation_service
from matching_service import get_matching_service
from subscription_service import get_subscription_service
from session_service import get_session_service
from intent_classifier import get_classifier
from direct_responses import get_direct_response
from voice_analysis_service import get_voice_analysis_service
from personality_service import get_personality_service
from config import WEBSOCKET_PORT, WEBSOCKET_HOST, EXPERTS, SESSION_CATEGORIES, SOCIAL_API_URL

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="MeetVoice API", version="3.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

ai_service = None
tts_service = None
api_service = None
db_service = None
conversation_service = None
matching_service = None
subscription_service = None
session_service = None
intent_classifier = None
embedding_model = None
voice_analysis_service = None
personality_service = None


@app.on_event("startup")
async def startup_event():
    global ai_service, tts_service, api_service, db_service
    global conversation_service, matching_service, subscription_service
    global session_service, intent_classifier, embedding_model
    global voice_analysis_service, personality_service

    logger.info("Initialisation des services...")

    logger.info("Chargement CamemBERT (instance unique)...")
    from sentence_transformers import SentenceTransformer
    embedding_model = SentenceTransformer('dangvantuan/sentence-camembert-base')
    logger.info("CamemBERT charge (768 dims)")

    logger.info("Initialisation classifier ML (SVM + LR)...")
    intent_classifier = get_classifier(embedding_model)

    ai_service = get_ai_service()
    tts_service = get_tts_service()
    api_service = ExternalAPIService()
    db_service = get_db_service()
    conversation_service = get_conversation_service()
    matching_service = get_matching_service()
    subscription_service = get_subscription_service()
    session_service = get_session_service(embedding_model)

    ai_service.set_api_service(api_service)

    voice_analysis_service = get_voice_analysis_service()
    personality_service = get_personality_service()
    logger.info("Services voice_analysis + personality initialises")

    logger.info("Pre-generation TTS (welcomes + reponses directes)...")
    await tts_service.prewarm_cache()

    logger.info("Tous les services prets!")


@app.on_event("shutdown")
async def shutdown_event():
    logger.info("Shutdown...")
    if api_service:
        await api_service.close()
    if ai_service:
        await ai_service.close()
    if matching_service:
        await matching_service.close()
    if session_service:
        await session_service.close()
    if subscription_service:
        await subscription_service.close()
    if voice_analysis_service:
        await voice_analysis_service.close()
    if personality_service:
        await personality_service.close()
    logger.info("Shutdown complete")


class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []
        self.contexts: Dict[WebSocket, Dict] = {}

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)
        self.contexts[websocket] = {
            "current_expert": None,
            "user_id": None,
            "last_search_results": None,
            "last_search_type": None,
            "conversation_history": [],
            "pending_message": None,
            "target_profile": None,
            "emotion_state": None,
        }

    def disconnect(self, websocket: WebSocket):
        ctx = self.contexts.get(websocket, {})
        uid = ctx.get("user_id")
        expert = ctx.get("current_expert")
        if uid and expert:
            _save_expert_memory(uid, expert)
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)
        self.contexts.pop(websocket, None)

    async def send(self, ws: WebSocket, msg: dict):
        await ws.send_text(json.dumps(msg, ensure_ascii=False))

    def ctx(self, ws: WebSocket) -> Dict:
        return self.contexts.get(ws, {})

    def set_ctx(self, ws: WebSocket, key: str, value):
        if ws in self.contexts:
            self.contexts[ws][key] = value


manager = ConnectionManager()

EXPERT_MEMORY_HOURS = 12
_user_expert_memory: Dict[int, Dict] = {}


def _save_expert_memory(user_id: int, expert_id: str):
    if expert_id and expert_id != "general":
        _user_expert_memory[user_id] = {
            "expert_id": expert_id,
            "activated_at": datetime.now(),
        }
    elif user_id in _user_expert_memory:
        del _user_expert_memory[user_id]


def _get_remembered_expert(user_id: int) -> Optional[str]:
    mem = _user_expert_memory.get(user_id)
    if not mem:
        return None
    from datetime import timedelta
    if datetime.now() - mem["activated_at"] > timedelta(hours=EXPERT_MEMORY_HOURS):
        del _user_expert_memory[user_id]
        return None
    return mem["expert_id"]


# ===== HELPERS =====

def parse_message(data: str) -> tuple:
    try:
        msg = json.loads(data)
        return (
            msg.get("message", data),
            msg.get("expert", None),
            msg.get("user_id", 1),
            msg.get("profile", None),
            msg.get("audio_data", None),
            msg.get("audio_format", "webm"),
        )
    except (json.JSONDecodeError, AttributeError):
        return data, None, 1, None, None, "webm"


async def check_sub_limit(user_id: int, ws: WebSocket) -> bool:
    can_send, error_msg = await subscription_service.check_can_send_message(user_id)
    if not can_send:
        await manager.send(ws, {"type": "subscription_limit", "message": error_msg})
    return can_send


def save_to_history(ws: WebSocket, user_msg: str, bot_msg: str, intention: str, score: float):
    ctx = manager.ctx(ws)
    conversation_service.add_to_history(ctx, user_msg, bot_msg, intention, {"score": score})


async def handle_api_search(intention: str, query: str) -> tuple:
    try:
        if intention == "recherche_evenement":
            city = "Paris"
            for c in ["lyon", "marseille", "toulouse", "nice", "nantes", "bordeaux"]:
                if c in query.lower():
                    city = c.capitalize()
                    break
            results = await api_service.search_events(city=city, limit=5)
            return api_service.format_events_response(results), results, "events"

        elif intention == "recherche_cinema":
            results = await api_service.search_movies(limit=5)
            return api_service.format_movies_response(results), results, "movies"

        elif intention == "recherche_musique":
            artist = ""
            if "de " in query.lower():
                parts = query.lower().split("de ")
                if len(parts) > 1:
                    artist = parts[-1].strip()
            results = await api_service.search_music(artist=artist, limit=5)
            return api_service.format_music_response(results), results, "music"

        elif intention == "recherche_video":
            results = await api_service.search_videos(query, limit=5)
            return api_service.format_videos_response(results), results, "videos"

    except Exception as e:
        logger.error(f"API search error: {e}")

    return "Desole, la recherche n'a pas fonctionne.", None, None


def handle_followup(query: str, ws: WebSocket) -> str:
    ctx = manager.ctx(ws)
    last_results = ctx.get("last_search_results")
    last_type = ctx.get("last_search_type")

    if not last_results or not last_type:
        return "J'ai pas de resultats precedents. Tu veux que je cherche quelque chose ?"

    query_lower = query.lower()
    item_idx = -1

    number_match = re.search(
        r'(\d+|premier|deuxieme|troisieme|quatrieme|cinquieme|1er|2eme|3eme|4eme|5eme|second)',
        query_lower
    )
    if number_match:
        item_idx = conversation_service._parse_number(number_match.group(1))

    if item_idx == -1:
        for idx, item in enumerate(last_results):
            for key in ("name", "title", "artist"):
                if key in item and any(w in item[key].lower() for w in query_lower.split() if len(w) > 3):
                    item_idx = idx
                    break
            if item_idx != -1:
                break

    if item_idx == -1 or item_idx >= len(last_results):
        return "J'ai pas trouve cet element. Donne-moi le numero ?"

    item = last_results[item_idx]
    return format_item_details(item, last_type, item_idx + 1)


def format_item_details(item: dict, search_type: str, position: int) -> str:
    if search_type == "events":
        return (f"**{item.get('name', 'N/A')}**\n"
                f"Date: {item.get('date', 'N/A')}\n"
                f"Lieu: {item.get('venue', 'N/A')}\n"
                f"Lien: {item.get('url', 'N/A')}")
    elif search_type == "movies":
        return (f"**{item.get('title', 'N/A')}**\n"
                f"Note: {item.get('rating', 'N/A')}/10\n"
                f"Sortie: {item.get('release_date', 'N/A')}\n"
                f"{item.get('overview', 'N/A')}")
    elif search_type == "music":
        return (f"**{item.get('title', 'N/A')}** - {item.get('artist', 'N/A')}\n"
                f"Album: {item.get('album', 'N/A')}\n"
                f"Lien: {item.get('link', 'N/A')}")
    elif search_type == "videos":
        return (f"**{item.get('title', 'N/A')}**\n"
                f"Chaine: {item.get('channel', 'N/A')}\n"
                f"Lien: {item.get('url', 'N/A')}")
    return "Details non disponibles"


# ===== EXPERT STREAMING + PARALLEL TTS =====

async def stream_expert_with_tts(ws: WebSocket, user_message: str, expert_id: str, user_id: int, intention: str, score: float):
    expert_info = EXPERTS.get(expert_id, EXPERTS["general"])
    category = expert_info.get("category", "general")

    session_id = None
    if category in SESSION_CATEGORIES:
        session_id = await session_service.get_or_create_session(user_id, expert_id, category)

    recent_history, similar_history = None, None
    if session_id:
        recent_history, similar_history = await session_service.get_contextual_history(
            session_id, user_message, max_results=5
        )

    profile = manager.ctx(ws).get("profile")

    emotion_ctx = ""
    emotion_state = manager.ctx(ws).get("emotion_state")
    if emotion_state:
        emotion_ctx = voice_analysis_service.emotion_to_context(emotion_state)
    try:
        personality_ctx = personality_service.personality_to_context(
            await personality_service.get_personality(user_id)
        )
    except Exception:
        personality_ctx = ""

    enriched_message = user_message
    if emotion_ctx or personality_ctx:
        enriched_message = user_message + "\n\n" + "\n".join(filter(None, [emotion_ctx, personality_ctx]))

    full_response = ""
    async for token in ai_service.generate_response_stream(
        enriched_message, expert_id, user_id,
        recent_history=recent_history,
        similar_history=similar_history,
        user_profile=profile
    ):
        full_response += token

    logger.info(f"[DEBUG] full_response ({len(full_response)} chars): {full_response[:200]!r}")

    image_url = None
    image_match = re.search(r'\[IMAGE:\s*(.+?)\]', full_response, re.IGNORECASE | re.DOTALL)
    if image_match:
        image_prompt = image_match.group(1).strip()
        full_response = re.sub(r'\s*\[IMAGE:\s*.+?\]\s*', '', full_response, flags=re.IGNORECASE | re.DOTALL).strip()
        encoded_prompt = urllib.parse.quote(image_prompt)
        image_url = f"https://image.pollinations.ai/prompt/{encoded_prompt}?width=768&height=512&nologo=true&model=flux&seed=42"
        logger.info(f"[IMAGE] Generated URL for prompt: {image_prompt[:60]}...")

    audio = await tts_service.text_to_speech_base64(full_response, expert_id)

    if session_id:
        asyncio.create_task(session_service.add_exchange(
            session_id=session_id,
            user_message=user_message,
            assistant_response=full_response,
            expert_id=expert_id,
            tokens_used=len(full_response) // 4
        ))

    asyncio.create_task(subscription_service.increment_usage(user_id, tokens_used=len(full_response) // 4))

    payload = {
        "type": "stream_end",
        "message": full_response,
        "expert": {"id": expert_id, "name": expert_info['name'], "voice": expert_info['voice']},
        "intention": intention,
        "score": score,
        "audio": audio
    }
    if image_url:
        payload["image_url"] = image_url
    if emotion_state:
        payload["emotion"] = {
            "emotion": emotion_state.get("emotion"),
            "label": emotion_state.get("emotion_label"),
            "confidence": emotion_state.get("confidence"),
        }

    await manager.send(ws, payload)

    save_to_history(ws, user_message, full_response, intention, score)


# ===== DIRECT RESPONSE + TTS =====

_TTS_SEARCH_INTROS = {
    "recherche_video": "Voici les vidéos que j'ai trouvées.",
    "recherche_cinema": "Voici les films à l'affiche.",
    "recherche_musique": "Voici les titres que j'ai trouvés.",
    "recherche_evenement": "Voici les événements que j'ai trouvés.",
    "recherche_profil": "Voici les profils que j'ai trouvés.",
    "compatibilite": "Voici l'analyse de compatibilité.",
    "review_profil": "Voici mes conseils pour ton profil.",
}


async def send_direct_with_tts(ws: WebSocket, text: str, intention: str, score: float, expert_id: str = None, tts_override: str = None, extra: dict = None):
    speak_raw = tts_override or _TTS_SEARCH_INTROS.get(intention) or text
    first_line = speak_raw.split("\n")[0].strip()
    speak = first_line[:200] if len(first_line) > 200 else first_line
    tts_task = asyncio.create_task(
        tts_service.text_to_speech_base64(speak, expert_id or "general")
    )

    await manager.send(ws, {
        "type": "stream",
        "token": text,
        "expert": {"id": expert_id or "general"}
    })

    audio_base64 = await tts_task

    payload = {
        "type": "stream_end",
        "message": text,
        "intention": intention,
        "score": score,
        "audio": audio_base64,
        "expert": {"id": expert_id or "general"}
    }
    if extra:
        payload.update(extra)
    await manager.send(ws, payload)


# ===== HELPERS PROFILES =====

def _build_profiles_payload(matches: list) -> list:
    profiles = []
    for p in matches:
        profiles.append({
            "user_id": p.get("id", ""),
            "prenom": p.get("prenom", "Anonyme"),
            "age": p.get("age"),
            "ville": p.get("ville", ""),
            "cheveux": (p.get("hair_color") or "").lower(),
            "yeux": (p.get("yeux") or "").lower(),
            "bio": p.get("bio") or "",
            "photo_url": p.get("thumbnail") or "",
        })
    return profiles


# ===== HELPERS MESSAGING + ICEBREAKER =====

async def _fetch_target_posts(target: dict) -> list:
    username = target.get("prenom")
    if not username:
        return []
    try:
        return await matching_service.fetch_user_posts(username, limit=5)
    except Exception as e:
        logger.warning(f"Fetch posts for {username}: {e}")
        return []


async def _generate_icebreaker_single(target: dict, user_profile: dict = None, posts: list = None) -> str:
    profile_ctx = matching_service.profile_to_context(target, posts=posts)
    prompt = (
        f"Génère UN SEUL premier message de drague pour {target.get('prenom', '?')}.\n"
        f"Profil : {profile_ctx}\n"
        f"Le message doit être court (1-2 phrases), naturel, personnalisé selon le profil. "
        f"Pas de 'Salut ça va ?'. Réponds UNIQUEMENT avec le message, sans guillemets ni explication."
    )
    response = ""
    async for token in ai_service.generate_response_stream(prompt, "seduction"):
        response += token
    return response.strip().strip('"').strip("«").strip("»").strip()


async def _handle_send_confirm(ws, pending: dict, uid, user_message: str) -> str:
    q = user_message.lower().strip()
    if q in ("oui", "ouais", "ok", "yes", "yep", "vas-y", "envoie", "go", "carrément", "confirme"):
        ok = await matching_service.send_message(
            from_id=str(uid),
            to_id=pending["to_id"],
            message=pending["message"],
        )
        manager.set_ctx(ws, "pending_message", None)
        if ok:
            return f"Message envoyé à {pending['to_name']} ! Bonne chance !"
        else:
            return f"Oups, l'envoi a échoué. Réessaie plus tard."
    else:
        manager.set_ctx(ws, "pending_message", None)
        return "OK, message annulé. Tu veux que j'en propose un autre ?"


# ===== SMART NAME INTERCEPTOR =====

_DB_AWARE_INTENTS = {
    "recherche_profil", "recherche_par_nom", "envoyer_message",
    "coaching_contextuel", "icebreaker", "compatibilite", "review_profil",
    "creer_post",
}

POST_CATEGORIES = {"général": "general", "general": "general", "amical": "amical", "libertin": "libertin", "amour": "amour"}


async def _publish_post(author_id: str, username: str, avatar: str, titre: str, text: str, category: str, image: str = None) -> bool:
    payload = {
        "titre": titre,
        "text": text,
        "category": category,
        "author_id": author_id,
        "username": username,
        "avatar": avatar,
    }
    if image:
        payload["image"] = image
    try:
        async with aiohttp.ClientSession() as sess:
            async with sess.post(SOCIAL_API_URL, json=payload, timeout=aiohttp.ClientTimeout(total=15)) as resp:
                ok = resp.status in (200, 201)
                if not ok:
                    body = await resp.text()
                    logger.error(f"Social post error {resp.status}: {body}")
                return ok
    except Exception as e:
        logger.error(f"Social post error: {e}")
        return False


async def _smart_name_intercept(ws, user_message: str, user_id, intention: str, score: float, expert_id: str) -> bool:
    if intention in _DB_AWARE_INTENTS:
        return False

    name = matching_service.parse_name_from_query(user_message)
    if not name:
        return False

    ctx = manager.ctx(ws)
    uid = ctx.get("user_id", user_id)

    try:
        matches = await matching_service.search_by_name(name, user_id=uid, limit=5)
    except Exception as e:
        logger.error(f"Smart name intercept DB error: {e}")
        return False

    if not matches:
        return False

    logger.info(f"Smart name intercept: found {len(matches)} profile(s) for '{name}'")

    target = matches[0]
    try:
        full_target = await matching_service.get_full_profile(target["id"])
        if full_target:
            manager.set_ctx(ws, "target_profile", full_target)
            target = full_target
    except Exception:
        manager.set_ctx(ws, "target_profile", target)

    manager.set_ctx(ws, "last_search_results", matches)
    manager.set_ctx(ws, "last_search_type", "profiles")

    prenom = target.get("prenom", name)
    age = target.get("age", "")
    ville = target.get("ville", "")
    bio = target.get("bio", "")

    age_str = f", {age} ans" if age else ""
    ville_str = f" à {ville}" if ville else ""
    bio_str = f"\n📝 Bio : {bio}" if bio else ""

    user_profile = ctx.get("profile")
    target_posts = await _fetch_target_posts(target)
    try:
        msg_text = await _generate_icebreaker_single(target, user_profile, posts=target_posts)
    except Exception as e:
        logger.error(f"Smart intercept icebreaker error: {e}")
        msg_text = None

    if msg_text:
        manager.set_ctx(ws, "pending_message", {
            "to_id": target["id"],
            "to_name": prenom,
            "message": msg_text,
        })

    if len(matches) == 1:
        if msg_text:
            response = (
                f"J'ai trouvé {prenom}{age_str}{ville_str} sur la plateforme !{bio_str}\n\n"
                f"J'ai rédigé un premier message pour toi :\n\n"
                f"\"{msg_text}\"\n\n"
                f"Tu veux que je lui envoie ? (oui/non)"
            )
        else:
            response = (
                f"J'ai trouvé {prenom}{age_str}{ville_str} sur la plateforme !{bio_str}\n\n"
                f"Tu veux que je lui rédige un premier message de ta part ?"
            )
    else:
        if msg_text:
            response = (
                f"J'ai trouvé {len(matches)} profils pour \"{name}\" !\n"
                f"Voici le premier : {prenom}{age_str}{ville_str}{bio_str}\n\n"
                f"J'ai préparé un message pour {prenom} :\n\n"
                f"\"{msg_text}\"\n\n"
                f"Tu veux que je lui envoie ? (oui/non)"
            )
        else:
            response = (
                f"J'ai trouvé {len(matches)} profils pour \"{name}\" !\n"
                f"Voici le premier : {prenom}{age_str}{ville_str}{bio_str}\n\n"
                f"Tu veux que je rédige un premier message pour {prenom} ?"
            )

    extra = {"profiles": _build_profiles_payload(matches)}
    await send_direct_with_tts(ws, response, "recherche_par_nom", score, expert_id, extra=extra)
    save_to_history(ws, user_message, response, "recherche_par_nom", score)
    return True


# ===== MAIN ROUTER (single function for all WS) =====

async def route_message(ws: WebSocket, user_message: str, force_expert: str, user_id: int):
    intent_result = intent_classifier.classify(user_message)
    intention = intent_result['intention']
    score = intent_result['score']
    logger.info(f"Intent: {intention} ({score:.0%}) [{intent_result['method']}]")

    ctx = manager.ctx(ws)
    current_expert = ctx.get("current_expert")
    expert_id = force_expert or current_expert

    if not force_expert and current_expert == "general":
        today = datetime.now().date().isoformat()
        if ctx.get("last_greeted_date") != today:
            profile = ctx.get("profile")
            prenom = profile.get("prenom") if profile else None
            _greet = random.choice(["Salut", "Coucou", "Bonjour"])
            greeting = f"{_greet} {prenom} !" if prenom else f"{_greet} !"
            g_audio = await tts_service.text_to_speech_base64(greeting, "general")
            await manager.send(ws, {
                "type": "stream_end",
                "message": greeting,
                "expert": {"id": "general", "name": EXPERTS["general"]["name"], "voice": EXPERTS["general"]["voice"]},
                "intention": "salutation",
                "score": 1.0,
                "audio": g_audio
            })
            manager.set_ctx(ws, "last_greeted_date", today)

    if intention == "question_suivi":
        response = handle_followup(user_message, ws)
        await send_direct_with_tts(ws, response, intention, score, expert_id)
        save_to_history(ws, user_message, response, intention, score)
        return

    pending_post = ctx.get("pending_post")
    if pending_post and intention != "creer_post":
        step = pending_post.get("step")
        q = user_message.strip().lower()

        if q in ("annule", "annuler", "stop", "non", "laisse tomber"):
            manager.set_ctx(ws, "pending_post", None)
            response = "Publication annulée !"
            await send_direct_with_tts(ws, response, "creer_post", score, expert_id)
            save_to_history(ws, user_message, response, "creer_post", score)
            return

        if step == "wait_image_prompt":
            if q in ("non", "pas d'image", "sans image", "aucune", "skip", "passer"):
                pending_post["image"] = None
                pending_post["step"] = "wait_description"
                manager.set_ctx(ws, "pending_post", pending_post)
                response = "Pas de souci, pas d'image ! Maintenant, écris la description de ton post (je l'améliorerai pour toi) :"
            else:
                await send_direct_with_tts(ws, "Je génère ton image, patiente quelques secondes...", "creer_post", score, expert_id)
                image_b64 = await ai_service.generate_image(user_message)
                if image_b64:
                    pending_post["image"] = image_b64
                    pending_post["image_prompt"] = user_message
                    pending_post["step"] = "wait_description"
                    manager.set_ctx(ws, "pending_post", pending_post)
                    response = "Image générée ! Maintenant, écris la description de ton post (je l'améliorerai pour toi) :"
                    extra = {"post_image_preview": image_b64}
                    await send_direct_with_tts(ws, response, "creer_post", score, expert_id, extra=extra)
                    save_to_history(ws, user_message, response, "creer_post", score)
                    return
                else:
                    response = "Désolé, la génération d'image a échoué. Réessaie avec une autre description, ou écris \"sans image\" pour continuer sans :"
            await send_direct_with_tts(ws, response, "creer_post", score, expert_id)
            save_to_history(ws, user_message, response, "creer_post", score)
            return

        if step == "wait_description":
            improved = await ai_service.improve_post_text(user_message)
            pending_post["titre"] = ""
            pending_post["text_original"] = user_message
            pending_post["text"] = improved
            pending_post["step"] = "wait_category"
            manager.set_ctx(ws, "pending_post", pending_post)
            response = (
                f"Voici ta description améliorée :\n\n\"{improved}\"\n\n"
                f"Choisis la catégorie du post :\n"
                f"• Général\n• Amical\n• Amour\n• Libertin"
            )
            await send_direct_with_tts(ws, response, "creer_post", score, expert_id)
            save_to_history(ws, user_message, response, "creer_post", score)
            return

        if step == "wait_category":
            cat = POST_CATEGORIES.get(q)
            if not cat:
                for key, val in POST_CATEGORIES.items():
                    if key in q:
                        cat = val
                        break
            if not cat:
                response = "Je n'ai pas compris la catégorie. Choisis parmi : Général, Amical, Amour, Libertin"
                await send_direct_with_tts(ws, response, "creer_post", score, expert_id)
                save_to_history(ws, user_message, response, "creer_post", score)
                return
            pending_post["category"] = cat
            pending_post["step"] = "wait_confirm"
            manager.set_ctx(ws, "pending_post", pending_post)
            img_str = "avec image" if pending_post.get("image") else "sans image"
            response = (
                f"Récapitulatif de ton post ({img_str}) :\n\n"
                f"Catégorie : {cat.capitalize()}\n"
                f"Texte : \"{pending_post['text']}\"\n\n"
                f"Tu confirmes la publication ? (oui/non)"
            )
            await send_direct_with_tts(ws, response, "creer_post", score, expert_id)
            save_to_history(ws, user_message, response, "creer_post", score)
            return

        if step == "wait_confirm":
            if q in ("oui", "ouais", "ok", "yes", "yep", "vas-y", "go", "confirme", "publie", "carrément"):
                uid = str(ctx.get("user_id", user_id))
                profile = ctx.get("profile") or {}
                username = profile.get("prenom", "Utilisateur")
                avatar = profile.get("avatar") or profile.get("thumbnail") or ""
                ok = await _publish_post(
                    author_id=uid,
                    username=username,
                    avatar=avatar,
                    titre=pending_post.get("titre", ""),
                    text=pending_post["text"],
                    category=pending_post["category"],
                    image=pending_post.get("image"),
                )
                manager.set_ctx(ws, "pending_post", None)
                if ok:
                    response = "Ton post a été publié avec succès sur MeetVoice ! 🎉"
                else:
                    response = "Oups, la publication a échoué. Réessaie plus tard."
            else:
                manager.set_ctx(ws, "pending_post", None)
                response = "Publication annulée. Tu peux recommencer quand tu veux !"
            await send_direct_with_tts(ws, response, "creer_post", score, expert_id)
            save_to_history(ws, user_message, response, "creer_post", score)
            return

    _CONTACT_KEYWORDS = {
        "contact", "contacter", "parler", "écrire", "message", "envoie",
        "envoyer", "dire", "aborder", "draguer", "séduire", "lui",
        "elle", "intéresse", "intéressé", "intéressée",
    }
    target_in_ctx = ctx.get("target_profile")
    if target_in_ctx and intention not in _DB_AWARE_INTENTS:
        words_set = set(user_message.lower().split())
        if words_set & _CONTACT_KEYWORDS:
            prenom = target_in_ctx.get("prenom", "?")
            target_posts = await _fetch_target_posts(target_in_ctx)
            user_profile = ctx.get("profile")
            msg_text = None
            try:
                msg_text = await _generate_icebreaker_single(target_in_ctx, user_profile, posts=target_posts)
            except Exception as e:
                logger.error(f"Context contact icebreaker error: {e}")
            if msg_text:
                manager.set_ctx(ws, "pending_message", {
                    "to_id": target_in_ctx["id"],
                    "to_name": prenom,
                    "message": msg_text,
                })
                response = (
                    f"J'ai préparé un message pour {prenom} :\n\n"
                    f"\"{msg_text}\"\n\n"
                    f"Tu veux que je lui envoie ? (oui/non)"
                )
            else:
                response = f"Je vais t'aider à contacter {prenom} ! Que veux-tu lui dire ?"
            await send_direct_with_tts(ws, response, "envoyer_message", score, expert_id)
            save_to_history(ws, user_message, response, "envoyer_message", score)
            return

    intercepted = await _smart_name_intercept(ws, user_message, user_id, intention, score, expert_id)
    if intercepted:
        return

    if intention == "recherche_profil":
        uid = ctx.get("user_id", user_id)
        criteria = matching_service.parse_search_criteria(user_message)
        try:
            matches = await matching_service.search_profiles(criteria, user_id=uid, limit=10)
        except Exception as e:
            logger.error(f"Profile search error: {e}")
            matches = []
        response = matching_service.format_matches_response(matches)
        manager.set_ctx(ws, "last_search_results", matches)
        manager.set_ctx(ws, "last_search_type", "profiles")
        extra = {"profiles": _build_profiles_payload(matches)} if matches else None
        await send_direct_with_tts(ws, response, intention, score, expert_id, extra=extra)
        save_to_history(ws, user_message, response, intention, score)
        return

    if intention == "recherche_par_nom":
        uid = ctx.get("user_id", user_id)
        name = matching_service.parse_name_from_query(user_message)
        matches = []
        if name:
            try:
                matches = await matching_service.search_by_name(name, user_id=uid, limit=5)
            except Exception as e:
                logger.error(f"Name search error: {e}")
                matches = []
            if matches:
                target = matches[0]
                try:
                    full_target = await matching_service.get_full_profile(target["id"])
                    if full_target:
                        target = full_target
                except Exception:
                    pass
                manager.set_ctx(ws, "target_profile", target)
                manager.set_ctx(ws, "last_search_results", matches)
                manager.set_ctx(ws, "last_search_type", "profiles")

                prenom = target.get("prenom", name)
                age = target.get("age", "")
                ville = target.get("ville", "")
                bio = target.get("bio", "")
                age_str = f", {age} ans" if age else ""
                ville_str = f" à {ville}" if ville else ""
                bio_str = f"\n📝 Bio : {bio}" if bio else ""

                user_profile = ctx.get("profile")
                target_posts = await _fetch_target_posts(target)
                try:
                    msg_text = await _generate_icebreaker_single(target, user_profile, posts=target_posts)
                except Exception:
                    msg_text = None

                if msg_text:
                    manager.set_ctx(ws, "pending_message", {
                        "to_id": target["id"],
                        "to_name": prenom,
                        "message": msg_text,
                    })
                    response = (
                        f"J'ai trouvé {prenom}{age_str}{ville_str} !{bio_str}\n\n"
                        f"J'ai rédigé un premier message pour toi :\n\n"
                        f"\"{msg_text}\"\n\n"
                        f"Tu veux que je lui envoie ? (oui/non)"
                    )
                else:
                    response = matching_service.format_matches_response(matches, name_search=True)
            else:
                response = f"Je n'ai trouvé personne qui s'appelle {name} sur la plateforme."
        else:
            response = "Dis-moi le prénom de la personne que tu cherches !"
        extra = {"profiles": _build_profiles_payload(matches)} if matches else None
        await send_direct_with_tts(ws, response, intention, score, expert_id, extra=extra)
        save_to_history(ws, user_message, response, intention, score)
        return

    if intention == "envoyer_message":
        uid = ctx.get("user_id", user_id)
        pending = ctx.get("pending_message")

        if pending:
            response = await _handle_send_confirm(ws, pending, uid, user_message)
            await send_direct_with_tts(ws, response, intention, score, expert_id)
            save_to_history(ws, user_message, response, intention, score)
            return

        target = ctx.get("target_profile")
        last_results = ctx.get("last_search_results") or []
        name = matching_service.parse_name_from_query(user_message)

        if not target and name:
            try:
                results = await matching_service.search_by_name(name, user_id=uid, limit=1)
                if results:
                    target = await matching_service.get_full_profile(results[0]["id"])
            except Exception as e:
                logger.error(f"Profile lookup error: {e}")

        if not target and last_results:
            first = last_results[0]
            try:
                target = await matching_service.get_full_profile(first["id"])
            except Exception:
                target = first

        if target:
            manager.set_ctx(ws, "target_profile", target)
            user_profile = ctx.get("profile")
            target_posts = await _fetch_target_posts(target)
            msg_text = await _generate_icebreaker_single(target, user_profile, posts=target_posts)
            manager.set_ctx(ws, "pending_message", {
                "to_id": target["id"],
                "to_name": target.get("prenom", "?"),
                "message": msg_text,
            })
            response = (
                f"Je te propose d'envoyer ce message à {target.get('prenom', '?')} :\n\n"
                f"\"{msg_text}\"\n\n"
                f"Tu veux que je l'envoie ? (oui/non)"
            )
            await send_direct_with_tts(ws, response, intention, score, expert_id)
            save_to_history(ws, user_message, response, intention, score)
            return

    if intention == "affirmatif" and ctx.get("pending_message"):
        pending = ctx.get("pending_message")
        uid = ctx.get("user_id", user_id)
        response = await _handle_send_confirm(ws, pending, uid, "oui")
        await send_direct_with_tts(ws, response, "envoyer_message", score, expert_id)
        save_to_history(ws, user_message, response, "envoyer_message", score)
        return

    if intention == "negatif" and ctx.get("pending_message"):
        manager.set_ctx(ws, "pending_message", None)
        response = "Pas de souci, le message n'a pas été envoyé. Tu veux que j'en propose un autre ?"
        await send_direct_with_tts(ws, response, "envoyer_message", score, expert_id)
        save_to_history(ws, user_message, response, "envoyer_message", score)
        return

    if intention == "coaching_contextuel":
        uid = ctx.get("user_id", user_id)
        target = ctx.get("target_profile")
        name = matching_service.parse_name_from_query(user_message)

        if not target and name:
            try:
                results = await matching_service.search_by_name(name, user_id=uid, limit=1)
                if results:
                    target = await matching_service.get_full_profile(results[0]["id"])
                    manager.set_ctx(ws, "target_profile", target)
            except Exception as e:
                logger.error(f"Coaching profile lookup: {e}")

        if not target:
            last_results = ctx.get("last_search_results") or []
            if last_results:
                try:
                    target = await matching_service.get_full_profile(last_results[0]["id"])
                    manager.set_ctx(ws, "target_profile", target)
                except Exception:
                    pass

        if target:
            target_posts = await _fetch_target_posts(target)
            profile_ctx = matching_service.profile_to_context(target, posts=target_posts)
            user_profile = ctx.get("profile")
            coaching_prompt = (
                f"L'utilisateur veut des conseils pour aborder {target.get('prenom', '?')}.\n"
                f"Voici le profil de {target.get('prenom', '?')} :\n{profile_ctx}\n\n"
                f"Message de l'utilisateur : {user_message}\n\n"
                f"Donne des conseils personnalisés basés sur le profil ET ses posts récents : "
                f"points d'accroche, sujets de conversation, erreurs à éviter. Sois concret et actionnable."
            )
            if not await check_sub_limit(user_id, ws):
                return
            manager.set_ctx(ws, "current_expert", "seduction")
            await stream_expert_with_tts(ws, coaching_prompt, "seduction", user_id, intention, score)
            return

    if intention == "icebreaker":
        uid = ctx.get("user_id", user_id)
        target = ctx.get("target_profile")
        name = matching_service.parse_name_from_query(user_message)

        if not target and name:
            try:
                results = await matching_service.search_by_name(name, user_id=uid, limit=1)
                if results:
                    target = await matching_service.get_full_profile(results[0]["id"])
                    manager.set_ctx(ws, "target_profile", target)
            except Exception as e:
                logger.error(f"Icebreaker profile lookup: {e}")

        if not target:
            last_results = ctx.get("last_search_results") or []
            if last_results:
                try:
                    target = await matching_service.get_full_profile(last_results[0]["id"])
                    manager.set_ctx(ws, "target_profile", target)
                except Exception:
                    pass

        if target:
            target_posts = await _fetch_target_posts(target)
            profile_ctx = matching_service.profile_to_context(target, posts=target_posts)
            user_profile = ctx.get("profile")
            icebreaker_prompt = (
                f"L'utilisateur veut des idées de premier message pour {target.get('prenom', '?')}.\n"
                f"Voici le profil de {target.get('prenom', '?')} :\n{profile_ctx}\n\n"
                f"Propose exactement 3 premiers messages différents, personnalisés selon le profil et ses posts. "
                f"Chaque message doit être basé sur un intérêt commun ou un détail du profil. "
                f"Numérote-les 1, 2, 3. Sois naturel, pas générique."
            )
            if not await check_sub_limit(user_id, ws):
                return
            manager.set_ctx(ws, "current_expert", "seduction")
            await stream_expert_with_tts(ws, icebreaker_prompt, "seduction", user_id, intention, score)
            return

    if intention == "compatibilite":
        uid = str(ctx.get("user_id", user_id))
        target = ctx.get("target_profile")
        name = matching_service.parse_name_from_query(user_message)

        if not target and name:
            try:
                results = await matching_service.search_by_name(name, user_id=uid, limit=1)
                if results:
                    target = await matching_service.get_full_profile(results[0]["id"])
                    manager.set_ctx(ws, "target_profile", target)
            except Exception as e:
                logger.error(f"Compat profile lookup: {e}")

        if not target:
            last_results = ctx.get("last_search_results") or []
            if last_results:
                try:
                    target = await matching_service.get_full_profile(last_results[0]["id"])
                    manager.set_ctx(ws, "target_profile", target)
                except Exception:
                    pass

        if target:
            try:
                user_full = await matching_service.get_full_profile(uid)
            except Exception:
                user_full = None

            if user_full:
                compat = matching_service.compute_compatibility(user_full, target)
                response = matching_service.format_compatibility(user_full, target, compat)
            else:
                response = (
                    f"Je n'ai pas trouvé ton profil pour comparer. "
                    f"Assure-toi d'être connecté avec ton compte MeetVoice !"
                )
        else:
            response = "Avec qui veux-tu tester ta compatibilité ? Cherche un profil d'abord !"

        await send_direct_with_tts(ws, response, intention, score, expert_id)
        save_to_history(ws, user_message, response, intention, score)
        return

    if intention == "review_profil":
        uid = str(ctx.get("user_id", user_id))
        try:
            user_full = await matching_service.get_full_profile(uid)
        except Exception as e:
            logger.error(f"Review profile lookup: {e}")
            user_full = None

        if user_full:
            profile_ctx = matching_service.profile_to_context(user_full)
            review_prompt = (
                f"L'utilisateur veut améliorer son profil de rencontre.\n"
                f"Voici son profil actuel :\n{profile_ctx}\n\n"
                f"Analyse le profil et donne des conseils concrets pour l'améliorer :\n"
                f"- La bio (est-elle accrocheuse, originale ?)\n"
                f"- Les photos (conseil général)\n"
                f"- Les centres d'intérêt (assez variés ?)\n"
                f"- Ce qui manque\n"
                f"- Ce qui est bien\n"
                f"Sois honnête mais bienveillant. Donne des exemples de bio améliorée si besoin."
            )
            if not await check_sub_limit(user_id, ws):
                return
            manager.set_ctx(ws, "current_expert", "seduction")
            await stream_expert_with_tts(ws, review_prompt, "seduction", user_id, intention, score)
        else:
            response = "Je n'ai pas trouvé ton profil. Tu es bien connecté avec ton compte MeetVoice ?"
            await send_direct_with_tts(ws, response, intention, score, expert_id)
            save_to_history(ws, user_message, response, intention, score)
        return

    if intention == "creer_post":
        manager.set_ctx(ws, "pending_post", {"step": "wait_image_prompt"})
        response = (
            "Super, on va créer ton post ! 🎨\n\n"
            "D'abord, tu veux une image ? Décris-moi ce que tu veux voir "
            "(ex: \"un coucher de soleil sur la plage\", \"un café cosy parisien\").\n\n"
            "Ou écris \"sans image\" pour un post texte uniquement."
        )
        await send_direct_with_tts(ws, response, intention, score, expert_id)
        save_to_history(ws, user_message, response, intention, score)
        return

    if intention == "comparer":
        last_results = ctx.get("last_search_results")
        last_type = ctx.get("last_search_type")
        if last_results and len(last_results) >= 2:
            items = conversation_service.parse_comparison_request(user_message, last_results)
            if items:
                response = conversation_service.compare_items(items[0], items[1], last_type)
            else:
                response = "Dis-moi lesquels tu veux comparer, genre 'compare le 1 et le 2'"
        else:
            response = "J'ai rien a comparer. Fais une recherche d'abord !"
        await send_direct_with_tts(ws, response, intention, score, expert_id)
        save_to_history(ws, user_message, response, intention, score)
        return

    if intention == "rappel_historique":
        response = conversation_service.get_history_summary(ctx, limit=5)
        await send_direct_with_tts(ws, response, intention, score, expert_id)
        save_to_history(ws, user_message, response, intention, score)
        return

    if intention in ("recherche_evenement", "recherche_cinema", "recherche_musique", "recherche_video"):
        response, results_data, search_type = await handle_api_search(intention, user_message)
        if results_data:
            manager.set_ctx(ws, "last_search_results", results_data)
            manager.set_ctx(ws, "last_search_type", search_type)
        await send_direct_with_tts(ws, response, intention, score, expert_id)
        save_to_history(ws, user_message, response, intention, score)
        return

    if intention == "liste_experts":
        lines = ["Voici les experts disponibles :\n"]
        for eid, info in EXPERTS.items():
            lines.append(f"- **{info['name']}** : {info['description']}")
        response = "\n".join(lines)
        await send_direct_with_tts(ws, response, intention, score, expert_id,
                                   tts_override="Voici les experts disponibles.")
        save_to_history(ws, user_message, response, intention, score)
        return

    if intention == "consultation_usage":
        uid = ctx.get("user_id", user_id)
        try:
            usage = await subscription_service.get_usage_summary(uid)
            tier = usage.get("tier", "free")
            msgs = usage.get("messages_today", 0)
            msgs_limit = usage.get("messages_limit", 5)
            tokens = usage.get("tokens_today", 0)
            tokens_limit = usage.get("tokens_limit", 2000)
            response = (
                f"Ton abonnement : **{tier.capitalize()}**\n"
                f"Messages aujourd'hui : {msgs}/{msgs_limit}\n"
                f"Tokens utilisés : {tokens}/{tokens_limit}"
            )
        except Exception as e:
            logger.error(f"Usage lookup error: {e}")
            response = "Je n'ai pas pu récupérer ta consommation."
        await send_direct_with_tts(ws, response, intention, score, expert_id,
                                   tts_override="Voici ta consommation du jour.")
        save_to_history(ws, user_message, response, intention, score)
        return

    if intention == "consultation_sessions":
        uid = ctx.get("user_id", user_id)
        try:
            sessions = await session_service.get_user_sessions(uid)
            if sessions:
                lines = [f"Tu as {len(sessions)} session(s) active(s) :\n"]
                for s in sessions[:5]:
                    expert = s.get("expert_id", "?")
                    count = s.get("message_count", 0)
                    lines.append(f"- **{expert}** : {count} messages")
                response = "\n".join(lines)
            else:
                response = "Tu n'as aucune session active pour le moment."
        except Exception as e:
            logger.error(f"Sessions lookup error: {e}")
            response = "Je n'ai pas pu récupérer tes sessions."
        await send_direct_with_tts(ws, response, intention, score, expert_id,
                                   tts_override="Voici tes sessions.")
        save_to_history(ws, user_message, response, intention, score)
        return

    if intention == "consultation_historique":
        uid = ctx.get("user_id", user_id)
        current = ctx.get("current_expert") or "general"
        try:
            sessions = await session_service.get_user_history_by_expert(str(uid), current, limit=5)
            if sessions:
                lines = [f"Historique avec **{current}** :\n"]
                for s in sessions:
                    count = s.get("message_count", 0)
                    date = s.get("last_message_at")
                    date_str = date.strftime("%d/%m %H:%M") if date else "?"
                    lines.append(f"- {count} messages (dernier : {date_str})")
                response = "\n".join(lines)
            else:
                response = f"Pas d'historique avec {current} pour le moment."
        except Exception as e:
            logger.error(f"History lookup error: {e}")
            response = "Je n'ai pas pu récupérer ton historique."
        await send_direct_with_tts(ws, response, intention, score, expert_id,
                                   tts_override="Voici ton historique.")
        save_to_history(ws, user_message, response, intention, score)
        return

    if intention == "consultation_emotion":
        uid = ctx.get("user_id", user_id)
        try:
            summary = await voice_analysis_service.get_emotion_summary(uid)
            current_emo = await voice_analysis_service.get_current_emotion(uid)
            if summary.get("total_analyses", 0) > 0:
                lines = []
                if current_emo:
                    from voice_analysis_service import EMOTION_LABELS
                    label = EMOTION_LABELS.get(current_emo["emotion"], current_emo["emotion"])
                    lines.append(f"Ton état actuel : **{label}** (confiance : {current_emo['confidence']:.0%})\n")
                lines.append(f"Sur {summary['total_analyses']} analyses :")
                for emo in summary["emotions"][:5]:
                    lines.append(f"- {emo['label']} : {emo['percentage']}% ({emo['count']} fois)")
                response = "\n".join(lines)
            else:
                response = "Je n'ai pas encore d'analyse émotionnelle pour toi. Envoie un message vocal pour que je puisse analyser ton humeur !"
        except Exception as e:
            logger.error(f"Emotion lookup error: {e}")
            response = "Je n'ai pas pu récupérer tes données émotionnelles."
        await send_direct_with_tts(ws, response, intention, score, expert_id,
                                   tts_override="Voici ton bilan émotionnel.")
        save_to_history(ws, user_message, response, intention, score)
        return

    if intention == "consultation_personnalite":
        uid = ctx.get("user_id", user_id)
        try:
            result = await personality_service.analyze_personality(uid)
            if result and result.get("status") == "complete":
                traits = result.get("traits", {})
                lines = ["Voici ton profil de personnalité (Big Five) :\n"]
                for key, data in traits.items():
                    name = data.get("name", key)
                    s = data.get("score", 5)
                    desc = data.get("description", "")
                    bar = "█" * s + "░" * (10 - s)
                    lines.append(f"**{name}** [{bar}] {s}/10\n  {desc}")
                resume = result.get("profil_resume", "")
                if resume:
                    lines.append(f"\n**Résumé** : {resume}")
                style = result.get("style_communication", "")
                if style:
                    lines.append(f"**Style** : {style}")
                response = "\n".join(lines)
            elif result and result.get("status") == "insufficient_data":
                response = result["message"]
            else:
                response = "Je n'ai pas pu analyser ta personnalité."
        except Exception as e:
            logger.error(f"Personality analysis error: {e}")
            response = "Erreur lors de l'analyse de personnalité."
        await send_direct_with_tts(ws, response, intention, score, expert_id,
                                   tts_override="Voici ton profil de personnalité.")
        save_to_history(ws, user_message, response, intention, score)
        return

    profile = ctx.get("profile")
    prenom = profile.get("prenom") if profile else None

    if not intent_classifier.needs_ai(intention):
        voice_expert = expert_id if expert_id and expert_id != "general" else "general"
        direct = get_direct_response(intention, voice_expert)
        if direct and prenom and "!" in direct:
            direct = direct.replace("!", f" {prenom} !", 1).replace("  ", " ")
        if direct:
            await send_direct_with_tts(ws, direct, intention, score, voice_expert)
            save_to_history(ws, user_message, direct, intention, score)
            return

    target_expert = force_expert or intent_classifier.route_to_expert(intention)
    if not force_expert and current_expert == "general":
        target_expert = "general"
    expert_info = EXPERTS.get(target_expert, EXPERTS["general"])

    if not await check_sub_limit(user_id, ws):
        return

    if current_expert != target_expert and not force_expert:
        welcome = expert_info.get(
            "welcome_message",
            f"Bonjour, je suis {expert_info['name'].split(' - ')[0]}. Comment puis-je vous aider ?"
        )
        if prenom:
            welcome = welcome.replace("?", f", {prenom} ?", 1) if "?" in welcome else f"{welcome} {prenom} !"
        welcome_audio = await tts_service.text_to_speech_base64(welcome, target_expert)
        await manager.send(ws, {
            "type": "expert_switch" if current_expert else "expert_intro",
            "message": welcome,
            "expert": {"id": target_expert, "name": expert_info['name'], "voice": expert_info['voice']},
            "audio": welcome_audio
        })

    manager.set_ctx(ws, "current_expert", target_expert)
    _save_expert_memory(user_id, target_expert)

    await stream_expert_with_tts(ws, user_message, target_expert, user_id, intention, score)


# ===== WS HANDLERS: VOICE & PERSONALITY =====

async def _ws_voice_analyze(ws: WebSocket, user_id: int, msg: dict):
    audio_data = msg.get("audio_data")
    audio_format = msg.get("audio_format", "webm")
    if not audio_data:
        await manager.send(ws, {"type": "error", "message": "audio_data manquant"})
        return
    result = await voice_analysis_service.analyze_and_store(user_id, audio_data, audio_format)
    if result:
        manager.set_ctx(ws, "emotion_state", result)
        await manager.send(ws, {
            "type": "voice_analysis",
            "emotion": result["emotion"],
            "label": result["emotion_label"],
            "confidence": result["confidence"],
            "description": result["description"],
            "top_emotions": result["top_emotions"],
            "features": result["features"],
            "analyzed_at": result["analyzed_at"],
        })
    else:
        await manager.send(ws, {"type": "voice_analysis", "error": "Impossible d'analyser l'audio"})


# ===== WEBSOCKET ENDPOINTS =====

@app.websocket("/ws")
async def websocket_main(websocket: WebSocket):
    await manager.connect(websocket)
    manager.set_ctx(websocket, "current_expert", "general")
    await manager.send(websocket, {
        "type": "ready",
        "experts_available": list(EXPERTS.keys())
    })

    _expert_restored = False

    try:
        while True:
            data = await websocket.receive_text()

            try:
                msg = json.loads(data)
            except (json.JSONDecodeError, TypeError):
                msg = {"message": data}

            msg_type = msg.get("type", "message")
            uid = msg.get("user_id", 1)
            manager.set_ctx(websocket, "user_id", uid)

            if not _expert_restored:
                _expert_restored = True
                remembered = _get_remembered_expert(uid)
                if remembered and remembered in EXPERTS:
                    manager.set_ctx(websocket, "current_expert", remembered)
                    logger.info(f"Expert restored for user {uid}: {remembered}")
            if msg.get("profile"):
                manager.set_ctx(websocket, "profile", msg["profile"])

            try:
                if msg_type == "voice_analyze":
                    await _ws_voice_analyze(websocket, uid, msg)
                else:
                    user_message, force_expert, user_id, profile, audio_data, audio_format = parse_message(data)

                    if audio_data and voice_analysis_service:
                        try:
                            emotion_result = await voice_analysis_service.analyze_and_store(
                                user_id, audio_data, audio_format
                            )
                            if emotion_result:
                                manager.set_ctx(websocket, "emotion_state", emotion_result)
                                await manager.send(websocket, {
                                    "type": "emotion_detected",
                                    "emotion": emotion_result["emotion"],
                                    "label": emotion_result["emotion_label"],
                                    "confidence": emotion_result["confidence"],
                                    "top_emotions": emotion_result["top_emotions"],
                                })
                        except Exception as e:
                            logger.warning(f"Voice analysis error: {e}")

                    await route_message(websocket, user_message, force_expert, user_id)

            except Exception as e:
                logger.error(f"Erreur traitement: {e}", exc_info=True)
                await manager.send(websocket, {
                    "type": "error",
                    "message": "Oups, j'ai eu un souci. Tu peux reformuler ?"
                })
    except WebSocketDisconnect:
        manager.disconnect(websocket)


async def websocket_expert_handler(websocket: WebSocket, expert_id: str):
    await manager.connect(websocket)
    manager.set_ctx(websocket, "current_expert", expert_id)

    expert_info = EXPERTS[expert_id]
    welcome = expert_info.get("welcome_message", f"Bonjour, je suis {expert_info['name'].split(' - ')[0]}.")

    welcome_audio = await tts_service.text_to_speech_base64(welcome, expert_id)
    await manager.send(websocket, {
        "type": "welcome",
        "expert": {"id": expert_id, "name": expert_info['name'], "description": expert_info['description']},
        "message": welcome,
        "audio": welcome_audio
    })

    try:
        while True:
            data = await websocket.receive_text()
            user_message, _, user_id, profile, _, _ = parse_message(data)
            manager.set_ctx(websocket, "user_id", user_id)
            if profile:
                manager.set_ctx(websocket, "profile", profile)

            try:
                await route_message(websocket, user_message, expert_id, user_id)
            except Exception as e:
                logger.error(f"Erreur [{expert_info['name']}]: {e}", exc_info=True)
                await manager.send(websocket, {
                    "type": "error",
                    "message": "Oups, j'ai eu un souci. Tu peux reformuler ?"
                })
    except WebSocketDisconnect:
        manager.disconnect(websocket)


@app.websocket("/ws/sexologie")
async def ws_sexologie(websocket: WebSocket):
    await websocket_expert_handler(websocket, "sexologie")

@app.websocket("/ws/psychologie")
async def ws_psychologie(websocket: WebSocket):
    await websocket_expert_handler(websocket, "psychologie")

@app.websocket("/ws/developpement_personnel")
async def ws_developpement(websocket: WebSocket):
    await websocket_expert_handler(websocket, "developpement_personnel")

@app.websocket("/ws/seduction")
async def ws_seduction(websocket: WebSocket):
    await websocket_expert_handler(websocket, "seduction")


# ===== REST ENDPOINTS (utilitaires uniquement, pas de chat) =====

@app.get("/")
async def root():
    return {"service": "MeetVoice API", "version": "3.0.0", "status": "running"}

@app.get("/health")
async def health():
    return {
        "status": "healthy",
        "services": {
            "classifier": intent_classifier is not None,
            "ai_service": ai_service is not None,
            "session_service": session_service is not None,
            "voice_analysis": voice_analysis_service is not None,
            "personality": personality_service is not None,
        },
        "tts_cache": tts_service.cache_stats() if tts_service else {}
    }

class SubscriptionRequest(BaseModel):
    user_id: int
    tier: str

@app.post("/api/subscription")
async def update_subscription(request: SubscriptionRequest):
    await subscription_service.set_user_tier(request.user_id, request.tier)
    return {"success": True, "user_id": request.user_id, "tier": request.tier}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host=WEBSOCKET_HOST, port=WEBSOCKET_PORT)
