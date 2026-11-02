FROM postgres:17-alpine
RUN apk add --no-cache openssl
COPY backup.sh restore.sh verify-restore.sh /usr/local/bin/
RUN chmod 0755 /usr/local/bin/backup.sh /usr/local/bin/restore.sh /usr/local/bin/verify-restore.sh
ENTRYPOINT ["/usr/local/bin/backup.sh"]
