FROM python:3.11-slim AS node-base

ARG NODE_VERSION=22.17.0
ENV NODE_HOME=/usr/local/lib/nodejs/node-v22.17.0-linux-x64
ENV PATH="${NODE_HOME}/bin:${PATH}"

RUN python -c "import hashlib,pathlib,tarfile,urllib.request; version='22.17.0'; name=f'node-v{version}-linux-x64.tar.xz'; base=f'https://nodejs.org/dist/v{version}/'; archive=pathlib.Path('/tmp')/name; urllib.request.urlretrieve(base+name, archive); sums=urllib.request.urlopen(base+'SHASUMS256.txt').read().decode(); expected=next(line.split()[0] for line in sums.splitlines() if line.endswith('  '+name)); actual=hashlib.sha256(archive.read_bytes()).hexdigest(); assert actual == expected, 'Node archive checksum mismatch'; pathlib.Path('/usr/local/lib/nodejs').mkdir(parents=True, exist_ok=True); tarfile.open(archive).extractall('/usr/local/lib/nodejs', filter='data'); archive.unlink()" \
    && npm install --global pnpm@10.32.0

FROM node-base AS build

WORKDIR /app

COPY package.json pnpm-lock.yaml ./
COPY prisma ./prisma
RUN pnpm install --frozen-lockfile

COPY nest-cli.json tsconfig.json tsconfig.build.json ./
COPY src ./src
RUN pnpm run prisma:generate \
    && pnpm run build \
    && pnpm prune --prod

FROM node-base AS runtime

ENV NODE_ENV=production
WORKDIR /app

COPY --from=build /app/package.json ./package.json
COPY --from=build /app/node_modules ./node_modules
COPY --from=build /app/dist ./dist
COPY --from=build /app/prisma ./prisma

EXPOSE 3000

CMD ["node", "dist/main"]
