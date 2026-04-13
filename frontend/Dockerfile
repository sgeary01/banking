## Build stage
FROM node:20-alpine AS build

WORKDIR /app
COPY package*.json ./
RUN npm install --silent

COPY . .
RUN npm run build

## Serve stage — tiny nginx image
FROM nginx:alpine
COPY --from=build /app/build /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 80
