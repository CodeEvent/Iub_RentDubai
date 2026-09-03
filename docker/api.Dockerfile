# Build context is the repo root: docker build -f docker/api.Dockerfile .
FROM node:22-slim
WORKDIR /app

COPY package.json ./
COPY shared ./shared
COPY api ./api

RUN npm install --workspace=@rentshield/shared --workspace=@rentshield/api

# Playwright renders the notice to a real PDF for the OpenSign
# notarization path (esign/renderPdf.js). --with-deps pulls the OS
# libraries Chromium needs on a slim base image.
RUN npx --prefix api playwright install --with-deps chromium

EXPOSE 4000
CMD ["node", "api/src/server.js"]
