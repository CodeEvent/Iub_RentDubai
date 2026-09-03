# Build context is the repo root: docker build -f docker/api.Dockerfile .
FROM node:22-slim
WORKDIR /app

COPY package.json ./
COPY shared ./shared
COPY api ./api
# api/src/services/legalSkills.js reads mcp/skills/*.md directly rather
# than duplicating the content — the api image needs just that folder,
# not the rest of the mcp/ workspace (no MCP server runs in this image).
COPY mcp/skills ./mcp/skills

RUN npm install --workspace=@rentshield/shared --workspace=@rentshield/api

# Playwright renders the notice to a real PDF for the OpenSign
# notarization path (esign/renderPdf.js). --with-deps pulls the OS
# libraries Chromium needs on a slim base image.
RUN npx --prefix api playwright install --with-deps chromium

EXPOSE 4000
CMD ["node", "api/src/server.js"]
