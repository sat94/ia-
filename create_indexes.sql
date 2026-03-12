-- Index pour améliorer les performances des requêtes de matching

-- Table profiles (requêtes de matching rapides)
CREATE INDEX IF NOT EXISTS idx_profiles_user_id_batch ON profiles(user_id) WHERE is_active = TRUE;
CREATE INDEX IF NOT EXISTS idx_profiles_location ON profiles(latitude, longitude) WHERE is_active = TRUE;
CREATE INDEX IF NOT EXISTS idx_profiles_age_gender ON profiles(age, gender) WHERE is_active = TRUE;

-- Index GIN pour recherche dans les arrays
CREATE INDEX IF NOT EXISTS idx_profiles_interests ON profiles USING GIN(interests);
