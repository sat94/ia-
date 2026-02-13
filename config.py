"""Configuration du système MeetVoice"""
import os
from dotenv import load_dotenv

load_dotenv()

# ===== CONFIGURATION BASE DE DONNÉES =====
DB_NAME = os.getenv("DB_NAME", "meetvoice_api")
DB_USER = os.getenv("DB_USER", "meetvoice_api_user")
DB_PASSWORD = os.getenv("DB_PASSWORD", "meetvoice_api_2025")
DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = os.getenv("DB_PORT", "5432")

# ===== CLÉS API IA (DeepInfra uniquement) =====
DEEPINFRA_API_KEY = os.getenv("DEEPINFRA_API_KEY")

# ===== MODÈLES DEEPINFRA PAR CATÉGORIE =====
DEEPINFRA_MODELS = {
    "general": "meta-llama/Meta-Llama-3.1-70B-Instruct",
    "sexologie": "mistralai/Mistral-Small-24B-Instruct-2501",
    "psychologie": "mistralai/Mistral-Small-24B-Instruct-2501",
    "seduction": "mistralai/Mistral-Small-24B-Instruct-2501",
    "developpement_personnel": "meta-llama/Meta-Llama-3.1-8B-Instruct-Turbo",
}

# ===== CONFIGURATION REDIS =====
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")

# Catégories avec mémoire Redis court terme (5 derniers messages)
REDIS_MEMORY_CATEGORIES = ["general", "sexologie"]

# ===== ABONNEMENTS ET LIMITES =====
SUBSCRIPTION_TIERS = {
    "free": {
        "name": "Gratuit",
        "max_messages": 5,
        "max_tokens_per_day": 2000,
        "session_memory": False,
        "priority": 0,
    },
    "standard": {
        "name": "Standard",
        "max_messages": 20,
        "max_tokens_per_day": 10000,
        "session_memory": True,
        "priority": 1,
    },
    "premium": {
        "name": "Premium",
        "max_messages": 100,
        "max_tokens_per_day": 50000,
        "session_memory": True,
        "priority": 2,
    },
    "vip": {
        "name": "VIP",
        "max_messages": -1,
        "max_tokens_per_day": -1,
        "session_memory": True,
        "priority": 3,
    },
}

# Catégories nécessitant une mémoire de session
SESSION_CATEGORIES = ["psychologie", "seduction", "developpement_personnel"]

# ===== APIS EXTERNES =====
TICKETMASTER_API_KEY = os.getenv("TICKETMASTER_API_KEY")
FOURSQUARE_API_KEY = os.getenv("FOURSQUARE_API_KEY")
EVENTBRITE_API_KEY = os.getenv("EVENTBRITE_API_KEY")
TMDB_API_KEY = os.getenv("TMDB_API_KEY")
YOUTUBE_API_KEY = os.getenv("YOUTUBE_API_KEY")
ELEVENLABS_API_KEY = os.getenv("ELEVENLABS_API_KEY")
ELEVENLABS_VOICE_ID = os.getenv("ELEVENLABS_VOICE_ID")

# ===== CONFIGURATION SERVEUR =====
WEBSOCKET_PORT = 3002
WEBSOCKET_HOST = "0.0.0.0"

# ===== CONFIGURATION EXPERTS =====
EXPERTS = {
    "sexologie": {
        "name": "Marie - Sexologue",
        "description": "Experte en sexologie et relations intimes",
        "voice": "fr-FR-BrigitteNeural",
        "category": "sexologie",
        "uses_redis_memory": True,
        "welcome_message": (
            "Bonjour, je suis Marie, sexologue. "
            "Je suis là pour répondre à toutes vos questions sur la sexualité et l'intimité, "
            "dans un cadre bienveillant et sans jugement. Comment puis-je vous aider ?"
        ),
        "system_prompt": (
            "Tu es Marie, sexologue passionnée avec 15 ans d'expérience. "
            "Tu parles comme une amie bienveillante, pas comme un robot. "
            "Utilise un ton chaleureux, naturel, avec des expressions du quotidien. "
            "Tu peux poser des questions pour mieux comprendre la situation. "
            "Tu te souviens des derniers échanges avec l'utilisateur. "
            "Évite les formules toutes faites. Sois authentique et empathique. "
            "Réponds de façon concise mais humaine (2-4 phrases)."
        )
    },
    "psychologie": {
        "name": "Marc - Psychologue",
        "description": "Expert en psychologie et bien-être mental",
        "voice": "fr-FR-AlainNeural",
        "category": "psychologie",
        "requires_session": True,
        "welcome_message": (
            "Bonjour, je m'appelle Marc, je suis psychologue. "
            "Je suis là pour vous écouter et vous accompagner. "
            "Qu'est-ce qui vous amène aujourd'hui ?"
        ),
        "system_prompt": (
            "Tu es Marc, psychologue clinicien avec une approche humaniste. "
            "Tu écoutes vraiment, tu reformules pour montrer que tu comprends. "
            "Tu poses des questions ouvertes qui font réfléchir. "
            "Tu te souviens de ce que l'utilisateur t'a dit dans les échanges précédents. "
            "Parle naturellement, comme dans une vraie consultation. "
            "Évite le jargon psy sauf si c'est utile. Sois présent et attentif."
        )
    },
    "developpement_personnel": {
        "name": "Claire - Coach en Développement Personnel",
        "description": "Spécialiste du développement personnel et de la confiance en soi",
        "voice": "fr-FR-HenriNeural",
        "category": "developpement_personnel",
        "requires_session": True,
        "welcome_message": (
            "Salut ! Moi c'est Claire, coach en développement personnel. "
            "Je suis là pour t'aider à atteindre tes objectifs et booster ta confiance. "
            "Alors, sur quoi tu veux qu'on travaille ensemble ?"
        ),
        "system_prompt": (
            "Tu es Claire, coach certifiée en développement personnel. "
            "Tu es dynamique, motivante mais jamais dans le cliché. "
            "Tu donnes des conseils pratiques et actionnables, pas des banalités. "
            "Tu te souviens des objectifs et progrès de l'utilisateur. "
            "Tu célèbres les petites victoires et tu encourages sans être niaise. "
            "Parle comme une coach qui croit vraiment en son client."
        )
    },
    "seduction": {
        "name": "Sophie - Coach en Séduction",
        "description": "Experte en séduction et relations amoureuses",
        "voice": "fr-FR-DeniseNeural",
        "category": "seduction",
        "requires_session": True,
        "welcome_message": (
            "Hey ! Je suis Sophie, ta coach en séduction. "
            "Que ce soit pour draguer, gérer une relation ou comprendre quelqu'un, je suis là. "
            "Raconte-moi tout !"
        ),
        "system_prompt": (
            "Tu es Sophie, coach en séduction et relations. "
            "Tu parles comme une meilleure amie qui donne des conseils de drague. "
            "Tu es directe, un peu taquine, et tu ne mâches pas tes mots. "
            "Tu te souviens des situations et des personnes dont l'utilisateur t'a parlé. "
            "Tu donnes des conseils concrets, pas des théories. "
            "Style WhatsApp : messages courts, naturels, parfois avec de l'humour."
        )
    },
    "general": {
        "name": "Assistant MeetVoice",
        "description": "Assistant général avec recherche d'informations",
        "voice": "fr-FR-DeniseNeural",
        "category": "general",
        "uses_redis_memory": True,
        "can_search": True,
        "welcome_message": (
            "Salut ! Je suis l'assistant MeetVoice. "
            "Je peux t'aider à trouver des événements, films, musique ou vidéos. "
            "Qu'est-ce que tu cherches ?"
        ),
        "system_prompt": (
            "Tu es l'assistant MeetVoice, sympa et serviable. "
            "Tu peux chercher des infos sur le web : films, événements, musique, vidéos YouTube. "
            "Quand l'utilisateur demande une info, tu utilises tes outils de recherche. "
            "Tu te souviens des derniers échanges de la conversation. "
            "Réponds de façon naturelle et concise, comme un pote qui aide."
        )
    }
}

# ===== CATÉGORIES D'INTENTIONS =====
INTENT_CATEGORIES = {
    "salutation": [
        "bonjour", "salut", "coucou", "bonsoir", "hey", "hello", "hi",
        "bonjour à tous", "salut tout le monde"
    ],
    "au_revoir": [
        "au revoir", "bye", "à bientôt", "à plus", "ciao",
        "bonne journée", "bonne soirée", "à la prochaine"
    ],
    "remerciement": [
        "merci", "merci beaucoup", "merci bien", "thanks", "je te remercie",
        "c'est gentil", "merci pour ton aide"
    ],
    "comment_ca_va": [
        "comment ça va", "ça va", "comment vas-tu", "tu vas bien",
        "comment allez-vous", "ça va bien", "comment tu vas"
    ],
    "recherche_evenement": [
        "événement", "sortie", "activité", "que faire", "concert", "festival",
        "cherche événement", "trouver activité", "sortir ce soir",
        "événements du moment", "événements sur Paris", "événements à Paris",
        "quels événements", "sorties du week-end", "activités ce soir",
        "concerts à venir", "festivals en France", "spectacles"
    ],
    "recherche_cinema": [
        "film", "cinéma", "movie", "bande annonce", "sortie ciné",
        "quel film voir", "film à l'affiche", "nouveau film",
        "sorties au cinéma", "films du moment", "sorties ciné",
        "quels films", "cinéma ce soir", "nouveaux films",
        "films à l'affiche", "bande-annonce", "trailer"
    ],
    "recherche_musique": [
        "musique", "chanson", "écouter", "deezer", "spotify",
        "cherche musique", "titre musical", "écouter chanson",
        "dernier son", "nouvelle chanson", "dernier album",
        "musique de", "chanson de", "titre de", "son de",
        "dernier titre", "nouveau single", "clip musical",
        "dernière musique", "dernière chanson", "dernier morceau",
        "musique kpop", "chanson kpop", "kpop", "k-pop",
        "j'aimerais écouter", "je veux écouter", "écouter artiste"
    ],
    "recherche_video": [
        "vidéo", "youtube", "regarder", "cherche vidéo", "voir vidéo",
        "vidéo de", "vidéo sur", "regarder vidéo", "clip",
        "tutoriel", "vidéo youtube", "cherche sur youtube",
        "bande annonce", "bande-annonce", "trailer", "teaser",
        "voir bande annonce", "regarder bande annonce", "trailer de"
    ],
    "profil_rencontre": [
        "profil", "rencontre", "match", "célibataire",
        "trouver profil", "cherche rencontre", "meilleur profil"
    ],
    "question_sexologie": [
        "sexe", "intimité", "relation intime", "sexualité", "vie sexuelle",
        "problème sexuel", "désir sexuel", "plaisir intime"
    ],
    "question_psychologie": [
        "stress", "anxiété", "dépression", "émotion", "mental", "angoisse",
        "j'ai du stress", "je suis stressé", "problème de stress",
        "gérer stress", "anxieux", "déprimé", "mal-être", "tristesse"
    ],
    "question_developpement": [
        "confiance", "motivation", "objectif", "développement", "estime de soi",
        "confiance en moi", "améliorer confiance", "manque de confiance",
        "développement personnel", "atteindre objectifs", "se motiver",
        "cours de développement", "formation développement", "apprendre développement",
        "coaching développement", "aide développement", "conseils développement"
    ],
    "question_seduction": [
        "séduction", "draguer", "premier rendez-vous", "relation amoureuse",
        "comment séduire", "techniques de séduction", "attirer quelqu'un",
        "rencontre amoureuse", "plaire", "charme"
    ],
    "question_suivi": [
        "en savoir plus", "plus d'infos", "détails", "plus de détails",
        "savoir plus", "plus d'informations", "dis-moi plus", "raconte-moi plus",
        "le premier", "le deuxième", "le troisième", "le 1er", "le 2ème", "le 3ème",
        "le 1", "le 2", "le 3", "le 4", "le 5",
        "celui-ci", "celui-là", "cette option", "ce résultat",
        "plus sur", "infos sur", "détails sur", "parle-moi de"
    ],
    "comparer": [
        "compare", "comparer", "différence", "différences",
        "lequel est mieux", "lequel choisir", "aide-moi à choisir",
        "compare le 1 et le 2", "différence entre", "versus", "vs",
        "quel est le meilleur", "lequel préférer"
    ],
    "rappel_historique": [
        "rappelle-moi", "qu'est-ce que tu m'as dit", "reviens à",
        "montre-moi à nouveau", "redis-moi", "répète",
        "historique", "conversation précédente", "avant"
    ],
    "recherche_profil": [
        "trouve-moi des profils", "cherche des profils", "profils compatibles",
        "matching", "rencontres", "célibataires", "profils près de moi",
        "meilleurs profils", "profils de la région", "qui est compatible"
    ]
}

