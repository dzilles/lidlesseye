# Project LidlessEye

Project LidlessEye is a schema-agnostic knowledge graph pipeline built with
Scrapy, RabbitMQ, Gemini through Instructor, Pydantic, and Neo4j.

The pipeline scrapes public web pages, publishes raw scrape messages to
RabbitMQ, lets scalable workers extract graph-shaped entities and relationships
with an LLM, validates the result with Pydantic, and stores the graph in Neo4j.

## Architecture

```text
Scrapy spider
  -> RabbitMQ raw_scrapes queue
  -> LLM extraction pipeline
  -> ontology normalization and suggestions
  -> Neo4j storage pipeline
```

Key behavior:

- Ontology profiles are external YAML configuration.
- The graph envelope is stable: `ExtractedGraph(nodes, edges)`.
- Unknown relationship types do not crash the run.
- Unknown relationships are recorded with counters and replay context.
- Workers use manual RabbitMQ acknowledgements.
- Neo4j writes are idempotent through `MERGE` plus a unique source URL constraint.
- Gemini API keys are loaded from a local vault outside the repo.

## Project Layout

```text
.
  run.py                         # Root CLI wrapper
  worker.py                      # Root worker CLI wrapper
  vault.py                       # Root vault CLI wrapper
  suggestions.py                 # Root suggestions CLI wrapper
  docker-compose.yml             # Neo4j and RabbitMQ infrastructure
  ontology.yaml                  # Default ontology profiles
  requirements.txt
  SETUP.md
  SETUP_PHASE3.md
  README.md
  src/
    lidlesseye/
      run.py
      worker.py
      vault.py
      suggestions.py
      models.py
      spider.py
      ontology.py
      cypher.py
      pipelines/
        llm_extraction.py
        neo4j_storage.py
        rabbitmq_publisher.py
        suggestions_store.py
  examples/
    historical_crime_syndicates/
      project.yaml
      ontology.yaml
      README.md
```

## Quick Start

Create and activate a virtual environment:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Store your Gemini API key once:

```bash
python vault.py set-google-key
```

Start Neo4j and RabbitMQ:

```bash
docker compose up -d
```

Create the source URL uniqueness constraint:

```cypher
CREATE CONSTRAINT scraped_article_url IF NOT EXISTS
FOR (a:ScrapedArticle)
REQUIRE a.url IS UNIQUE;
```

Run one or more workers:

```bash
python worker.py --project-file examples/historical_crime_syndicates/project.yaml
```

Run the historical crime syndicate spider publisher:

```bash
python run.py --project-file examples/historical_crime_syndicates/project.yaml
```

## Ontology Suggestions

When the LLM emits relationship types not allowed by the active ontology, those
edges are skipped from Neo4j and stored in the configured suggestions file.

List suggestion counters:

```bash
python suggestions.py list \
  --suggestions-file examples/historical_crime_syndicates/ontology_suggestions.json \
  --profile historical_crime_syndicates
```

After promoting a suggested relationship into the ontology, replay saved edges:

```bash
python suggestions.py replay \
  --suggestions-file examples/historical_crime_syndicates/ontology_suggestions.json \
  --ontology-file examples/historical_crime_syndicates/ontology.yaml \
  --profile historical_crime_syndicates \
  --relationship SOME_RELATIONSHIP
```

## Notes

- `pipeline.py` is the original Phase 1 single-file walking skeleton.
- The production-oriented Phase 3 implementation lives under `src/lidlesseye`.
- Full distributed setup instructions are in `SETUP_PHASE3.md`.
- Local secrets are stored outside the repository at
  `~/.config/lidlesseye/secrets.yaml`.
