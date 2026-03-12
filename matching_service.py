import re
import logging
import asyncpg
import aiohttp
from typing import List, Dict, Optional
from datetime import date
from config import MAIN_DB_HOST, MAIN_DB_PORT, MAIN_DB_NAME, MAIN_DB_USER, MAIN_DB_PASSWORD

logger = logging.getLogger(__name__)

MESSAGING_API_URL = "https://messagerie.meet-voice.fr/api/messages"
SOCIAL_API_BASE = "https://social.meet-voice.fr/api/posts"
_POST_CATEGORIES = ["general", "amical", "amour", "libertin"]

HAIR_COLOR_MAP = {
    "blonde": "Blond", "blond": "Blond", "blonds": "Blond", "blondes": "Blond",
    "brune": "Brun", "brun": "Brun", "bruns": "Brun", "brunes": "Brun",
    "châtain": "Châtain", "chatain": "Châtain", "châtains": "Châtain",
    "rousse": "Roux", "roux": "Roux", "rousses": "Roux",
    "noir": "Noir", "noirs": "Noir", "noire": "Noir", "noires": "Noir",
    "gris": "Gris", "grise": "Gris", "poivre et sel": "Gris",
    "rouge": "Rouge", "rouges": "Rouge",
}

EYE_COLOR_MAP = {
    "bleu": "Bleu", "bleus": "Bleu", "bleue": "Bleu", "bleues": "Bleu",
    "vert": "Vert", "verts": "Vert", "verte": "Vert", "vertes": "Vert",
    "marron": "Marron", "marrons": "Marron",
    "noisette": "Noisette", "noisettes": "Noisette",
    "noir": "Noir", "noirs": "Noir",
    "gris": "Gris",
}

GENDER_MAP = {
    "femme": "Femme", "femmes": "Femme", "fille": "Femme", "filles": "Femme",
    "meuf": "Femme", "meufs": "Femme", "nana": "Femme", "nanas": "Femme",
    "homme": "Homme", "hommes": "Homme", "garçon": "Homme", "garçons": "Homme",
    "mec": "Homme", "mecs": "Homme", "gars": "Homme", "guy": "Homme",
}

_RE_AGE_RANGE = re.compile(r'entre\s+(\d+)\s+et\s+(\d+)\s*ans')
_RE_AGE_LESS = re.compile(r'moins\s+de\s+(\d+)\s*ans')
_RE_AGE_MORE = re.compile(r'plus\s+de\s+(\d+)\s*ans')
_RE_AGE_AROUND = re.compile(r'(?:environ|vers|autour\s+de)\s+(\d+)\s*ans')
_RE_DISTANCE = re.compile(r'(\d+)\s*km')

_PROFILE_SELECT = """
    c.id, c.prenom, c.sexe, c.date_de_naissance, c.bio,
    c.ville, c.pays, c.yeux, c.hair_color, c.taille,
    c.shilhouette, c.ethnique, c.recherche, c.situation,
    c.avatar, c.thumbnail, c.is_online,
    c.latitude, c.longitude, c.sport, c.metier, c.education,
    c.smoke, c.alcool, c.enfant, c.religion, c.animaux
"""


class MatchingService:

    def __init__(self):
        self._pool: Optional[asyncpg.Pool] = None
        self._http: Optional[aiohttp.ClientSession] = None
        logger.info("Service de matching initialisé")

    async def _get_pool(self) -> asyncpg.Pool:
        if self._pool is None or self._pool._closed:
            self._pool = await asyncpg.create_pool(
                host=MAIN_DB_HOST,
                port=int(MAIN_DB_PORT),
                database=MAIN_DB_NAME,
                user=MAIN_DB_USER,
                password=MAIN_DB_PASSWORD,
                min_size=1,
                max_size=5,
                command_timeout=10,
            )
            logger.info(f"Pool asyncpg connecté à {MAIN_DB_HOST}/{MAIN_DB_NAME}")
        return self._pool

    async def _get_http(self) -> aiohttp.ClientSession:
        if self._http is None or self._http.closed:
            self._http = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=10))
        return self._http

    async def close(self):
        if self._pool and not self._pool._closed:
            await self._pool.close()
        if self._http and not self._http.closed:
            await self._http.close()

    def _calc_age(self, dob) -> Optional[int]:
        if not dob:
            return None
        try:
            birth = dob if isinstance(dob, date) else date.fromisoformat(str(dob))
            today = date.today()
            return today.year - birth.year - ((today.month, today.day) < (birth.month, birth.day))
        except Exception:
            return None

    def _row_to_profile(self, row) -> Dict:
        profile = dict(row)
        profile["age"] = self._calc_age(profile.get("date_de_naissance"))
        profile["id"] = str(profile["id"])
        return profile

    async def _enrich_profile(self, profile: Dict) -> Dict:
        pool = await self._get_pool()
        uid = profile["id"]

        hobbies_q = pool.fetch("""
            SELECT h.hobie FROM compte_compte_hobie ch
            JOIN compte_hobie h ON h.id = ch.hobie_id
            WHERE ch.compte_id = $1::uuid
        """, uid)
        chars_q = pool.fetch("""
            SELECT ca.caractere FROM compte_compte_caractere cc
            JOIN compte_caractere ca ON ca.id = cc.caractere_id
            WHERE cc.compte_id = $1::uuid
        """, uid)
        langs_q = pool.fetch("""
            SELECT l.langue FROM compte_compte_langue cl
            JOIN compte_langue l ON l.id = cl.langue_id
            WHERE cl.compte_id = $1::uuid
        """, uid)
        music_q = pool.fetch("""
            SELECT m.musique FROM compte_compte_style_de_musique cm
            JOIN compte_musique m ON m.id = cm.musique_id
            WHERE cm.compte_id = $1::uuid
        """, uid)
        films_q = pool.fetch("""
            SELECT f.film FROM compte_compte_style_de_film cf
            JOIN compte_film f ON f.id = cf.film_id
            WHERE cf.compte_id = $1::uuid
        """, uid)

        import asyncio
        hobbies, chars, langs, music, films = await asyncio.gather(
            hobbies_q, chars_q, langs_q, music_q, films_q
        )

        profile["hobbies"] = [r["hobie"] for r in hobbies]
        profile["caracteres"] = [r["caractere"] for r in chars]
        profile["langues"] = [r["langue"] for r in langs]
        profile["musique"] = [r["musique"] for r in music]
        profile["films"] = [r["film"] for r in films]
        return profile

    async def get_full_profile(self, user_id: str) -> Optional[Dict]:
        pool = await self._get_pool()
        row = await pool.fetchrow(f"""
            SELECT {_PROFILE_SELECT} FROM compte_compte c
            WHERE c.id = $1::uuid AND c.is_active = true
        """, user_id)
        if not row:
            return None
        profile = self._row_to_profile(row)
        return await self._enrich_profile(profile)

    def parse_search_criteria(self, query: str) -> Dict:
        q = query.lower()
        criteria = {}

        for token, db_val in HAIR_COLOR_MAP.items():
            if token in q:
                criteria["hair_color"] = db_val
                break

        eye_context = re.search(r'yeux\s+(\w+)', q)
        if eye_context:
            mapped = EYE_COLOR_MAP.get(eye_context.group(1))
            if mapped:
                criteria["yeux"] = mapped
        else:
            for token, db_val in EYE_COLOR_MAP.items():
                if f"yeux {token}" in q or f"aux yeux {token}" in q:
                    criteria["yeux"] = db_val
                    break

        for token, db_val in GENDER_MAP.items():
            if re.search(rf'\b{re.escape(token)}\b', q):
                criteria["sexe"] = db_val
                break

        m = _RE_AGE_RANGE.search(q)
        if m:
            criteria["min_age"] = int(m.group(1))
            criteria["max_age"] = int(m.group(2))
        else:
            m = _RE_AGE_LESS.search(q)
            if m:
                criteria["max_age"] = int(m.group(1))
            m = _RE_AGE_MORE.search(q)
            if m:
                criteria["min_age"] = int(m.group(1))
            m = _RE_AGE_AROUND.search(q)
            if m:
                center = int(m.group(1))
                criteria["min_age"] = center - 3
                criteria["max_age"] = center + 3

        cities = [
            "paris", "lyon", "marseille", "toulouse", "nice", "nantes",
            "bordeaux", "lille", "strasbourg", "montpellier", "rennes",
        ]
        for city in cities:
            if city in q:
                criteria["ville"] = city.capitalize()
                break

        m = _RE_DISTANCE.search(q)
        if m:
            criteria["max_distance_km"] = int(m.group(1))
        if "près de moi" in q or "proximité" in q:
            criteria["max_distance_km"] = 20

        return criteria

    def parse_name_from_query(self, query: str) -> Optional[str]:
        q = query.lower().strip()
        words = query.strip().split()

        stopwords = {
            "un", "une", "le", "la", "les", "des", "du", "de", "ce", "cette",
            "mon", "ma", "mes", "son", "sa", "ses", "quelqu", "quoi", "quel",
            "quelle", "comment", "profil", "profils", "message", "quelque",
            "chose", "moi", "toi", "lui", "elle", "nous", "vous", "eux",
            "pas", "plus", "aussi", "mais", "pour", "dans", "avec", "sur",
            "je", "tu", "il", "on", "qui", "que", "quoi", "où", "est",
            "suis", "es", "sont", "ai", "as", "avons", "avoir", "être",
            "faire", "dit", "dire", "sais", "veux", "peux", "aime",
            "aimerais", "voudrais", "travailler", "travaille", "fait",
            "envie", "besoin", "intéressé", "intéresser", "parler",
            "salut", "bonjour", "coucou", "hey", "hello",
        }

        if len(words) == 1 and len(words[0]) >= 2:
            word = words[0]
            if word[0].isupper() and word.isalpha():
                return word.capitalize()

        patterns = [
            r"(?:parler|écrire|envoyer|message|contacter|dire)\s+(?:à|a|avec)\s+(\w+)",
            r"(?:intéress[ée]?e?\s+par)\s+(\w+)",
            r"(?:profil\s+(?:de|d'))\s*(\w+)",
            r"(?:connais|trouver?|chercher?|voir)\s+(\w+)",
            r"(?:c'est\s+qui|qui\s+est)\s+(\w+)",
            r"(?:cherche|trouve)\s+(\w+)",
            r"(?:aborder|séduire|draguer|impressionner)\s+(\w+)",
        ]
        for pattern in patterns:
            m = re.search(pattern, q)
            if m:
                name = m.group(1).strip()
                if name not in stopwords and len(name) >= 2:
                    return name.capitalize()

        for w in reversed(words):
            clean = re.sub(r'[^\w]', '', w)
            if clean and clean[0].isupper() and clean.isalpha() and len(clean) >= 2 and clean.lower() not in stopwords:
                return clean.capitalize()

        return None

    async def search_profiles(self, criteria: Dict, user_id: str = None, limit: int = 10) -> List[Dict]:
        pool = await self._get_pool()

        conditions = ["c.is_active = true", "c.ghost = false"]
        params = []
        idx = 1

        if user_id:
            conditions.append(f"c.id != ${idx}::uuid")
            params.append(str(user_id))
            idx += 1

        if "sexe" in criteria:
            conditions.append(f"c.sexe = ${idx}")
            params.append(criteria["sexe"])
            idx += 1

        if "hair_color" in criteria:
            conditions.append(f"c.hair_color = ${idx}")
            params.append(criteria["hair_color"])
            idx += 1

        if "yeux" in criteria:
            conditions.append(f"c.yeux = ${idx}")
            params.append(criteria["yeux"])
            idx += 1

        if "ville" in criteria:
            conditions.append(f"c.ville ILIKE ${idx}")
            params.append(f"%{criteria['ville']}%")
            idx += 1

        min_age = criteria.get("min_age")
        max_age = criteria.get("max_age")
        if min_age:
            conditions.append(f"c.date_de_naissance <= ${idx}::date")
            params.append(str(date(date.today().year - min_age, 12, 31)))
            idx += 1
        if max_age:
            conditions.append(f"c.date_de_naissance >= ${idx}::date")
            params.append(str(date(date.today().year - max_age - 1, 1, 1)))
            idx += 1

        where = " AND ".join(conditions)
        query = f"""
            SELECT {_PROFILE_SELECT} FROM compte_compte c
            WHERE {where}
            ORDER BY c.is_online DESC, c.updated_at DESC
            LIMIT ${idx}
        """
        params.append(limit)

        rows = await pool.fetch(query, *params)
        return [self._row_to_profile(row) for row in rows]

    async def search_by_name(self, name: str, user_id: str = None, limit: int = 5) -> List[Dict]:
        pool = await self._get_pool()
        conditions = ["c.is_active = true", "c.ghost = false", "c.prenom ILIKE $1"]
        params = [f"%{name}%"]
        idx = 2

        if user_id:
            conditions.append(f"c.id != ${idx}::uuid")
            params.append(str(user_id))
            idx += 1

        where = " AND ".join(conditions)
        query = f"""
            SELECT {_PROFILE_SELECT} FROM compte_compte c
            WHERE {where}
            ORDER BY c.is_online DESC, c.updated_at DESC
            LIMIT ${idx}
        """
        params.append(limit)

        rows = await pool.fetch(query, *params)
        return [self._row_to_profile(row) for row in rows]

    async def send_message(self, from_id: str, to_id: str, message: str) -> bool:
        try:
            session = await self._get_http()
            async with session.post(MESSAGING_API_URL, json={
                "from": from_id,
                "to": to_id,
                "message": message,
            }) as resp:
                ok = resp.status in (200, 201)
                if ok:
                    logger.info(f"Message envoyé de {from_id[:8]} à {to_id[:8]}")
                else:
                    body = await resp.text()
                    logger.error(f"Message API error {resp.status}: {body}")
                return ok
        except Exception as e:
            logger.error(f"Message send error: {e}")
            return False

    async def fetch_user_posts(self, username: str, limit: int = 5) -> List[Dict]:
        session = await self._get_http()
        all_posts = []
        for cat in _POST_CATEGORIES:
            url = f"{SOCIAL_API_BASE}/{cat}?username={username}"
            try:
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        posts = data if isinstance(data, list) else data.get("posts", data.get("data", []))
                        for p in posts:
                            all_posts.append({
                                "text": p.get("text") or p.get("titre") or "",
                                "titre": p.get("titre", ""),
                                "category": cat,
                                "created_at": p.get("created_at", ""),
                            })
            except Exception as e:
                logger.warning(f"Fetch posts {cat}/{username}: {e}")
        all_posts.sort(key=lambda x: x.get("created_at", ""), reverse=True)
        return all_posts[:limit]

    def profile_to_context(self, profile: Dict, posts: List[Dict] = None) -> str:
        parts = []
        prenom = profile.get("prenom", "?")
        age = profile.get("age")
        parts.append(f"{prenom}, {age} ans" if age else prenom)

        if profile.get("ville"):
            parts.append(f"Ville: {profile['ville']}")
        if profile.get("bio"):
            parts.append(f"Bio: {profile['bio']}")
        if profile.get("metier"):
            parts.append(f"Métier: {profile['metier']}")
        if profile.get("hobbies"):
            parts.append(f"Hobbies: {', '.join(profile['hobbies'])}")
        if profile.get("caracteres"):
            parts.append(f"Caractère: {', '.join(profile['caracteres'])}")
        if profile.get("musique"):
            parts.append(f"Musique: {', '.join(profile['musique'])}")
        if profile.get("films"):
            parts.append(f"Films: {', '.join(profile['films'])}")
        if profile.get("langues"):
            parts.append(f"Langues: {', '.join(profile['langues'])}")
        if profile.get("recherche"):
            parts.append(f"Recherche: {profile['recherche']}")
        if profile.get("situation"):
            parts.append(f"Situation: {profile['situation']}")
        if profile.get("sport"):
            parts.append(f"Sport: {profile['sport']}")

        if posts:
            post_texts = []
            for p in posts[:5]:
                txt = p.get("text") or p.get("titre") or ""
                if txt:
                    post_texts.append(f"- [{p.get('category', '')}] {txt[:150]}")
            if post_texts:
                parts.append(f"Derniers posts sur le réseau:\n" + "\n".join(post_texts))

        return "\n".join(parts)

    def compute_compatibility(self, p1: Dict, p2: Dict) -> Dict:
        score = 0
        total = 0
        details = []

        h1 = set(p1.get("hobbies", []))
        h2 = set(p2.get("hobbies", []))
        if h1 and h2:
            total += 30
            common = h1 & h2
            ratio = len(common) / len(h1 | h2)
            pts = round(ratio * 30)
            score += pts
            if common:
                details.append(f"Hobbies en commun : {', '.join(common)}")

        c1 = set(p1.get("caracteres", []))
        c2 = set(p2.get("caracteres", []))
        if c1 and c2:
            total += 20
            common = c1 & c2
            ratio = len(common) / len(c1 | c2)
            pts = round(ratio * 20)
            score += pts
            if common:
                details.append(f"Traits de caractère communs : {', '.join(common)}")

        m1 = set(p1.get("musique", []))
        m2 = set(p2.get("musique", []))
        if m1 and m2:
            total += 15
            common = m1 & m2
            ratio = len(common) / len(m1 | m2)
            pts = round(ratio * 15)
            score += pts
            if common:
                details.append(f"Goûts musicaux communs : {', '.join(common)}")

        f1 = set(p1.get("films", []))
        f2 = set(p2.get("films", []))
        if f1 and f2:
            total += 15
            common = f1 & f2
            ratio = len(common) / len(f1 | f2)
            pts = round(ratio * 15)
            score += pts
            if common:
                details.append(f"Films en commun : {', '.join(common)}")

        if p1.get("ville") and p2.get("ville"):
            total += 10
            if p1["ville"].lower() == p2["ville"].lower():
                score += 10
                details.append(f"Même ville : {p1['ville']}")

        if p1.get("age") and p2.get("age"):
            total += 10
            diff = abs(p1["age"] - p2["age"])
            if diff <= 3:
                score += 10
            elif diff <= 5:
                score += 7
            elif diff <= 10:
                score += 4
            else:
                score += 1

        pct = round((score / total) * 100) if total > 0 else 50
        return {"score": pct, "details": details}

    def format_matches_response(self, matches: List[Dict], name_search: bool = False) -> str:
        if not matches:
            if name_search:
                return "Je n'ai trouvé personne avec ce prénom sur la plateforme."
            return "Aucun profil ne correspond à tes critères. Essaie d'élargir ta recherche !"

        count = len(matches)
        if name_search:
            response = f"J'ai trouvé {count} profil{'s' if count > 1 else ''} :\n\n"
        else:
            response = f"{count} profil{'s' if count > 1 else ''} trouvé{'s' if count > 1 else ''} :\n\n"

        for i, p in enumerate(matches, 1):
            prenom = p.get("prenom", "Anonyme")
            age = p.get("age")
            ville = p.get("ville", "")
            hair = p.get("hair_color", "")
            yeux = p.get("yeux", "")
            bio = p.get("bio") or ""
            online = p.get("is_online", False)

            age_str = f", {age} ans" if age else ""
            ville_str = f" - {ville}" if ville else ""
            status = " (en ligne)" if online else ""

            response += f"{i}. {prenom}{age_str}{ville_str}{status}\n"

            details = []
            if hair:
                details.append(f"cheveux {hair.lower()}")
            if yeux:
                details.append(f"yeux {yeux.lower()}")
            if details:
                response += f"   {', '.join(details)}\n"
            if bio:
                short_bio = bio[:80] + ("..." if len(bio) > 80 else "")
                response += f"   {short_bio}\n"
            response += "\n"

        response += "Dis-moi si tu veux en savoir plus sur l'un d'eux !"
        return response

    def format_compatibility(self, p1: Dict, p2: Dict, compat: Dict) -> str:
        name1 = p1.get("prenom", "Toi")
        name2 = p2.get("prenom", "?")
        score = compat["score"]
        details = compat["details"]

        response = f"Compatibilité entre {name1} et {name2} : {score}%\n\n"

        if details:
            for d in details:
                response += f"- {d}\n"
            response += "\n"

        if score >= 75:
            response += f"Vous avez beaucoup en commun avec {name2} ! Ça vaut le coup de tenter le contact."
        elif score >= 50:
            response += f"Pas mal de points communs avec {name2}. Il y a du potentiel !"
        elif score >= 25:
            response += f"Quelques points communs avec {name2}. Les opposés s'attirent parfois !"
        else:
            response += f"Peu de points communs sur le papier, mais la chimie ne se mesure pas qu'en chiffres."

        return response


_matching_service = None

def get_matching_service() -> MatchingService:
    global _matching_service
    if _matching_service is None:
        _matching_service = MatchingService()
    return _matching_service
