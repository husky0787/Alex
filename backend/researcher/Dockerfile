FROM public.ecr.aws/awsguru/aws-lambda-adapter:1.0.0 AS lambda-adapter
FROM python:3.12-slim AS browser-deps

ARG INSTALL_BUILD_ESSENTIAL=false
ARG DEBIAN_MIRROR=http://deb.debian.org

WORKDIR /app

ENV PLAYWRIGHT_BROWSERS_PATH=/ms-playwright \
    HOME=/tmp \
    XDG_CACHE_HOME=/tmp/.cache

# Install Node.js, build tools, and the Playwright MCP server.
RUN sed -i "s|http://deb.debian.org|${DEBIAN_MIRROR}|g" /etc/apt/sources.list.d/debian.sources \
    && apt-get update \
    && apt-get install -y curl \
    && if [ "$INSTALL_BUILD_ESSENTIAL" = "true" ]; then apt-get install -y build-essential; fi \
    && curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
    && apt-get install -y nodejs \
    && npm install -g @playwright/mcp@0.0.75 \
    && rm -rf /var/lib/apt/lists/*

# Keep OS dependencies cached when a browser download needs to be retried.
RUN npx -y playwright install-deps chromium

FROM browser-deps AS runtime
ARG PLAYWRIGHT_CHROMIUM_DOWNLOAD_HOST
# MCP launches the full Chromium executable; a second headless-shell binary is unused.
RUN npx -y playwright install --no-shell chromium

# Install uv for Python dependency management inside the container.
ARG PIP_INDEX_URL=https://pypi.org/simple
RUN pip install uv

# Copy dependency metadata first so Docker can cache the install layer.
COPY researcher/pyproject.toml researcher/uv.lock ./
COPY research /research
RUN uv sync --frozen --no-install-project
ENV PATH="/app/.venv/bin:$PATH"

# Copy the application code.
COPY researcher/*.py ./

# Add the Lambda Web Adapter so Lambda can proxy HTTP requests to uvicorn.
COPY --from=lambda-adapter /lambda-adapter /opt/extensions/lambda-adapter

# The FastAPI app listens on port 8000 inside the container.
ENV AWS_LWA_PORT=8000

# Expose the app port and run the web server.
EXPOSE 8000
CMD ["uvicorn", "server:app", "--host", "0.0.0.0", "--port", "8000"]
