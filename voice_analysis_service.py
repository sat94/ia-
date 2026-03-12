"""Service d'analyse vocale pour détection d'état émotionnel via features audio (librosa)"""
import logging
import base64
import io
import subprocess
import tempfile
import os
import numpy as np
from typing import Optional, Dict, Tuple
from datetime import datetime
import asyncpg
import asyncio

from config import DB_NAME, DB_USER, DB_PASSWORD, DB_HOST, DB_PORT

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

EMOTION_LABELS = {
    "happy": "Joyeux",
    "sad": "Triste",
    "angry": "En colère",
    "fearful": "Anxieux",
    "surprised": "Surpris",
    "calm": "Calme",
    "neutral": "Neutre",
    "stressed": "Stressé",
    "excited": "Excité",
    "tired": "Fatigué",
}

EMOTION_DESCRIPTIONS = {
    "happy": "L'utilisateur semble joyeux et de bonne humeur",
    "sad": "L'utilisateur semble triste ou mélancolique",
    "angry": "L'utilisateur semble irrité ou en colère",
    "fearful": "L'utilisateur semble anxieux ou inquiet",
    "surprised": "L'utilisateur semble surpris ou étonné",
    "calm": "L'utilisateur est calme et posé",
    "neutral": "L'utilisateur est dans un état neutre",
    "stressed": "L'utilisateur semble stressé ou sous pression",
    "excited": "L'utilisateur semble enthousiaste et excité",
    "tired": "L'utilisateur semble fatigué ou las",
}


class VoiceAnalysisService:

    def __init__(self):
        self.dsn = f"postgresql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"
        self.pool: Optional[asyncpg.Pool] = None
        self._librosa = None

    async def _ensure_pool(self):
        if self.pool is None or self.pool._closed:
            self.pool = await asyncpg.create_pool(
                self.dsn, min_size=1, max_size=5, command_timeout=10
            )

    def _get_librosa(self):
        if self._librosa is None:
            import librosa
            self._librosa = librosa
        return self._librosa

    def _decode_audio(self, audio_b64: str, audio_format: str = "webm") -> Optional[np.ndarray]:
        try:
            audio_bytes = base64.b64decode(audio_b64)

            if audio_format in ("wav", "wave"):
                librosa = self._get_librosa()
                y, sr = librosa.load(io.BytesIO(audio_bytes), sr=16000, mono=True)
                return y

            with tempfile.NamedTemporaryFile(suffix=f".{audio_format}", delete=False) as tmp_in:
                tmp_in.write(audio_bytes)
                tmp_in_path = tmp_in.name

            tmp_out_path = tmp_in_path + ".wav"
            try:
                subprocess.run(
                    ["ffmpeg", "-y", "-i", tmp_in_path, "-ar", "16000", "-ac", "1", "-f", "wav", tmp_out_path],
                    capture_output=True, timeout=10
                )
                librosa = self._get_librosa()
                y, sr = librosa.load(tmp_out_path, sr=16000, mono=True)
                return y
            finally:
                for p in (tmp_in_path, tmp_out_path):
                    if os.path.exists(p):
                        os.unlink(p)

        except Exception as e:
            logger.error(f"Audio decode error: {e}")
            return None

    def _extract_features(self, y: np.ndarray, sr: int = 16000) -> Dict:
        librosa = self._get_librosa()

        pitches, magnitudes = librosa.piptrack(y=y, sr=sr, fmin=50, fmax=500)
        pitch_values = []
        for t in range(pitches.shape[1]):
            idx = magnitudes[:, t].argmax()
            pitch = pitches[idx, t]
            if pitch > 0:
                pitch_values.append(pitch)

        pitch_mean = float(np.mean(pitch_values)) if pitch_values else 0.0
        pitch_std = float(np.std(pitch_values)) if pitch_values else 0.0
        pitch_range = float(np.ptp(pitch_values)) if pitch_values else 0.0

        rms = librosa.feature.rms(y=y)[0]
        energy_mean = float(np.mean(rms))
        energy_std = float(np.std(rms))
        energy_max = float(np.max(rms))

        mfccs = librosa.feature.mfcc(y=y, sr=sr, n_mfcc=13)
        mfcc_means = [float(np.mean(mfccs[i])) for i in range(13)]
        mfcc_stds = [float(np.std(mfccs[i])) for i in range(13)]

        zcr = librosa.feature.zero_crossing_rate(y)[0]
        zcr_mean = float(np.mean(zcr))

        onset_env = librosa.onset.onset_strength(y=y, sr=sr)
        tempo = float(librosa.feature.tempo(onset_envelope=onset_env, sr=sr)[0])

        spec_cent = librosa.feature.spectral_centroid(y=y, sr=sr)[0]
        spectral_centroid_mean = float(np.mean(spec_cent))

        spec_bw = librosa.feature.spectral_bandwidth(y=y, sr=sr)[0]
        spectral_bandwidth_mean = float(np.mean(spec_bw))

        return {
            "pitch_mean": pitch_mean,
            "pitch_std": pitch_std,
            "pitch_range": pitch_range,
            "energy_mean": energy_mean,
            "energy_std": energy_std,
            "energy_max": energy_max,
            "mfcc_means": mfcc_means,
            "mfcc_stds": mfcc_stds,
            "zcr_mean": zcr_mean,
            "tempo": tempo,
            "spectral_centroid": spectral_centroid_mean,
            "spectral_bandwidth": spectral_bandwidth_mean,
            "duration": float(len(y) / sr),
        }

    def _classify_emotion(self, features: Dict) -> Tuple[str, float, Dict[str, float]]:
        scores = {
            "happy": 0.0,
            "sad": 0.0,
            "angry": 0.0,
            "fearful": 0.0,
            "surprised": 0.0,
            "calm": 0.0,
            "neutral": 0.0,
            "stressed": 0.0,
            "excited": 0.0,
            "tired": 0.0,
        }

        pitch = features["pitch_mean"]
        pitch_var = features["pitch_std"]
        energy = features["energy_mean"]
        energy_var = features["energy_std"]
        tempo = features["tempo"]
        zcr = features["zcr_mean"]
        spectral_centroid = features["spectral_centroid"]

        if pitch > 200 and energy > 0.05 and tempo > 120:
            scores["happy"] += 0.4
            scores["excited"] += 0.3
        if pitch > 250 and pitch_var > 40:
            scores["happy"] += 0.2
            scores["surprised"] += 0.3

        if pitch < 150 and energy < 0.02 and tempo < 90:
            scores["sad"] += 0.5
            scores["tired"] += 0.3
        if energy < 0.015:
            scores["sad"] += 0.2
            scores["tired"] += 0.2

        if energy > 0.08 and pitch > 180 and zcr > 0.1:
            scores["angry"] += 0.5
        if energy_var > 0.03 and spectral_centroid > 3000:
            scores["angry"] += 0.2
            scores["stressed"] += 0.2

        if pitch_var > 50 and energy_var > 0.02 and tempo > 100:
            scores["fearful"] += 0.3
            scores["stressed"] += 0.3
        if zcr > 0.08 and energy_var > 0.025:
            scores["stressed"] += 0.2

        if pitch_var > 60 and energy > 0.04:
            scores["surprised"] += 0.3

        if 130 <= pitch <= 200 and 0.02 <= energy <= 0.05 and pitch_var < 30:
            scores["calm"] += 0.4
        if 80 <= tempo <= 110 and energy_var < 0.015:
            scores["calm"] += 0.3

        if energy > 0.06 and tempo > 130 and pitch > 200:
            scores["excited"] += 0.4

        if energy < 0.025 and tempo < 85 and pitch < 140:
            scores["tired"] += 0.4

        base_neutral = 0.3
        extreme_count = sum(1 for v in scores.values() if v > 0.3)
        if extreme_count == 0:
            scores["neutral"] += base_neutral + 0.2
        else:
            scores["neutral"] += base_neutral * 0.5

        total = sum(scores.values())
        if total > 0:
            scores = {k: v / total for k, v in scores.items()}

        primary_emotion = max(scores, key=scores.get)
        confidence = scores[primary_emotion]

        return primary_emotion, confidence, scores

    async def analyze_audio(self, audio_b64: str, audio_format: str = "webm") -> Optional[Dict]:
        try:
            y = await asyncio.get_event_loop().run_in_executor(
                None, self._decode_audio, audio_b64, audio_format
            )
            if y is None or len(y) < 1600:
                logger.warning("Audio trop court ou invalide pour l'analyse")
                return None

            features = await asyncio.get_event_loop().run_in_executor(
                None, self._extract_features, y
            )

            emotion, confidence, all_scores = self._classify_emotion(features)

            top_3 = sorted(all_scores.items(), key=lambda x: x[1], reverse=True)[:3]

            result = {
                "emotion": emotion,
                "emotion_label": EMOTION_LABELS.get(emotion, emotion),
                "confidence": round(confidence, 3),
                "description": EMOTION_DESCRIPTIONS.get(emotion, ""),
                "top_emotions": [
                    {"emotion": e, "label": EMOTION_LABELS.get(e, e), "score": round(s, 3)}
                    for e, s in top_3
                ],
                "features": {
                    "pitch_mean": round(features["pitch_mean"], 1),
                    "pitch_variability": round(features["pitch_std"], 1),
                    "energy_mean": round(features["energy_mean"], 4),
                    "tempo": round(features["tempo"], 1),
                    "speech_duration": round(features["duration"], 2),
                },
                "analyzed_at": datetime.now().isoformat(),
            }

            return result

        except Exception as e:
            logger.error(f"Voice analysis error: {e}")
            return None

    async def analyze_and_store(self, user_id: int, audio_b64: str, audio_format: str = "webm", session_id: str = None) -> Optional[Dict]:
        result = await self.analyze_audio(audio_b64, audio_format)
        if not result:
            return None

        await self._store_emotion(user_id, result, session_id)
        return result

    async def _store_emotion(self, user_id: int, result: Dict, session_id: str = None):
        await self._ensure_pool()
        try:
            await self.pool.execute(
                """
                INSERT INTO user_emotions 
                (user_id, emotion, confidence, top_emotions, audio_features, session_id)
                VALUES ($1, $2, $3, $4::jsonb, $5::jsonb, $6)
                """,
                user_id,
                result["emotion"],
                result["confidence"],
                __import__("json").dumps(result["top_emotions"]),
                __import__("json").dumps(result["features"]),
                session_id,
            )
        except Exception as e:
            logger.error(f"Store emotion error: {e}")

    async def get_user_emotion_history(self, user_id: int, limit: int = 20) -> list:
        await self._ensure_pool()
        try:
            rows = await self.pool.fetch(
                """
                SELECT emotion, confidence, top_emotions, audio_features, 
                       session_id, created_at
                FROM user_emotions
                WHERE user_id = $1
                ORDER BY created_at DESC
                LIMIT $2
                """,
                user_id, limit,
            )
            return [dict(r) for r in rows]
        except Exception as e:
            logger.error(f"Get emotion history error: {e}")
            return []

    async def get_current_emotion(self, user_id: int) -> Optional[Dict]:
        await self._ensure_pool()
        try:
            row = await self.pool.fetchrow(
                """
                SELECT emotion, confidence, top_emotions, created_at
                FROM user_emotions
                WHERE user_id = $1
                ORDER BY created_at DESC
                LIMIT 1
                """,
                user_id,
            )
            if row:
                return dict(row)
            return None
        except Exception as e:
            logger.error(f"Get current emotion error: {e}")
            return None

    async def get_emotion_summary(self, user_id: int) -> Dict:
        await self._ensure_pool()
        try:
            rows = await self.pool.fetch(
                """
                SELECT emotion, COUNT(*) as count, AVG(confidence) as avg_confidence
                FROM user_emotions
                WHERE user_id = $1
                GROUP BY emotion
                ORDER BY count DESC
                """,
                user_id,
            )
            total = sum(r["count"] for r in rows) if rows else 0
            return {
                "total_analyses": total,
                "emotions": [
                    {
                        "emotion": r["emotion"],
                        "label": EMOTION_LABELS.get(r["emotion"], r["emotion"]),
                        "count": r["count"],
                        "percentage": round(r["count"] / total * 100, 1) if total else 0,
                        "avg_confidence": round(float(r["avg_confidence"]), 3),
                    }
                    for r in rows
                ],
            }
        except Exception as e:
            logger.error(f"Get emotion summary error: {e}")
            return {"total_analyses": 0, "emotions": []}

    def emotion_to_context(self, emotion_result: Dict) -> str:
        if not emotion_result:
            return ""
        emotion = emotion_result.get("emotion", "neutral")
        label = EMOTION_LABELS.get(emotion, emotion)
        confidence = emotion_result.get("confidence", 0)
        if confidence < 0.2:
            return ""
        return (
            f"[Etat emotionnel detecte: {label} (confiance: {confidence:.0%}). "
            f"Adapte ton ton et ta reponse en consequence. "
            f"Si la personne semble triste ou stressée, sois plus douce et empathique. "
            f"Si elle semble joyeuse, partage son enthousiasme.]"
        )

    async def close(self):
        if self.pool:
            await self.pool.close()


_voice_instance = None


def get_voice_analysis_service():
    global _voice_instance
    if _voice_instance is None:
        _voice_instance = VoiceAnalysisService()
    return _voice_instance
