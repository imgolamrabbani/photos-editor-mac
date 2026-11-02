-- Microsoft Photos Library SQLite Database Schema
-- Reverse Engineered from Microsoft.Windows.Photos 2026.11090.22001.0 (Photos.Database.dll)
-- Part of Cross-Platform Reverse Engineering Analysis

PRAGMA foreign_keys = ON;

-- 1. Media Folders Table (Watched and Indexed Folders)
CREATE TABLE IF NOT EXISTS mediaFolder (
    FolderId INTEGER PRIMARY KEY AUTOINCREMENT,
    FolderKey TEXT UNIQUE NOT NULL,
    FolderPath TEXT UNIQUE NOT NULL,
    ParentFolderId INTEGER,
    FolderAttributes INTEGER DEFAULT 0,
    IsLibraryFolder INTEGER DEFAULT 1,
    ScanDate INTEGER,
    FOREIGN KEY(ParentFolderId) REFERENCES mediaFolder(FolderId) ON DELETE CASCADE
);

-- 2. Media Item File Table (File System Metadata)
CREATE TABLE IF NOT EXISTS mediaItemFile (
    ItemId INTEGER PRIMARY KEY AUTOINCREMENT,
    MediaItemKey TEXT UNIQUE NOT NULL,
    FolderKey TEXT NOT NULL,
    FileName TEXT NOT NULL,
    FileSize INTEGER NOT NULL,
    FileAttributes INTEGER DEFAULT 0,
    DateCreated INTEGER NOT NULL,
    DateModified INTEGER NOT NULL,
    DateIngested INTEGER NOT NULL,
    AlternateDateTaken INTEGER,
    FOREIGN KEY(FolderKey) REFERENCES mediaFolder(FolderKey) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_mediaItemFile_FileName ON mediaItemFile(FileName);
CREATE INDEX IF NOT EXISTS idx_mediaItemFile_DateCreated ON mediaItemFile(DateCreated);
CREATE INDEX IF NOT EXISTS idx_mediaItemFile_AlternateDateTaken ON mediaItemFile(AlternateDateTaken);

-- 3. Media Item Props Table (EXIF, Dimensions, Geolocation & Rating)
CREATE TABLE IF NOT EXISTS mediaItemProps (
    MediaItemKey TEXT PRIMARY KEY,
    DateTaken INTEGER,
    PropScanDate INTEGER,
    Width INTEGER,
    Height INTEGER,
    Orientation INTEGER DEFAULT 1,
    CameraManufacturer TEXT,
    CameraModel TEXT,
    FNumber REAL,
    ExposureTime REAL,
    ISO INTEGER,
    FocalLength REAL,
    Latitude REAL,
    Longitude REAL,
    LatitudeBucket INTEGER,
    LongitudeBucket INTEGER,
    IsFavorite INTEGER DEFAULT 0,
    Rating INTEGER DEFAULT 0,
    Duration INTEGER DEFAULT 0, -- For video items (ms)
    FOREIGN KEY(MediaItemKey) REFERENCES mediaItemFile(MediaItemKey) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_mediaItemProps_DateTaken ON mediaItemProps(DateTaken);
CREATE INDEX IF NOT EXISTS idx_mediaItemProps_LatitudeBucket ON mediaItemProps(LatitudeBucket);
CREATE INDEX IF NOT EXISTS idx_mediaItemProps_LongitudeBucket ON mediaItemProps(LongitudeBucket);

-- 4. Media Item Formatted Dates Table (Timeline Grouping)
CREATE TABLE IF NOT EXISTS mediaItemDates (
    MediaItemKey TEXT NOT NULL,
    DateFormatterType INTEGER NOT NULL,
    FormattedDate TEXT NOT NULL,
    DateValue INTEGER NOT NULL,
    PRIMARY KEY (MediaItemKey, DateFormatterType),
    FOREIGN KEY(MediaItemKey) REFERENCES mediaItemFile(MediaItemKey) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_mediaItemDates_DateFormatterType_FormattedDate 
    ON mediaItemDates(DateFormatterType, FormattedDate);

-- 5. Media Item Addresses Table (Reverse Geocoded Location)
CREATE TABLE IF NOT EXISTS mediaItemAddresses (
    MediaItemKey TEXT PRIMARY KEY,
    Town TEXT,
    Region TEXT,
    Country TEXT,
    NormalizedAddress TEXT,
    IsDataMissing INTEGER DEFAULT 0,
    FOREIGN KEY(MediaItemKey) REFERENCES mediaItemFile(MediaItemKey) ON DELETE CASCADE
);

-- 6. Media Item Semantic Category & Tagging
CREATE TABLE IF NOT EXISTS mediaItemCategory (
    MediaItemKey TEXT NOT NULL,
    Category TEXT NOT NULL,
    Confidence REAL DEFAULT 1.0,
    PRIMARY KEY (MediaItemKey, Category),
    FOREIGN KEY(MediaItemKey) REFERENCES mediaItemFile(MediaItemKey) ON DELETE CASCADE
);

-- 7. Media Item Vector Image Embeddings (Local Semantic AI Search)
CREATE TABLE IF NOT EXISTS mediaItemImageEmbeddings (
    MediaItemKey TEXT PRIMARY KEY,
    Embedding BLOB NOT NULL, -- 512 or 768 float vector
    ModelVersion TEXT NOT NULL,
    FOREIGN KEY(MediaItemKey) REFERENCES mediaItemFile(MediaItemKey) ON DELETE CASCADE
);

-- 8. Full-Text Search (FTS5) for Dates & Locations
CREATE VIRTUAL TABLE IF NOT EXISTS mediaItemDatesFts USING fts5(
    MediaItemKey UNINDEXED,
    FormattedDate
);

CREATE VIRTUAL TABLE IF NOT EXISTS mediaItemAddressesFts USING fts5(
    MediaItemKey UNINDEXED,
    Town,
    Region,
    Country,
    NormalizedAddress
);
