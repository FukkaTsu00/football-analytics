"""Football News Analytics dashboard (Streamlit), reading the warehouse tables.

Run on your PC (reads WAREHOUSE_URL from .env):
    streamlit run app/dashboard.py
In Docker, WAREHOUSE_URL is set by docker-compose.yml.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pandas as pd
import plotly.express as px
import streamlit as st
from dotenv import load_dotenv
from sqlalchemy import create_engine, text

load_dotenv(Path(__file__).resolve().parents[1] / ".env")  # no effect if the file doesn't exist

st.set_page_config(page_title="Football News Analytics", page_icon="⚽", layout="wide")

SOURCE_COLORS = {"BBC Sport": "#2a6fdb", "Goal.com": "#e07a1f"}


# ---------------------------------------------------------------- data access
@st.cache_resource
def get_engine():
    url = os.environ.get("WAREHOUSE_URL")
    if not url:
        st.error("WAREHOUSE_URL is not set. Add it to your .env file (see .env.example).")
        st.stop()
    return create_engine(url, pool_pre_ping=True)


@st.cache_data(ttl=300)  # re-query the database at most every 5 minutes
def query(sql: str) -> pd.DataFrame:
    with get_engine().connect() as conn:
        return pd.read_sql(text(sql), conn)


def load_data() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    articles = query(
        "SELECT article_id, ingest_date, source, title, url, author, published_at, content_length FROM articles"
    )
    articles["published_at"] = pd.to_datetime(articles["published_at"], utc=True, errors="coerce")
    topics = query("SELECT article_id, topic, method FROM article_topics")
    entities = query("SELECT article_id, entity_type, entity FROM article_entities")
    runs = query("SELECT ingest_date, loaded_at, articles_loaded, quality_report FROM pipeline_runs")
    return articles, topics, entities, runs


def bar(df: pd.DataFrame, x: str, y: str, title: str, **kwargs):
    fig = px.bar(df, x=x, y=y, title=title, **kwargs)
    fig.update_layout(margin=dict(l=10, r=10, t=50, b=10), legend_title_text="")
    return fig


# ---------------------------------------------------------------- page
def main() -> None:
    try:
        articles, topics, entities, runs = load_data()
    except Exception as exc:  # database down or tables not created yet
        st.error(f"Could not read the warehouse: {exc}")
        st.info("Start the stack (docker compose up -d) and run the pipeline at least once.")
        st.stop()

    if articles.empty:
        st.info("The warehouse is empty: run the pipeline first.")
        st.stop()

    # ---------------- sidebar filters
    st.sidebar.header("Filters")
    sources = sorted(articles["source"].unique())
    chosen_sources = st.sidebar.multiselect("Sources", sources, default=sources)
    dates = sorted(articles["ingest_date"].unique())
    if len(dates) > 1:
        start, end = st.sidebar.select_slider("Ingestion dates", options=dates, value=(dates[0], dates[-1]))
    else:
        start = end = dates[0]
    st.sidebar.caption(f"Data from {dates[0]} to {dates[-1]}")

    view = articles[articles["source"].isin(chosen_sources) & articles["ingest_date"].between(start, end)]
    ids = set(view["article_id"])
    topic_view = topics[topics["article_id"].isin(ids)]
    entity_view = entities[entities["article_id"].isin(ids)]
    clubs = entity_view[entity_view["entity_type"] == "club"]
    players = entity_view[entity_view["entity_type"] == "player"]

    # ---------------- header and KPIs
    st.title("⚽ Football News Analytics")
    last_load = pd.to_datetime(runs["loaded_at"]).max()
    st.caption(
        "BBC Sport and Goal.com, scraped hourly by Airflow → bronze / silver / gold → PostgreSQL. "
        f"Last load: {last_load:%Y-%m-%d %H:%M} UTC."
    )
    k1, k2, k3, k4 = st.columns(4)
    k1.metric("Articles", f"{len(view):,}")
    k2.metric("Days covered", view["ingest_date"].nunique())
    k3.metric("Clubs mentioned", clubs["entity"].nunique())
    k4.metric("Players & managers mentioned", players["entity"].nunique())

    overview, entities_tab, explorer, quality = st.tabs(["Overview", "Clubs & players", "Articles", "Data quality"])

    # ---------------- Overview
    with overview:
        c1, c2 = st.columns(2)
        per_day = view.groupby(["ingest_date", "source"]).size().reset_index(name="articles")
        c1.plotly_chart(
            bar(per_day, "ingest_date", "articles", "Articles per day", color="source",
                color_discrete_map=SOURCE_COLORS),
            width="stretch",
        )
        hourly = (
            view.dropna(subset=["published_at"])
            .assign(hour=lambda d: d["published_at"].dt.hour)
            .groupby(["hour", "source"])
            .size()
            .reset_index(name="articles")
        )
        c2.plotly_chart(
            bar(hourly, "hour", "articles", "Publication hour (UTC)", color="source",
                color_discrete_map=SOURCE_COLORS),
            width="stretch",
        )

        topic_counts = topic_view.groupby("topic").size().sort_values().reset_index(name="articles")
        st.plotly_chart(bar(topic_counts, "articles", "topic", "Topics", orientation="h"), width="stretch")
        methods = ", ".join(sorted(topics["method"].unique())) or "n/a"
        st.caption(
            f"Topics, clubs and players are tagged with `{methods}`: a keyword baseline. "
            "Broad words like 'season' or 'points' over-tag the title-race topic; "
            "the NLP phase will replace this with entity recognition and a classifier."
        )

    # ---------------- Clubs & players
    with entities_tab:
        c1, c2 = st.columns(2)
        for col, df, title in ((c1, clubs, "Most mentioned clubs"), (c2, players, "Most mentioned players & managers")):
            top = df.groupby("entity").size().nlargest(10).sort_values().reset_index(name="articles")
            col.plotly_chart(bar(top, "articles", "entity", title, orientation="h"), width="stretch")

        if not clubs.empty:
            club = st.selectbox("Club mentions over time", sorted(clubs["entity"].unique()))
            trend = (
                clubs[clubs["entity"] == club]
                .merge(view[["article_id", "ingest_date"]], on="article_id")
                .groupby("ingest_date")
                .size()
                .reset_index(name="articles")
            )
            st.plotly_chart(
                bar(trend, "ingest_date", "articles", f"Articles mentioning {club}"),
                width="stretch",
            )

    # ---------------- Articles
    with explorer:
        c1, c2 = st.columns(2)
        topic = c1.selectbox("Topic", ["all"] + sorted(topic_view["topic"].unique()))
        club_filter = c2.selectbox("Club", ["all"] + sorted(clubs["entity"].unique()))
        table = view
        if topic != "all":
            table = table[table["article_id"].isin(topic_view.loc[topic_view["topic"] == topic, "article_id"])]
        if club_filter != "all":
            table = table[table["article_id"].isin(clubs.loc[clubs["entity"] == club_filter, "article_id"])]
        st.caption(f"{len(table)} articles")
        st.dataframe(
            table.sort_values("published_at", ascending=False)[["published_at", "source", "title", "url"]],
            column_config={
                "published_at": st.column_config.DatetimeColumn("published (UTC)", format="YYYY-MM-DD HH:mm"),
                "url": st.column_config.LinkColumn("link", display_text="open"),
            },
            hide_index=True,
            width="stretch",
        )

    # ---------------- Data quality
    with quality:
        rows = []
        for _, r in runs.sort_values("ingest_date", ascending=False).iterrows():
            q = json.loads(r["quality_report"] or "{}")
            rows.append(
                {
                    "date": r["ingest_date"],
                    "bronze files": q.get("bronze_files"),
                    "raw items": q.get("input"),
                    "duplicates removed": q.get("duplicates"),
                    "empty dropped": q.get("dropped_empty"),
                    "missing date": q.get("missing_published_at"),
                    "articles loaded": r["articles_loaded"],
                }
            )
        st.caption(
            "Each hourly run re-scrapes the homepages, so the same article is collected many times a day; "
            "silver keeps one copy. This table comes from silver's quality report."
        )
        st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")


main()