from datetime import datetime
from functools import lru_cache
from sqlalchemy import (
    create_engine, Column, Integer, String, Text, DateTime, Float, ForeignKey, JSON, Boolean
)
from sqlalchemy.orm import declarative_base, relationship, sessionmaker

Base = declarative_base()


class RawFeedback(Base):
    """One raw item pulled from any source (Reddit post/comment, YT comment, etc)."""
    __tablename__ = "raw_feedback"
    id = Column(Integer, primary_key=True)
    source = Column(String, nullable=False)          # "reddit" | "youtube" | ...
    source_id = Column(String, nullable=False, unique=True)
    product_name = Column(String, nullable=False)     # from config, not hardcoded
    text = Column(Text, nullable=False)
    author = Column(String)
    url = Column(String)
    created_at = Column(DateTime)
    fetched_at = Column(DateTime, default=datetime.utcnow)
    is_relevant = Column(Integer, default=None)       # nullable bool: filled by relevance filter
    meta = Column(JSON, default={})


class CleanFeedback(Base):
    """Post-cleaning, deduplicated feedback. Downstream analysis stages (ontology
    discovery, aspect extraction) read from here, never from RawFeedback directly —
    keeps 'what survived cleaning' separate from 'what we scraped'.
    """
    __tablename__ = "clean_feedback"
    id = Column(Integer, primary_key=True)
    raw_feedback_id = Column(Integer, ForeignKey("raw_feedback.id"), unique=True)
    product_name = Column(String, nullable=False)
    clean_text = Column(Text, nullable=False)
    created_at = Column(DateTime)              # carried over from raw_feedback.created_at
    is_duplicate_of = Column(Integer, ForeignKey("clean_feedback.id"), nullable=True)
    processed_at = Column(DateTime, default=datetime.utcnow)
    aspect_extraction_done = Column(Boolean, default=False)  # set True once aspect_extraction has run on this row, even if it produced zero mentions — a review with no extractable feature must not look identical to one never attempted, or it gets re-sent to the LLM forever

    raw_feedback = relationship("RawFeedback")


class FeatureOntology(Base):
    """LLM-discovered features/aspects for a product. Not predefined."""
    __tablename__ = "feature_ontology"
    id = Column(Integer, primary_key=True)
    product_name = Column(String, nullable=False)
    feature_name = Column(String, nullable=False)
    description = Column(Text)
    category = Column(String, nullable=True)  # e.g. "Engine & Powertrain" — assigned by a one-off categorize_features pass, not ontology discovery itself, so re-running discovery doesn't require re-categorizing
    discovered_at = Column(DateTime, default=datetime.utcnow)


class AspectMention(Base):
    """A single clean-feedback item mapped to a feature + sentiment + verbatim snippet."""
    __tablename__ = "aspect_mention"
    id = Column(Integer, primary_key=True)
    clean_feedback_id = Column(Integer, ForeignKey("clean_feedback.id"))
    feature_name = Column(String, nullable=False)
    sentiment = Column(String)         # "positive" | "negative" | "neutral"
    severity = Column(Float)           # 0-1, LLM-estimated functional/business impact — NOT emotional tone
    safety_related = Column(Boolean, default=False)  # rider/physical safety risk — separate axis from severity, see aspect_extraction.py
    snippet = Column(Text)
    extracted_at = Column(DateTime, default=datetime.utcnow)

    clean_feedback = relationship("CleanFeedback")


class IssueCluster(Base):
    """Grouped negative aspect mentions -> one real issue, with priority score."""
    __tablename__ = "issue_cluster"
    id = Column(Integer, primary_key=True)
    product_name = Column(String, nullable=False)
    feature_name = Column(String, nullable=False)
    issue_summary = Column(Text)
    mention_count = Column(Integer)
    avg_severity = Column(Float)
    safety_related = Column(Boolean, default=False)  # true if any member mention was safety-related
    priority_score = Column(Float)
    trend = Column(String)             # "increasing" | "stable" | "decreasing" | "insufficient_data"
    confidence = Column(Float)         # 0-1, derived from evidence volume — not a statistical CI, see clustering_scoring.py
    primary_context = Column(String)   # short LLM-derived context, e.g. "Long-distance / pillion riding"
    recommended_investigation = Column(Text)  # decision support only — never proof of a defect, DASHBOARD.md section 7
    representative_snippets = Column(JSON, default=[])
    computed_at = Column(DateTime, default=datetime.utcnow)


class IssueClusterMember(Base):
    """Join table: which aspect_mention rows belong to which cluster.
    This is the full evidence chain — every insight traceable back to its
    source review, not just the top-5 representative snippets on the cluster.
    """
    __tablename__ = "issue_cluster_member"
    id = Column(Integer, primary_key=True)
    issue_cluster_id = Column(Integer, ForeignKey("issue_cluster.id"), nullable=False)
    aspect_mention_id = Column(Integer, ForeignKey("aspect_mention.id"), nullable=False)

    issue_cluster = relationship("IssueCluster")
    aspect_mention = relationship("AspectMention")


class PipelineRunLog(Base):
    """One row per full pipeline execution. Used to gate the monthly
    auto-run — 'due' means no scheduled run in the last N days — and to
    give an honest, inspectable history of what actually ran and when
    (not just a claim that scheduling exists)."""
    __tablename__ = "pipeline_run_log"
    id = Column(Integer, primary_key=True)
    trigger = Column(String, nullable=False)     # "manual" | "scheduled"
    started_at = Column(DateTime, default=datetime.utcnow)
    finished_at = Column(DateTime)
    results = Column(JSON, default={})


@lru_cache
def get_engine(db_url: str):
    # lru_cache -> one shared connection pool per process, not one per module/call.
    # pool_pre_ping avoids stale-connection errors after Neon's serverless
    # compute auto-suspends on idle.
    return create_engine(db_url, pool_pre_ping=True, pool_recycle=300)


@lru_cache
def get_session_factory(db_url: str):
    engine = get_engine(db_url)
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)