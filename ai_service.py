import logging
import json
import re
import base64
from typing import Optional, List, Dict, AsyncGenerator
import aiohttp
from config import DEEPINFRA_API_KEY, DEEPINFRA_MODELS, EXPERTS, DEEPINFRA_IMAGE_MODEL

_RE_THINK_OPEN = re.compile(r'<\s*think\s*>')
_RE_THINK_CLOSE = re.compile(r'<\s*/\s*think\s*>')

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

SEARCH_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "search_events",
            "description": "Recherche des evenements, concerts, festivals dans une ville",
            "parameters": {
                "type": "object",
                "properties": {
                    "city": {"type": "string", "description": "Ville (ex: Paris, Lyon)"},
                    "query": {"type": "string", "description": "Type d'evenement"}
                },
                "required": ["city"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "search_movies",
            "description": "Recherche des films a l'affiche",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Titre ou genre"}
                },
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "search_music",
            "description": "Recherche de musique sur Deezer",
            "parameters": {
                "type": "object",
                "properties": {
                    "artist": {"type": "string", "description": "Nom de l'artiste"},
                    "track": {"type": "string", "description": "Titre"}
                },
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "search_videos",
            "description": "Recherche de videos YouTube",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Recherche"}
                },
                "required": ["query"]
            }
        }
    }
]


class AIService:
    def __init__(self):
        self.api_key = DEEPINFRA_API_KEY
        self.base_url = "https://api.deepinfra.com/v1/openai/chat/completions"
        self.api_service = None
        self._session: Optional[aiohttp.ClientSession] = None

        if self.api_key:
            logger.info("DeepInfra configured")
        else:
            logger.error("DeepInfra NOT configured (no API key)")

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json"
                },
                timeout=aiohttp.ClientTimeout(total=30, sock_connect=5)
            )
        return self._session

    async def close(self):
        if self._session and not self._session.closed:
            await self._session.close()

    @staticmethod
    def _strip_think(text: str, strip_ws: bool = True) -> str:
        cleaned = re.sub(r'<\s*think\s*>.*?<\s*/\s*think\s*>', '', text, flags=re.DOTALL)
        cleaned = re.sub(r'<\s*think\s*>.*', '', cleaned, flags=re.DOTALL)
        return cleaned.strip() if strip_ws else cleaned

    def set_api_service(self, api_service):
        self.api_service = api_service

    def _build_messages(
        self,
        system_prompt: str,
        user_message: str,
        recent_history: Optional[List[Dict]] = None,
        similar_history: Optional[List[Dict]] = None,
        user_profile: Optional[Dict] = None
    ) -> List[Dict]:
        prompt = system_prompt

        if user_profile:
            parts = []
            if user_profile.get("prenom"):
                parts.append(f"prénom: {user_profile['prenom']}")
            if user_profile.get("age"):
                parts.append(f"âge: {user_profile['age']} ans")
            if user_profile.get("ville"):
                parts.append(f"ville: {user_profile['ville']}")
            if user_profile.get("genre"):
                parts.append(f"genre: {user_profile['genre']}")
            if parts:
                prompt += f"\n\n[Profil utilisateur: {', '.join(parts)}] Utilise son prénom naturellement, adapte tes conseils à son âge et sa situation."

        messages = [{"role": "system", "content": prompt}]

        if similar_history:
            history_text = ""
            for ex in similar_history:
                history_text += f"User: {ex.get('user_message', '')}\nToi: {ex.get('assistant_response', '')}\n\n"
            if history_text:
                messages[0]["content"] += "\n\n[Echanges passes similaires - EVITE de repeter]:\n" + history_text

        if recent_history:
            history_text = ""
            for ex in recent_history[-5:]:
                history_text += f"User: {ex.get('user', '')}\nToi: {ex.get('assistant', '')}\n\n"
            if history_text:
                messages[0]["content"] += "\n\n[Derniers echanges]:\n" + history_text

        messages.append({"role": "user", "content": user_message})
        return messages

    async def _execute_tool_call(self, tool_name: str, arguments: Dict) -> str:
        if not self.api_service:
            return "Service de recherche non disponible."

        try:
            if tool_name == "search_events":
                events = await self.api_service.search_events(city=arguments.get("city", "Paris"), limit=5)
                return self.api_service.format_events_response(events) if events else f"Aucun evenement."

            elif tool_name == "search_movies":
                movies = await self.api_service.search_movies(limit=5)
                return self.api_service.format_movies_response(movies) if movies else "Aucun film."

            elif tool_name == "search_music":
                query = arguments.get("artist", "") or arguments.get("track", "") or "top hits"
                tracks = await self.api_service.search_music(artist=query, limit=5)
                return self.api_service.format_music_response(tracks) if tracks else "Aucune musique."

            elif tool_name == "search_videos":
                videos = await self.api_service.search_videos(arguments.get("query", ""), limit=5)
                return self.api_service.format_videos_response(videos) if videos else "Aucune video."

        except Exception as e:
            logger.error(f"Tool exec error {tool_name}: {e}")
            return f"Erreur recherche: {e}"

        return f"Outil {tool_name} non reconnu."

    async def _parse_sse_tokens(self, response) -> AsyncGenerator[str, None]:
        buffer = ""
        async for raw_chunk in response.content.iter_any():
            buffer += raw_chunk.decode("utf-8")
            while "\n" in buffer:
                line, buffer = buffer.split("\n", 1)
                line = line.strip()
                if not line or not line.startswith("data: "):
                    continue
                if line == "data: [DONE]":
                    return
                try:
                    payload = json.loads(line[6:])
                    content = payload.get("choices", [{}])[0].get("delta", {}).get("content", "")
                    if content:
                        yield content
                except json.JSONDecodeError:
                    continue

    async def generate_response_stream(
        self,
        prompt: str,
        expert_id: str,
        user_id: int = 1,
        recent_history: Optional[List[Dict]] = None,
        similar_history: Optional[List[Dict]] = None,
        user_profile: Optional[Dict] = None
    ) -> AsyncGenerator[str, None]:
        if not self.api_key:
            yield "Service IA non configure."
            return

        expert_config = EXPERTS.get(expert_id, EXPERTS.get("general", {}))
        category = expert_config.get("category", "general")
        model = DEEPINFRA_MODELS.get(category, DEEPINFRA_MODELS["general"])
        system_prompt = expert_config.get("system_prompt", "Tu es un assistant utile.")
        can_search = expert_config.get("can_search", False)

        messages = self._build_messages(system_prompt, prompt, recent_history, similar_history, user_profile)

        max_tok = 800 if category == "general" else 1200

        try:
            session = await self._get_session()

            data = {
                "model": model,
                "messages": messages,
                "temperature": 0.7,
                "max_tokens": max_tok,
                "stream": True
            }

            if can_search and self.api_service:
                data["tools"] = SEARCH_TOOLS
                data["tool_choice"] = "auto"
                data["stream"] = False

                async with session.post(self.base_url, json=data) as response:
                    if response.status != 200:
                        yield "Erreur service IA."
                        return

                    result = await response.json()
                    message = result["choices"][0]["message"]

                    if message.get("tool_calls"):
                        tool_results = []
                        for tc in message["tool_calls"]:
                            tr = await self._execute_tool_call(
                                tc["function"]["name"],
                                json.loads(tc["function"]["arguments"])
                            )
                            tool_results.append(tr)

                        messages.append(message)
                        messages.append({
                            "role": "tool",
                            "tool_call_id": message["tool_calls"][0]["id"],
                            "content": "\n\n".join(tool_results)
                        })
                        data["messages"] = messages
                        del data["tools"]
                        del data["tool_choice"]
                        data["stream"] = True

            async with session.post(self.base_url, json=data) as response:
                if response.status != 200:
                    yield "Erreur service IA."
                    return

                in_think = False
                think_buf = ""

                async for token in self._parse_sse_tokens(response):
                    if in_think:
                        think_buf += token
                        close_match = _RE_THINK_CLOSE.search(think_buf)
                        if close_match:
                            after = think_buf[close_match.end():]
                            in_think = False
                            think_buf = ""
                            if after:
                                yield after
                        continue

                    open_match = _RE_THINK_OPEN.search(token)
                    if open_match:
                        before = token[:open_match.start()]
                        if before:
                            yield before
                        in_think = True
                        think_buf = token[open_match.end():]
                        close_match = _RE_THINK_CLOSE.search(think_buf)
                        if close_match:
                            after = think_buf[close_match.end():]
                            in_think = False
                            think_buf = ""
                            if after:
                                yield after
                        continue

                    yield token

        except aiohttp.ClientError as e:
            logger.error(f"Network error: {e}")
            yield "Probleme de connexion."
        except Exception as e:
            logger.error(f"Stream error: {e}")
            yield "Erreur inattendue."


    async def generate_image(self, prompt: str, width: int = 1024, height: int = 1024) -> Optional[str]:
        session = await self._get_session()
        url = "https://api.deepinfra.com/v1/inference/" + DEEPINFRA_IMAGE_MODEL
        payload = {
            "prompt": prompt,
            "width": width,
            "height": height,
            "num_inference_steps": 4,
            "num_outputs": 1,
        }
        try:
            async with session.post(url, json=payload, timeout=aiohttp.ClientTimeout(total=60)) as resp:
                if resp.status != 200:
                    body = await resp.text()
                    logger.error(f"Image generation error {resp.status}: {body}")
                    return None
                data = await resp.json()
                images = data.get("images") or data.get("output") or []
                if not images:
                    logger.error(f"No images in response: {data}")
                    return None
                img = images[0]
                if img.startswith("data:"):
                    return img
                if img.startswith("http"):
                    async with session.get(img, timeout=aiohttp.ClientTimeout(total=30)) as img_resp:
                        if img_resp.status == 200:
                            img_bytes = await img_resp.read()
                            b64 = base64.b64encode(img_bytes).decode()
                            content_type = img_resp.headers.get("Content-Type", "image/png")
                            return f"data:{content_type};base64,{b64}"
                    return img
                return f"data:image/png;base64,{img}"
        except Exception as e:
            logger.error(f"Image generation error: {e}")
            return None

    async def improve_post_text(self, user_text: str) -> str:
        prompt = (
            "Tu es un expert en rédaction de posts pour un réseau social de rencontres. "
            "L'utilisateur veut publier ce texte. Améliore-le pour qu'il soit plus engageant, "
            "naturel et attractif. Garde le même sens et la même longueur approximative. "
            "Réponds UNIQUEMENT avec le texte amélioré, sans guillemets ni explication.\n\n"
            f"Texte original : {user_text}"
        )
        response = ""
        async for token in self.generate_response_stream(prompt, "general"):
            response += token
        return response.strip().strip('"').strip("«").strip("»").strip()


_ai_instance = None

def get_ai_service():
    global _ai_instance
    if _ai_instance is None:
        _ai_instance = AIService()
    return _ai_instance
