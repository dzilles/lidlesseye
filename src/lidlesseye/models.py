from typing import Any

from pydantic import BaseModel, Field


class Node(BaseModel):
    id: str = Field(..., description="Stable unique identifier for this node.")
    label: str = Field(..., description="Ontology-approved graph node label.")
    properties: dict[str, Any] = Field(default_factory=dict)


class Edge(BaseModel):
    source_id: str = Field(..., description="ID of the source node.")
    target_id: str = Field(..., description="ID of the target node.")
    relationship: str = Field(..., description="Ontology-approved relationship type.")


class ExtractedGraph(BaseModel):
    nodes: list[Node] = Field(default_factory=list)
    edges: list[Edge] = Field(default_factory=list)


class ScrapedArticle(BaseModel):
    url: str = Field(..., description="Canonical source URL for the scraped article.")
    raw_text: str = Field(..., description="Raw article text extracted by the spider.")
