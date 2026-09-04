FROM node:22-bookworm-slim AS build
WORKDIR /build
ENV BUILD_STANDALONE=1
COPY frontend/package*.json ./
RUN npm install
COPY frontend/ ./
RUN npm run build

FROM node:22-bookworm-slim
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends python3 python3-pip && rm -rf /var/lib/apt/lists/*
COPY backend/requirements.txt /app/backend/requirements.txt
RUN pip3 install --break-system-packages --no-cache-dir -r /app/backend/requirements.txt
COPY backend/ /app/backend/
COPY --from=build /build/.next/standalone /app/frontend/
COPY --from=build /build/.next/static /app/frontend/.next/static
COPY --from=build /build/public /app/frontend/public
WORKDIR /app/frontend
ENV PORT=80 PYTHON_BIN=/usr/bin/python3
EXPOSE 80
CMD ["node", "server.js"]
