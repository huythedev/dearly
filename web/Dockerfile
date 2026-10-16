FROM node:24-alpine AS build
WORKDIR /web
COPY package.json package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY index.html tsconfig.json vite.config.ts ./
COPY src ./src
COPY public ./public
RUN npm run build

FROM nginx:1.30.6-alpine
COPY --from=build /web/dist /usr/share/nginx/html
COPY docker/nginx.conf.template /etc/nginx/dearly.conf.template
COPY --chmod=755 docker/entrypoint.sh /usr/local/bin/dearly-frontend
ENV DEARLY_FRONTEND_LISTEN_PORT=8080
USER nginx
EXPOSE 8080
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD wget -q -O /dev/null "http://127.0.0.1:${DEARLY_FRONTEND_LISTEN_PORT}/frontend-health" || exit 1
ENTRYPOINT ["/usr/local/bin/dearly-frontend"]
