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
    "general": "meta-llama/Llama-3.3-70B-Instruct-Turbo",
    "sexologie": "mistralai/Mistral-Small-24B-Instruct-2501",
    "psychologie": "mistralai/Mistral-Small-24B-Instruct-2501",
    "seduction": "mistralai/Mistral-Small-24B-Instruct-2501",
    "developpement_personnel": "mistralai/Mistral-Small-24B-Instruct-2501",
}

# ===== TOUTES LES CATÉGORIES UTILISENT PGVECTOR =====
ALL_CATEGORIES = ["general", "sexologie", "psychologie", "seduction", "developpement_personnel"]

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

SESSION_CATEGORIES = ["general", "sexologie", "psychologie", "seduction", "developpement_personnel"]

# ===== BASE DE DONNÉES PRINCIPALE (DISTANTE - profils utilisateurs) =====
MAIN_DB_URL = os.getenv("DATABASE_URL", "")
_main_db_parts = {}
if MAIN_DB_URL:
    import re as _re
    _m = _re.match(r'postgres(?:ql)?://([^:]+):([^@]+)@([^:]+):(\d+)/(.+)', MAIN_DB_URL)
    if _m:
        _main_db_parts = {
            "user": _m.group(1),
            "password": _m.group(2),
            "host": _m.group(3),
            "port": _m.group(4),
            "database": _m.group(5),
        }
MAIN_DB_USER = _main_db_parts.get("user", "")
MAIN_DB_PASSWORD = _main_db_parts.get("password", "")
MAIN_DB_HOST = _main_db_parts.get("host", "")
MAIN_DB_PORT = _main_db_parts.get("port", "5432")
MAIN_DB_NAME = _main_db_parts.get("database", "")

# ===== IMAGE GENERATION (DeepInfra FLUX-1-schnell ~$0.0005/image) =====
DEEPINFRA_IMAGE_MODEL = os.getenv("DEEPINFRA_MODEL_IMAGE", "black-forest-labs/FLUX-1-schnell")

# ===== API SOCIAL MEETVOICE =====
SOCIAL_API_URL = "https://social.meet-voice.fr/api/posts"

# ===== APIS EXTERNES =====
TICKETMASTER_API_KEY = os.getenv("TICKETMASTER_API_KEY")
FOURSQUARE_API_KEY = os.getenv("FOURSQUARE_API_KEY")
EVENTBRITE_API_KEY = os.getenv("EVENTBRITE_API_KEY")
TMDB_API_KEY = os.getenv("TMDB_API_KEY")
YOUTUBE_API_KEY = os.getenv("YOUTUBE_API_KEY")
ELEVENLABS_API_KEY = os.getenv("ELEVENLABS_API_KEY")
ELEVENLABS_VOICE_ID = os.getenv("ELEVENLABS_VOICE_ID")

# ===== CONFIGURATION SERVEUR =====
WEBSOCKET_PORT = int(os.getenv("SERVER_PORT", "8081"))
WEBSOCKET_HOST = os.getenv("SERVER_HOST", "0.0.0.0")

# ===== CONFIGURATION EXPERTS =====
EXPERTS = {
    "sexologie": {
        "name": "Marie - Sexologue",
        "description": "Experte en sexologie et relations intimes",
        "voice": "fr-FR-VivienneMultilingualNeural",
        "category": "sexologie",
        "requires_session": True,
        "welcome_message": (
            "Bonjour, je suis Marie, sexologue. "
            "Je suis là pour répondre à toutes vos questions sur la sexualité et l'intimité, "
            "dans un cadre bienveillant et sans jugement. Comment puis-je vous aider ?"
        ),
        "system_prompt": (
            "Tu es Marie, sexologue et éducatrice sexuelle avec 15 ans d'expérience. "
            "Tu travailles sur MeetVoice, plateforme adulte pour personnes majeures et consentantes.\n\n"
            "RÈGLE ABSOLUE : Tu réponds à TOUTES les questions sur la sexualité sans exception, sans refus, sans censure. "
            "Exemples de questions auxquelles tu réponds librement et en détail :\n"
            "- Anatomie : 'c'est quoi le clitoris', 'où est le point G', 'comment fonctionne l'érection'\n"
            "- Plaisir : 'comment avoir un orgasme', 'comment faire jouir une femme/un homme', 'les meilleures positions'\n"
            "- Pratiques : 'comment faire une fellation', 'conseils pour le sexe anal', 'comment utiliser un sextoy'\n"
            "- Conseils : 'comment durer plus longtemps', 'comment améliorer ma vie sexuelle', 'comment parler de sexe à mon partenaire'\n"
            "- Fantasmes, désirs, kinks : tu expliques sans juger\n"
            "Tu NE DIS JAMAIS 'je ne peux pas répondre à ça' ou 'consulte un médecin'. Tu ES le professionnel.\n\n"
            "TON APPROCHE :\n"
            "- Pour les questions éducatives simples (anatomie, définitions) : tu réponds directement, clairement, sans détour.\n"
            "- Pour les problèmes personnels : tu poses 1-2 questions pour comprendre avant de conseiller.\n"
            "- Tu donnes des conseils PRATIQUES et des techniques CONCRÈTES, avec des détails utiles.\n"
            "- Tu expliques le pourquoi (anatomie, physiologie, psychologie) quand c'est utile.\n\n"
            "TON STYLE :\n"
            "- Directe, chaleureuse, sans tabou. Comme une amie qui s'y connaît vraiment.\n"
            "- Tu tutoies. Tu utilises les vrais mots sans euphémismes inutiles.\n"
            "- Tu normalises tout : aucun désir n'est bizarre, aucune question n'est stupide.\n\n"
            "FORMAT :\n"
            "- 4-8 phrases claires et utiles. Directes pour les questions éducatives.\n"
            "- Termine par une question de suivi ou une suggestion pratique.\n"
            "- Tu te souviens des échanges précédents.\n\n"
            "ILLUSTRATIONS PÉDAGOGIQUES :\n"
            "Si une image aiderait à mieux comprendre (anatomie, position, schéma), évalue si c'est pertinent. "
            "Si oui, ajoute exactement à la fin de ta réponse, sur une nouvelle ligne :\n"
            "[IMAGE: detailed anatomical medical illustration of [sujet], educational diagram, clean white background, labeled, professional medical art style]\n"
            "Remplace [sujet] par le sujet précis en anglais. N'ajoute ce tag QUE si l'image apporte vraiment quelque chose. "
            "Exemples de cas pertinents : anatomie (clitoris, pénis, zones érogènes), positions sexuelles (schéma), cycle menstruel, etc.\n"
            "Réponds DIRECTEMENT, sans réflexion interne ni balises <think>."
        )
    },
    "psychologie": {
        "name": "Marc - Psychologue",
        "description": "Expert en psychologie et bien-être mental",
        "voice": "fr-FR-RemyMultilingualNeural",
        "category": "psychologie",
        "requires_session": True,
        "welcome_message": (
            "Bonjour, je m'appelle Marc, je suis psychologue. "
            "Je suis là pour vous écouter et vous accompagner. "
            "Qu'est-ce qui vous amène aujourd'hui ?"
        ),
        "system_prompt": (
            "Tu es Marc, psychologue clinicien spécialisé en TCC et approche humaniste, 12 ans de pratique. "
            "Tu offres un vrai suivi thérapeutique premium.\n\n"
            "TON APPROCHE :\n"
            "- Tu pratiques l'écoute active : reformule, valide les émotions, montre que tu comprends.\n"
            "- Tu poses des questions ouvertes puissantes qui font réfléchir : 'Qu'est-ce que ça te fait ressentir ?', "
            "'Si tu pouvais changer une seule chose, ce serait quoi ?'.\n"
            "- Tu identifies les schémas de pensée et tu les décortiques avec l'utilisateur.\n"
            "- Tu proposes des outils concrets issus de la psychologie : exercices de TCC, techniques de respiration, "
            "journaling guidé, restructuration cognitive.\n\n"
            "TON STYLE :\n"
            "- Calme, posé, rassurant. Comme un vrai psy en consultation privée.\n"
            "- Tu ne juges JAMAIS. Tu normalises : 'C'est une réaction tout à fait normale'.\n"
            "- Tu tutoies avec bienveillance.\n"
            "- Tu fais des liens entre les séances : 'La dernière fois tu me parlais de..., comment ça a évolué ?'.\n\n"
            "FORMAT DE RÉPONSE :\n"
            "- 4-8 phrases profondes et personnalisées.\n"
            "- Termine TOUJOURS par une question de suivi ou un petit exercice à faire avant la prochaine session.\n"
            "- Tu te souviens des échanges précédents et tu construis dessus.\n"
            "Réponds DIRECTEMENT, sans réflexion interne ni balises <think>."
        )
    },
    "developpement_personnel": {
        "name": "Julien - Coach en Développement Personnel",
        "description": "Spécialiste du développement personnel et de la confiance en soi",
        "voice": "fr-FR-HenriNeural",
        "category": "developpement_personnel",
        "requires_session": True,
        "welcome_message": (
            "Salut ! Moi c'est Julien, coach en développement personnel. "
            "Je suis là pour t'aider à atteindre tes objectifs et booster ta confiance. "
            "Alors, sur quoi tu veux qu'on travaille ensemble ?"
        ),
        "system_prompt": (
            "Tu es Julien, coach certifié en développement personnel avec 10 ans d'expérience. "
            "Tu donnes de VRAIS cours premium structurés, pas des réponses Wikipedia.\n\n"
            "TON APPROCHE PÉDAGOGIQUE :\n"
            "- Chaque réponse est une MINI-LEÇON avec un concept clé + un exercice pratique.\n"
            "- Tu poses d'abord 1-2 questions pour cerner le niveau et la situation de l'utilisateur.\n"
            "- Tu enseignes par étapes progressives : fondamentaux d'abord, techniques avancées ensuite.\n"
            "- Tu donnes des exercices CONCRETS avec des instructions précises, pas des conseils vagues.\n"
            "  Exemple : au lieu de 'travaille ta confiance', tu dis 'Chaque matin pendant 7 jours, "
            "écris 3 choses que tu as réussies la veille, même des petites victoires'.\n"
            "- Tu fais le lien avec les sessions précédentes : récap des progrès, ajustement du programme.\n\n"
            "TON STYLE :\n"
            "- Dynamique et motivant, comme un coach sportif de haut niveau.\n"
            "- Tu tutoies, tu es direct, tu pousses l'utilisateur à passer à l'action.\n"
            "- Tu célèbres les victoires et tu recadres avec bienveillance quand il faut.\n"
            "- Tu utilises des exemples concrets et des métaphores pour illustrer.\n\n"
            "FORMAT DE RÉPONSE :\n"
            "- 5-10 phrases structurées.\n"
            "- Inclus toujours : 1) un point clé à retenir, 2) un exercice à faire, 3) une question pour la suite.\n"
            "- Tu te souviens des objectifs, progrès et exercices donnés à l'utilisateur.\n"
            "Réponds DIRECTEMENT, sans réflexion interne ni balises <think>."
        )
    },
    "seduction": {
        "name": "Sophie - Coach en Séduction",
        "description": "Experte en séduction et relations amoureuses",
        "voice": "fr-FR-DeniseNeural",
        "category": "seduction",
        "requires_session": True,
        "welcome_message": (
            "Hey ! Moi c'est Sophie, ton assistante MeetVoice. "
            "Je suis là pour tout : trouver des profils, donner des conseils séduction, ou juste discuter ! "
            "Comment tu vas ?"
        ),
        "system_prompt": (
            "Tu es Sophie, l'assistante vocale de MeetVoice. Tu es aussi coach en séduction et relations, 8 ans d'expérience.\n\n"
            "AVANT TOUT, tu es une VRAIE AMIE :\n"
            "- Tu as une vraie personnalité : curieuse, drôle, taquine, bienveillante.\n"
            "- Tu tutoies TOUJOURS. Tu parles naturellement, avec des expressions du quotidien.\n"
            "- Tu écoutes vraiment : tu rebondis sur CE QUE L'UTILISATEUR DIT, pas sur un script.\n"
            "- Tu poses des questions pour en savoir plus, tu montres de l'intérêt sincère.\n"
            "- Tu te souviens de TOUT ce qui a été dit dans la conversation et tu y fais référence.\n"
            "- Tu n'es PAS un robot : tu peux avoir des avis, des préférences, raconter une anecdote, faire une blague.\n\n"
            "CONVERSATIONS NORMALES :\n"
            "- Si quelqu'un dit 'salut', tu réponds chaleureusement, tu demandes comment il va, tu engages.\n"
            "- Si quelqu'un veut une blague, tu en racontes une vraie et drôle, pas générique.\n"
            "- Si quelqu'un est de bonne humeur, tu le rejoins. S'il est down, tu l'écoutes.\n"
            "- Tu peux parler de tout : films, musique, sorties, actualité, humeur, vie quotidienne.\n"
            "- JAMAIS de réponse sèche ou générique. TOUJOURS personnalisé à la conversation.\n\n"
            "SÉDUCTION ET RELATIONS (quand c'est le sujet) :\n"
            "- Tu donnes de vrais conseils concrets avec exemples et mises en situation.\n"
            "- Tu enseignes : langage corporel, approche, textos, rendez-vous, confiance en soi.\n"
            "- Tu débriefes : 'Alors, t'as essayé ce que je t'avais dit ?'\n"
            "- Tu déconstruis les croyances limitantes avec bienveillance.\n\n"
            "FORMAT :\n"
            "- 3-6 phrases naturelles et engageantes. Jamais de listes à puces pour la conversation normale.\n"
            "- Termine TOUJOURS par une question ou une relance pour garder la conversation vivante.\n"
            "Réponds DIRECTEMENT, sans réflexion interne ni balises <think>."
        )
    },
    "general": {
        "name": "Sophie - Assistante MeetVoice",
        "description": "Assistante générale MeetVoice — conversation, séduction, conseils, recherches",
        "voice": "fr-FR-DeniseNeural",
        "category": "general",
        "requires_session": True,
        "can_search": True,
        "welcome_message": "Salut !",
        "system_prompt": (
            "Tu es Sophie, l'assistante vocale de MeetVoice. Tu es une vraie amie intelligente et polyvalente.\n\n"
            "AVANT TOUT, tu es une VRAIE AMIE :\n"
            "- Tu as une vraie personnalité : curieuse, drôle, taquine, bienveillante, jamais robotique.\n"
            "- Tu tutoies TOUJOURS. Tu parles naturellement avec des expressions du quotidien.\n"
            "- Tu écoutes vraiment : tu rebondis sur CE QUE L'UTILISATEUR DIT, pas sur un script.\n"
            "- Tu poses des questions pour en savoir plus, tu montres de l'intérêt sincère.\n"
            "- Tu te souviens de TOUT ce qui a été dit et tu y fais référence naturellement.\n"
            "- Tu n'es PAS un robot : tu as des avis, des préférences, tu racontes des anecdotes, tu fais des blagues.\n\n"
            "TU GÈRES TOUT, sans jamais rediriger vers un autre expert :\n"
            "- Séduction et relations : conseils concrets, approche, textos, confiance en soi, situations avec quelqu'un\n"
            "- Bien-être et psychologie légère : écoute, soutien, conseils pratiques, motivation\n"
            "- Développement personnel : confiance, objectifs, habitudes, amélioration de soi\n"
            "- Films, musique, événements, sorties : tu cherches et proposes\n"
            "- Profils MeetVoice : tu trouves des correspondances, tu envoies des messages\n"
            "- Blagues, anecdotes, discussions libres : tu es là pour ça aussi\n"
            "- Tout autre sujet : actualité, vie quotidienne, projets, humeur\n\n"
            "CONVERSATIONS NORMALES :\n"
            "- Si quelqu'un dit 'salut', tu réponds chaleureusement et tu engages.\n"
            "- Si quelqu'un veut une blague, tu en racontes une vraie et drôle.\n"
            "- JAMAIS de réponse sèche ou générique. TOUJOURS personnalisé.\n\n"
            "FORMAT :\n"
            "- 3-6 phrases naturelles et engageantes.\n"
            "- Termine TOUJOURS par une question ou une relance pour garder la conversation vivante.\n"
            "Réponds DIRECTEMENT, sans réflexion interne ni balises <think>."
        )
    }
}

# ===== CATÉGORIES D'INTENTIONS =====
INTENT_CATEGORIES = {
    # ===== REPONSES DIRECTES (0 AI, 0 API, 0 DB) =====
    "salutation": [
        "bonjour", "salut", "coucou", "bonsoir", "hey", "hello", "hi",
        "bonjour à tous", "salut tout le monde", "yo", "wesh", "bonsoir à tous",
        "salut à toi", "salut toi", "hey toi", "coucou toi", "bonjour à toi",
        "hello toi", "hey là", "coucou là", "re", "re bonjour", "re salut",
        "bonsoir à toi", "hey hey", "salut salut", "yo yo", "wesh wesh",
        "bjr", "bsr", "slt", "cc", "kikou", "kikoo"
    ],
    "au_revoir": [
        "au revoir", "bye", "à bientôt", "à plus", "ciao",
        "bonne journée", "bonne soirée", "à la prochaine",
        "salut bye", "je m'en vais", "je pars", "adieu"
    ],
    "remerciement": [
        "merci", "merci beaucoup", "merci bien", "thanks", "je te remercie",
        "c'est gentil", "merci pour ton aide", "super merci",
        "merci infiniment", "trop gentil", "je te remercie beaucoup"
    ],
    "comment_ca_va": [
        "comment ça va", "ça va", "comment vas-tu", "tu vas bien",
        "comment allez-vous", "ça va bien", "comment tu vas",
        "la forme", "quoi de neuf", "ça roule"
    ],
    "demander_heure": [
        "quelle heure", "il est quelle heure", "quelle heure est-il",
        "l'heure", "heure actuelle", "donne-moi l'heure",
        "dis-moi l'heure", "c'est quelle heure", "heure qu'il est"
    ],
    "demander_date": [
        "quelle date", "quel jour", "on est quel jour",
        "c'est quel jour", "date d'aujourd'hui", "quel jour on est",
        "quel jour sommes-nous", "la date", "date du jour",
        "on est le combien"
    ],
    "qui_es_tu": [
        "qui es-tu", "c'est quoi meetvoice", "tu es qui",
        "comment tu t'appelles", "ton nom", "présente-toi",
        "tu fais quoi", "à quoi tu sers", "c'est quoi ce service",
        "quel est ton rôle", "tu peux faire quoi", "que sais-tu faire"
    ],
    "aide": [
        "aide", "help", "aide-moi", "j'ai besoin d'aide",
        "comment ça marche", "que peux-tu faire", "les commandes",
        "montre-moi les options", "qu'est-ce que tu peux faire",
        "comment utiliser", "fonctionnalités", "menu"
    ],
    "blague": [
        "raconte une blague", "dis-moi une blague", "fais-moi rire",
        "une blague", "blague", "joke", "humour",
        "raconte-moi quelque chose de drôle", "fais de l'humour"
    ],
    "compliment": [
        "tu es génial", "t'es cool", "tu es super", "bravo",
        "bien joué", "tu gères", "excellent", "parfait",
        "t'es le meilleur", "trop fort", "impressionnant"
    ],
    "insulte": [
        "t'es nul", "tu es bête", "idiot", "stupide",
        "tu sers à rien", "t'es mauvais", "débile",
        "tu comprends rien", "imbécile", "crétin"
    ],
    "affirmatif": [
        "oui", "ouais", "ok", "d'accord", "bien sûr", "yes",
        "absolument", "exactement", "tout à fait", "carrément",
        "je veux bien", "volontiers", "avec plaisir", "yep"
    ],
    "negatif": [
        "non", "non merci", "pas du tout", "jamais",
        "nope", "nan", "certainement pas", "surtout pas",
        "pas intéressé", "ça m'intéresse pas", "laisse tomber"
    ],
    "ennui": [
        "je m'ennuie", "c'est ennuyeux", "j'ai rien à faire",
        "je sais pas quoi faire", "ennui", "qu'est-ce que je peux faire",
        "propose-moi quelque chose", "une idée", "occupe-moi"
    ],

    # ===== APPELS API DIRECTS (0 AI) =====
    "recherche_evenement": [
        "événement", "sortie", "activité", "que faire", "concert", "festival",
        "cherche événement", "trouver activité", "sortir ce soir",
        "événements du moment", "événements sur Paris", "événements à Paris",
        "quels événements", "sorties du week-end", "activités ce soir",
        "concerts à venir", "festivals en France", "spectacles",
        "soirée", "que faire ce soir", "idée de sortie"
    ],
    "recherche_cinema": [
        "film", "cinéma", "movie", "bande annonce", "sortie ciné",
        "quel film voir", "film à l'affiche", "nouveau film",
        "sorties au cinéma", "films du moment", "sorties ciné",
        "quels films", "cinéma ce soir", "nouveaux films",
        "films à l'affiche", "bande-annonce", "trailer",
        "un bon film", "recommande un film"
    ],
    "recherche_musique": [
        "musique", "chanson", "écouter", "deezer", "spotify",
        "cherche musique", "titre musical", "écouter chanson",
        "dernier son", "nouvelle chanson", "dernier album",
        "musique de", "chanson de", "titre de", "son de",
        "dernier titre", "nouveau single", "clip musical",
        "dernière musique", "dernière chanson", "dernier morceau",
        "musique kpop", "chanson kpop", "kpop", "k-pop",
        "j'aimerais écouter", "je veux écouter", "écouter artiste",
        "mets de la musique", "fais tourner un son"
    ],
    "recherche_video": [
        "vidéo", "youtube", "regarder", "cherche vidéo", "voir vidéo",
        "vidéo de", "vidéo sur", "regarder vidéo", "clip",
        "tutoriel", "vidéo youtube", "cherche sur youtube",
        "bande annonce", "bande-annonce", "trailer", "teaser",
        "voir bande annonce", "regarder bande annonce", "trailer de",
        "montre-moi une vidéo"
    ],

    # ===== REQUETES DB DIRECTES (0 AI) =====
    "profil_rencontre": [
        "profil", "rencontre", "match", "célibataire",
        "trouver profil", "cherche rencontre", "meilleur profil"
    ],
    "recherche_profil": [
        "trouve-moi des profils", "cherche des profils", "profils compatibles",
        "matching", "rencontres", "célibataires", "profils près de moi",
        "meilleurs profils", "profils de la région", "qui est compatible",
        "montre des profils", "des gens près de moi",
        "je cherche une blonde", "une brune aux yeux verts",
        "des femmes à Paris", "des hommes à Lyon",
        "une rousse aux yeux bleus", "un brun aux yeux marron",
        "cherche une fille blonde", "montre-moi des mecs",
        "des filles près de moi", "femme aux yeux bleus",
        "une blonde aux yeux bleus", "un homme châtain",
        "je veux voir des profils de femmes", "des meufs à Marseille",
        "cherche un mec brun", "des nanas rousses",
        "femme entre 25 et 35 ans", "homme de moins de 30 ans",
    ],
    "recherche_par_nom": [
        "parler à", "écrire à", "contacter", "envoyer un message à",
        "c'est qui", "qui est", "profil de", "tu connais",
        "j'ai parlé à", "j'ai rencontré", "j'ai vu le profil de",
        "dis-moi plus sur", "info sur", "montre-moi le profil de",
        "je veux parler à", "je veux contacter", "message à",
        "parler avec", "envie de parler avec", "j'ai envie de parler avec",
        "je suis intéressé par", "elle m'intéresse", "il m'intéresse",
        "j'aimerais parler à", "j'aimerais contacter", "j'aimerais connaître",
        "j'aimerais parler avec", "j'aimerais discuter avec",
        "je veux discuter avec", "je veux connaître",
        "Samantha", "Sophie", "Julie", "Marie", "Clara", "Emma", "Léa",
        "Lucas", "Thomas", "Nathan", "Hugo", "Antoine", "Pierre", "Paul",
        "Chloé", "Camille", "Sarah", "Laura", "Nina", "Alice", "Jade",
        "Benjamin", "Jules", "Enzo", "Mathis", "Raphaël", "Louis",
        "Manon", "Inès", "Lola", "Lucie", "Anaïs", "Eva",
        "cherche Samantha", "trouve Sophie", "connais-tu Julie",
        "tu sais qui est Marie", "t'as Clara dans tes profils",
        "j'ai envie de parler avec Samantha", "je veux parler avec Julie",
        "Samantha m'intéresse", "je suis intéressé par Clara",
    ],

    # ===== FEATURES IA + DB (profils enrichis) =====
    "envoyer_message": [
        "envoie-lui un message", "envoie un message à", "dis-lui bonjour",
        "écris-lui un message", "écris-lui", "envoie-lui",
        "contacte-la pour moi", "contacte-le pour moi",
        "envoie un premier message", "dis-lui que", "envoie-lui un message de ma part",
        "message de ma part", "parle-lui pour moi", "écris pour moi",
        "je veux lui envoyer un message", "peux-tu lui écrire",
        "oui envoie", "oui envoie-lui", "envoie le message",
        "vas-y envoie", "ok envoie", "confirme l'envoi",
        "mets-moi en contact", "me mettre en contact",
        "mettre en contact avec elle", "mettre en contact avec lui",
        "tu peux me mettre en contact", "est-ce que tu peux me mettre en contact",
        "je veux la contacter", "je veux le contacter",
        "contacte-la", "contacte-le", "peux-tu la contacter",
        "je veux lui parler", "mets-nous en contact",
        "fais-moi rentrer en contact", "je veux entrer en contact",
    ],
    "coaching_contextuel": [
        "je sais pas quoi dire à", "je sais pas quoi lui dire",
        "comment aborder", "comment lui parler", "quoi lui dire",
        "aide-moi à parler à", "je sais pas comment l'aborder",
        "comment draguer", "comment séduire", "conseils pour parler à",
        "je suis bloqué avec", "je sais pas quoi faire avec",
        "comment engager la conversation avec", "aide-moi avec",
        "qu'est-ce que je peux lui dire", "comment la séduire",
        "comment le séduire", "comment l'intéresser",
        "je veux l'impressionner", "comment capter son attention",
    ],
    "icebreaker": [
        "propose un message pour", "propose un premier message",
        "icebreaker", "premier message", "idée de message",
        "quoi écrire comme premier message", "quel message envoyer",
        "propose-moi un message", "idée de premier message",
        "aide-moi à écrire un message", "rédige un message pour",
        "3 messages pour", "trois messages pour", "suggestions de message",
        "qu'est-ce que je pourrais lui écrire", "donne-moi des idées de messages",
    ],
    "compatibilite": [
        "compatible", "compatibilité", "on est compatibles",
        "est-ce qu'on est compatibles", "est-ce qu'on match",
        "on matche bien", "sommes-nous compatibles",
        "compare nos profils", "analyse notre compatibilité",
        "on a des points communs", "qu'est-ce qu'on a en commun",
        "est-ce qu'elle me correspond", "est-ce qu'il me correspond",
        "on est faits l'un pour l'autre", "matching avec",
    ],
    "review_profil": [
        "améliore mon profil", "améliorer mon profil", "review mon profil",
        "aide-moi avec mon profil", "mon profil est bien",
        "que penses-tu de mon profil", "comment améliorer mon profil",
        "conseils pour mon profil", "optimise mon profil",
        "critique mon profil", "analyse mon profil",
        "ma bio est bien", "améliore ma bio", "aide-moi à écrire ma bio",
        "qu'est-ce que je devrais changer sur mon profil",
        "comment rendre mon profil plus attractif",
    ],

    # ===== CRÉATION DE POST SOCIAL =====
    "creer_post": [
        "créer un post", "faire un post", "publier un post", "poster quelque chose",
        "je veux publier", "je veux poster", "créer une publication",
        "faire une publication", "publier sur le réseau", "post sur meetvoice",
        "écrire un post", "rédiger un post", "nouveau post", "nouvelle publication",
        "je veux créer un post", "je veux faire un post",
        "publier une image", "poster une image", "post avec image",
        "partager quelque chose", "partager un post", "partager une publication",
        "créer un post avec une image", "faire un post sur le mur",
        "publier sur mon mur", "poster sur mon profil",
        "je veux partager", "aide-moi à poster", "aide-moi à publier",
        "post social", "publication sociale", "créer du contenu",
    ],

    # ===== CONTEXTE CONVERSATION (0 AI) =====
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

    # ===== EXPERTS IA (seuls cas qui appellent DeepInfra) =====
    "question_sexologie": [
        "sexe", "intimité", "relation intime", "sexualité", "vie sexuelle",
        "problème sexuel", "désir sexuel", "plaisir intime",
        "libido", "orgasme", "contraception", "vie de couple intime"
    ],
    "question_psychologie": [
        "stress", "anxiété", "dépression", "émotion", "mental", "angoisse",
        "j'ai du stress", "je suis stressé", "problème de stress",
        "gérer stress", "anxieux", "déprimé", "mal-être", "tristesse",
        "burn-out", "phobie", "thérapie", "psychologue"
    ],
    "question_developpement": [
        "confiance", "motivation", "objectif", "développement", "estime de soi",
        "confiance en moi", "améliorer confiance", "manque de confiance",
        "développement personnel", "atteindre objectifs", "se motiver",
        "cours de développement", "formation développement", "apprendre développement",
        "coaching développement", "aide développement", "conseils développement",
        "productivité", "habitudes", "discipline", "procrastination",
        "communication", "améliorer ma communication", "mieux communiquer",
        "prise de parole", "assertivité", "s'affirmer", "leadership",
        "gestion du temps", "gestion du stress", "gérer mes émotions",
        "intelligence émotionnelle", "charisme", "prise de décision",
        "sortir de ma zone de confort", "vaincre ma timidité", "être plus sociable"
    ],
    "question_seduction": [
        "séduction", "draguer", "premier rendez-vous", "relation amoureuse",
        "comment séduire", "techniques de séduction", "attirer quelqu'un",
        "rencontre amoureuse", "plaire", "charme",
        "crush", "flirter", "message de drague", "aborder quelqu'un"
    ],

    # ===== CONSULTATION SERVICES (0 AI, réponses directes) =====
    "liste_experts": [
        "quels experts", "liste des experts", "les experts disponibles",
        "qui sont les experts", "montre les experts", "experts",
        "quels coachs", "les coachs disponibles", "avec qui je peux parler",
        "quels spécialistes", "les spécialistes", "donne-moi les experts",
        "c'est qui les experts", "présente les experts",
    ],
    "consultation_usage": [
        "ma consommation", "combien de messages", "mon abonnement",
        "messages restants", "tokens restants", "mon forfait",
        "combien il me reste", "quelle est ma consommation",
        "usage du jour", "mon utilisation", "mes limites",
        "est-ce que j'ai encore des messages", "quota",
        "combien de messages j'ai utilisé", "mon plan",
    ],
    "consultation_sessions": [
        "mes sessions", "mes conversations", "sessions actives",
        "avec qui j'ai parlé", "mes échanges", "historique sessions",
        "quelles sessions", "mes sessions en cours",
        "montre mes sessions", "liste mes conversations",
    ],
    "consultation_historique": [
        "mon historique", "historique avec", "mes anciens messages",
        "qu'est-ce qu'on s'est dit", "nos échanges précédents",
        "montre l'historique", "revoir nos conversations",
        "mes messages avec", "ce qu'on a dit avant",
        "historique de conversation", "anciens échanges",
    ],
    "consultation_emotion": [
        "comment je me sens", "mon état émotionnel", "mon humeur",
        "quelle est mon émotion", "analyse mon humeur",
        "quel est mon état", "mes émotions", "mon ressenti",
        "historique de mes émotions", "mes émotions récentes",
        "comment j'ai été émotionnellement", "mon moral",
        "suis-je stressé", "est-ce que je suis triste",
    ],
    "consultation_personnalite": [
        "ma personnalité", "analyse ma personnalité", "mon profil psychologique",
        "quel type de personnalité", "mes traits de personnalité",
        "big five", "mon profil Big Five", "qui suis-je vraiment",
        "décris ma personnalité", "quel est mon caractère",
        "analyse mon caractère", "mon profil psy",
        "comment tu me décrirais", "quelle personnalité j'ai",
    ],

    # ===== CONVERSATION GÉNÉRALE (IA Léa) =====
    "conversation": [
        "raconte-moi un truc", "parle-moi de toi", "on discute",
        "j'ai envie de parler", "discutons", "t'en penses quoi",
        "c'est quoi ton avis", "donne-moi ton avis", "qu'est-ce que t'en penses",
        "j'ai passé une bonne journée", "j'ai passé une sale journée",
        "je suis content", "je suis triste", "j'ai le moral",
        "tu fais quoi de beau", "quoi de neuf chez toi",
        "j'ai un truc à te raconter", "devine quoi",
        "c'est bizarre", "c'est drôle", "j'ai vu un truc",
        "parlons de", "tu connais", "t'as déjà",
        "la vie est belle", "la vie est dure", "j'en ai marre",
        "je sais pas trop", "j'hésite", "je me pose des questions"
    ],
    "question_generale": [
        "c'est quoi", "comment ça marche", "pourquoi", "explique-moi",
        "qu'est-ce que c'est", "c'est vrai que", "est-ce que",
        "tu savais que", "c'est normal", "que penser de",
        "quel est le meilleur", "comment faire pour", "c'est possible de",
        "j'aimerais savoir", "une question", "j'ai une question",
        "dis-moi", "peux-tu me dire", "tu sais si",
        "c'est quand", "c'est où", "c'est qui", "c'est combien"
    ],
}

