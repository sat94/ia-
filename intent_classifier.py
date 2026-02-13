"""Classifier d'intentions ultra-performant en français avec CamemBERT"""
from sentence_transformers import SentenceTransformer
from sklearn.metrics.pairwise import cosine_similarity
import numpy as np
from config import INTENT_CATEGORIES
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class IntentClassifier:
    """Classifier d'intentions basé sur CamemBERT pour le français"""
    
    def __init__(self, model_name='dangvantuan/sentence-camembert-base'):
        """
        Initialise le classifier avec CamemBERT
        
        Args:
            model_name: Nom du modèle Sentence Transformer à utiliser
        """
        logger.info(f"🔄 Chargement du modèle {model_name}...")
        self.model = SentenceTransformer(model_name)
        
        # Catégories d'intentions
        self.categories = INTENT_CATEGORIES
        
        # Pré-calculer les embeddings des exemples
        logger.info("📊 Calcul des embeddings des catégories...")
        self.embeddings_categories = {}
        for categorie, exemples in self.categories.items():
            self.embeddings_categories[categorie] = self.model.encode(
                exemples,
                show_progress_bar=False,
                convert_to_numpy=True
            )
        
        logger.info("✅ Classifier d'intentions prêt!")
    
    def classify(self, texte: str, seuil: float = 0.5, top_k: int = 3):
        """
        Classifie un texte selon son intention
        
        Args:
            texte: Le texte à classifier
            seuil: Score minimum pour considérer une intention valide
            top_k: Nombre d'intentions à retourner
            
        Returns:
            dict: Résultat de la classification
        """
        # Encoder le texte
        emb_texte = self.model.encode([texte], convert_to_numpy=True)
        
        # Comparer avec chaque catégorie
        resultats = {}
        for categorie, emb_exemples in self.embeddings_categories.items():
            # Similarité avec tous les exemples
            similarities = cosine_similarity(emb_texte, emb_exemples)[0]
            max_sim = np.max(similarities)
            best_idx = np.argmax(similarities)
            
            resultats[categorie] = {
                'score': float(max_sim),
                'exemple_proche': self.categories[categorie][best_idx]
            }
        
        # Trier par score
        resultats_tries = sorted(
            resultats.items(),
            key=lambda x: x[1]['score'],
            reverse=True
        )
        
        # Meilleure intention
        meilleure = resultats_tries[0]
        
        return {
            'texte': texte,
            'intention': meilleure[0],
            'score': meilleure[1]['score'],
            'exemple_proche': meilleure[1]['exemple_proche'],
            'valide': meilleure[1]['score'] > seuil,
            'confiance': self._get_confiance(meilleure[1]['score']),
            f'top_{top_k}': [
                {
                    'intention': cat,
                    'score': info['score'],
                    'exemple': info['exemple_proche']
                }
                for cat, info in resultats_tries[:top_k]
            ]
        }
    
    def _get_confiance(self, score: float) -> str:
        """Retourne le niveau de confiance basé sur le score"""
        if score > 0.8:
            return 'haute'
        elif score > 0.6:
            return 'moyenne'
        else:
            return 'faible'
    
    def route_to_expert(self, intention: str) -> str:
        """
        Route une intention vers l'expert approprié
        
        Args:
            intention: L'intention détectée
            
        Returns:
            str: Nom de l'expert (clé dans EXPERTS)
        """
        # Mapping intentions -> experts
        routing = {
            'question_sexologie': 'sexologie',
            'question_psychologie': 'psychologie',
            'question_developpement': 'developpement_personnel',
            'question_seduction': 'seduction',
        }
        
        # Si l'intention correspond à un expert spécifique
        if intention in routing:
            return routing[intention]
        
        # Sinon, retourner un expert par défaut
        # 👉 On utilise le coach de séduction comme expert "de base"
        #    (par exemple pour les salutations, questions générales, etc.)
        return 'seduction'
    
    def needs_expert(self, intention: str) -> bool:
        """ 
        Détermine si une intention doit être traitée comme **simple** ou **complexe**.

        Les intentions "simples" (salutation, remerciement, etc.)
        sont désormais également gérées par l'IA (Ollama), mais avec
        un traitement légèrement différent dans `main.py`.

        Cette méthode est donc utilisée uniquement pour router la logique
        (branche "simple" vs "expert") et non plus pour décider d'utiliser
        ou non un modèle IA.
        """
        simple_intents = [
            'salutation',
            'au_revoir',
            'remerciement',
            'comment_ca_va'
        ]

        return intention not in simple_intents


# Instance globale du classifier
_classifier_instance = None


def get_classifier():
    """Retourne l'instance singleton du classifier"""
    global _classifier_instance
    if _classifier_instance is None:
        _classifier_instance = IntentClassifier()
    return _classifier_instance




