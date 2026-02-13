"""Service de matching et recherche de profils compatibles"""
import logging
from typing import List, Dict, Optional
from db_service import get_db_service

logger = logging.getLogger(__name__)


class MatchingService:
    """Service pour trouver des profils compatibles"""
    
    def __init__(self):
        """Initialise le service"""
        self.db = get_db_service()
        logger.info("✅ Service de matching initialisé")
    
    def find_matches(
        self,
        user_id: str,
        max_distance_km: int = 50,
        min_age: int = None,
        max_age: int = None,
        limit: int = 10
    ) -> List[Dict]:
        """Trouve les meilleurs profils compatibles pour un utilisateur"""
        try:
            # Utiliser la fonction de matching de db_service
            matches = self.db.find_best_matches(
                user_id=user_id,
                max_distance_km=max_distance_km,
                min_age=min_age,
                max_age=max_age,
                limit=limit
            )
            
            logger.info(f"✅ {len(matches)} profils trouvés pour user {user_id}")
            return matches
            
        except Exception as e:
            logger.error(f"❌ Erreur matching: {e}")
            return []
    
    def format_matches_response(self, matches: List[Dict]) -> str:
        """Formate la réponse avec les profils matchés"""
        if not matches:
            return "Aucun profil compatible trouvé dans votre région. Essayez d'élargir vos critères de recherche."
        
        response = f"💕 **{len(matches)} Profils Compatibles Trouvés**\n\n"
        
        for i, profile in enumerate(matches, 1):
            prenom = profile.get('prenom', 'Anonyme')
            age = profile.get('age', '?')
            ville = profile.get('ville', 'Ville inconnue')
            distance = profile.get('distance_km', '?')
            score = profile.get('match_score', 0)
            bio = profile.get('bio', 'Pas de bio')
            photo = profile.get('photo_profil', '')
            
            # Emoji selon le score
            if score >= 80:
                emoji = "💖"
            elif score >= 60:
                emoji = "💕"
            else:
                emoji = "💙"
            
            response += f"""**{i}. {emoji} {prenom}, {age} ans**
📍 {ville} ({distance} km)
⭐ Compatibilité: {score}%
📝 {bio[:100]}{'...' if len(bio) > 100 else ''}

"""
        
        response += "\n💡 **Astuce** : Dites \"en savoir plus sur le 1er\" pour voir les détails complets !"
        
        return response
    
    def format_profile_details(self, profile: Dict, position: int) -> str:
        """Formate les détails complets d'un profil"""
        prenom = profile.get('prenom', 'Anonyme')
        nom = profile.get('nom', '')
        age = profile.get('age', '?')
        sexe = profile.get('sexe', '?')
        ville = profile.get('ville', 'Ville inconnue')
        pays = profile.get('pays', 'Pays inconnu')
        distance = profile.get('distance_km', '?')
        score = profile.get('match_score', 0)
        bio = profile.get('bio', 'Pas de bio')
        description = profile.get('description', 'Pas de description')
        type_relation = profile.get('type_relation', 'Non spécifié')
        photo = profile.get('photo_profil', '')
        
        # Emoji selon le sexe
        sexe_emoji = "👨" if sexe == "M" else "👩" if sexe == "F" else "👤"
        
        # Emoji selon le score
        if score >= 80:
            score_emoji = "💖"
        elif score >= 60:
            score_emoji = "💕"
        else:
            score_emoji = "💙"
        
        return f"""💕 **Profil #{position} - Détails Complets**

{sexe_emoji} **{prenom} {nom[0] if nom else ''}., {age} ans**

📍 **Localisation**
   Ville: {ville}, {pays}
   Distance: {distance} km

⭐ **Compatibilité: {score}%** {score_emoji}

💬 **Bio**
{bio}

📝 **Description**
{description}

💕 **Recherche**
Type de relation: {type_relation}

📸 **Photo**
{photo if photo else 'Pas de photo'}

---

💡 **Actions possibles** :
- "Compare le {position} avec un autre profil"
- "Envoie un message à {prenom}"
- "Voir d'autres profils"
"""
    
    def search_profiles_by_criteria(
        self,
        user_id: str = None,
        city: str = None,
        min_age: int = None,
        max_age: int = None,
        gender: str = None,
        limit: int = 10
    ) -> List[Dict]:
        """Recherche des profils selon des critères spécifiques"""
        try:
            profiles = self.db.search_profiles(
                user_id=user_id,
                city=city,
                min_age=min_age,
                max_age=max_age,
                gender=gender,
                limit=limit
            )
            
            logger.info(f"✅ {len(profiles)} profils trouvés avec critères")
            return profiles
            
        except Exception as e:
            logger.error(f"❌ Erreur recherche profils: {e}")
            return []
    
    def parse_search_criteria(self, query: str) -> Dict:
        """Parse une requête pour extraire les critères de recherche"""
        query_lower = query.lower()
        criteria = {}
        
        # Extraire la ville
        cities = ["paris", "lyon", "marseille", "toulouse", "nice", "nantes", "bordeaux"]
        for city in cities:
            if city in query_lower:
                criteria["city"] = city.capitalize()
                break
        
        # Extraire l'âge
        import re
        
        # Pattern: "entre X et Y ans"
        age_pattern = r'entre (\d+) et (\d+) ans'
        match = re.search(age_pattern, query_lower)
        if match:
            criteria["min_age"] = int(match.group(1))
            criteria["max_age"] = int(match.group(2))
        
        # Pattern: "moins de X ans"
        age_pattern2 = r'moins de (\d+) ans'
        match = re.search(age_pattern2, query_lower)
        if match:
            criteria["max_age"] = int(match.group(1))
        
        # Pattern: "plus de X ans"
        age_pattern3 = r'plus de (\d+) ans'
        match = re.search(age_pattern3, query_lower)
        if match:
            criteria["min_age"] = int(match.group(1))
        
        # Extraire le genre
        if "homme" in query_lower or "hommes" in query_lower:
            criteria["gender"] = "M"
        elif "femme" in query_lower or "femmes" in query_lower:
            criteria["gender"] = "F"
        
        # Extraire la distance
        distance_pattern = r'(\d+)\s*km'
        match = re.search(distance_pattern, query_lower)
        if match:
            criteria["max_distance_km"] = int(match.group(1))
        
        # Distance par défaut
        if "près de moi" in query_lower or "proximité" in query_lower:
            criteria["max_distance_km"] = 20
        elif "région" in query_lower:
            criteria["max_distance_km"] = 50
        
        return criteria


# Instance globale
_matching_service = None

def get_matching_service() -> MatchingService:
    """Retourne l'instance unique du service de matching"""
    global _matching_service
    if _matching_service is None:
        _matching_service = MatchingService()
    return _matching_service

