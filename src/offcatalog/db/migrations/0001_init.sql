CREATE TABLE files (
  id TEXT PRIMARY KEY,
  path TEXT UNIQUE NOT NULL,
  mtime REAL NOT NULL,
  size INTEGER NOT NULL,
  fingerprint TEXT NOT NULL,
  last_scanned_at TEXT NOT NULL,
  deleted_at TEXT
);

CREATE TABLE local_tracks (
  id TEXT PRIMARY KEY,
  file_id TEXT NOT NULL REFERENCES files(id),
  artist TEXT NOT NULL,
  album_artist TEXT,
  title TEXT NOT NULL,
  album TEXT,
  version_qualifiers TEXT NOT NULL,
  track_number INTEGER,
  disc_number INTEGER,
  duration_seconds REAL NOT NULL,
  year INTEGER,
  isrc TEXT,
  musicbrainz_track_id TEXT,
  musicbrainz_recording_id TEXT,
  raw_tags_json TEXT NOT NULL
);

CREATE TABLE providers (
  id TEXT PRIMARY KEY,
  name TEXT UNIQUE NOT NULL
);

CREATE TABLE provider_candidates (
  id TEXT PRIMARY KEY,
  local_track_id TEXT NOT NULL REFERENCES local_tracks(id),
  provider_id TEXT NOT NULL REFERENCES providers(id),
  provider_track_id TEXT NOT NULL,
  provider_artist TEXT NOT NULL,
  provider_title TEXT NOT NULL,
  provider_album TEXT,
  provider_duration REAL NOT NULL,
  match_score REAL NOT NULL,
  match_reason TEXT NOT NULL,
  checked_at TEXT NOT NULL
);

CREATE TABLE availability_results (
  local_track_id TEXT NOT NULL REFERENCES local_tracks(id),
  provider_id TEXT NOT NULL REFERENCES providers(id),
  state TEXT NOT NULL,
  best_candidate_id TEXT REFERENCES provider_candidates(id),
  checked_at TEXT,
  error_message TEXT,
  PRIMARY KEY (local_track_id, provider_id)
);

CREATE TABLE manual_match_decisions (
  local_track_id TEXT NOT NULL REFERENCES local_tracks(id),
  provider_candidate_id TEXT NOT NULL REFERENCES provider_candidates(id),
  decision TEXT NOT NULL,
  decided_at TEXT NOT NULL,
  PRIMARY KEY (local_track_id, provider_candidate_id)
);

CREATE TABLE scan_runs (
  id TEXT PRIMARY KEY,
  started_at TEXT NOT NULL,
  finished_at TEXT,
  files_added INTEGER NOT NULL DEFAULT 0,
  files_changed INTEGER NOT NULL DEFAULT 0,
  files_deleted INTEGER NOT NULL DEFAULT 0
);
