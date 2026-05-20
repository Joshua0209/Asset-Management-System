-- Compose-only credentials for prom/mysqld-exporter (Phase 3, locked decision 8).
--
-- MySQL 8.4 auto-runs files under /docker-entrypoint-initdb.d/ on first boot.
-- If the user already exists from a previous boot, you must run
-- `docker compose down -v` to re-seed.
--
-- The grant is intentionally narrow — PROCESS + REPLICATION CLIENT + SELECT
-- is what mysqld-exporter needs to populate process / replication / table-stats
-- collectors. The exporter has no write access.

CREATE USER IF NOT EXISTS 'exporter'@'%' IDENTIFIED BY 'exporter' WITH MAX_USER_CONNECTIONS 3;
GRANT PROCESS, REPLICATION CLIENT, SELECT ON *.* TO 'exporter'@'%';
FLUSH PRIVILEGES;
