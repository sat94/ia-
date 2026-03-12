"""Service de connexion et requêtes PostgreSQL pour MeetVoice"""
import psycopg2
from psycopg2.extras import RealDictCursor
import logging
from typing import List, Dict, Optional
from datetime import datetime, date
import math
from config import DB_NAME, DB_USER, DB_PASSWORD, DB_HOST, DB_PORT

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class DatabaseService:
    """Service pour interagir avec PostgreSQL"""
    
    def __init__(self):
        """Initialise la connexion à PostgreSQL"""
        self.connection_params = {
            'dbname': DB_NAME,
            'user': DB_USER,
            'password': DB_PASSWORD,
            'host': DB_HOST,
            'port': DB_PORT
        }
        self.conn = None
        self._connect()
    
    def _connect(self):
        """Établit la connexion à la base de données"""
        try:
            self.conn = psycopg2.connect(**self.connection_params)
            logger.info(f"✅ Connecté à PostgreSQL: {DB_NAME}")
        except Exception as e:
            logger.error(f"❌ Erreur connexion PostgreSQL: {e}")
            self.conn = None
    
    def _ensure_connection(self):
        """Vérifie et rétablit la connexion si nécessaire"""
        if self.conn is None or self.conn.closed:
            self._connect()
    
    def execute_query(self, query: str, params: tuple = None, fetch: bool = True) -> Optional[List[Dict]]:
        """Exécute une requête SQL"""
        self._ensure_connection()
        if not self.conn:
            return None
        
        try:
            with self.conn.cursor(cursor_factory=RealDictCursor) as cursor:
                cursor.execute(query, params)
                
                if fetch:
                    results = cursor.fetchall()
                    return [dict(row) for row in results]
                else:
                    self.conn.commit()
                    return None
        except Exception as e:
            logger.error(f"❌ Erreur requête SQL: {e}")
            self.conn.rollback()
            return None
    
    # ===== EXPLORATION DE LA BASE =====
    
    def get_all_tables(self) -> List[str]:
        """Liste toutes les tables de la base de données"""
        query = """
            SELECT table_name 
            FROM information_schema.tables 
            WHERE table_schema = 'public'
            ORDER BY table_name;
        """
        results = self.execute_query(query)
        if results:
            return [row['table_name'] for row in results]
        return []
    
    def get_table_schema(self, table_name: str) -> List[Dict]:
        """Récupère le schéma d'une table"""
        query = """
            SELECT 
                column_name,
                data_type,
                character_maximum_length,
                is_nullable,
                column_default
            FROM information_schema.columns
            WHERE table_name = %s
            ORDER BY ordinal_position;
        """
        return self.execute_query(query, (table_name,))
    
    def get_table_count(self, table_name: str) -> int:
        """Compte le nombre de lignes dans une table"""
        query = f"SELECT COUNT(*) as count FROM {table_name};"
        results = self.execute_query(query)
        if results:
            return results[0]['count']
        return 0
    
    def get_sample_data(self, table_name: str, limit: int = 5) -> List[Dict]:
        """Récupère des exemples de données d'une table"""
        query = f"SELECT * FROM {table_name} LIMIT %s;"
        return self.execute_query(query, (limit,))
    
    def explore_database(self) -> Dict:
        """Explore complètement la base de données"""
        logger.info("🔍 Exploration de la base de données...")
        
        tables = self.get_all_tables()
        exploration = {
            "database": DB_NAME,
            "total_tables": len(tables),
            "tables": {}
        }
        
        for table in tables:
            schema = self.get_table_schema(table)
            count = self.get_table_count(table)
            sample = self.get_sample_data(table, 2)
            
            exploration["tables"][table] = {
                "columns": schema,
                "row_count": count,
                "sample_data": sample
            }
            
            logger.info(f"  📋 {table}: {count} lignes, {len(schema)} colonnes")
        
        return exploration
    
    # ===== GESTION DES PROFILS =====

    def _add_age_field(self, profile: Dict) -> None:
        """Ajoute un champ 'age' calculé à partir de date_de_naissance si possible."""
        try:
            dob = profile.get("date_de_naissance")
            if not dob:
                return

            if isinstance(dob, datetime):
                birth_date = dob.date()
            elif isinstance(dob, date):
                birth_date = dob
            else:
                # Dernier recours: tenter un parse ISO
                birth_date = datetime.fromisoformat(str(dob)).date()

            today = date.today()
            age = today.year - birth_date.year - (
                (today.month, today.day) < (birth_date.month, birth_date.day)
            )
            profile["age"] = age
        except Exception:
            # En cas de format inattendu, on ignore simplement l'âge
            return

    def get_profile_by_id(self, profile_id: int) -> Optional[Dict]:
        """Récupère un profil par son ID"""
        query = """
            SELECT 
                c.*,
                c.ville AS location_city,
                c.pays AS country
            FROM compte_compte c
            WHERE c.id = %s
        """
        results = self.execute_query(query, (profile_id,))
        if not results:
            return None

        profile = results[0]
        # Ajouter l'âge calculé si possible
        self._add_age_field(profile)
        return profile
    
    def search_profiles(
        self, 
        user_id: int = None,
        city: str = None, 
        min_age: int = None, 
        max_age: int = None,
        gender: str = None,
        limit: int = 10
    ) -> List[Dict]:
        """Recherche des profils selon des critères"""
        conditions = []
        params = []
        
        # Exclure l'utilisateur actuel
        if user_id:
            conditions.append("id != %s")
            params.append(user_id)
        
        # Filtrer par ville
        if city:
            conditions.append("ville ILIKE %s")
            params.append(f"%{city}%")
        
        # Filtrer par âge :
        # La colonne "age" n'existe pas dans la base, on calcule donc
        # l'âge côté Python à partir de date_de_naissance plus bas.
        
        # Filtrer par genre
        if gender:
            conditions.append("sexe = %s")
            params.append(gender)
        
        where_clause = " AND ".join(conditions) if conditions else "1=1"
        query = f"""
            SELECT 
                c.*,
                c.ville AS location_city,
                c.pays AS country
            FROM compte_compte c
            WHERE {where_clause}
            LIMIT %s
        """
        params.append(limit)

        results = self.execute_query(query, tuple(params)) or []

        # Ajouter l'âge calculé et filtrer par âge côté Python si besoin
        for profile in results:
            self._add_age_field(profile)

        if min_age or max_age:
            filtered: List[Dict] = []
            for profile in results:
                age = profile.get("age")
                if age is None:
                    continue
                if min_age and age < min_age:
                    continue
                if max_age and age > max_age:
                    continue
                filtered.append(profile)
            results = filtered

        return results
    
    def calculate_distance(self, lat1: float, lon1: float, lat2: float, lon2: float) -> float:
        """Calcule la distance en km entre deux coordonnées GPS (formule de Haversine)"""
        R = 6371  # Rayon de la Terre en km
        
        dlat = math.radians(lat2 - lat1)
        dlon = math.radians(lon2 - lon1)
        
        a = (math.sin(dlat / 2) ** 2 + 
             math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * 
             math.sin(dlon / 2) ** 2)
        
        c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
        distance = R * c
        
        return round(distance, 2)
    
    def find_nearby_profiles(
        self, 
        user_lat: float, 
        user_lon: float, 
        max_distance_km: int = 50,
        user_id: int = None,
        limit: int = 10
    ) -> List[Dict]:
        """Trouve des profils à proximité géographique"""
        # Récupérer tous les profils avec leurs géolocalisations
        if user_id:
            query = """
                SELECT 
                    c.*,
                    c.ville AS location_city,
                    c.pays AS country
                FROM compte_compte c
                WHERE c.id != %s
            """
            profiles = self.execute_query(query, (user_id,))
        else:
            query = """
                SELECT 
                    c.*,
                    c.ville AS location_city,
                    c.pays AS country
                FROM compte_compte c
            """
            profiles = self.execute_query(query)
        
        if not profiles:
            return []

        # Ajouter un champ d'âge calculé si possible
        for profile in profiles:
            self._add_age_field(profile)
        
        # Calculer les distances et filtrer
        nearby = []
        for profile in profiles:
            # Vérifier si le profil a des coordonnées GPS
            if 'latitude' in profile and 'longitude' in profile:
                if profile['latitude'] and profile['longitude']:
                    distance = self.calculate_distance(
                        user_lat, user_lon,
                        float(profile['latitude']), float(profile['longitude'])
                    )
                    
                    if distance <= max_distance_km:
                        profile['distance_km'] = distance
                        nearby.append(profile)
        
        # Trier par distance
        nearby.sort(key=lambda x: x['distance_km'])
        
        return nearby[:limit]
    
    def _get_m2m_values(self, user_id, query: str) -> List[str]:
        results = self.execute_query(query, (user_id,))
        if results:
            key = list(results[0].keys())[0]
            return [row[key] for row in results]
        return []

    def get_user_interests(self, user_id) -> List[str]:
        results = self.execute_query("""
            SELECT interests FROM profiles WHERE user_id = %s
        """, (user_id,))
        if results and results[0]['interests']:
            return results[0]['interests']
        return []

    def get_user_languages(self, user_id) -> List[str]:
        return []

    def get_user_values(self, user_id) -> List[str]:
        return []

    def get_matching_score(self, user_profile: Dict, target_profile: Dict) -> float:
        """Calcule un score de compatibilité entre deux profils (0-100)"""
        score = 0.0
        max_score = 0.0

        # 1. Proximité géographique (25 points)
        max_score += 25
        if 'distance_km' in target_profile:
            distance = target_profile['distance_km']
            if distance <= 5:
                score += 25
            elif distance <= 10:
                score += 20
            elif distance <= 20:
                score += 15
            elif distance <= 50:
                score += 10
            else:
                score += 3

        # 2. Différence d'âge (15 points)
        max_score += 15
        if 'age' in user_profile and 'age' in target_profile:
            age_diff = abs(user_profile['age'] - target_profile['age'])
            if age_diff <= 2:
                score += 15
            elif age_diff <= 5:
                score += 12
            elif age_diff <= 10:
                score += 8
            else:
                score += 3

        # 3. Centres d'intérêt communs (30 points)
        max_score += 30
        user_interests = set(self.get_user_interests(user_profile.get('id')))
        target_interests = set(self.get_user_interests(target_profile.get('id')))

        if user_interests and target_interests:
            common_interests = user_interests & target_interests
            total_interests = user_interests | target_interests

            if total_interests:
                interest_ratio = len(common_interests) / len(total_interests)
                score += interest_ratio * 30

        # 4. Langues communes (15 points)
        max_score += 15
        user_languages = set(self.get_user_languages(user_profile.get('id')))
        target_languages = set(self.get_user_languages(target_profile.get('id')))

        if user_languages and target_languages:
            common_languages = user_languages & target_languages
            if common_languages:
                score += (len(common_languages) / max(len(user_languages), len(target_languages))) * 15

        # 5. Valeurs communes (15 points)
        max_score += 15
        user_values = set(self.get_user_values(user_profile.get('id')))
        target_values = set(self.get_user_values(target_profile.get('id')))

        if user_values and target_values:
            common_values = user_values & target_values
            if common_values:
                score += (len(common_values) / max(len(user_values), len(target_values))) * 15

        # Normaliser sur 100
        final_score = (score / max_score) * 100 if max_score > 0 else 0
        return round(final_score, 2)
    
    def _batch_load_user_data(self, user_ids: List[int]) -> Dict:
        """Charge toutes les données (interests) pour plusieurs users en 1 requête"""
        if not user_ids:
            return {'interests': {}}
        
        user_ids_tuple = tuple(user_ids)
        
        interests_map = {}
        results = self.execute_query("""
            SELECT user_id, interests
            FROM profiles
            WHERE user_id IN %s
        """, (user_ids_tuple,))
        
        if results:
            for row in results:
                uid = row['user_id']
                interests_map[uid] = row['interests'] or []
        
        return {
            'interests': interests_map
        }

    def get_matching_score_batch(
        self, 
        user_profile: Dict, 
        target_profile: Dict,
        user_data: Dict,
        target_data: Dict
    ) -> float:
        """Calcule un score de compatibilité avec données pré-chargées"""
        score = 0.0
        max_score = 0.0

        max_score += 30
        if 'distance_km' in target_profile:
            distance = target_profile['distance_km']
            if distance <= 5:
                score += 30
            elif distance <= 10:
                score += 24
            elif distance <= 20:
                score += 18
            elif distance <= 50:
                score += 12
            else:
                score += 5

        max_score += 20
        if 'age' in user_profile and 'age' in target_profile:
            age_diff = abs(user_profile['age'] - target_profile['age'])
            if age_diff <= 2:
                score += 20
            elif age_diff <= 5:
                score += 16
            elif age_diff <= 10:
                score += 10
            else:
                score += 4

        max_score += 50
        user_interests = set(user_data.get('interests', []))
        target_interests = set(target_data.get('interests', []))

        if user_interests and target_interests:
            common_interests = user_interests & target_interests
            total_interests = user_interests | target_interests

            if total_interests:
                interest_ratio = len(common_interests) / len(total_interests)
                score += interest_ratio * 50

        final_score = (score / max_score) * 100 if max_score > 0 else 0
        return round(final_score, 2)

    def find_best_matches(
        self,
        user_id: int,
        max_distance_km: int = 50,
        min_age: int = None,
        max_age: int = None,
        limit: int = 10
    ) -> List[Dict]:
        """Trouve les meilleurs profils compatibles"""
        user_profile = self.get_profile_by_id(user_id)
        
        if not user_profile:
            logger.error(f"❌ Profil utilisateur {user_id} introuvable")
            return []
        
        if 'latitude' not in user_profile or 'longitude' not in user_profile:
            logger.warning(f"⚠️ Profil {user_id} sans coordonnées GPS")
            return []
        
        nearby_profiles = self.find_nearby_profiles(
            float(user_profile['latitude']),
            float(user_profile['longitude']),
            max_distance_km,
            user_id,
            limit * 3
        )
        
        if min_age or max_age:
            filtered = []
            for profile in nearby_profiles:
                if 'age' in profile:
                    age = profile['age']
                    if min_age and age < min_age:
                        continue
                    if max_age and age > max_age:
                        continue
                    filtered.append(profile)
            nearby_profiles = filtered
        
        all_ids = [user_id] + [p.get('user_id', p.get('id')) for p in nearby_profiles]
        batch_data = self._batch_load_user_data(all_ids)
        
        user_data = {
            'interests': batch_data['interests'].get(user_id, [])
        }
        
        for profile in nearby_profiles:
            profile_user_id = profile.get('user_id', profile.get('id'))
            target_data = {
                'interests': batch_data['interests'].get(profile_user_id, [])
            }
            profile['match_score'] = self.get_matching_score_batch(
                user_profile, profile, user_data, target_data
            )
        
        nearby_profiles.sort(key=lambda x: x['match_score'], reverse=True)
        
        return nearby_profiles[:limit]
    
    def close(self):
        """Ferme la connexion à la base de données"""
        if self.conn:
            self.conn.close()
            logger.info("✅ Connexion PostgreSQL fermée")


# Instance globale
_db_service = None

def get_db_service() -> DatabaseService:
    """Retourne l'instance unique du service de base de données"""
    global _db_service
    if _db_service is None:
        _db_service = DatabaseService()
    return _db_service

