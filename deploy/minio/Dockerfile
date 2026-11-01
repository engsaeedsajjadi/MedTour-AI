# MinIO server and client built from the official source releases.
# MinIO stopped publishing the minio/minio and minio/mc images on Docker Hub, so the
# self-hosted medical document store is built locally from pinned release tags instead.
FROM golang:1.25-alpine AS build
ENV CGO_ENABLED=0 GOTOOLCHAIN=auto
RUN apk add --no-cache git
ARG MINIO_RELEASE=RELEASE.2025-10-15T17-29-55Z
ARG MC_RELEASE=RELEASE.2025-08-13T08-35-41Z
WORKDIR /src
RUN git clone --depth 1 --branch "$MINIO_RELEASE" https://github.com/minio/minio.git minio \
 && cd minio \
 && go build -trimpath -ldflags "-s -w -X github.com/minio/minio/cmd.ReleaseTag=$MINIO_RELEASE" -o /out/minio .
RUN git clone --depth 1 --branch "$MC_RELEASE" https://github.com/minio/mc.git mc \
 && cd mc \
 && go build -trimpath -ldflags "-s -w -X github.com/minio/mc/cmd.ReleaseTag=$MC_RELEASE" -o /out/mc .

FROM alpine:3.20
RUN apk add --no-cache ca-certificates
COPY --from=build /out/minio /out/mc /usr/local/bin/
EXPOSE 9000 9001
