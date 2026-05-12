-- 启用 pgcrypto 扩展（生成 UUID）
CREATE EXTENSION IF NOT EXISTS pgcrypto;

-- 用户记忆表
CREATE TABLE user_memory (
    user_id VARCHAR(128) PRIMARY KEY,
    preferences JSONB DEFAULT '{}',
    habits JSONB DEFAULT '{}',
    history JSONB DEFAULT '[]',
    last_updated TIMESTAMPTZ DEFAULT NOW(),
    version INTEGER DEFAULT 1
);

-- 任务记忆表
CREATE TABLE task_memory (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id VARCHAR(128),
    task_id VARCHAR(128),
    title TEXT,
    status VARCHAR(20) CHECK (status IN ('pending', 'in_progress', 'completed', 'failed')),
    steps JSONB,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    metadata JSONB DEFAULT '{}'
);

-- 经验记忆表
CREATE TABLE experience_memory (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id VARCHAR(128),
    task_type VARCHAR(64),
    success BOOLEAN,
    steps_sequence JSONB,
    summary TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    frequency INTEGER DEFAULT 1
);

-- 索引优化查询性能
CREATE INDEX idx_user_memory_user ON user_memory(user_id);
CREATE INDEX idx_task_memory_user ON task_memory(user_id);
CREATE INDEX idx_task_memory_task_id ON task_memory(task_id);
CREATE INDEX idx_experience_user ON experience_memory(user_id);
CREATE INDEX idx_experience_task_type ON experience_memory(task_type);
CREATE INDEX idx_experience_success ON experience_memory(success);