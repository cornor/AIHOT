FROM ghcr.io/rachelos/we-mp-rss@sha256:af771f21b3f7958a5dea16911fba050a6d7b92eac2fb2499c467c1b11f07ef34 AS upstream
FROM node:24-trixie-slim AS frontend
WORKDIR /ui
COPY --from=upstream /app/web_ui/ ./
COPY werss/patch-ui.mjs /patch-ui.mjs
RUN node /patch-ui.mjs /ui
ARG NPM_REGISTRY=https://registry.npmmirror.com
RUN npm ci --no-audit --no-fund --registry=$NPM_REGISTRY
RUN npm run build

FROM upstream
COPY --from=frontend /ui/dist/ /app/static/
COPY werss/weread_mp.py /app/core/wx/model/weread_mp.py
COPY werss/patch-backend.py /tmp/patch-backend.py
RUN python3 /tmp/patch-backend.py && rm /tmp/patch-backend.py
COPY werss/auth_event.py /app/core/gamehot_auth_event.py
COPY werss/patch-auth-event.py /tmp/patch-auth-event.py
RUN python3 /tmp/patch-auth-event.py && rm /tmp/patch-auth-event.py
