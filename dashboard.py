"""
Dashboard — Horários de pico dos jogadores Challenger/Grão-Mestre
na Ranqueada Flex (BR1).

Hospedado no Streamlit Community Cloud, lê data/snapshots.csv do repositório.
Rodar localmente: streamlit run dashboard.py
"""

from pathlib import Path
import pandas as pd
import plotly.express as px
import streamlit as st

CSV_PATH = Path(__file__).parent / "data" / "snapshots.csv"

DIAS_PT = {
    0: "Segunda",
    1: "Terça",
    2: "Quarta",
    3: "Quinta",
    4: "Sexta",
    5: "Sábado",
    6: "Domingo",
}
ORDEM_DIAS = ["Segunda", "Terça", "Quarta", "Quinta", "Sexta", "Sábado", "Domingo"]

st.set_page_config(
    page_title="Tracker Challenger/GM — Flex BR",
    page_icon="🏆",
    layout="wide",
)

st.title("🏆 Horários de pico — Challenger & Grão-Mestre | Flex BR")
st.caption(
    "Quantos jogadores de elite costumam estar em partida Flex em cada hora e dia da semana. "
    "Dados coletados automaticamente a cada hora via GitHub Actions."
)


@st.cache_data(ttl=300)   # recarrega a cada 5 minutos
def load_data() -> pd.DataFrame:
    if not CSV_PATH.exists():
        return pd.DataFrame()
    df = pd.read_csv(CSV_PATH, parse_dates=["timestamp_utc"])
    if df.empty:
        return df

    # Converter UTC → horário de Brasília (UTC-3)
    df["timestamp_br"] = df["timestamp_utc"].dt.tz_localize("UTC").dt.tz_convert("America/Sao_Paulo")
    df["hora"]        = df["timestamp_br"].dt.hour
    df["dia_semana"]  = df["timestamp_br"].dt.weekday.map(DIAS_PT)
    df["pct_em_jogo"] = (
        df["players_in_game"] / df["total_tracked"].replace(0, pd.NA) * 100
    ).round(1)
    return df


df = load_data()

if df.empty:
    st.warning(
        "Ainda não há dados em `data/snapshots.csv`. "
        "Aguarde o GitHub Actions rodar o primeiro ciclo de coleta "
        "(acontece automaticamente todo início de hora) ou dispare manualmente "
        "na aba **Actions** do repositório."
    )
    st.stop()

# ── Métricas rápidas ─────────────────────────────────────────────────────────
c1, c2, c3, c4 = st.columns(4)
c1.metric("Snapshots coletados", len(df))
c2.metric(
    "Período coberto",
    f"{df['timestamp_br'].min():%d/%m} → {df['timestamp_br'].max():%d/%m}",
)
c3.metric("Máx. jogadores em jogo", int(df["players_in_game"].max()))
c4.metric(
    "Última coleta (horário BR)",
    df["timestamp_br"].max().strftime("%d/%m %H:%M"),
)

st.divider()

# ── Heatmap ──────────────────────────────────────────────────────────────────
st.subheader("🔥 Heatmap: intensidade por dia e hora (horário de Brasília)")
st.caption("Tons mais escuros = mais jogadores de elite em partida Flex nesse slot. Evite esses horários!")

pivot = (
    df.groupby(["dia_semana", "hora"])["players_in_game"]
    .mean()
    .reset_index()
    .pivot(index="dia_semana", columns="hora", values="players_in_game")
    .reindex(ORDEM_DIAS)
)

fig_heat = px.imshow(
    pivot,
    labels=dict(x="Hora (Brasília)", y="Dia da semana", color="Média em partida"),
    color_continuous_scale="Reds",
    aspect="auto",
    text_auto=".1f",
)
fig_heat.update_xaxes(dtick=1, tickformat="%H:00")
fig_heat.update_layout(margin=dict(l=10, r=10, t=30, b=10))
st.plotly_chart(fig_heat, use_container_width=True)

# ── Gráfico de linha ─────────────────────────────────────────────────────────
st.subheader("📈 Série temporal completa")

tab_abs, tab_pct = st.tabs(["Nº absoluto de jogadores em partida", "% do total rastreado"])

with tab_abs:
    fig_line = px.line(
        df.sort_values("timestamp_br"),
        x="timestamp_br",
        y="players_in_game",
        labels={"timestamp_br": "Data/Hora (Brasília)", "players_in_game": "Jogadores em partida"},
    )
    st.plotly_chart(fig_line, use_container_width=True)

with tab_pct:
    fig_pct = px.line(
        df.sort_values("timestamp_br"),
        x="timestamp_br",
        y="pct_em_jogo",
        labels={"timestamp_br": "Data/Hora (Brasília)", "pct_em_jogo": "% em partida"},
    )
    st.plotly_chart(fig_pct, use_container_width=True)

# ── Tabela dos horários mais perigosos ──────────────────────────────────────
st.subheader("⚠️ Top 10 horários com mais jogadores de elite")
top = (
    df.groupby(["dia_semana", "hora"])["players_in_game"]
    .mean()
    .reset_index()
    .rename(columns={"players_in_game": "média_em_partida", "hora": "hora_br", "dia_semana": "dia"})
    .sort_values("média_em_partida", ascending=False)
    .head(10)
    .reset_index(drop=True)
)
top["hora_br"] = top["hora_br"].apply(lambda h: f"{h:02d}:00")
top.index += 1
st.dataframe(top, use_container_width=True)

# ── Últimos snapshots ────────────────────────────────────────────────────────
with st.expander("Ver últimos 20 snapshots brutos"):
    st.dataframe(
        df[["timestamp_br", "players_in_game", "total_tracked", "pct_em_jogo",
            "challenger_count", "gm_count"]]
        .sort_values("timestamp_br", ascending=False)
        .head(20),
        use_container_width=True,
    )
