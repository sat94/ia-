"""Service IA avec DeepInfra - Modèles par catégorie, mémoire Redis et recherche web"""
import logging
import json
from typing import Optional, List, Dict, Any, AsyncGenerator
import aiohttp
from config import DEEPINFRA_API_KEY, DEEPINFRA_MODELS, EXPERTS, REDIS_MEMORY_CATEGORIES

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

SEARCH_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "search_events",
            "description": "Recherche des événements, concerts, festivals, spectacles dans une ville",
            "parameters": {
                "type": "object",
                "properties": {
                    "city": {
                        "type": "string",
                        "description": "Ville où chercher les événements (ex: Paris, Lyon, Marseille)"
                    },
                    "query": {
                        "type": "string",
                        "description": "Type d'événement recherché (ex: concert, festival, spectacle)"
                    }
                },
                "required": ["city"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "search_movies",
            "description": "Recherche des films à l'affiche, sorties cinéma, films populaires",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Titre du film ou genre recherché"
                    }
                },
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "search_music",
            "description": "Recherche de musique, chansons, artistes sur Deezer",
            "parameters": {
                "type": "object",
                "properties": {
                    "artist": {
                        "type": "string",
                        "description": "Nom de l'artiste"
                    },
                    "track": {
                        "type": "string",
                        "description": "Titre de la chanson"
                    }
                },
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "search_videos",
            "description": "Recherche de vidéos YouTube, tutoriels, clips, bandes annonces",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Ce que l'utilisateur veut regarder"
                    }
                },
                "required": ["query"]
            }
        }
    }
]


class AIService:
    """Service IA DeepInfra avec mémoire Redis et recherche web"""

    def __init__(self):
        """Initialise le service DeepInfra"""
        self.api_key = DEEPINFRA_API_KEY
        self.base_url = "https://api.deepinfra.com/v1/openai/chat/completions"
        self.redis_memory = None
        self.api_service = None

        if self.api_key:
            logger.info("✅ DeepInfra configuré")
            for cat, model in DEEPINFRA_MODELS.items():
                logger.info(f"   └─ {cat}: {model}")
        else:
            logger.error("❌ DeepInfra non configuré (pas de clé API)")

    def set_redis_memory(self, redis_memory):
        """Injecte le service de mémoire Redis"""
        self.redis_memory = redis_memory
        logger.info("✅ Redis Memory injecté dans AIService")

    def set_api_service(self, api_service):
        """Injecte le service d'API externes"""
        self.api_service = api_service
        logger.info("✅ API Service injecté dans AIService")

    def _get_model_for_category(self, category: str) -> str:
        """Retourne le modèle approprié pour une catégorie"""
        return DEEPINFRA_MODELS.get(category, DEEPINFRA_MODELS["general"])

    def _build_messages(
        self,
        system_prompt: str,
        user_message: str,
        memory_history: Optional[List[Dict]] = None,
        session_history: Optional[List[Dict]] = None
    ) -> List[Dict]:
        """Construit la liste des messages pour l'API"""
        messages = [{"role": "system", "content": system_prompt}]

        if memory_history:
            context_intro = "\n\n[Tes 5 derniers échanges avec cet utilisateur]:\n"
            history_text = ""
            for exchange in memory_history:
                history_text += f"User: {exchange.get('user', '')}\n"
                history_text += f"Toi: {exchange.get('assistant', '')}\n\n"

            if history_text:
                messages[0]["content"] += context_intro + history_text

        if session_history:
            context_intro = "\n\n[Historique de la session de coaching]:\n"
            history_text = ""
            for exchange in session_history[-5:]:
                history_text += f"User: {exchange.get('user', '')}\n"
                history_text += f"Toi: {exchange.get('assistant', '')}\n\n"

            if history_text:
                messages[0]["content"] += context_intro + history_text

        messages.append({"role": "user", "content": user_message})
        return messages

    async def _execute_tool_call(self, tool_name: str, arguments: Dict) -> str:
        """Exécute un appel d'outil et retourne le résultat"""
        if not self.api_service:
            return "Service de recherche non disponible."

        try:
            if tool_name == "search_events":
                city = arguments.get("city", "Paris")
                events = self.api_service.search_events(city=city, limit=5)
                if events:
                    return self.api_service.format_events_response(events)
                return f"Aucun événement trouvé à {city}."

            elif tool_name == "search_movies":
                movies = self.api_service.search_movies(limit=5)
                if movies:
                    return self.api_service.format_movies_response(movies)
                return "Aucun film trouvé."

            elif tool_name == "search_music":
                artist = arguments.get("artist", "")
                track = arguments.get("track", "")
                query = artist or track or "top hits"
                tracks = self.api_service.search_music(artist=query, limit=5)
                if tracks:
                    return self.api_service.format_music_response(tracks)
                return "Aucune musique trouvée."

            elif tool_name == "search_videos":
                query = arguments.get("query", "")
                videos = self.api_service.search_videos(query, limit=5)
                if videos:
                    return self.api_service.format_videos_response(videos)
                return "Aucune vidéo trouvée."

            else:
                return f"Outil {tool_name} non reconnu."

        except Exception as e:
            logger.error(f"❌ Erreur exécution outil {tool_name}: {e}")
            return f"Erreur lors de la recherche : {str(e)}"

    async def generate_response(
        self,
        prompt: str,
        expert_id: str,
        user_id: int = 1,
        session_history: Optional[List[Dict]] = None
    ) -> str:
        """
        Génère une réponse avec DeepInfra
        
        Args:
            prompt: Message de l'utilisateur
            expert_id: ID de l'expert
            user_id: ID de l'utilisateur pour la mémoire Redis
            session_history: Historique de session (pour psychologie/séduction/dev perso)
            
        Returns:
            str: Réponse générée
        """
        if not self.api_key:
            return "Désolé, le service IA n'est pas configuré."

        expert_config = EXPERTS.get(expert_id)
        if not expert_config:
            expert_config = EXPERTS.get("general", {})
            expert_id = "general"

        category = expert_config.get("category", "general")
        model = self._get_model_for_category(category)
        system_prompt = expert_config.get("system_prompt", "Tu es un assistant utile.")
        uses_redis = expert_config.get("uses_redis_memory", False)
        can_search = expert_config.get("can_search", False)

        memory_history = None
        if uses_redis and self.redis_memory and category in REDIS_MEMORY_CATEGORIES:
            memory_history = await self.redis_memory.get_history(user_id, category)

        messages = self._build_messages(system_prompt, prompt, memory_history, session_history)

        try:
            async with aiohttp.ClientSession() as session:
                headers = {
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json"
                }

                data = {
                    "model": model,
                    "messages": messages,
                    "temperature": 0.8,
                    "max_tokens": 400,
                    "top_p": 0.9,
                }

                if can_search and self.api_service:
                    data["tools"] = SEARCH_TOOLS
                    data["tool_choice"] = "auto"

                async with session.post(
                    self.base_url,
                    headers=headers,
                    json=data,
                    timeout=aiohttp.ClientTimeout(total=60)
                ) as response:
                    if response.status != 200:
                        error_text = await response.text()
                        logger.error(f"❌ DeepInfra erreur {response.status}: {error_text}")
                        return "Désolé, une erreur s'est produite. Réessaie dans un instant."

                    result = await response.json()
                    choice = result["choices"][0]
                    message = choice["message"]

                    if message.get("tool_calls"):
                        tool_results = []
                        for tool_call in message["tool_calls"]:
                            func_name = tool_call["function"]["name"]
                            func_args = json.loads(tool_call["function"]["arguments"])
                            logger.info(f"🔧 Appel outil: {func_name}({func_args})")

                            tool_result = await self._execute_tool_call(func_name, func_args)
                            tool_results.append(tool_result)

                        combined_results = "\n\n".join(tool_results)

                        messages.append(message)
                        messages.append({
                            "role": "tool",
                            "tool_call_id": message["tool_calls"][0]["id"],
                            "content": combined_results
                        })

                        data["messages"] = messages
                        del data["tools"]
                        del data["tool_choice"]

                        async with session.post(
                            self.base_url,
                            headers=headers,
                            json=data,
                            timeout=aiohttp.ClientTimeout(total=30)
                        ) as final_response:
                            if final_response.status == 200:
                                final_result = await final_response.json()
                                content = final_result["choices"][0]["message"]["content"]
                            else:
                                content = combined_results
                    else:
                        content = message.get("content", "")

                    logger.info(f"✅ Réponse générée ({model}): {len(content)} chars")

                    if uses_redis and self.redis_memory and category in REDIS_MEMORY_CATEGORIES:
                        await self.redis_memory.add_message(user_id, category, prompt, content)

                    return content

        except aiohttp.ClientError as e:
            logger.error(f"❌ Erreur réseau DeepInfra: {e}")
            return "Problème de connexion. Réessaie dans un instant."
        except Exception as e:
            logger.error(f"❌ Erreur inattendue: {e}")
            return "Désolé, quelque chose s'est mal passé."

    async def generate_with_context(
        self,
        prompt: str,
        expert_id: str,
        session_id: str,
        session_service,
        user_id: int = 1
    ) -> str:
        """
        Génère une réponse avec contexte de session (pour psychologie, séduction, dev perso)
        """
        session_history = None

        expert_config = EXPERTS.get(expert_id, {})
        if expert_config.get("requires_session"):
            session_history = await session_service.get_session_history(session_id)

        response = await self.generate_response(prompt, expert_id, user_id, session_history)

        if expert_config.get("requires_session") and session_service:
            await session_service.add_exchange(
                session_id=session_id,
                user_message=prompt,
                assistant_response=response,
                expert_id=expert_id
            )

        return response

    async def generate_response_stream(
        self,
        prompt: str,
        expert_id: str,
        user_id: int = 1,
        session_history: Optional[List[Dict]] = None
    ) -> AsyncGenerator[str, None]:
        """
        Génère une réponse en streaming (token par token)
        
        Yields:
            str: Tokens de la réponse au fur et à mesure
        """
        if not self.api_key:
            yield "Désolé, le service IA n'est pas configuré."
            return

        expert_config = EXPERTS.get(expert_id)
        if not expert_config:
            expert_config = EXPERTS.get("general", {})
            expert_id = "general"

        category = expert_config.get("category", "general")
        model = self._get_model_for_category(category)
        system_prompt = expert_config.get("system_prompt", "Tu es un assistant utile.")
        uses_redis = expert_config.get("uses_redis_memory", False)
        can_search = expert_config.get("can_search", False)

        memory_history = None
        if uses_redis and self.redis_memory and category in REDIS_MEMORY_CATEGORIES:
            memory_history = await self.redis_memory.get_history(user_id, category)

        messages = self._build_messages(system_prompt, prompt, memory_history, session_history)
        full_response = ""

        try:
            async with aiohttp.ClientSession() as session:
                headers = {
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json"
                }

                data = {
                    "model": model,
                    "messages": messages,
                    "temperature": 0.8,
                    "max_tokens": 400,
                    "top_p": 0.9,
                    "stream": True
                }

                if can_search and self.api_service:
                    data["tools"] = SEARCH_TOOLS
                    data["tool_choice"] = "auto"
                    data["stream"] = False
                    
                    async with session.post(
                        self.base_url,
                        headers=headers,
                        json=data,
                        timeout=aiohttp.ClientTimeout(total=60)
                    ) as response:
                        if response.status != 200:
                            yield "Désolé, une erreur s'est produite."
                            return

                        result = await response.json()
                        choice = result["choices"][0]
                        message = choice["message"]

                        if message.get("tool_calls"):
                            tool_results = []
                            for tool_call in message["tool_calls"]:
                                func_name = tool_call["function"]["name"]
                                func_args = json.loads(tool_call["function"]["arguments"])
                                logger.info(f"🔧 Appel outil: {func_name}({func_args})")
                                tool_result = await self._execute_tool_call(func_name, func_args)
                                tool_results.append(tool_result)

                            combined_results = "\n\n".join(tool_results)
                            messages.append(message)
                            messages.append({
                                "role": "tool",
                                "tool_call_id": message["tool_calls"][0]["id"],
                                "content": combined_results
                            })

                            data["messages"] = messages
                            del data["tools"]
                            del data["tool_choice"]
                            data["stream"] = True

                async with session.post(
                    self.base_url,
                    headers=headers,
                    json=data,
                    timeout=aiohttp.ClientTimeout(total=60)
                ) as response:
                    if response.status != 200:
                        yield "Désolé, une erreur s'est produite."
                        return

                    async for line in response.content:
                        line = line.decode('utf-8').strip()
                        
                        if not line or not line.startswith('data: '):
                            continue
                            
                        if line == 'data: [DONE]':
                            break
                            
                        try:
                            json_str = line[6:]
                            chunk = json.loads(json_str)
                            
                            delta = chunk.get("choices", [{}])[0].get("delta", {})
                            content = delta.get("content", "")
                            
                            if content:
                                full_response += content
                                yield content
                                
                        except json.JSONDecodeError:
                            continue

                logger.info(f"✅ Stream terminé ({model}): {len(full_response)} chars")

                if uses_redis and self.redis_memory and category in REDIS_MEMORY_CATEGORIES:
                    await self.redis_memory.add_message(user_id, category, prompt, full_response)

        except aiohttp.ClientError as e:
            logger.error(f"❌ Erreur réseau DeepInfra: {e}")
            yield "Problème de connexion."
        except Exception as e:
            logger.error(f"❌ Erreur streaming: {e}")
            yield "Désolé, quelque chose s'est mal passé."

    async def generate_stream_with_context(
        self,
        prompt: str,
        expert_id: str,
        session_id: str,
        session_service,
        user_id: int = 1
    ) -> AsyncGenerator[str, None]:
        """
        Génère une réponse en streaming avec contexte de session
        """
        session_history = None
        expert_config = EXPERTS.get(expert_id, {})
        
        if expert_config.get("requires_session"):
            session_history = await session_service.get_session_history(session_id)

        full_response = ""
        async for token in self.generate_response_stream(prompt, expert_id, user_id, session_history):
            full_response += token
            yield token

        if expert_config.get("requires_session") and session_service:
            await session_service.add_exchange(
                session_id=session_id,
                user_message=prompt,
                assistant_response=full_response,
                expert_id=expert_id
            )


_ai_instance = None


def get_ai_service():
    """Retourne l'instance singleton du service IA"""
    global _ai_instance
    if _ai_instance is None:
        _ai_instance = AIService()
    return _ai_instance
