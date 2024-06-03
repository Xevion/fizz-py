docker pull ghcr.io/jefuller/artifact-server:latest
docker run -d --name artifact-server -p 8080:8080 --add-host host.docker.internal:host-gateway -e AUTH_KEY=foo ghcr.io/jefuller/artifact-server:latest
act --env ACTIONS_RUNTIME_URL=http://host.docker.internal:8080/ --env ACTIONS_RUNTIME_TOKEN=foo --env ACTIONS_CACHE_URL=http://host.docker.internal:8080/ --artifact-server-path out