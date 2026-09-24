"""SQLite schema: base DDL + incremental migrations (v1.2.18 refactor, P3).

Extracted verbatim from core/storage/sqlite_store.py. The DDL strings, ordering,
IF NOT EXISTS guards and migration list are BYTE-FOR-BYTE identical to the
original — SqliteStore references these constants so existing databases migrate
exactly as before.

Re-exported from sqlite_store (SCHEMA_VERSION / _MIGRATIONS / _PROFILE_TABLES).
"""

SCHEMA_VERSION = 3  # v1: no profile col (v1.1.5-), v2: profile col (v1.1.6+), v3: user_memory composite PK (v1.2.0)

_MIGRATIONS = [
    (4, "Add last_access_at to 6 memory tables",
     [
         "ALTER TABLE user_memory ADD COLUMN last_access_at TEXT DEFAULT ''",
         "ALTER TABLE task_memory ADD COLUMN last_access_at TEXT DEFAULT ''",
         "ALTER TABLE experience_memory ADD COLUMN last_access_at TEXT DEFAULT ''",
         "ALTER TABLE context_memory ADD COLUMN last_access_at TEXT DEFAULT ''",
         "ALTER TABLE knowledge_memory ADD COLUMN last_access_at TEXT DEFAULT ''",
         "ALTER TABLE research_papers ADD COLUMN last_access_at TEXT DEFAULT ''",
         "CREATE INDEX IF NOT EXISTS idx_user_last_access ON user_memory(last_access_at)",
         "CREATE INDEX IF NOT EXISTS idx_task_last_access ON task_memory(last_access_at)",
         "CREATE INDEX IF NOT EXISTS idx_experience_last_access ON experience_memory(last_access_at)",
         "CREATE INDEX IF NOT EXISTS idx_knowledge_last_access ON knowledge_memory(last_access_at)",
         "CREATE INDEX IF NOT EXISTS idx_context_last_access ON context_memory(last_access_at)",
         "CREATE INDEX IF NOT EXISTS idx_papers_last_access ON research_papers(last_access_at)",
     ]),
    (5, "Add context_archive table for evicted session messages",
     [
         "CREATE TABLE IF NOT EXISTS context_archive ("
         " id INTEGER PRIMARY KEY AUTOINCREMENT,"
         " session_id TEXT NOT NULL,"
         " role TEXT NOT NULL,"
         " content TEXT NOT NULL,"
         " archived_at TEXT DEFAULT (datetime('now'))"
         ")",
         "CREATE INDEX IF NOT EXISTS idx_archive_session ON context_archive(session_id)",
     ]),
    (6, "Add language column indexes for faster filtered retrieval",
     [
         "CREATE INDEX IF NOT EXISTS idx_task_language ON task_memory(language)",
         "CREATE INDEX IF NOT EXISTS idx_experience_language ON experience_memory(language)",
         "CREATE INDEX IF NOT EXISTS idx_knowledge_language ON knowledge_memory(language)",
     ]),
    (7, "Add memory_states table for lifecycle tracking",
     [
         "CREATE TABLE IF NOT EXISTS memory_states ("
         " id INTEGER PRIMARY KEY AUTOINCREMENT,"
         " memory_type TEXT NOT NULL,"
         " memory_id TEXT NOT NULL,"
         " state TEXT NOT NULL DEFAULT 'active',"
         " state_changed_at TEXT DEFAULT (datetime('now')),"
         " reason TEXT DEFAULT '',"
         " previous_state TEXT DEFAULT '',"
         " source TEXT DEFAULT 'system',"
         " UNIQUE(memory_type, memory_id)"
         ")",
         "CREATE INDEX IF NOT EXISTS idx_memory_states_lookup ON memory_states(memory_type, memory_id)",
         "CREATE INDEX IF NOT EXISTS idx_memory_states_current ON memory_states(memory_type, state)",
         # Backfill: all existing memories start as 'active'
         "INSERT OR IGNORE INTO memory_states (memory_type, memory_id, state, reason, source) "
         "SELECT 'user', user_id, 'active', 'backfill', 'system' FROM user_memory",
         "INSERT OR IGNORE INTO memory_states (memory_type, memory_id, state, reason, source) "
         "SELECT 'task', id, 'active', 'backfill', 'system' FROM task_memory",
         "INSERT OR IGNORE INTO memory_states (memory_type, memory_id, state, reason, source) "
         "SELECT 'experience', id, 'active', 'backfill', 'system' FROM experience_memory",
         "INSERT OR IGNORE INTO memory_states (memory_type, memory_id, state, reason, source) "
         "SELECT 'context', session_id, 'active', 'backfill', 'system' FROM context_memory",
         "INSERT OR IGNORE INTO memory_states (memory_type, memory_id, state, reason, source) "
         "SELECT 'knowledge', id, 'active', 'backfill', 'system' FROM knowledge_memory",
         "INSERT OR IGNORE INTO memory_states (memory_type, memory_id, state, reason, source) "
         "SELECT 'paper', id, 'active', 'backfill', 'system' FROM research_papers",
     ]),
    (8, "Add knowledge_evolution table for tracking knowledge relationships",
     [
         "CREATE TABLE IF NOT EXISTS knowledge_evolution ("
         " id INTEGER PRIMARY KEY AUTOINCREMENT,"
         " source_id TEXT NOT NULL,"
         " target_id TEXT NOT NULL,"
         " relation_type TEXT NOT NULL,"
         " confidence REAL DEFAULT 0.5,"
         " reason TEXT DEFAULT '',"
         " detection_method TEXT DEFAULT 'jaccard',"
         " created_at TEXT DEFAULT (datetime('now'))"
         ")",
"CREATE INDEX IF NOT EXISTS idx_evolution_source ON knowledge_evolution(source_id)",
          "CREATE INDEX IF NOT EXISTS idx_evolution_target ON knowledge_evolution(target_id)",
      ]),
    (9, "Add provenance columns to knowledge_evolution for memory provenance tracking",
     [
         "ALTER TABLE knowledge_evolution ADD COLUMN origin_agent TEXT DEFAULT ''",
         "ALTER TABLE knowledge_evolution ADD COLUMN origin_session_id TEXT DEFAULT ''",
         "ALTER TABLE knowledge_evolution ADD COLUMN origin_turn INTEGER DEFAULT 0",
     ]),
    (10, "Add origin provenance (transport + client) to all memory tables",
     [
         # v1.2.14 provenance: origin_platform = transport (mcp/http/hermes/cli),
         # origin_client = producing client (claude-code/opencode/...).
         # Legacy `platform` columns on context_memory/reflections are KEPT and
         # dual-written; the empty default keeps old rows visible to any
         # origin filter (audit-safe backward compatibility).
         "ALTER TABLE knowledge_memory ADD COLUMN origin_platform TEXT DEFAULT ''",
         "ALTER TABLE knowledge_memory ADD COLUMN origin_client TEXT DEFAULT ''",
         "ALTER TABLE experience_memory ADD COLUMN origin_platform TEXT DEFAULT ''",
         "ALTER TABLE experience_memory ADD COLUMN origin_client TEXT DEFAULT ''",
         "ALTER TABLE task_memory ADD COLUMN origin_platform TEXT DEFAULT ''",
         "ALTER TABLE task_memory ADD COLUMN origin_client TEXT DEFAULT ''",
         "ALTER TABLE context_memory ADD COLUMN origin_client TEXT DEFAULT ''",
         "ALTER TABLE research_papers ADD COLUMN origin_platform TEXT DEFAULT ''",
         "ALTER TABLE research_papers ADD COLUMN origin_client TEXT DEFAULT ''",
         "ALTER TABLE research_notes ADD COLUMN origin_platform TEXT DEFAULT ''",
         "ALTER TABLE research_notes ADD COLUMN origin_client TEXT DEFAULT ''",
         "ALTER TABLE session_transcripts ADD COLUMN origin_platform TEXT DEFAULT ''",
         "ALTER TABLE session_transcripts ADD COLUMN origin_client TEXT DEFAULT ''",
         "ALTER TABLE reflections ADD COLUMN origin_client TEXT DEFAULT ''",
         "CREATE INDEX IF NOT EXISTS idx_knowledge_origin ON knowledge_memory(origin_platform, origin_client, project)",
         "CREATE INDEX IF NOT EXISTS idx_experience_origin ON experience_memory(origin_platform, origin_client, project)",
         "CREATE INDEX IF NOT EXISTS idx_task_origin ON task_memory(origin_platform, origin_client, project)",
         # context_memory has no origin_platform column (the legacy `platform`
         # column carries the transport), so its index uses that instead.
         "CREATE INDEX IF NOT EXISTS idx_context_origin ON context_memory(platform, origin_client, project)",
     ]),
    (11, "Provenance review fixes: experience metadata column + client cleanup",
     [
         # P2-4 fix (v1.2.14 review): experience_memory had no metadata
         # column, so the provenance envelope could not persist across
         # restarts. ADD COLUMN is idempotent and keeps existing rows.
         "ALTER TABLE experience_memory ADD COLUMN metadata TEXT DEFAULT '{}'",
         # P1-1 fix (v1.2.14 review): rows stored while store() fell back to
         # the transport value polluted the client column — an HTTP write got
         # client='http'. Hermes rows (client='hermes') are plan-intended and
         # stay. Empty client makes the row transparent to any client filter.
         "UPDATE knowledge_memory SET origin_client='' WHERE origin_platform='http' AND origin_client='http'",
         "UPDATE experience_memory SET origin_client='' WHERE origin_platform='http' AND origin_client='http'",
         "UPDATE task_memory SET origin_client='' WHERE origin_platform='http' AND origin_client='http'",
         "UPDATE context_memory SET origin_client='' WHERE platform='http' AND origin_client='http'",
     ]),
]

_PROFILE_TABLES = [
    "user_memory", "task_memory", "experience_memory",
    "context_memory", "knowledge_memory", "research_papers",
    "research_notes", "session_transcripts",
]

# Base schema DDL (verbatim from ensure_tables' first executescript)
BASE_SCHEMA_SQL = """
-- 1. User memory: preferences, habits, interaction history
                    CREATE TABLE IF NOT EXISTS user_memory (
                        user_id TEXT NOT NULL,
                        profile TEXT NOT NULL DEFAULT 'default',
                        preferences TEXT DEFAULT '{}',
                        habits TEXT DEFAULT '{}',
                        history TEXT DEFAULT '[]',
                        last_updated TEXT DEFAULT (datetime('now')),
                        last_access_at TEXT DEFAULT '',
                        created_at TEXT DEFAULT (datetime('now')),
                        version INTEGER DEFAULT 1,
                        PRIMARY KEY (user_id, profile)
                    );

                -- 2. Task memory: status, steps, metadata
                CREATE TABLE IF NOT EXISTS task_memory (
                    id TEXT PRIMARY KEY,
                    user_id TEXT,
                    title TEXT,
                    status TEXT,
                    steps TEXT DEFAULT '[]',
                    metadata TEXT DEFAULT '{}',
                    project TEXT DEFAULT 'default',
                    profile TEXT DEFAULT 'default',
                    session_id TEXT DEFAULT '',
                    session_title TEXT DEFAULT '',
                    tags TEXT DEFAULT '[]',
                    created_at TEXT DEFAULT (datetime('now')),
                    updated_at TEXT DEFAULT (datetime('now')),
                    language TEXT DEFAULT '',
                    last_access_at TEXT DEFAULT ''
                );

                -- 3. Experience memory: success/failure experience, step sequences
                CREATE TABLE IF NOT EXISTS experience_memory (
                    id TEXT PRIMARY KEY,
                    user_id TEXT,
                    task_type TEXT,
                    success INTEGER,
                    steps_sequence TEXT DEFAULT '[]',
                    summary TEXT,
                    project TEXT DEFAULT 'default',
                    profile TEXT DEFAULT 'default',
                    session_id TEXT DEFAULT '',
                    session_title TEXT DEFAULT '',
                    tags TEXT DEFAULT '[]',
                    created_at TEXT DEFAULT (datetime('now')),
                    frequency INTEGER DEFAULT 1,
                    language TEXT DEFAULT '',
                    last_access_at TEXT DEFAULT ''
                );

                -- 4. Context memory: conversation context, token count, session ID、Platform source
                CREATE TABLE IF NOT EXISTS context_memory (
                    session_id TEXT PRIMARY KEY,
                    user_id TEXT,
                    messages TEXT DEFAULT '[]',
                    token_count INTEGER DEFAULT 0,
                    platform TEXT DEFAULT 'default',
                    project TEXT DEFAULT 'default',
                    profile TEXT DEFAULT 'default',
                    created_at TEXT DEFAULT (datetime('now')),
                    updated_at TEXT DEFAULT (datetime('now')),
                    last_access_at TEXT DEFAULT ''
                );

                -- 5. Knowledge memory: domain knowledge, structured entries
                CREATE TABLE IF NOT EXISTS knowledge_memory (
                    id TEXT PRIMARY KEY,
                    domain TEXT DEFAULT 'general',
                    content TEXT,
                    metadata TEXT DEFAULT '{}',
                    trust_score REAL DEFAULT 0.5,
                    entry_type TEXT DEFAULT 'fact',
                    prerequisites TEXT DEFAULT '[]',
                    output_template TEXT DEFAULT '',
                    last_verified_at TEXT DEFAULT (datetime('now')),
                    half_life_days INTEGER DEFAULT 90,
                    access_count INTEGER DEFAULT 0,
                    project TEXT DEFAULT 'default',
                    profile TEXT DEFAULT 'default',
                    session_id TEXT DEFAULT '',
                    session_title TEXT DEFAULT '',
                    tags TEXT DEFAULT '[]',
                    user_id TEXT DEFAULT 'default',
                    created_at TEXT DEFAULT (datetime('now')),
                    updated_at TEXT DEFAULT (datetime('now')),
                    language TEXT DEFAULT '',
                    last_access_at TEXT DEFAULT ''
                );

                -- 6. Research papers: academic paper metadata
                CREATE TABLE IF NOT EXISTS research_papers (
                    id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    authors TEXT DEFAULT '[]',
                    year INTEGER,
                    journal TEXT,
                    abstract TEXT DEFAULT '',
                    keywords TEXT DEFAULT '[]',
                    domain TEXT DEFAULT 'general',
                    paper_type TEXT DEFAULT 'theory',
                    key_points TEXT DEFAULT '[]',
                    importance_score REAL DEFAULT 0.5,
                    metadata TEXT DEFAULT '{}',
                    project TEXT DEFAULT 'default',
                    profile TEXT DEFAULT 'default',
                    user_id TEXT DEFAULT 'default',
                    created_at TEXT DEFAULT (datetime('now')),
                    last_access_at TEXT DEFAULT ''
                );

                -- 7. Research notes: paper reading notes, research leads
                CREATE TABLE IF NOT EXISTS research_notes (
                    id TEXT PRIMARY KEY,
                    user_id TEXT,
                    topic TEXT NOT NULL,
                    content TEXT DEFAULT '',
                    linked_papers TEXT DEFAULT '[]',
                    tags TEXT DEFAULT '[]',
                    project TEXT DEFAULT 'default',
                    profile TEXT DEFAULT 'default',
                    created_at TEXT DEFAULT (datetime('now')),
                    updated_at TEXT DEFAULT (datetime('now'))
                );

                -- 8. Reflection records table（v1.1.0）
                CREATE TABLE IF NOT EXISTS reflections (
                    id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    platform TEXT DEFAULT 'default',
                    source_episodic_ids TEXT,
                    key_insights TEXT,
                    user_preferences TEXT,
                    procedural_rules TEXT,
                    new_knowledge TEXT,
                    importance_scores TEXT,
                    forget_suggestions TEXT,
                    confidence REAL DEFAULT 0.0,
                    meta TEXT,
                    created_at TEXT DEFAULT (datetime('now'))
                );

                -- 9. Session transcripts: full conversation history + Compression summary
                CREATE TABLE IF NOT EXISTS session_transcripts (
                    session_id TEXT PRIMARY KEY,
                    user_id TEXT,
                    project TEXT DEFAULT 'default',
                    profile TEXT DEFAULT 'default',
                    messages TEXT,
                    compressed_summary TEXT DEFAULT '',
                    key_decisions TEXT DEFAULT '[]',
                    created_at TEXT DEFAULT (datetime('now')),
                    updated_at TEXT DEFAULT (datetime('now'))
                );

                -- 10. Reflection daily counters: per-(user, date) reflection quota
                -- consumed by the daily limit. Persisted so the limit survives
                -- process restarts and is isolated per user (P5-B).
                CREATE TABLE IF NOT EXISTS reflection_daily_count (
                    user_id TEXT NOT NULL,
                    date TEXT NOT NULL,
                    count INTEGER NOT NULL DEFAULT 0,
                    PRIMARY KEY (user_id, date)
                );

                -- index
                CREATE INDEX IF NOT EXISTS idx_task_project ON task_memory(project);
                CREATE INDEX IF NOT EXISTS idx_task_updated ON task_memory(updated_at);
                CREATE INDEX IF NOT EXISTS idx_task_session ON task_memory(session_id);
                CREATE INDEX IF NOT EXISTS idx_experience_user ON experience_memory(user_id);
                CREATE INDEX IF NOT EXISTS idx_experience_project ON experience_memory(project);
                CREATE INDEX IF NOT EXISTS idx_experience_session ON experience_memory(session_id);
                CREATE INDEX IF NOT EXISTS idx_context_user ON context_memory(user_id);
                CREATE INDEX IF NOT EXISTS idx_knowledge_domain ON knowledge_memory(domain);
                CREATE INDEX IF NOT EXISTS idx_knowledge_user ON knowledge_memory(user_id);
                CREATE INDEX IF NOT EXISTS idx_knowledge_project ON knowledge_memory(project);
                CREATE INDEX IF NOT EXISTS idx_research_domain ON research_papers(domain);
                CREATE INDEX IF NOT EXISTS idx_research_user ON research_papers(user_id);
                CREATE INDEX IF NOT EXISTS idx_notes_user ON research_notes(user_id);
                CREATE INDEX IF NOT EXISTS idx_session_transcripts_user ON session_transcripts(user_id);
                -- P6-A: missing join/lookup indexes (idempotent)
                CREATE INDEX IF NOT EXISTS idx_knowledge_content ON knowledge_memory(content);
                CREATE INDEX IF NOT EXISTS idx_task_user_created ON task_memory(user_id, created_at);
                CREATE INDEX IF NOT EXISTS idx_experience_user_created ON experience_memory(user_id, created_at);
                    CREATE INDEX IF NOT EXISTS idx_reflections_user ON reflections(user_id, created_at);

                -- 11. Hit history: binary retrieval-hit log for RL significance
                -- verification (verify_improvement). Persisted so the learning
                -- verification loop survives restarts (unlike AEIS in-memory).
                CREATE TABLE IF NOT EXISTS hit_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id TEXT DEFAULT 'default',
                    hit INTEGER DEFAULT 0,
                    task_type TEXT DEFAULT '',
                    ts TEXT DEFAULT (datetime('now'))
                );
                CREATE INDEX IF NOT EXISTS idx_hit_history_user ON hit_history(user_id, ts);
            """

# Profile indexes built after migration (verbatim from second executescript)
PROFILE_INDEX_SQL = """
                CREATE INDEX IF NOT EXISTS idx_user_profile ON user_memory(profile);
                CREATE INDEX IF NOT EXISTS idx_task_profile ON task_memory(profile);
                CREATE INDEX IF NOT EXISTS idx_experience_profile ON experience_memory(profile);
                CREATE INDEX IF NOT EXISTS idx_context_profile ON context_memory(profile);
                CREATE INDEX IF NOT EXISTS idx_knowledge_profile ON knowledge_memory(profile);
                CREATE INDEX IF NOT EXISTS idx_papers_profile ON research_papers(profile);
                CREATE INDEX IF NOT EXISTS idx_notes_profile ON research_notes(profile);
                CREATE INDEX IF NOT EXISTS idx_transcripts_profile ON session_transcripts(profile);
            """

# Tables that get the language column added on legacy DBs
_LANG_TABLES = ["task_memory", "experience_memory", "knowledge_memory"]
