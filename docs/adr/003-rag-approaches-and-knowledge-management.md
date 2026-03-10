# ADR-003: RAG Approaches and Knowledge Management

**Status:** Accepted
**Date:** 2026-03-10
**Issue:** [#3](https://github.com/DigitalTwinSystems/entsim/issues/3)

## Context

entsim agents need enterprise-specific context (org structure, processes, domain knowledge) to simulate realistic employee behavior. We need a knowledge layer supporting ~12 concurrent agents with role-based access to a shared document corpus (estimated 1,000–5,000 documents).

Requirements: async Python compatibility, hybrid search (semantic + keyword), role-based filtering, low operational complexity, minimal cost at this scale.

## Decision

### Vector store: Qdrant (self-hosted via Docker)

| Component | Choice |
|-----------|--------|
| Vector store | [Qdrant](https://github.com/qdrant/qdrant) (Docker, Apache 2.0) |
| Python client | [`qdrant-client`](https://python-client.qdrant.tech/) `AsyncQdrantClient` |
| Search strategy | Hybrid: sparse (SPLADE) + dense vectors with RRF fusion |

### Embedding model: OpenAI text-embedding-3-small (default)

| Model | Dimensions | Cost/MTok | Use case |
|-------|-----------|-----------|----------|
| [text-embedding-3-small](https://platform.openai.com/docs/guides/embeddings) | 1536 | $0.02 | Default — good quality, negligible cost |
| [BGE-M3](https://huggingface.co/BAAI/bge-m3) (local) | 1024 | Free | Offline/local dev — provides sparse+dense in one model |

### RAG framework: Direct implementation (no framework)

Use Qdrant's async client directly with embedding API calls. No LlamaIndex/LangChain/Haystack.

### Knowledge architecture: Shared collection with metadata filtering

One Qdrant collection for all enterprise documents. Role-based access via metadata pre-filtering at query time.

## Rationale

### Why Qdrant over alternatives

| Criterion | ChromaDB | Qdrant | pgvector | Pinecone |
|-----------|----------|--------|----------|----------|
| Native async Python | No (thread-safe only) | Yes (`AsyncQdrantClient`) | Via asyncpg | SDK-dependent |
| Native hybrid search | No | Yes (SPLADE + dense + [RRF](https://glaforge.dev/posts/2026/02/10/advanced-rag-understanding-reciprocal-rank-fusion-in-hybrid-search/)) | Requires [extra extensions](https://www.paradedb.com/blog/hybrid-search-in-postgresql-the-missing-manual) | No |
| Query latency (small scale) | ~3 ms | Sub-1 ms p99 | 1–5 ms | ~7 ms |
| Setup | `pip install` | `docker run` | Postgres + extensions | API key |
| Cost | Free | Free (self-hosted) | Free (infra only) | [$0.33/GB + ops](https://www.tigerdata.com/blog/a-guide-to-pinecone-pricing) |
| Production readiness | Improving (v1.0) | Strong (RBAC, SOC-2) | Very strong | Very strong |

Qdrant wins on the two features most critical for this system: native async Python and native hybrid search. ChromaDB lacks both. pgvector would require additional extensions for hybrid search. Pinecone adds cost and vendor lock-in without benefit at this scale.

If we later adopt PostgreSQL for agent state, pgvector becomes worth reconsidering to consolidate infrastructure.

### Why text-embedding-3-small

- At 5,000 documents: total embedding cost is ~$0.10. Cost is irrelevant at this scale.
- MTEB score (~62) is sufficient for enterprise document retrieval.
- 1536 dimensions; supports [Matryoshka reduction](https://platform.openai.com/docs/guides/embeddings#use-cases) to 512 if storage matters.
- Available via LiteLLM for consistency with LLM integration layer.
- [Cohere embed-v4](https://docs.cohere.com/changelog/embed-multimodal-v4) (MTEB 65.2, 128K context) is a future upgrade path if retrieval quality needs improvement.

### Why no RAG framework

At this scale (one vector store, one embedding model, straightforward retrieval):
- Direct Qdrant async client calls are ~20 lines of code for search.
- Framework overhead adds 5–14 ms per query and significant dependency weight.
- Frameworks change rapidly — LlamaIndex and LangChain have had breaking API changes across versions.
- If ingestion pipelines grow complex (many document types, async bulk processing), [LlamaIndex](https://developers.llamaindex.ai/python/examples/ingestion/async_ingestion_pipeline/) is the first framework to consider.

### Why shared collection with metadata filtering

- [Standard enterprise pattern](https://aws.amazon.com/blogs/machine-learning/access-control-for-vector-stores-using-metadata-filtering-with-knowledge-bases-for-amazon-bedrock/) validated by AWS Bedrock, Azure AI, and [academic research](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=5360983).
- Single ingestion pipeline; no document duplication across per-agent collections.
- Cross-department queries possible for agents with broad access (e.g., CEO).
- Qdrant applies metadata filters server-side before ANN search — no performance penalty.

Example metadata schema per document:

```json
{
  "department": "engineering",
  "sensitivity": "internal",
  "accessible_roles": ["cto", "developer", "ceo"],
  "source": "confluence",
  "updated_at": "2026-03-10T12:00:00Z"
}
```

### Hybrid search justification

Enterprise content includes structured terminology (product names, employee names, platform names like "LinkedIn", "X"). Pure dense retrieval underperforms on exact-match queries for these terms. [Hybrid search with RRF](https://superlinked.com/vectorhub/articles/optimizing-rag-with-hybrid-search-reranking) is the 2025–2026 standard for enterprise RAG:

1. Dense ANN retrieval (semantic similarity)
2. Sparse BM25/SPLADE retrieval (keyword matching)
3. RRF fusion: `score = Σ 1/(k + rank_i)`, k=60

Qdrant supports this natively — no external BM25 index needed.

### Storage and performance projections

| Metric | Value |
|--------|-------|
| Corpus size | 1,000–5,000 documents |
| Raw vector storage (1536d) | 30–150 MB with HNSW index |
| Embedding cost (one-time) | $0.02–$0.10 |
| Query latency (12 concurrent) | Sub-1 ms p99 per query |
| Re-embedding on model change | $0.02–$0.10 |

## Consequences

### Positive

- Native async integration with our asyncio agent system
- Hybrid search improves retrieval quality for enterprise-specific terms
- Role-based filtering without per-agent collection duplication
- Zero ongoing cost (self-hosted Qdrant)
- Minimal dependencies (qdrant-client + embedding API)

### Negative

- Qdrant Docker container adds an infrastructure component to manage
- No framework means implementing chunking, metadata extraction, and ingestion logic ourselves
- text-embedding-3-small is API-dependent; offline operation requires switching to BGE-M3
- If retrieval quality is insufficient, may need to add a reranking stage (Cohere Rerank or cross-encoder)
