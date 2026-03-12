"""
Classifier d'intentions ML hybride pour le français.

Architecture à 3 niveaux (du plus rapide au plus lent):
  1. Keyword exact match    → ~0.0001s (salutations, au_revoir, etc.)
  2. SVM/LogisticRegression → ~0.001s  (classifieur entraîné sur embeddings)
  3. Cosine similarity      → ~0.05s   (fallback si ML peu confiant)

Utilise scikit-learn (SVM + LogisticRegression) entraîné sur les embeddings CamemBERT
des exemples définis dans INTENT_CATEGORIES.
"""
import time
import logging
import numpy as np
import joblib
import os
from typing import Optional, Dict
from sklearn.svm import LinearSVC
from sklearn.linear_model import LogisticRegression
from sklearn.calibration import CalibratedClassifierCV
from sklearn.preprocessing import LabelEncoder
from sklearn.metrics.pairwise import cosine_similarity
from config import INTENT_CATEGORIES

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

MODEL_CACHE_DIR = os.path.join(os.path.dirname(__file__), ".model_cache")
SVM_PATH = os.path.join(MODEL_CACHE_DIR, "svm_intent.joblib")
LR_PATH = os.path.join(MODEL_CACHE_DIR, "lr_intent.joblib")
LABEL_ENC_PATH = os.path.join(MODEL_CACHE_DIR, "label_encoder.joblib")
EMBEDDINGS_PATH = os.path.join(MODEL_CACHE_DIR, "category_embeddings.joblib")

KEYWORD_MAP = {}
for cat, examples in INTENT_CATEGORIES.items():
    for ex in examples:
        normalized = ex.strip().lower()
        KEYWORD_MAP[normalized] = cat


class IntentClassifier:

    def __init__(self, embedding_model=None):
        self.embedding_model = embedding_model
        self.categories = INTENT_CATEGORIES

        self.svm_model = None
        self.lr_model = None
        self.label_encoder = None
        self.embeddings_categories = {}
        self._is_trained = False

        if self.embedding_model:
            self._init_models()

    def set_embedding_model(self, model):
        self.embedding_model = model
        if not self._is_trained:
            self._init_models()

    def _init_models(self):
        if self._load_cached_models():
            logger.info("ML classifiers loaded from cache")
            self._is_trained = True
            return

        logger.info("Training ML classifiers from scratch...")
        self._train_models()
        self._save_cached_models()
        self._is_trained = True

    def _load_cached_models(self) -> bool:
        try:
            if all(os.path.exists(p) for p in [SVM_PATH, LR_PATH, LABEL_ENC_PATH, EMBEDDINGS_PATH]):
                self.svm_model = joblib.load(SVM_PATH)
                self.lr_model = joblib.load(LR_PATH)
                self.label_encoder = joblib.load(LABEL_ENC_PATH)
                self.embeddings_categories = joblib.load(EMBEDDINGS_PATH)
                logger.info("ML models loaded from cache")
                return True
        except Exception as e:
            logger.warning(f"Cache load failed: {e}")
        return False

    def _save_cached_models(self):
        try:
            os.makedirs(MODEL_CACHE_DIR, exist_ok=True)
            joblib.dump(self.svm_model, SVM_PATH)
            joblib.dump(self.lr_model, LR_PATH)
            joblib.dump(self.label_encoder, LABEL_ENC_PATH)
            joblib.dump(self.embeddings_categories, EMBEDDINGS_PATH)
            logger.info(f"ML models cached to {MODEL_CACHE_DIR}")
        except Exception as e:
            logger.warning(f"Cache save failed: {e}")

    def _train_models(self):
        all_texts = []
        all_labels = []
        for cat, examples in self.categories.items():
            all_texts.extend(examples)
            all_labels.extend([cat] * len(examples))

        logger.info(f"Encoding {len(all_texts)} training examples...")
        X = self.embedding_model.encode(all_texts, show_progress_bar=False, convert_to_numpy=True, batch_size=64)

        self.label_encoder = LabelEncoder()
        y = self.label_encoder.fit_transform(all_labels)

        logger.info("Training LinearSVC...")
        base_svm = LinearSVC(C=1.0, max_iter=5000, class_weight='balanced')
        self.svm_model = CalibratedClassifierCV(base_svm, cv=3)
        self.svm_model.fit(X, y)

        logger.info("Training LogisticRegression...")
        self.lr_model = LogisticRegression(C=1.0, max_iter=2000, class_weight='balanced')
        self.lr_model.fit(X, y)

        for cat, examples in self.categories.items():
            self.embeddings_categories[cat] = self.embedding_model.encode(
                examples, show_progress_bar=False, convert_to_numpy=True
            )

        svm_score = self.svm_model.score(X, y)
        lr_score = self.lr_model.score(X, y)
        logger.info(f"SVM accuracy: {svm_score:.2%} | LR accuracy: {lr_score:.2%}")

    def classify(self, texte: str, seuil: float = 0.5, top_k: int = 3) -> Dict:
        t0 = time.perf_counter()

        keyword_result = self._keyword_match(texte)
        if keyword_result:
            elapsed = time.perf_counter() - t0
            logger.info(f"KEYWORD match: {keyword_result} in {elapsed*1000:.2f}ms")
            return {
                'texte': texte,
                'intention': keyword_result,
                'score': 0.99,
                'exemple_proche': texte,
                'valide': True,
                'confiance': 'haute',
                'method': 'keyword',
                'latency_ms': round(elapsed * 1000, 2),
                f'top_{top_k}': [{'intention': keyword_result, 'score': 0.99, 'exemple': texte}]
            }

        if self._is_trained and self.embedding_model:
            return self._ml_classify(texte, seuil, top_k, t0)

        return self._cosine_classify(texte, seuil, top_k, t0)

    def _keyword_match(self, texte: str) -> Optional[str]:
        normalized = texte.strip().lower()
        if normalized in KEYWORD_MAP:
            return KEYWORD_MAP[normalized]

        simple_patterns = {
            'salutation': {'bonjour', 'salut', 'coucou', 'bonsoir', 'hey', 'hello', 'hi', 'yo', 'wesh'},
            'au_revoir': {'bye', 'ciao', 'a+', 'a plus', 'adieu'},
            'remerciement': {'merci', 'thanks', 'thx'},
            'comment_ca_va': {'ca va', 'cv', 'la forme', 'quoi de neuf'},
            'demander_heure': {'quelle heure', 'heure', "l'heure"},
            'demander_date': {'quel jour', 'quelle date', 'la date'},
            'aide': {'aide', 'help', 'menu'},
            'blague': {'blague', 'joke', 'humour'},
            'affirmatif': {'oui', 'ouais', 'ok', 'yes', 'yep', 'ouep'},
            'negatif': {'non', 'nan', 'nope'},
            'compliment': {'bravo', 'parfait', 'excellent'},
            'insulte': {'idiot', 'stupide', 'débile', 'crétin', 'imbécile'},
        }
        for cat, keywords in simple_patterns.items():
            if normalized in keywords:
                return cat
        return None

    def _ml_classify(self, texte: str, seuil: float, top_k: int, t0: float) -> Dict:
        emb = self.embedding_model.encode([texte], convert_to_numpy=True)

        svm_proba = self.svm_model.predict_proba(emb)[0]
        lr_proba = self.lr_model.predict_proba(emb)[0]

        ensemble_proba = 0.6 * svm_proba + 0.4 * lr_proba

        top_indices = np.argsort(ensemble_proba)[::-1][:top_k]
        best_idx = top_indices[0]
        best_label = self.label_encoder.inverse_transform([best_idx])[0]
        best_score = float(ensemble_proba[best_idx])

        if best_score < 0.3 and self.embeddings_categories:
            return self._cosine_classify(texte, seuil, top_k, t0, precomputed_emb=emb)

        top_results = []
        for idx in top_indices:
            label = self.label_encoder.inverse_transform([idx])[0]
            closest = self._find_closest_example(emb[0], label)
            top_results.append({
                'intention': label,
                'score': float(ensemble_proba[idx]),
                'exemple': closest
            })

        elapsed = time.perf_counter() - t0
        logger.info(f"ML classify: {best_label} ({best_score:.2%}) in {elapsed*1000:.2f}ms")

        return {
            'texte': texte,
            'intention': best_label,
            'score': best_score,
            'exemple_proche': top_results[0]['exemple'],
            'valide': best_score > seuil,
            'confiance': self._get_confiance(best_score),
            'method': 'ml_ensemble',
            'latency_ms': round(elapsed * 1000, 2),
            f'top_{top_k}': top_results
        }

    def _cosine_classify(self, texte: str, seuil: float, top_k: int, t0: float, precomputed_emb=None) -> Dict:
        if precomputed_emb is not None:
            emb_texte = precomputed_emb
        else:
            emb_texte = self.embedding_model.encode([texte], convert_to_numpy=True)

        resultats = {}
        for categorie, emb_exemples in self.embeddings_categories.items():
            similarities = cosine_similarity(emb_texte, emb_exemples)[0]
            max_sim = float(np.max(similarities))
            best_idx = int(np.argmax(similarities))
            resultats[categorie] = {
                'score': max_sim,
                'exemple_proche': self.categories[categorie][best_idx]
            }

        resultats_tries = sorted(resultats.items(), key=lambda x: x[1]['score'], reverse=True)
        meilleure = resultats_tries[0]

        elapsed = time.perf_counter() - t0
        logger.info(f"COSINE classify: {meilleure[0]} ({meilleure[1]['score']:.2%}) in {elapsed*1000:.2f}ms")

        return {
            'texte': texte,
            'intention': meilleure[0],
            'score': meilleure[1]['score'],
            'exemple_proche': meilleure[1]['exemple_proche'],
            'valide': meilleure[1]['score'] > seuil,
            'confiance': self._get_confiance(meilleure[1]['score']),
            'method': 'cosine_similarity',
            'latency_ms': round(elapsed * 1000, 2),
            f'top_{top_k}': [
                {'intention': cat, 'score': info['score'], 'exemple': info['exemple_proche']}
                for cat, info in resultats_tries[:top_k]
            ]
        }

    def _find_closest_example(self, emb: np.ndarray, category: str) -> str:
        if category in self.embeddings_categories:
            cat_embs = self.embeddings_categories[category]
            sims = cosine_similarity([emb], cat_embs)[0]
            best_idx = int(np.argmax(sims))
            return self.categories[category][best_idx]
        return ""

    def _get_confiance(self, score: float) -> str:
        if score > 0.8:
            return 'haute'
        elif score > 0.6:
            return 'moyenne'
        else:
            return 'faible'

    def route_to_expert(self, intention: str) -> str:
        routing = {
            'question_sexologie': 'sexologie',
            'question_psychologie': 'psychologie',
            'question_developpement': 'developpement_personnel',
            'question_seduction': 'seduction',
        }
        return routing.get(intention, 'general')

    INTENTS_NO_AI = {
        'salutation', 'au_revoir', 'remerciement',
        'comment_ca_va', 'qui_es_tu',
        'demander_heure', 'demander_date',
        'aide', 'blague', 'compliment', 'insulte', 'ennui',
        'affirmatif', 'negatif',
        'recherche_evenement', 'recherche_cinema', 'recherche_musique', 'recherche_video',
        'recherche_profil', 'profil_rencontre', 'recherche_par_nom',
        'question_suivi', 'comparer', 'rappel_historique',
        'envoyer_message', 'compatibilite',
        'coaching_contextuel', 'icebreaker', 'review_profil',
        'creer_post',
        'liste_experts', 'consultation_usage',
        'consultation_historique', 'consultation_sessions',
        'consultation_emotion', 'consultation_personnalite',
    }

    INTENTS_NEED_AI = {
        'question_sexologie', 'question_psychologie',
        'question_developpement', 'question_seduction',
        'conversation', 'question_generale',
    }

    def needs_ai(self, intention: str) -> bool:
        return intention in self.INTENTS_NEED_AI

    def needs_expert(self, intention: str) -> bool:
        return intention in self.INTENTS_NEED_AI


_classifier_instance = None


def get_classifier(embedding_model=None):
    global _classifier_instance
    if _classifier_instance is None:
        _classifier_instance = IntentClassifier(embedding_model)
    elif embedding_model and not _classifier_instance.embedding_model:
        _classifier_instance.set_embedding_model(embedding_model)
    return _classifier_instance
