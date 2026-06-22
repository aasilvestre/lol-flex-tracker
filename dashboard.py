"""
Dashboard — Horários de pico dos jogadores Challenger/Grão-Mestre
na Ranqueada Flex (BR1).

Combina dois sinais:
  - Partidas ativas detectadas pela Spectator API (ao vivo)
  - Jogos inferidos por variação de LP entre snapshots consecutivos
"""

from pathlib import Path
import pandas as pd
import plotly.express as px
import streamlit as st

DATA_DIR      = Path(__file__).parent / "data"
SNAPSHOTS_CSV = DATA_DIR / "snapshots.csv"
PLAYER_LP_CSV = DATA_DIR / "player_lp.csv"

DIAS_PT   = {0:"Segunda",1:"Terça",2:"Quarta",3:"Quinta",4:"Sexta",5:"Sábado",6:"Domingo"}
ORDEM_DIAS = ["Segunda","Terça","Quarta","Quinta","Sexta","Sábado","Domingo"]

st.set_page_config(page_title="Tracker Challenger/GM — Flex BR", page_icon="🏆", layout="wide")
st.title("🏆 Horários de pico — Challenger & Grão-Mestre | Flex BR")
st.caption("Combina partidas detectadas ao vivo (Spectator API) + jogos inferidos por variação de LP entre coletas horárias.")


@st.cache_data(ttl=300)
def load_snapshots() -> pd.DataFrame:
    if not SNAPSHOTS_CSV.exists():
        return pd.DataFrame()
    df = pd.read_csv(SNAPSHOTS_CSV, parse_dates=["timestamp_utc"])
    if df.empty:
        return df
    df["timestamp_br"] = df["timestamp_utc"].dt.tz_localize("UTC").dt.tz_convert("America/Sao_Paulo")
    df["hora"]         = df["timestamp_br"].dt.hour
    df["dia_semana"]   = df["timestamp_br"].dt.weekday.map(DIAS_PT)
    df["pct_em_jogo"]  = (df["players_in_game"] / df["total_tracked"].replace(0, pd.NA) * 100).round(1)
    # Métrica combinada: máximo entre detecção ao vivo e detecção por LP
    df["atividade_combinada"] = df[["players_in_game", "games_detected_by_lp"]].max(axis=1)
    return df


@st.cache_data(ttl=300)
def load_player_lp() -> pd.DataFrame:
    if not PLAYER_LP_CSV.exists():
        return pd.DataFrame()
    df = pd.read_csv(PLAYER_LP_CSV, parse_dates=["timestamp_utc"])
    if df.empty:
        return df
    df["timestamp_br"] = df["timestamp_utc"].dt.tz_localize("UTC").dt.tz_convert("America/Sao_Paulo")
    return df


df = load_snapshots()

if df.empty:
    st.warning("Ainda não há dados. Aguarde o GitHub Actions rodar o primeiro ciclo.")
    st.stop()

# ── Métricas rápidas ─────────────────────────────────────────────────────────
c1, c2, c3, c4 = st.columns(4)
c1.metric("Snapshots coletados", len(df))
c2.metric("Período coberto",
          f"{df['timestamp_br'].min():%d/%m} → {df['timestamp_br'].max():%d/%m}")
c3.metric("Máx. em jogo ao vivo",   int(df["players_in_game"].max()))
c4.metric("Máx. jogos detectados (LP)", int(df.get("games_detected_by_lp", pd.Series([0])).max()))

st.divider()

# ── Tabs principais ──────────────────────────────────────────────────────────
tab_heat, tab_serie, tab_lp, tab_raw = st.tabs([
    "🔥 Heatmap", "📈 Série temporal", "⚔️ Análise de LP", "🗃️ Dados brutos"
])

with tab_heat:
    st.subheader("Heatmap de atividade combinada (horário de Brasília)")
    st.caption("Usa o maior valor entre 'em partida ao vivo' e 'jogos detectados por LP' em cada slot.")

    metrica = st.radio(
        "Métrica:",
        ["Atividade combinada (recomendado)", "Partidas ao vivo (Spectator)", "Jogos detectados por LP"],
        horizontal=True,
    )
    col_map = {
        "Atividade combinada (recomendado)": "atividade_combinada",
        "Partidas ao vivo (Spectator)":      "players_in_game",
        "Jogos detectados por LP":           "games_detected_by_lp",
    }
    col = col_map[metrica]

    if col not in df.columns:
        st.info("Dados de LP disponíveis a partir do segundo snapshot coletado.")
    else:
        pivot = (
            df.groupby(["dia_semana", "hora"])[col]
            .mean().reset_index()
            .pivot(index="dia_semana", columns="hora", values=col)
            .reindex(ORDEM_DIAS)
        )
        fig = px.imshow(
            pivot,
            labels=dict(x="Hora (Brasília)", y="Dia da semana", color="Média"),
            color_continuous_scale="Reds",
            aspect="auto",
            text_auto=".1f",
        )
        fig.update_xaxes(dtick=1)
        fig.update_layout(margin=dict(l=10, r=10, t=30, b=10))
        st.plotly_chart(fig, use_container_width=True)

    st.subheader("⚠️ Top 10 horários mais perigosos")
    if col in df.columns:
        top = (
            df.groupby(["dia_semana", "hora"])[col]
            .mean().reset_index()
            .rename(columns={col: "média", "hora": "hora_br", "dia_semana": "dia"})
            .sort_values("média", ascending=False).head(10).reset_index(drop=True)
        )
        top.index += 1
        top["hora_br"] = top["hora_br"].apply(lambda h: f"{h:02d}:00")
        st.dataframe(top, use_container_width=True)

with tab_serie:
    st.subheader("Série temporal completa")
    fig = px.line(
        df.sort_values("timestamp_br"),
        x="timestamp_br",
        y=["players_in_game", "games_detected_by_lp"] if "games_detected_by_lp" in df.columns else ["players_in_game"],
        labels={"timestamp_br": "Data/Hora (Brasília)", "value": "Jogadores", "variable": "Sinal"},
    )
    newnames = {"players_in_game": "Em jogo ao vivo", "games_detected_by_lp": "Jogos detectados (LP)"}
    fig.for_each_trace(lambda t: t.update(name=newnames.get(t.name, t.name)))
    st.plotly_chart(fig, use_container_width=True)

with tab_lp:
    st.subheader("⚔️ Detecção de jogos por variação de LP")
    st.caption(
        "Compara o LP de cada jogador entre snapshots consecutivos. "
        "Qualquer variação indica que ao menos um jogo foi jogado naquele intervalo."
    )

    if "games_detected_by_lp" not in df.columns or df["games_detected_by_lp"].sum() == 0:
        st.info("Ainda sem dados de variação de LP. Disponível a partir do segundo snapshot.")
    else:
        c1, c2, c3 = st.columns(3)
        c1.metric("Total de jogos detectados (LP)", int(df["games_detected_by_lp"].sum()))
        c2.metric("Vitórias inferidas (LP subiu)",  int(df["lp_wins_detected"].sum()) if "lp_wins_detected" in df.columns else "—")
        c3.metric("Derrotas inferidas (LP caiu)",   int(df["lp_losses_detected"].sum()) if "lp_losses_detected" in df.columns else "—")

        fig_lp = px.bar(
            df.sort_values("timestamp_br"),
            x="timestamp_br",
            y=["lp_wins_detected", "lp_losses_detected"],
            labels={"timestamp_br": "Data/Hora (Brasília)", "value": "Jogadores", "variable": ""},
            color_discrete_map={"lp_wins_detected": "#4ade80", "lp_losses_detected": "#f87171"},
            barmode="stack",
        )
        newnames2 = {"lp_wins_detected": "LP subiu (vitória)", "lp_losses_detected": "LP caiu (derrota)"}
        fig_lp.for_each_trace(lambda t: t.update(name=newnames2.get(t.name, t.name)))
        st.plotly_chart(fig_lp, use_container_width=True)

        df_lp = load_player_lp()
        if not df_lp.empty:
            st.subheader("Evolução de LP por tier ao longo do tempo")
            lp_avg = (
                df_lp.groupby(["timestamp_br", "tier"])["lp"]
                .mean().reset_index()
            )
            fig_tier = px.line(
                lp_avg, x="timestamp_br", y="lp", color="tier",
                labels={"timestamp_br": "Data/Hora (Brasília)", "lp": "LP médio", "tier": "Tier"},
                color_discrete_map={"challenger": "#f59e0b", "gm": "#818cf8"},
            )
            st.plotly_chart(fig_tier, use_container_width=True)

with tab_raw:
    st.subheader("Últimos 30 snapshots")
    cols_show = [c for c in [
        "timestamp_br","players_in_game","total_tracked","pct_em_jogo",
        "games_detected_by_lp","lp_wins_detected","lp_losses_detected",
        "challenger_count","gm_count"
    ] if c in df.columns]
    st.dataframe(
        df[cols_show].sort_values("timestamp_br", ascending=False).head(30),
        use_container_width=True,
    )
