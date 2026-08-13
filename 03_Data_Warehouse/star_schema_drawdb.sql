-- =====================================================================
-- Steam Games Data Warehouse - Star Schema DDL
-- ใช้สำหรับ import เข้า drawDB:  File -> Import from SQL -> เลือกไฟล์นี้
-- dialect: MySQL   (ตอนเปิด drawDB ให้เลือก MySQL หรือ Generic)
-- =====================================================================

-- ---------------------------------------------------------------
-- DIMENSION TABLES
-- ---------------------------------------------------------------

CREATE TABLE DIM_GAME (
    game_key            INT             NOT NULL,
    steam_appid         INT             NOT NULL,
    name                VARCHAR(150)    NOT NULL,
    type                VARCHAR(20)     NOT NULL,
    is_free             TINYINT         NOT NULL,
    required_age        INT             NOT NULL,
    initial_price       DECIMAL(10,2)   NOT NULL,
    price_tier          VARCHAR(20)     NOT NULL,
    controller_support  TINYINT         NOT NULL,
    dlc_count           INT             NOT NULL,
    achievements_total  INT             NOT NULL,
    content_depth_tier  VARCHAR(20)     NOT NULL,
    language_count      INT             NOT NULL,
    price_currency      VARCHAR(20)     NOT NULL,
    is_premium          TINYINT         NOT NULL,
    PRIMARY KEY (game_key),
    UNIQUE (steam_appid)
);

CREATE TABLE DIM_DATE (
    date_key    INT             NOT NULL,
    full_date   DATE            NOT NULL,
    day         INT             NOT NULL,
    month       INT             NOT NULL,
    month_name  VARCHAR(20)     NOT NULL,
    quarter     INT             NOT NULL,
    year        INT             NOT NULL,
    PRIMARY KEY (date_key)
);

CREATE TABLE DIM_PLATFORM (
    platform_key      INT           NOT NULL,
    platform_windows  TINYINT       NOT NULL,
    platform_mac      TINYINT       NOT NULL,
    platform_linux    TINYINT       NOT NULL,
    platform_desc     VARCHAR(50)   NOT NULL,
    platform_count    INT           NOT NULL,
    PRIMARY KEY (platform_key)
);

CREATE TABLE DIM_REVIEW_SCORE (
    review_score_key   INT           NOT NULL,
    review_score       INT           NOT NULL,
    review_score_desc  VARCHAR(50)   NOT NULL,
    sentiment_band     VARCHAR(30)   NOT NULL,
    PRIMARY KEY (review_score_key)
);

CREATE TABLE DIM_DEVELOPER (
    developer_key   INT             NOT NULL,
    developer_name  VARCHAR(150)    NOT NULL,
    PRIMARY KEY (developer_key)
);

CREATE TABLE DIM_PUBLISHER (
    publisher_key   INT             NOT NULL,
    publisher_name  VARCHAR(150)    NOT NULL,
    PRIMARY KEY (publisher_key)
);

CREATE TABLE DIM_GENRE (
    genre_key                      INT           NOT NULL,
    genre_name                     VARCHAR(50)   NOT NULL,
    genre_avg_price                DECIMAL(10,2),
    genre_avg_recommendation_rate  DOUBLE,
    genre_avg_review_score         DOUBLE,
    PRIMARY KEY (genre_key)
);

CREATE TABLE DIM_LANGUAGE (
    language_key   INT           NOT NULL,
    language_name  VARCHAR(60)   NOT NULL,
    PRIMARY KEY (language_key)
);

CREATE TABLE DIM_CATEGORY (
    category_key   INT           NOT NULL,
    category_name  VARCHAR(80)   NOT NULL,
    PRIMARY KEY (category_key)
);

-- ---------------------------------------------------------------
-- FACT TABLES
-- ---------------------------------------------------------------

CREATE TABLE FACT_GAME_ENGAGEMENT (
    engagement_key              INT             NOT NULL,
    game_key                    INT             NOT NULL,
    date_key                    INT             NOT NULL,
    platform_key                INT             NOT NULL,
    review_score_key            INT             NOT NULL,
    primary_developer_key       INT             NOT NULL,
    primary_publisher_key       INT             NOT NULL,
    total_positive              INT             NOT NULL,
    total_negative              INT             NOT NULL,
    total_reviews               INT             NOT NULL,
    recommendations             INT             NOT NULL,
    owners                      BIGINT          NOT NULL,
    ccu                         INT             NOT NULL,
    estimated_revenue           DECIMAL(18,2)   NOT NULL,
    concurrent_engagement_rate  DOUBLE,
    content_depth_score         INT             NOT NULL,
    recommendation_rate         DOUBLE,
    PRIMARY KEY (engagement_key),
    FOREIGN KEY (game_key)              REFERENCES DIM_GAME (game_key),
    FOREIGN KEY (date_key)              REFERENCES DIM_DATE (date_key),
    FOREIGN KEY (platform_key)          REFERENCES DIM_PLATFORM (platform_key),
    FOREIGN KEY (review_score_key)      REFERENCES DIM_REVIEW_SCORE (review_score_key),
    FOREIGN KEY (primary_developer_key) REFERENCES DIM_DEVELOPER (developer_key),
    FOREIGN KEY (primary_publisher_key) REFERENCES DIM_PUBLISHER (publisher_key)
);

CREATE TABLE FACT_GAME_PLAYTIME (
    playtime_key          INT   NOT NULL,
    game_key              INT   NOT NULL,
    date_key              INT   NOT NULL,
    platform_key          INT   NOT NULL,
    primary_genre_key     INT,
    primary_category_key  INT,
    average_forever       INT   NOT NULL,
    average_2weeks        INT   NOT NULL,
    median_forever        INT   NOT NULL,
    median_2weeks         INT   NOT NULL,
    has_playtime          TINYINT NOT NULL,
    PRIMARY KEY (playtime_key),
    FOREIGN KEY (game_key)             REFERENCES DIM_GAME (game_key),
    FOREIGN KEY (date_key)             REFERENCES DIM_DATE (date_key),
    FOREIGN KEY (platform_key)         REFERENCES DIM_PLATFORM (platform_key),
    FOREIGN KEY (primary_genre_key)    REFERENCES DIM_GENRE (genre_key),
    FOREIGN KEY (primary_category_key) REFERENCES DIM_CATEGORY (category_key)
);

-- ---------------------------------------------------------------
-- BRIDGE TABLES (many-to-many)
-- ---------------------------------------------------------------

CREATE TABLE BRIDGE_GAME_GENRES (
    game_key           INT             NOT NULL,
    genre_key          INT             NOT NULL,
    allocation_factor  DECIMAL(10,6)   NOT NULL,
    is_primary         TINYINT         NOT NULL,
    PRIMARY KEY (game_key, genre_key),
    FOREIGN KEY (game_key)  REFERENCES DIM_GAME (game_key),
    FOREIGN KEY (genre_key) REFERENCES DIM_GENRE (genre_key)
);

CREATE TABLE BRIDGE_GAME_CATEGORIES (
    game_key           INT             NOT NULL,
    category_key       INT             NOT NULL,
    allocation_factor  DECIMAL(10,6)   NOT NULL,
    is_primary         TINYINT         NOT NULL,
    PRIMARY KEY (game_key, category_key),
    FOREIGN KEY (game_key)     REFERENCES DIM_GAME (game_key),
    FOREIGN KEY (category_key) REFERENCES DIM_CATEGORY (category_key)
);

CREATE TABLE BRIDGE_GAME_DEVELOPERS (
    game_key           INT             NOT NULL,
    developer_key      INT             NOT NULL,
    allocation_factor  DECIMAL(10,6)   NOT NULL,
    is_primary         TINYINT         NOT NULL,
    PRIMARY KEY (game_key, developer_key),
    FOREIGN KEY (game_key)      REFERENCES DIM_GAME (game_key),
    FOREIGN KEY (developer_key) REFERENCES DIM_DEVELOPER (developer_key)
);

CREATE TABLE BRIDGE_GAME_LANGUAGES (
    game_key           INT             NOT NULL,
    language_key       INT             NOT NULL,
    allocation_factor  DECIMAL(10,6)   NOT NULL,
    is_primary         TINYINT         NOT NULL,
    PRIMARY KEY (game_key, language_key),
    FOREIGN KEY (game_key)     REFERENCES DIM_GAME (game_key),
    FOREIGN KEY (language_key) REFERENCES DIM_LANGUAGE (language_key)
);

CREATE TABLE BRIDGE_GAME_PUBLISHERS (
    game_key           INT             NOT NULL,
    publisher_key      INT             NOT NULL,
    allocation_factor  DECIMAL(10,6)   NOT NULL,
    is_primary         TINYINT         NOT NULL,
    PRIMARY KEY (game_key, publisher_key),
    FOREIGN KEY (game_key)      REFERENCES DIM_GAME (game_key),
    FOREIGN KEY (publisher_key) REFERENCES DIM_PUBLISHER (publisher_key)
);

-- ---------------------------------------------------------------
-- INDEXES — เร่ง query ที่ใช้บ่อย
-- หมายเหตุ: drawDB อ่านเฉพาะ CREATE TABLE ถ้า import แล้วติดปัญหา
--          ให้ลบส่วนนี้ออกก่อน แล้วค่อยใช้ตอนสร้างฐานข้อมูลจริง
-- ---------------------------------------------------------------
CREATE INDEX idx_eng_date        ON FACT_GAME_ENGAGEMENT (date_key);
CREATE INDEX idx_eng_game        ON FACT_GAME_ENGAGEMENT (game_key);
CREATE INDEX idx_eng_owners      ON FACT_GAME_ENGAGEMENT (owners);
CREATE INDEX idx_eng_depth       ON FACT_GAME_ENGAGEMENT (content_depth_score);
CREATE INDEX idx_play_game       ON FACT_GAME_PLAYTIME (game_key);
CREATE INDEX idx_play_date       ON FACT_GAME_PLAYTIME (date_key);
CREATE INDEX idx_game_price_tier ON DIM_GAME (price_tier);
CREATE INDEX idx_game_depth_tier ON DIM_GAME (content_depth_tier);
CREATE INDEX idx_game_premium    ON DIM_GAME (is_premium);
CREATE INDEX idx_date_year       ON DIM_DATE (year);
