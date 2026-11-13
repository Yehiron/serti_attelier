# Backup runner: PostgreSQL client tools + age for public-key encryption.
FROM postgres:16-alpine
RUN apk add --no-cache age tzdata
COPY scripts/backup.sh scripts/backup-cron.sh scripts/restore.sh scripts/backup-verify-restore.sh /usr/local/bin/
RUN chmod 0755 /usr/local/bin/backup.sh /usr/local/bin/backup-cron.sh /usr/local/bin/restore.sh /usr/local/bin/backup-verify-restore.sh
ENTRYPOINT ["/usr/local/bin/backup-cron.sh"]
