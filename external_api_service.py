"""Service d'intégration avec les APIs externes (Ticketmaster, TMDb, Deezer, YouTube)"""
import requests
from typing import List, Dict
import logging
from config import TICKETMASTER_API_KEY, TMDB_API_KEY, YOUTUBE_API_KEY

logger = logging.getLogger(__name__)


class ExternalAPIService:
    
    def __init__(self):
        self.ticketmaster_key = TICKETMASTER_API_KEY
        self.tmdb_key = TMDB_API_KEY
        self.youtube_key = YOUTUBE_API_KEY
        self.deezer_base_url = "https://api.deezer.com"
        logger.info("✅ Service API externes initialisé")
    
    # ===== ÉVÉNEMENTS (Ticketmaster) =====
    
    def search_events(self, city: str = "Paris", keyword: str = "", limit: int = 5) -> List[Dict]:
        """Recherche d'événements via Ticketmaster"""
        try:
            if not self.ticketmaster_key:
                logger.warning("⚠️ Clé Ticketmaster manquante")
                return self._mock_events(city)
            
            url = "https://app.ticketmaster.com/discovery/v2/events.json"
            params = {
                "apikey": self.ticketmaster_key,
                "city": city,
                "keyword": keyword,
                "size": limit,
                "locale": "fr-FR"
            }
            
            response = requests.get(url, params=params, timeout=5)
            response.raise_for_status()
            
            data = response.json()
            events = []
            
            if "_embedded" in data and "events" in data["_embedded"]:
                for event in data["_embedded"]["events"][:limit]:
                    events.append({
                        "name": event.get("name", ""),
                        "date": event.get("dates", {}).get("start", {}).get("localDate", ""),
                        "venue": event.get("_embedded", {}).get("venues", [{}])[0].get("name", ""),
                        "url": event.get("url", ""),
                        "image": event.get("images", [{}])[0].get("url", "") if event.get("images") else ""
                    })
            
            logger.info(f"✅ {len(events)} événements trouvés pour {city}")
            return events
            
        except Exception as e:
            logger.error(f"❌ Erreur Ticketmaster: {e}")
            return self._mock_events(city)
    
    def _mock_events(self, city: str) -> List[Dict]:
        """Événements fictifs si API indisponible"""
        return [
            {
                "name": f"Concert Jazz à {city}",
                "date": "2025-11-15",
                "venue": "Olympia",
                "url": "https://example.com",
                "image": ""
            },
            {
                "name": f"Festival Rock à {city}",
                "date": "2025-11-20",
                "venue": "Zénith",
                "url": "https://example.com",
                "image": ""
            }
        ]
    
    # ===== FILMS (TMDb) =====
    
    def search_movies(self, query: str = "", limit: int = 5) -> List[Dict]:
        """Recherche de films via TMDb"""
        try:
            if not self.tmdb_key:
                logger.warning("⚠️ Clé TMDb manquante")
                return self._mock_movies()
            
            # Si pas de query, récupérer les films populaires
            if not query:
                url = "https://api.themoviedb.org/3/movie/now_playing"
                params = {
                    "api_key": self.tmdb_key,
                    "language": "fr-FR",
                    "region": "FR",
                    "page": 1
                }
            else:
                url = "https://api.themoviedb.org/3/search/movie"
                params = {
                    "api_key": self.tmdb_key,
                    "language": "fr-FR",
                    "query": query,
                    "page": 1
                }
            
            response = requests.get(url, params=params, timeout=5)
            response.raise_for_status()
            
            data = response.json()
            movies = []
            
            for movie in data.get("results", [])[:limit]:
                movies.append({
                    "title": movie.get("title", ""),
                    "release_date": movie.get("release_date", ""),
                    "overview": movie.get("overview", "")[:200] + "...",
                    "rating": movie.get("vote_average", 0),
                    "poster": f"https://image.tmdb.org/t/p/w500{movie.get('poster_path', '')}" if movie.get("poster_path") else ""
                })
            
            logger.info(f"✅ {len(movies)} films trouvés")
            return movies
            
        except Exception as e:
            logger.error(f"❌ Erreur TMDb: {e}")
            return self._mock_movies()
    
    def _mock_movies(self) -> List[Dict]:
        """Films fictifs si API indisponible"""
        return [
            {
                "title": "Film Populaire 1",
                "release_date": "2025-11-01",
                "overview": "Un film passionnant...",
                "rating": 7.5,
                "poster": ""
            },
            {
                "title": "Film Populaire 2",
                "release_date": "2025-11-08",
                "overview": "Une comédie hilarante...",
                "rating": 8.0,
                "poster": ""
            }
        ]
    
    # ===== MUSIQUE (Deezer) =====
    
    def search_music(self, artist: str = "", track: str = "", limit: int = 5) -> List[Dict]:
        """Recherche de musique via Deezer (API gratuite, pas de clé nécessaire)"""
        try:
            query = f"{artist} {track}".strip()
            
            if not query:
                # Top tracks du moment
                url = f"{self.deezer_base_url}/chart/0/tracks"
                params = {"limit": limit}
            else:
                # Recherche
                url = f"{self.deezer_base_url}/search/track"
                params = {"q": query, "limit": limit}
            
            response = requests.get(url, params=params, timeout=5)
            response.raise_for_status()
            
            data = response.json()
            tracks = []
            
            for track in data.get("data", [])[:limit]:
                tracks.append({
                    "title": track.get("title", ""),
                    "artist": track.get("artist", {}).get("name", ""),
                    "album": track.get("album", {}).get("title", ""),
                    "duration": track.get("duration", 0),
                    "preview": track.get("preview", ""),
                    "cover": track.get("album", {}).get("cover_medium", "")
                })
            
            logger.info(f"✅ {len(tracks)} titres trouvés")
            return tracks
            
        except Exception as e:
            logger.error(f"❌ Erreur Deezer: {e}")
            return self._mock_music(artist)
    
    def _mock_music(self, artist: str = "") -> List[Dict]:
        """Musique fictive si API indisponible"""
        return [
            {
                "title": f"Dernier titre de {artist}" if artist else "Titre Populaire 1",
                "artist": artist or "Artiste Populaire",
                "album": "Album 2025",
                "duration": 180,
                "preview": "",
                "cover": ""
            }
        ]
    
    # ===== VIDÉOS (YouTube) =====
    
    def search_videos(self, query: str, limit: int = 5) -> List[Dict]:
        """Recherche de vidéos via YouTube"""
        try:
            if not self.youtube_key:
                logger.warning("⚠️ Clé YouTube manquante")
                return self._mock_videos(query)
            
            url = "https://www.googleapis.com/youtube/v3/search"
            params = {
                "key": self.youtube_key,
                "q": query,
                "part": "snippet",
                "type": "video",
                "maxResults": limit,
                "regionCode": "FR",
                "relevanceLanguage": "fr"
            }
            
            response = requests.get(url, params=params, timeout=5)
            response.raise_for_status()
            
            data = response.json()
            videos = []
            
            for item in data.get("items", []):
                video_id = item.get("id", {}).get("videoId", "")
                snippet = item.get("snippet", {})
                
                videos.append({
                    "title": snippet.get("title", ""),
                    "channel": snippet.get("channelTitle", ""),
                    "description": snippet.get("description", "")[:200] + "...",
                    "thumbnail": snippet.get("thumbnails", {}).get("medium", {}).get("url", ""),
                    "url": f"https://www.youtube.com/watch?v={video_id}"
                })
            
            logger.info(f"✅ {len(videos)} vidéos trouvées")
            return videos
            
        except Exception as e:
            logger.error(f"❌ Erreur YouTube: {e}")
            return self._mock_videos(query)
    
    def _mock_videos(self, query: str) -> List[Dict]:
        """Vidéos fictives si API indisponible"""
        return [
            {
                "title": f"Vidéo sur {query}",
                "channel": "Chaîne Populaire",
                "description": "Une vidéo intéressante...",
                "thumbnail": "",
                "url": "https://youtube.com"
            }
        ]
    
    # ===== FORMATAGE DES RÉSULTATS =====
    
    def format_events_response(self, events: List[Dict]) -> str:
        """Formate la liste d'événements en texte"""
        if not events:
            return "Je n'ai trouvé aucun événement pour le moment."
        
        response = "Voici les événements que j'ai trouvés :\n\n"
        for i, event in enumerate(events, 1):
            response += f"{i}. **{event['name']}**\n"
            response += f"   📅 {event['date']}\n"
            response += f"   📍 {event['venue']}\n"
            if event['url']:
                response += f"   🔗 {event['url']}\n"
            response += "\n"
        
        return response
    
    def format_movies_response(self, movies: List[Dict]) -> str:
        """Formate la liste de films en texte"""
        if not movies:
            return "Je n'ai trouvé aucun film pour le moment."
        
        response = "Voici les films à l'affiche :\n\n"
        for i, movie in enumerate(movies, 1):
            response += f"{i}. **{movie['title']}** ⭐ {movie['rating']}/10\n"
            response += f"   📅 Sortie : {movie['release_date']}\n"
            response += f"   📝 {movie['overview']}\n\n"
        
        return response
    
    def format_music_response(self, tracks: List[Dict]) -> str:
        """Formate la liste de musique en texte"""
        if not tracks:
            return "Je n'ai trouvé aucune musique."
        
        response = "Voici les titres que j'ai trouvés :\n\n"
        for i, track in enumerate(tracks, 1):
            response += f"{i}. **{track['title']}** - {track['artist']}\n"
            response += f"   💿 Album : {track['album']}\n"
            if track['preview']:
                response += f"   🎵 Extrait : {track['preview']}\n"
            response += "\n"
        
        return response
    
    def format_videos_response(self, videos: List[Dict]) -> str:
        """Formate la liste de vidéos en texte"""
        if not videos:
            return "Je n'ai trouvé aucune vidéo."
        
        response = "Voici les vidéos que j'ai trouvées :\n\n"
        for i, video in enumerate(videos, 1):
            response += f"{i}. **{video['title']}**\n"
            response += f"   📺 Chaîne : {video['channel']}\n"
            response += f"   🔗 {video['url']}\n\n"
        
        return response

