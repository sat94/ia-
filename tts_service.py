import edge_tts
import io
import re
import base64
import hashlib
import asyncio
from config import EXPERTS
from direct_responses import RESPONSE_TEMPLATES, EXPERT_SALUTATIONS
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class TTSService:
    def __init__(self):
        self.voices = {
            eid: edata['voice'] for eid, edata in EXPERTS.items()
        }
        self._cache: dict[str, str] = {}
        logger.info(f"TTS init: {len(self.voices)} voix")

    _RE_URL = re.compile(r'https?://\S+|www\.\S+')
    _RE_EMOJI = re.compile(
        "["
        "\U0001F600-\U0001F64F"
        "\U0001F300-\U0001F5FF"
        "\U0001F680-\U0001F6FF"
        "\U0001F1E0-\U0001F1FF"
        "\U00002702-\U000027B0"
        "\U000024C2-\U0001F251"
        "\U0001F900-\U0001F9FF"
        "\U0001FA00-\U0001FA6F"
        "\U0001FA70-\U0001FAFF"
        "\U00002600-\U000026FF"
        "]+", flags=re.UNICODE
    )
    _RE_MARKDOWN_BOLD = re.compile(r'\*\*(.+?)\*\*')
    _RE_MARKDOWN_ITALIC = re.compile(r'\*(.+?)\*')
    _RE_MARKDOWN_LINK = re.compile(r'\[([^\]]+)\]\([^\)]+\)')
    _RE_MARKDOWN_HEADER = re.compile(r'^#{1,6}\s+', re.MULTILINE)
    _RE_MARKDOWN_LIST = re.compile(r'^[\-\*]\s+', re.MULTILINE)
    _RE_MULTI_SPACE = re.compile(r'[ \t]{2,}')
    _RE_MULTI_NEWLINE = re.compile(r'\n{3,}')

    @classmethod
    def _clean_for_tts(cls, text: str) -> str:
        t = cls._RE_MARKDOWN_LINK.sub(r'\1', text)
        t = cls._RE_URL.sub('', t)
        t = cls._RE_EMOJI.sub('', t)
        t = cls._RE_MARKDOWN_BOLD.sub(r'\1', t)
        t = cls._RE_MARKDOWN_ITALIC.sub(r'\1', t)
        t = cls._RE_MARKDOWN_HEADER.sub('', t)
        t = cls._RE_MARKDOWN_LIST.sub('', t)
        t = t.replace('```', '').replace('`', '')
        t = t.replace(' :', ':').replace(' ;', ';')
        t = t.replace('...', ', ')
        t = t.replace('★', '').replace('☆', '').replace('•', ',')
        t = t.replace('→', '').replace('←', '').replace('↑', '').replace('↓', '')
        t = t.replace('#', '').replace('_', ' ')
        t = cls._RE_MULTI_SPACE.sub(' ', t)
        t = cls._RE_MULTI_NEWLINE.sub('\n', t)
        return t.strip()

    def _cache_key(self, text: str, voice: str) -> str:
        return hashlib.md5(f"{voice}:{text}".encode()).hexdigest()

    async def _generate_b64(self, text: str, voice: str) -> str:
        text = self._clean_for_tts(text)
        if not text:
            return None
        communicate = edge_tts.Communicate(text, voice)
        buffer = io.BytesIO()
        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                buffer.write(chunk["data"])
        audio_bytes = buffer.getvalue()
        if not audio_bytes:
            return None
        return base64.b64encode(audio_bytes).decode('utf-8')

    async def prewarm_cache(self):
        items = []

        for expert_id, info in EXPERTS.items():
            welcome = info.get("welcome_message", "")
            if welcome:
                items.append((welcome, expert_id))

        for expert_id, salutations in EXPERT_SALUTATIONS.items():
            for text in salutations:
                items.append((text, expert_id))

        for intention, templates in RESPONSE_TEMPLATES.items():
            if templates is None:
                continue
            for text in templates:
                items.append((text, "general"))

        search_intros = [
            "Voici les vidéos que j'ai trouvées.",
            "Voici les films à l'affiche.",
            "Voici les titres que j'ai trouvés.",
            "Voici les événements que j'ai trouvés.",
            "Voici les profils qui pourraient te plaire.",
        ]
        for text in search_intros:
            items.append((text, "general"))

        total = len(items)
        logger.info(f"TTS prewarm: {total} phrases (batch de 5)...")
        ok = 0
        for i in range(0, total, 5):
            batch = items[i:i+5]
            coros = [self._cache_one(text, eid) for text, eid in batch]
            results = await asyncio.gather(*coros, return_exceptions=True)
            ok += sum(1 for r in results if r is True)
            await asyncio.sleep(0.3)
        logger.info(f"TTS prewarm done: {ok}/{total} cached ({len(self._cache)} entries)")

    async def _cache_one(self, text: str, expert_id: str) -> bool:
        voice = self.voices.get(expert_id, 'fr-FR-DeniseNeural')
        key = self._cache_key(text, voice)
        if key in self._cache:
            return True
        try:
            b64 = await self._generate_b64(text, voice)
            if b64:
                self._cache[key] = b64
                return True
        except Exception as e:
            logger.warning(f"TTS prewarm fail: {text[:30]}... -> {e}")
        return False

    async def text_to_speech_base64(self, text: str, expert_id: str) -> str:
        if not text or not text.strip():
            return None

        voice = self.voices.get(expert_id, 'fr-FR-DeniseNeural')
        key = self._cache_key(text, voice)

        cached = self._cache.get(key)
        if cached:
            return cached

        try:
            b64 = await self._generate_b64(text, voice)
            if b64:
                self._cache[key] = b64
            return b64
        except Exception as e:
            logger.error(f"TTS error: {e}")
            return None

    def get_expert_voice(self, expert_id: str) -> str:
        return self.voices.get(expert_id, 'fr-FR-DeniseNeural')

    def cache_stats(self) -> dict:
        return {"entries": len(self._cache)}


_tts_instance = None

def get_tts_service():
    global _tts_instance
    if _tts_instance is None:
        _tts_instance = TTSService()
    return _tts_instance
