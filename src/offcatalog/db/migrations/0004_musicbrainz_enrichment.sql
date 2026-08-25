ALTER TABLE local_tracks ADD COLUMN musicbrainz_isrc TEXT;
ALTER TABLE local_tracks ADD COLUMN musicbrainz_disambiguation TEXT;
ALTER TABLE local_tracks ADD COLUMN musicbrainz_checked_fingerprint TEXT;
ALTER TABLE provider_candidates ADD COLUMN provider_isrc TEXT;
