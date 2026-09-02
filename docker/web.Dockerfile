# Build context is the repo root: docker build -f docker/web.Dockerfile .
FROM node:22-slim AS build
WORKDIR /app

COPY package.json ./
COPY shared ./shared
COPY vue ./vue

RUN npm install --workspace=@rentshield/shared --workspace=@rentshield/vue
RUN npm run build --workspace=@rentshield/vue

FROM node:22-slim
WORKDIR /app
RUN npm install -g serve@14
COPY --from=build /app/vue/dist ./dist
EXPOSE 5173
CMD ["serve", "-s", "dist", "-l", "5173"]
