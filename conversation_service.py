"""Service de gestion de la mémoire conversationnelle et comparaisons"""
import logging
from typing import List, Dict, Optional
from datetime import datetime

logger = logging.getLogger(__name__)


class ConversationService:
    """Service pour gérer l'historique et les comparaisons"""
    
    def __init__(self):
        """Initialise le service"""
        logger.info("✅ Service de conversation initialisé")
    
    # ===== MÉMOIRE CONVERSATIONNELLE =====
    
    def add_to_history(
        self, 
        context: Dict, 
        user_message: str, 
        bot_response: str,
        intention: str,
        metadata: Dict = None
    ):
        """Ajoute un échange à l'historique (max 10 derniers)"""
        if "conversation_history" not in context:
            context["conversation_history"] = []
        
        exchange = {
            "timestamp": datetime.now().isoformat(),
            "user": user_message,
            "bot": bot_response,
            "intention": intention,
            "metadata": metadata or {}
        }
        
        context["conversation_history"].append(exchange)
        
        # Garder seulement les 10 derniers échanges
        if len(context["conversation_history"]) > 10:
            context["conversation_history"] = context["conversation_history"][-10:]
    
    def get_history_summary(self, context: Dict, limit: int = 5) -> str:
        """Retourne un résumé de l'historique"""
        if "conversation_history" not in context or not context["conversation_history"]:
            return "Aucun historique de conversation disponible."
        
        history = context["conversation_history"][-limit:]
        
        summary = "📜 **Historique de Conversation**\n\n"
        
        for i, exchange in enumerate(history, 1):
            timestamp = datetime.fromisoformat(exchange["timestamp"])
            time_str = timestamp.strftime("%H:%M")
            
            summary += f"**{i}. [{time_str}]**\n"
            summary += f"   👤 Vous: {exchange['user'][:100]}...\n"
            summary += f"   🤖 Moi: {exchange['bot'][:100]}...\n\n"
        
        return summary
    
    def find_in_history(self, context: Dict, keyword: str) -> Optional[Dict]:
        """Recherche un échange dans l'historique par mot-clé"""
        if "conversation_history" not in context:
            return None
        
        keyword_lower = keyword.lower()
        
        # Chercher dans l'ordre inverse (plus récent d'abord)
        for exchange in reversed(context["conversation_history"]):
            if (keyword_lower in exchange["user"].lower() or 
                keyword_lower in exchange["bot"].lower()):
                return exchange
        
        return None
    
    def get_last_search(self, context: Dict) -> Optional[Dict]:
        """Récupère la dernière recherche effectuée"""
        if "conversation_history" not in context:
            return None
        
        # Chercher la dernière recherche (événements, films, musique, vidéos)
        search_intentions = [
            "recherche_evenement", 
            "recherche_cinema", 
            "recherche_musique", 
            "recherche_video",
            "recherche_profil"
        ]
        
        for exchange in reversed(context["conversation_history"]):
            if exchange["intention"] in search_intentions:
                return exchange
        
        return None
    
    # ===== COMPARAISON =====
    
    def compare_items(
        self, 
        item1: Dict, 
        item2: Dict, 
        search_type: str
    ) -> str:
        """Compare deux items selon leur type"""
        if search_type == "events":
            return self._compare_events(item1, item2)
        elif search_type == "movies":
            return self._compare_movies(item1, item2)
        elif search_type == "music":
            return self._compare_music(item1, item2)
        elif search_type == "videos":
            return self._compare_videos(item1, item2)
        elif search_type == "profiles":
            return self._compare_profiles(item1, item2)
        else:
            return "Type de comparaison non supporté."
    
    def _compare_events(self, event1: Dict, event2: Dict) -> str:
        """Compare deux événements"""
        return f"""📊 **Comparaison d'Événements**

| Critère | Événement 1 | Événement 2 |
|---------|-------------|-------------|
| **Nom** | {event1.get('name', 'N/A')} | {event2.get('name', 'N/A')} |
| **Date** | {event1.get('date', 'N/A')} | {event2.get('date', 'N/A')} |
| **Lieu** | {event1.get('venue', 'N/A')} | {event2.get('venue', 'N/A')} |
| **Lien** | [Voir]({event1.get('url', '#')}) | [Voir]({event2.get('url', '#')}) |

💡 **Recommandation** : Comparez les dates et lieux pour choisir !
"""
    
    def _compare_movies(self, movie1: Dict, movie2: Dict) -> str:
        """Compare deux films"""
        rating1 = movie1.get('rating', 0)
        rating2 = movie2.get('rating', 0)
        
        winner = ""
        if rating1 > rating2:
            winner = "✅ Film 1 a une meilleure note !"
        elif rating2 > rating1:
            winner = "✅ Film 2 a une meilleure note !"
        else:
            winner = "⚖️ Notes identiques !"
        
        return f"""📊 **Comparaison de Films**

| Critère | Film 1 | Film 2 |
|---------|--------|--------|
| **Titre** | {movie1.get('title', 'N/A')} | {movie2.get('title', 'N/A')} |
| **Note** | {rating1}/10 {'✅' if rating1 > rating2 else ''} | {rating2}/10 {'✅' if rating2 > rating1 else ''} |
| **Sortie** | {movie1.get('release_date', 'N/A')} | {movie2.get('release_date', 'N/A')} |
| **Synopsis** | {movie1.get('overview', 'N/A')[:50]}... | {movie2.get('overview', 'N/A')[:50]}... |

💡 **Recommandation** : {winner}
"""
    
    def _compare_music(self, track1: Dict, track2: Dict) -> str:
        """Compare deux morceaux de musique"""
        return f"""📊 **Comparaison de Musique**

| Critère | Morceau 1 | Morceau 2 |
|---------|-----------|-----------|
| **Titre** | {track1.get('title', 'N/A')} | {track2.get('title', 'N/A')} |
| **Artiste** | {track1.get('artist', 'N/A')} | {track2.get('artist', 'N/A')} |
| **Album** | {track1.get('album', 'N/A')} | {track2.get('album', 'N/A')} |
| **Écouter** | [Deezer]({track1.get('link', '#')}) | [Deezer]({track2.get('link', '#')}) |

💡 **Recommandation** : Écoutez les deux et choisissez votre préféré !
"""
    
    def _compare_videos(self, video1: Dict, video2: Dict) -> str:
        """Compare deux vidéos"""
        return f"""📊 **Comparaison de Vidéos**

| Critère | Vidéo 1 | Vidéo 2 |
|---------|---------|---------|
| **Titre** | {video1.get('title', 'N/A')} | {video2.get('title', 'N/A')} |
| **Chaîne** | {video1.get('channel', 'N/A')} | {video2.get('channel', 'N/A')} |
| **Regarder** | [YouTube]({video1.get('url', '#')}) | [YouTube]({video2.get('url', '#')}) |

💡 **Recommandation** : Regardez les deux pour comparer !
"""
    
    def _compare_profiles(self, profile1: Dict, profile2: Dict) -> str:
        """Compare deux profils utilisateurs"""
        score1 = profile1.get('match_score', 0)
        score2 = profile2.get('match_score', 0)
        
        winner = ""
        if score1 > score2:
            winner = "✅ Profil 1 est plus compatible !"
        elif score2 > score1:
            winner = "✅ Profil 2 est plus compatible !"
        else:
            winner = "⚖️ Compatibilité identique !"
        
        return f"""📊 **Comparaison de Profils**

| Critère | Profil 1 | Profil 2 |
|---------|----------|----------|
| **Prénom** | {profile1.get('prenom', 'N/A')} | {profile2.get('prenom', 'N/A')} |
| **Âge** | {profile1.get('age', 'N/A')} ans | {profile2.get('age', 'N/A')} ans |
| **Ville** | {profile1.get('ville', 'N/A')} | {profile2.get('ville', 'N/A')} |
| **Distance** | {profile1.get('distance_km', 'N/A')} km | {profile2.get('distance_km', 'N/A')} km |
| **Compatibilité** | {score1}% {'✅' if score1 > score2 else ''} | {score2}% {'✅' if score2 > score1 else ''} |
| **Bio** | {profile1.get('bio', 'N/A')[:50]}... | {profile2.get('bio', 'N/A')[:50]}... |

💡 **Recommandation** : {winner}
"""
    
    def parse_comparison_request(self, query: str, results: List[Dict]) -> Optional[tuple]:
        """Parse une demande de comparaison et retourne (item1, item2)"""
        query_lower = query.lower()
        
        # Chercher des patterns comme "compare le 1 et le 2"
        import re
        
        # Pattern 1: "le X et le Y"
        pattern1 = r'le (\d+|premier|deuxième|troisième|1er|2ème|3ème) et le (\d+|premier|deuxième|troisième|1er|2ème|3ème)'
        match = re.search(pattern1, query_lower)
        
        if match:
            idx1 = self._parse_number(match.group(1))
            idx2 = self._parse_number(match.group(2))
            
            if idx1 < len(results) and idx2 < len(results):
                return (results[idx1], results[idx2])
        
        return None
    
    def _parse_number(self, text: str) -> int:
        """Convertit un texte en index (0-based)"""
        mapping = {
            "1": 0, "premier": 0, "1er": 0,
            "2": 1, "deuxième": 1, "2ème": 1, "second": 1,
            "3": 2, "troisième": 2, "3ème": 2,
            "4": 3, "quatrième": 3, "4ème": 3,
            "5": 4, "cinquième": 4, "5ème": 4
        }
        return mapping.get(text, 0)


# Instance globale
_conversation_service = None

def get_conversation_service() -> ConversationService:
    """Retourne l'instance unique du service de conversation"""
    global _conversation_service
    if _conversation_service is None:
        _conversation_service = ConversationService()
    return _conversation_service

