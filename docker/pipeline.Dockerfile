# Same image as the db, so psql matches the server (schema.sql needs psql 18 for \restrict).
# The scripts are standard-library Python, so python3 is all that's added.
FROM postgres:18

RUN apt-get update \
 && apt-get install -y --no-install-recommends python3 \
 && rm -rf /var/lib/apt/lists/*

# The repo is bind-mounted here by docker-compose, so script edits apply without a rebuild.
WORKDIR /app
ENTRYPOINT []
CMD ["bash"]
