# Project LidlessEye Phase 3 Setup

Phase 3 separates ingestion from graph extraction and storage:

```text
Scrapy spider -> RabbitMQ raw_scrapes queue -> scalable workers -> Gemini -> Neo4j
```

## 1. Install Dependencies

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Store your Gemini key once:

```bash
python vault.py set-google-key
```

## 2. Launch Infrastructure

Start Neo4j and RabbitMQ:

```bash
docker compose up -d
```

Neo4j browser:

```text
http://localhost:7474
```

RabbitMQ management UI:

```text
http://localhost:15672
```

Default RabbitMQ login:

```text
guest / guest
```

## 3. Create Neo4j Constraint

Before starting workers, create the source URL uniqueness constraint.

In the Neo4j browser, run:

```cypher
CREATE CONSTRAINT scraped_article_url IF NOT EXISTS
FOR (a:ScrapedArticle)
REQUIRE a.url IS UNIQUE;
```

Or with `cypher-shell`:

```bash
docker exec -it lidlesseye-neo4j cypher-shell -u neo4j -p password \
  "CREATE CONSTRAINT scraped_article_url IF NOT EXISTS FOR (a:ScrapedArticle) REQUIRE a.url IS UNIQUE;"
```

This lets workers acknowledge duplicate URLs instead of retrying them forever.

## 4. Run The Spider Publisher

In terminal 1:

```bash
source .venv/bin/activate
python run.py --project-file examples/historical_crime_syndicates/project.yaml
```

The spider publishes JSON messages to the durable RabbitMQ queue:

```text
raw_scrapes
```

## 5. Run Scalable Workers

In terminal 2:

```bash
source .venv/bin/activate
python worker.py --project-file examples/historical_crime_syndicates/project.yaml
```

In terminal 3:

```bash
source .venv/bin/activate
python worker.py --project-file examples/historical_crime_syndicates/project.yaml
```

Start more worker terminals to increase parallelism. Workers use manual
acknowledgements and only ack after successful graph extraction and Neo4j
storage. Unexpected failures are nacked and requeued.

## 6. Useful Environment Variables

```bash
export RABBITMQ_URL="amqp://guest:guest@localhost:5672/%2F"
export RABBITMQ_QUEUE="raw_scrapes"
export NEO4J_URI="bolt://localhost:7687"
export NEO4J_USER="neo4j"
export NEO4J_PASSWORD="password"
```

