-- =====================================================
-- SCHEMA MEETVOICE - PostgreSQL 16 + pgvector 0.8.1
-- =====================================================

-- Extension pgvector (déjà activée)
CREATE EXTENSION IF NOT EXISTS vector;

-- =====================================================
-- TABLE: users (Utilisateurs)
-- =====================================================
CREATE TABLE IF NOT EXISTS users (
    id SERIAL PRIMARY KEY,
    email VARCHAR(255) UNIQUE NOT NULL,
    username VARCHAR(100),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_login TIMESTAMP,
    is_active BOOLEAN DEFAULT TRUE
);

CREATE INDEX idx_users_email ON users(email);
CREATE INDEX idx_users_active ON users(is_active);

-- =====================================================
-- TABLE: subscriptions (Abonnements)
-- =====================================================
CREATE TABLE IF NOT EXISTS subscriptions (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    tier VARCHAR(20) NOT NULL DEFAULT 'free', -- free, standard, premium, vip
    messages_today INTEGER DEFAULT 0,
    tokens_today INTEGER DEFAULT 0,
    messages_limit INTEGER DEFAULT 5,
    tokens_limit INTEGER DEFAULT 2000,
    reset_at TIMESTAMP DEFAULT (CURRENT_DATE + INTERVAL '1 day'),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    expires_at TIMESTAMP,
    is_active BOOLEAN DEFAULT TRUE
);

CREATE INDEX idx_subscriptions_user_id ON subscriptions(user_id);
CREATE INDEX idx_subscriptions_tier ON subscriptions(tier);
CREATE INDEX idx_subscriptions_reset_at ON subscriptions(reset_at);

-- =====================================================
-- TABLE: coaching_sessions (Sessions de coaching)
-- =====================================================
CREATE TABLE IF NOT EXISTS coaching_sessions (
    id SERIAL PRIMARY KEY,
    session_id VARCHAR(64) UNIQUE NOT NULL,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    expert_id VARCHAR(50) NOT NULL, -- sexologie, psychologie, seduction, etc.
    category VARCHAR(50) NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_message_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    is_active BOOLEAN DEFAULT TRUE,
    message_count INTEGER DEFAULT 0,
    summary TEXT, -- Résumé automatique de la session
    topics TEXT[] -- Topics extraits (ex: ['anxiété', 'respiration'])
);

CREATE INDEX idx_sessions_user_id ON coaching_sessions(user_id);
CREATE INDEX idx_sessions_session_id ON coaching_sessions(session_id);
CREATE INDEX idx_sessions_expert_id ON coaching_sessions(expert_id);
CREATE INDEX idx_sessions_active ON coaching_sessions(is_active);
CREATE INDEX idx_sessions_topics ON coaching_sessions USING GIN (topics);

-- =====================================================
-- TABLE: session_exchanges (Échanges avec embeddings)
-- ⭐ TABLE CLÉE AVEC PGVECTOR
-- =====================================================
CREATE TABLE IF NOT EXISTS session_exchanges (
    id SERIAL PRIMARY KEY,
    session_id VARCHAR(64) NOT NULL REFERENCES coaching_sessions(session_id) ON DELETE CASCADE,
    user_message TEXT NOT NULL,
    assistant_response TEXT NOT NULL,
    
    -- 🔥 EMBEDDINGS VECTORIELS (768 dimensions pour CamemBERT)
    user_embedding vector(768),
    
    -- Métadonnées
    topics_extracted TEXT[], -- Topics du message (ex: ['stress', 'anxiété'])
    sentiment VARCHAR(20), -- positive, negative, neutral
    tokens_used INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_exchanges_session_id ON session_exchanges(session_id);
CREATE INDEX idx_exchanges_created_at ON session_exchanges(created_at);
CREATE INDEX idx_exchanges_topics ON session_exchanges USING GIN (topics_extracted);

-- 🔥 INDEX VECTORIEL HNSW (le plus performant)
CREATE INDEX idx_exchanges_embedding ON session_exchanges 
USING hnsw (user_embedding vector_cosine_ops)
WITH (m = 16, ef_construction = 64);

-- Alternative: Index IVFFlat (moins mémoire, un peu plus lent)
-- CREATE INDEX idx_exchanges_embedding ON session_exchanges 
-- USING ivfflat (user_embedding vector_cosine_ops)
-- WITH (lists = 100);

-- =====================================================
-- TABLE: profiles (Profils utilisateurs pour matching)
-- =====================================================
CREATE TABLE IF NOT EXISTS profiles (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    display_name VARCHAR(100),
    bio TEXT,
    age INTEGER,
    gender VARCHAR(20),
    looking_for VARCHAR(20),
    latitude DECIMAL(10, 8),
    longitude DECIMAL(11, 8),
    city VARCHAR(100),
    interests TEXT[],
    photos TEXT[], -- URLs des photos
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    is_active BOOLEAN DEFAULT TRUE
);

CREATE INDEX idx_profiles_user_id ON profiles(user_id);
CREATE INDEX idx_profiles_gender ON profiles(gender);
CREATE INDEX idx_profiles_age ON profiles(age);
CREATE INDEX idx_profiles_location ON profiles(latitude, longitude);
CREATE INDEX idx_profiles_active ON profiles(is_active);

-- =====================================================
-- TABLE: conversation_memory (Mémoire court terme)
-- Alternative légère à Redis pour les 5 derniers messages
-- =====================================================
CREATE TABLE IF NOT EXISTS conversation_memory (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    category VARCHAR(50) NOT NULL, -- general, sexologie
    user_message TEXT NOT NULL,
    assistant_response TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    expires_at TIMESTAMP DEFAULT (CURRENT_TIMESTAMP + INTERVAL '24 hours')
);

CREATE INDEX idx_memory_user_category ON conversation_memory(user_id, category);
CREATE INDEX idx_memory_expires_at ON conversation_memory(expires_at);

-- =====================================================
-- FONCTIONS UTILITAIRES
-- =====================================================

-- Fonction: Nettoyer les messages expirés
CREATE OR REPLACE FUNCTION clean_expired_memory()
RETURNS INTEGER AS $$
DECLARE
    deleted_count INTEGER;
BEGIN
    DELETE FROM conversation_memory WHERE expires_at < CURRENT_TIMESTAMP;
    GET DIAGNOSTICS deleted_count = ROW_COUNT;
    RETURN deleted_count;
END;
$$ LANGUAGE plpgsql;

-- Fonction: Recherche sémantique dans les échanges
CREATE OR REPLACE FUNCTION search_similar_messages(
    p_session_id VARCHAR(64),
    p_query_embedding vector(768),
    p_limit INTEGER DEFAULT 5
)
RETURNS TABLE (
    id INTEGER,
    user_message TEXT,
    assistant_response TEXT,
    similarity FLOAT,
    topics_extracted TEXT[],
    created_at TIMESTAMP
) AS $$
BEGIN
    RETURN QUERY
    SELECT 
        e.id,
        e.user_message,
        e.assistant_response,
        1 - (e.user_embedding <=> p_query_embedding) as similarity,
        e.topics_extracted,
        e.created_at
    FROM session_exchanges e
    WHERE e.session_id = p_session_id
      AND e.user_embedding IS NOT NULL
    ORDER BY e.user_embedding <=> p_query_embedding
    LIMIT p_limit;
END;
$$ LANGUAGE plpgsql;

-- =====================================================
-- TRIGGERS
-- =====================================================

-- Trigger: Mettre à jour updated_at automatiquement
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER update_sessions_updated_at
BEFORE UPDATE ON coaching_sessions
FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_subscriptions_updated_at
BEFORE UPDATE ON subscriptions
FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_profiles_updated_at
BEFORE UPDATE ON profiles
FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- Trigger: Incrémenter message_count sur coaching_sessions
CREATE OR REPLACE FUNCTION increment_session_message_count()
RETURNS TRIGGER AS $$
BEGIN
    UPDATE coaching_sessions
    SET message_count = message_count + 1,
        last_message_at = CURRENT_TIMESTAMP,
        updated_at = CURRENT_TIMESTAMP
    WHERE session_id = NEW.session_id;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER increment_message_count
AFTER INSERT ON session_exchanges
FOR EACH ROW EXECUTE FUNCTION increment_session_message_count();

-- =====================================================
-- VUES UTILES
-- =====================================================

-- Vue: Sessions actives avec statistiques
CREATE OR REPLACE VIEW active_sessions_stats AS
SELECT 
    s.session_id,
    s.user_id,
    s.expert_id,
    s.category,
    s.message_count,
    s.created_at,
    s.last_message_at,
    EXTRACT(EPOCH FROM (CURRENT_TIMESTAMP - s.created_at))/3600 as session_duration_hours,
    s.topics
FROM coaching_sessions s
WHERE s.is_active = TRUE
ORDER BY s.last_message_at DESC;

-- Vue: Usage quotidien par utilisateur
CREATE OR REPLACE VIEW daily_usage_stats AS
SELECT 
    u.id as user_id,
    u.email,
    s.tier,
    s.messages_today,
    s.tokens_today,
    s.messages_limit,
    s.tokens_limit,
    ROUND((s.messages_today::DECIMAL / s.messages_limit) * 100, 2) as usage_percentage
FROM users u
JOIN subscriptions s ON u.id = s.user_id
WHERE s.is_active = TRUE;

-- =====================================================
-- DONNÉES INITIALES
-- =====================================================

-- Créer un utilisateur de test
INSERT INTO users (id, email, username) 
VALUES (1, 'test@meetvoice.fr', 'TestUser')
ON CONFLICT (id) DO NOTHING;

-- Créer un abonnement free pour l'utilisateur test
INSERT INTO subscriptions (user_id, tier, messages_limit, tokens_limit)
VALUES (1, 'free', 5, 2000)
ON CONFLICT DO NOTHING;

-- =====================================================
-- TABLE: user_emotions (Historique des émotions vocales)
-- =====================================================
CREATE TABLE IF NOT EXISTS user_emotions (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    emotion VARCHAR(30) NOT NULL,
    confidence FLOAT NOT NULL,
    top_emotions JSONB,
    audio_features JSONB,
    session_id VARCHAR(64),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_emotions_user_id ON user_emotions(user_id);
CREATE INDEX idx_emotions_created_at ON user_emotions(created_at);
CREATE INDEX idx_emotions_emotion ON user_emotions(emotion);

-- =====================================================
-- TABLE: user_personality (Profil de personnalité Big Five)
-- =====================================================
CREATE TABLE IF NOT EXISTS user_personality (
    id SERIAL PRIMARY KEY,
    user_id INTEGER UNIQUE NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    traits JSONB NOT NULL DEFAULT '{}',
    style_communication TEXT,
    centres_interet TEXT[],
    traits_dominants TEXT[],
    points_attention TEXT[],
    profil_resume TEXT,
    messages_analyzed INTEGER DEFAULT 0,
    analyzed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    version INTEGER DEFAULT 1,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_personality_user_id ON user_personality(user_id);

-- Vue: Dernier état émotionnel par utilisateur
CREATE OR REPLACE VIEW user_current_emotion AS
SELECT DISTINCT ON (user_id)
    user_id, emotion, confidence, top_emotions, created_at
FROM user_emotions
ORDER BY user_id, created_at DESC;

-- Vue: Résumé émotionnel par utilisateur
CREATE OR REPLACE VIEW user_emotion_summary AS
SELECT 
    user_id,
    emotion,
    COUNT(*) as occurrence_count,
    AVG(confidence) as avg_confidence,
    MAX(created_at) as last_seen
FROM user_emotions
GROUP BY user_id, emotion
ORDER BY user_id, occurrence_count DESC;

-- =====================================================
-- COMMENTAIRES & DOCUMENTATION
-- =====================================================

COMMENT ON TABLE session_exchanges IS 'Échanges de coaching avec embeddings vectoriels (CamemBERT 768d)';
COMMENT ON COLUMN session_exchanges.user_embedding IS 'Embedding vectoriel du message utilisateur (768 dimensions)';
COMMENT ON INDEX idx_exchanges_embedding IS 'Index HNSW pour recherche sémantique ultra-rapide';

COMMENT ON FUNCTION search_similar_messages IS 'Recherche les messages similaires dans une session via similarité cosinus';
COMMENT ON FUNCTION clean_expired_memory IS 'Nettoie les messages en mémoire court terme expirés';

COMMENT ON TABLE user_emotions IS 'Historique des émotions détectées par analyse vocale';
COMMENT ON TABLE user_personality IS 'Profil de personnalité Big Five analysé depuis les conversations';
