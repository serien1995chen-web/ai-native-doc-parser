## 4. 数据库设计

### 4.1 E-R 关系概览

```
users (1) ----- (N) files
users (1) ----- (N) api_keys
users (1) ----- (N) collections
users (1) ----- (N) collection_items
users (1) ----- (N) parse_tasks

files (1) ----- (N) file_identifications
files (1) ----- (N) parse_tasks
files (1) ----- (N) parse_results

parse_tasks (1) ----- (N) parse_results

collections (1) ----- (N) collection_items
collection_items (N) ---- (1) files (via file_id)
collection_items (N) ---- (1) parse_tasks (via task_id)
```

### 4.2 建表 DDL

```sql
-- ============================================================
-- 1. 用户表
-- ============================================================
CREATE TABLE users (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    username        VARCHAR(100) NOT NULL UNIQUE,
    email           VARCHAR(255),
    password_hash   VARCHAR(255) NOT NULL,
    role            VARCHAR(20) DEFAULT 'user',
    is_active       BOOLEAN DEFAULT TRUE,
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW()
);

-- ============================================================
-- 2. API 密钥表
-- ============================================================
CREATE TABLE api_keys (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id         UUID REFERENCES users(id) ON DELETE CASCADE,
    key_prefix      VARCHAR(8) NOT NULL,
    key_hash        VARCHAR(255) NOT NULL,
    name            VARCHAR(100),
    is_active       BOOLEAN DEFAULT TRUE,
    last_used_at    TIMESTAMPTZ,
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

-- ============================================================
-- 3. 文件表（核心）
-- ============================================================
CREATE TABLE files (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id             UUID REFERENCES users(id) ON DELETE CASCADE,
    original_name       VARCHAR(500) NOT NULL,
    uploaded_type       VARCHAR(20) NOT NULL,
    source_content      TEXT,
    type_hint           VARCHAR(20),
    stored_path         VARCHAR(1000) NOT NULL,
    file_size           BIGINT,
    file_hash           VARCHAR(64),
    identified_type     VARCHAR(50),
    content_type        VARCHAR(30),
    identified_confidence FLOAT,
    mime_type           VARCHAR(200),
    is_suspicious       BOOLEAN DEFAULT FALSE,
    status              VARCHAR(20) DEFAULT 'uploaded',
    error_message       TEXT,
    created_at          TIMESTAMPTZ DEFAULT NOW(),
    updated_at          TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_files_user_id ON files(user_id);
CREATE INDEX idx_files_status ON files(status);
CREATE INDEX idx_files_content_type ON files(content_type);
CREATE INDEX idx_files_created_at ON files(created_at DESC);
CREATE INDEX idx_files_name_trgm ON files USING gin (original_name gin_trgm_ops);

-- ============================================================
-- 4. 文件识别明细表
-- ============================================================
CREATE TABLE file_identifications (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    file_id         UUID REFERENCES files(id) ON DELETE CASCADE,
    layer           SMALLINT NOT NULL,
    detected_type   VARCHAR(50) NOT NULL,
    confidence      FLOAT NOT NULL,
    details         JSONB,
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_fi_file_id ON file_identifications(file_id);

-- ============================================================
-- 5. 解析任务表
-- ============================================================
CREATE TABLE parse_tasks (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    file_id         UUID REFERENCES files(id) ON DELETE CASCADE,
    user_id         UUID REFERENCES users(id) ON DELETE CASCADE,
    parser_type     VARCHAR(50),
    output_formats  VARCHAR(50) DEFAULT 'markdown,json',
    status          VARCHAR(20) DEFAULT 'queued',
    progress        SMALLINT DEFAULT 0,
    error_message   TEXT,
    error_details   JSONB,
    retry_count     SMALLINT DEFAULT 0,
    started_at      TIMESTAMPTZ,
    completed_at    TIMESTAMPTZ,
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_pt_file_id ON parse_tasks(file_id);
CREATE INDEX idx_pt_user_id ON parse_tasks(user_id);
CREATE INDEX idx_pt_status ON parse_tasks(status);
CREATE INDEX idx_pt_created_at ON parse_tasks(created_at DESC);

-- ============================================================
-- 6. 解析结果表
-- ============================================================
CREATE TABLE parse_results (
    id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    task_id           UUID REFERENCES parse_tasks(id) ON DELETE CASCADE,
    file_id           UUID REFERENCES files(id) ON DELETE CASCADE,
    output_format     VARCHAR(20) NOT NULL,
    output_text       TEXT,
    output_path       VARCHAR(1000),
    output_size       BIGINT,
    processing_time_ms BIGINT,
    created_at        TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_pr_task_id ON parse_results(task_id);
CREATE INDEX idx_pr_file_id ON parse_results(file_id);

-- ============================================================
-- 7. 收藏集表
-- ============================================================
CREATE TABLE collections (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id     UUID REFERENCES users(id) ON DELETE CASCADE,
    name        VARCHAR(200) NOT NULL,
    description TEXT,
    is_default  BOOLEAN DEFAULT FALSE,
    created_at  TIMESTAMPTZ DEFAULT NOW(),
    updated_at  TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_collections_user ON collections(user_id);

-- ============================================================
-- 8. 收藏条目表
-- ============================================================
CREATE TABLE collection_items (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    collection_id   UUID REFERENCES collections(id) ON DELETE CASCADE,
    user_id         UUID REFERENCES users(id) ON DELETE CASCADE,
    task_id         UUID REFERENCES parse_tasks(id) ON DELETE CASCADE,
    file_id         UUID REFERENCES files(id) ON DELETE CASCADE,
    content_type    VARCHAR(30) NOT NULL,
    identified_type VARCHAR(50),
    original_name   VARCHAR(500),
    label           VARCHAR(200),
    notes           TEXT,
    tags            TEXT[],
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_ci_collection ON collection_items(collection_id);
CREATE INDEX idx_ci_user ON collection_items(user_id);
CREATE INDEX idx_ci_content_type ON collection_items(content_type);
CREATE INDEX idx_ci_tags ON collection_items USING gin(tags);

-- ============================================================
-- 9. 系统配置表（私有化运维用）
-- ============================================================
CREATE TABLE system_config (
    key         VARCHAR(255) PRIMARY KEY,
    value       TEXT NOT NULL,
    description TEXT,
    updated_at  TIMESTAMPTZ DEFAULT NOW()
);
```

---

