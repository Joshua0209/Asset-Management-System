-- Compose-only credentials for prom/mysqld-exporter (Phase 3, locked decision 8).
--
-- MySQL 8.4 auto-runs files under /docker-entrypoint-initdb.d/ on first boot.
-- If your mysql_data volume already exists from a previous boot, this file is
-- skipped. To apply the grant against the live container without wiping dev
-- data (mysql_data + backend_uploads), run:
--
--   docker compose exec mysql sh -c \
--     'mysql -uroot -ppassword < /docker-entrypoint-initdb.d/01-exporter-grant.sql'
--
-- The destructive equivalent (wipes mysql_data + backend_uploads) is:
--
--   docker compose down -v && \
--     docker compose -f docker-compose.yml \
--                    -f docker-compose.observability.yml up -d
--
-- The grant is intentionally narrow: PROCESS, REPLICATION CLIENT, SELECT is
-- everything mysqld-exporter needs for its process / replication / table-stats
-- collectors. The exporter has no write access.

CREATE USER IF NOT EXISTS 'exporter'@'%' IDENTIFIED BY 'exporter' WITH MAX_USER_CONNECTIONS 3;
GRANT PROCESS, REPLICATION CLIENT, SELECT ON *.* TO 'exporter'@'%';
FLUSH PRIVILEGES;
