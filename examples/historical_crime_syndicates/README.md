# Historical Crime Syndicate Connections Example

This example runs Project LidlessEye against public Wikipedia pages and asks the
Gemini extraction layer to produce a small historical knowledge graph.

## Files

```text
examples/historical_crime_syndicates/
  project.yaml
  ontology.yaml
  README.md
```

## Run

From the repository root:

```bash
python run.py --project-file examples/historical_crime_syndicates/project.yaml
```

The project file selects:

- `historical_crime_syndicates` as the ontology profile
- `google/gemini-2.5-flash-lite` as the default Gemini model
- Wikipedia pages for the Five Families, Sicilian Mafia, and Irish Mob
- `ontology_suggestions.json` as the relationship suggestion store

If Gemini extracts relationship types that are not in the active ontology, the
pipeline skips those edges instead of crashing and records them in:

```text
examples/historical_crime_syndicates/ontology_suggestions.json
```

Each suggestion keeps a counter plus example source/target node snapshots so a
promoted relationship can be recreated without rerunning Wikipedia scraping and
LLM extraction.

List suggestions:

```bash
python suggestions.py list \
  --suggestions-file examples/historical_crime_syndicates/ontology_suggestions.json \
  --profile historical_crime_syndicates
```

After adding a suggested relationship to `allowed_relationships`, replay its
saved edges into Neo4j:

```bash
python suggestions.py replay \
  --suggestions-file examples/historical_crime_syndicates/ontology_suggestions.json \
  --ontology-file examples/historical_crime_syndicates/ontology.yaml \
  --profile historical_crime_syndicates \
  --relationship SOME_RELATIONSHIP
```

Neo4j and `GOOGLE_API_KEY` must be configured as described in the root
`SETUP.md`.
