import random
from datetime import datetime

RESPONSE_TEMPLATES = {
    "salutation": [
        "Salut ! Comment je peux t'aider ?",
        "Hey ! Qu'est-ce que je peux faire pour toi ?",
        "Coucou ! Dis-moi ce qu'il te faut.",
        "Bonjour ! Je suis là, qu'est-ce qui t'amène ?",
    ],
    "au_revoir": [
        "À bientôt ! Prends soin de toi.",
        "Ciao ! N'hésite pas à revenir.",
        "Salut ! Bonne continuation.",
        "À plus ! J'étais content de t'aider.",
    ],
    "remerciement": [
        "De rien ! Si t'as besoin d'autre chose, hésite pas.",
        "Avec plaisir ! Je suis là pour ça.",
        "Pas de quoi ! N'hésite pas.",
    ],
    "comment_ca_va": [
        "Ça roule ! Et toi, comment tu vas ?",
        "Super bien, merci ! Qu'est-ce que je peux faire pour toi ?",
        "La forme ! Et toi ?",
    ],
    "demander_heure": None,
    "demander_date": None,
    "qui_es_tu": [
        "Je suis MeetVoice, ton assistant IA. Je peux t'aider à trouver des événements, "
        "des films, de la musique, des profils compatibles, ou te mettre en relation avec "
        "nos experts en sexologie, psychologie, développement personnel et séduction.",
    ],
    "aide": [
        "Voici ce que je peux faire :\n"
        "- Rechercher des événements, films, musiques ou vidéos\n"
        "- Trouver des profils compatibles près de chez toi\n"
        "- Te mettre en relation avec un expert (sexologue, psychologue, coach)\n"
        "- Répondre à tes questions de séduction, confiance, bien-être\n\n"
        "Dis-moi ce qui t'intéresse !",
    ],
    "blague": [
        "Pourquoi les plongeurs plongent-ils toujours en arrière ? Parce que s'ils plongeaient en avant, ils tomberaient dans le bateau !",
        "C'est l'histoire d'un mec qui entre dans un café... Plouf !",
        "Qu'est-ce qu'un crocodile qui surveille la cour de récréation ? Un surVEILLeur.",
        "Pourquoi les maths sont tristes ? Parce qu'elles ont trop de problèmes.",
        "Un homme entre chez le médecin : 'Docteur, tout le monde m'ignore.' Le médecin : 'Au suivant !'",
        "Quel est le comble pour un électricien ? De ne pas être au courant.",
    ],
    "compliment": [
        "Oh merci, c'est gentil ! Je fais de mon mieux. Comment je peux t'aider ?",
        "Trop sympa ! Alors, qu'est-ce qu'on fait ensemble ?",
        "Merci ! Ça me fait plaisir. Dis-moi ce qu'il te faut.",
    ],
    "insulte": [
        "Aïe ! Je préfère qu'on reste cool. Comment je peux t'aider ?",
        "C'est pas très sympa ça ! Mais bon, dis-moi ce que tu veux, je suis là.",
        "On repart sur de bonnes bases ? Dis-moi comment je peux t'aider.",
    ],
    "affirmatif": [
        "Super ! Qu'est-ce que tu veux qu'on fasse ?",
        "OK ! Dis-moi la suite.",
        "Parfait, je t'écoute !",
    ],
    "negatif": [
        "D'accord, pas de souci. Autre chose ?",
        "OK, c'est noté. Dis-moi si t'as besoin d'autre chose.",
        "Pas de problème ! Je suis là si tu changes d'avis.",
    ],
    "ennui": [
        "Je peux te proposer : chercher des événements près de chez toi, "
        "te montrer des profils compatibles, ou discuter avec un de nos experts. "
        "Qu'est-ce qui te tente ?",
        "Tu veux qu'on cherche un film, de la musique, ou des sorties ? "
        "Ou tu préfères discuter avec un coach ?",
    ],
}

EXPERT_SALUTATIONS = {
    "sexologie": [
        "Bonjour ! Je suis Marie, sexologue. Comment puis-je vous aider aujourd'hui ?",
        "Salut ! Marie ici. N'hésite pas, je suis là pour répondre à toutes tes questions.",
    ],
    "psychologie": [
        "Bonjour, je suis Marc, psychologue. Qu'est-ce qui vous amène ?",
        "Salut ! Marc ici. Je vous écoute, prenez votre temps.",
    ],
    "developpement_personnel": [
        "Salut ! Moi c'est Julien, ton coach. Sur quoi tu veux qu'on travaille ?",
        "Hey ! Julien ici. Alors, qu'est-ce qu'on bouste aujourd'hui ?",
    ],
    "seduction": [
        "Hey ! Sophie ici, ta coach séduction. Raconte-moi tout !",
        "Salut ! C'est Sophie. Qu'est-ce qui se passe côté coeur ?",
    ],
    "general": [
        "Salut ! Comment je peux t'aider ?",
        "Hey ! Dis-moi ce qu'il te faut.",
    ],
}


def get_direct_response(intention: str, expert_id: str = None) -> str:
    if intention == "demander_heure":
        now = datetime.now()
        return f"Il est {now.strftime('%H:%M')}."

    if intention == "demander_date":
        now = datetime.now()
        jours = ["lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche"]
        mois = ["janvier", "février", "mars", "avril", "mai", "juin",
                "juillet", "août", "septembre", "octobre", "novembre", "décembre"]
        jour_nom = jours[now.weekday()]
        mois_nom = mois[now.month - 1]
        return f"On est {jour_nom} {now.day} {mois_nom} {now.year}."

    if intention == "salutation" and expert_id and expert_id in EXPERT_SALUTATIONS:
        return random.choice(EXPERT_SALUTATIONS[expert_id])

    templates = RESPONSE_TEMPLATES.get(intention)
    if templates:
        return random.choice(templates)

    return None
