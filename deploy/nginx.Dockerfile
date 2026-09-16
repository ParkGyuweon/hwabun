FROM node:22-alpine AS frontend-build

WORKDIR /app/frontend
COPY frontend/package*.json ./
RUN npm ci
COPY frontend/ ./
COPY contracts/ /app/contracts/

# Vite substitutes only VITE_* variables at build time. These two identifiers
# are intentionally public; PortOne API/webhook secrets stay in shop-backend.
ARG VITE_PORTONE_STORE_ID
ARG VITE_PORTONE_CHANNEL_KEY
ENV VITE_PORTONE_STORE_ID=${VITE_PORTONE_STORE_ID}
ENV VITE_PORTONE_CHANNEL_KEY=${VITE_PORTONE_CHANNEL_KEY}

RUN npm run build

FROM nginx:1.27-alpine

COPY deploy/nginx/default.conf /etc/nginx/conf.d/default.conf
COPY --from=frontend-build /app/frontend/dist /usr/share/nginx/html

EXPOSE 80 443
