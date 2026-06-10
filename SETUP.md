# Project LidlessEye Phase 2 Setup

## Directory Layout

Place these files in the same project directory:

```text
lidlessEye/
  README.md
  ontology.yaml
  run.py
  vault.py
  suggestions.py
  requirements.txt
  src/
    lidlesseye/
      models.py
      spider.py
      run.py
      vault.py
      suggestions.py
      pipelines/
        llm_extraction.py
        neo4j_storage.py
        suggestions_store.py
```

## Create and Activate a Virtual Environment

macOS/Linux:

```bash
python3 -m venv venv
source venv/bin/activate
```

Windows PowerShell:

```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
```

## Install Dependencies

```bash
pip install -r requirements.txt
```

## Start Neo4j

```bash
docker run --name lidlesseye-neo4j -p 7474:7474 -p 7687:7687 -e NEO4J_AUTH=neo4j/password neo4j:latest
```

If the container already exists:

```bash
docker start lidlesseye-neo4j
```

## Configure LLM Access

Store your Gemini API key once in the local LidlessEye vault:

```bash
python vault.py set-google-key
```

The vault stores secrets at:

```bash
python vault.py path
```

You can still override the vault for a single terminal session by exporting
`GOOGLE_API_KEY` manually.

macOS/Linux:

```bash
export GOOGLE_API_KEY="your_api_key_here"
```

Windows PowerShell:

```powershell
$env:GOOGLE_API_KEY="your_api_key_here"
```

## Run the Pipeline

Cyber threats profile:

```bash
python run.py --profile cyber_threats
```

Use a different Gemini model if needed:

```bash
python run.py --profile cyber_threats --llm-model google/gemini-2.5-flash
```

Corporate networks profile:

```bash
python run.py --profile corporate_networks
```

Historical crime syndicate Wikipedia example:

```bash
python run.py --project-file examples/historical_crime_syndicates/project.yaml
```

Unknown LLM relationship types are not fatal. They are skipped from Neo4j and
recorded with counters and replay context in the project suggestions file, for
example:

```text
examples/historical_crime_syndicates/ontology_suggestions.json
```

Review suggestion counters:

```bash
python suggestions.py list \
  --suggestions-file examples/historical_crime_syndicates/ontology_suggestions.json \
  --profile historical_crime_syndicates
```

After promoting a suggested relationship into the ontology, replay its saved
edges without scraping or calling the LLM again:

```bash
python suggestions.py replay \
  --suggestions-file examples/historical_crime_syndicates/ontology_suggestions.json \
  --ontology-file examples/historical_crime_syndicates/ontology.yaml \
  --profile historical_crime_syndicates \
  --relationship SOME_RELATIONSHIP
```
