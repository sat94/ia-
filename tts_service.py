"""Service TTS avec Edge TTS pour les 4 experts"""
import edge_tts
import os
import base64
from config import EXPERTS
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class TTSService:
    """Service de synthèse vocale avec Edge TTS"""
    
    def __init__(self):
        """Initialise le service TTS"""
        self.experts_voices = {
            expert_id: expert_data['voice']
            for expert_id, expert_data in EXPERTS.items()
        }
        logger.info("✅ Service TTS initialisé avec 4 voix d'experts")
    
    async def text_to_speech(self, text: str, expert_id: str, output_file: str = None) -> str:
        """
        Convertit du texte en audio avec la voix de l'expert
        
        Args:
            text: Le texte à convertir
            expert_id: ID de l'expert (sexologie, psychologie, etc.)
            output_file: Chemin du fichier de sortie (optionnel)
            
        Returns:
            str: Chemin du fichier audio généré ou base64 si pas de fichier
        """
        if expert_id not in self.experts_voices:
            logger.error(f"Expert {expert_id} inconnu")
            # Fallback global : coach de séduction (Denise)
            expert_id = 'seduction'
        
        voice = self.experts_voices[expert_id]
        
        # Générer un nom de fichier si non fourni
        if output_file is None:
            output_file = f"audio_{expert_id}_{hash(text)}.mp3"
        
        try:
            # Créer le dossier audio s'il n'existe pas
            os.makedirs("audio", exist_ok=True)
            output_path = os.path.join("audio", output_file)
            
            # Générer l'audio
            communicate = edge_tts.Communicate(text, voice)
            await communicate.save(output_path)
            
            logger.info(f"✅ Audio généré: {output_path} (voix: {voice})")
            return output_path
            
        except Exception as e:
            logger.error(f"❌ Erreur TTS: {e}")
            return None
    
    async def text_to_speech_base64(self, text: str, expert_id: str) -> str:
        """
        Convertit du texte en audio et retourne en base64
        
        Args:
            text: Le texte à convertir
            expert_id: ID de l'expert
            
        Returns:
            str: Audio encodé en base64
        """
        # Générer l'audio
        audio_file = await self.text_to_speech(text, expert_id)
        
        if audio_file and os.path.exists(audio_file):
            # Lire et encoder en base64
            with open(audio_file, 'rb') as f:
                audio_data = f.read()
                audio_base64 = base64.b64encode(audio_data).decode('utf-8')
            
            # Supprimer le fichier temporaire
            os.remove(audio_file)
            
            return audio_base64
        
        return None
    
    def get_expert_voice(self, expert_id: str) -> str:
        """Retourne la voix associée à un expert"""
        # Par défaut, on utilise la voix du coach de séduction (Denise)
        return self.experts_voices.get(expert_id, self.experts_voices['seduction'])
    
    def list_available_voices(self):
        """Liste toutes les voix disponibles"""
        return self.experts_voices


# Instance globale du service TTS
_tts_instance = None


def get_tts_service():
    """Retourne l'instance singleton du service TTS"""
    global _tts_instance
    if _tts_instance is None:
        _tts_instance = TTSService()
    return _tts_instance




