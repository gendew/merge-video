# Node-only image for Next.js + ffmpeg-static
FROM node:20-slim AS base

WORKDIR /app
ENV PNPM_HOME=/root/.local/share/pnpm
ENV PATH=$PNPM_HOME:$PATH
RUN corepack enable pnpm

COPY package.json tsconfig.json next.config.js next-env.d.ts ./
COPY src ./src
COPY .gitignore .dockerignore ./

RUN pnpm install --frozen-lockfile || pnpm install
RUN pnpm build

FROM node:20-slim
WORKDIR /app
ENV NODE_ENV=production
ENV PNPM_HOME=/root/.local/share/pnpm
ENV PATH=$PNPM_HOME:$PATH
RUN corepack enable pnpm

COPY --from=base /app/package.json /app/next.config.js /app/tsconfig.json /app/next-env.d.ts ./
COPY --from=base /app/node_modules ./node_modules
COPY --from=base /app/.next ./.next
COPY --from=base /app/src ./src

EXPOSE 3000
CMD ["pnpm", "start"]
