# Build stage
FROM node:22-alpine AS build

WORKDIR /app

COPY interfaces/dashboard/package*.json ./
RUN npm ci

COPY interfaces/dashboard/ ./

# Pass API URL at build time (conductor's internal Docker URL)
ARG VITE_API_URL=http://localhost:10000
ENV VITE_API_URL=$VITE_API_URL

RUN npm run build

# Serve stage — lightweight static server
FROM nginx:alpine

# Copy built assets
COPY --from=build /app/dist /usr/share/nginx/html

# Nginx config for SPA routing + API proxy
COPY interfaces/dashboard/nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 1607

CMD ["nginx", "-g", "daemon off;"]
