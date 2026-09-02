# Build context is the repo root: docker build -f docker/api.Dockerfile .
FROM node:22-slim
WORKDIR /app

COPY package.json ./
COPY shared ./shared
COPY api ./api

RUN npm install --workspace=@rentshield/shared --workspace=@rentshield/api

EXPOSE 4000
CMD ["node", "api/src/server.js"]
