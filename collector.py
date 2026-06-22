"""
Coleta um snapshot dos jogadores Challenger/Grão-Mestre da fila Flex (BR1):
  1. Registra quantos estão em partida ativa (Spectator API)
  2. Registra o LP atual de cada jogador e compara com o snapshot anterior
     para detectar jogos que ocorreram no intervalo entre coletas.

Arquivos gerados/atualizados:
  data/snapshots.csv   — uma linha por ciclo (agregado)
  data/player_lp.csv   — uma linha por jogador por ciclo (histórico de LP)
"""

import csv
import os
import time
from datetime import datetime, timezone
from pathlib import Path

import requests

API_KEY = os.environ.get("RIOT_API_KEY", "")
if not API_KEY:
    raise SystemExit("Variável RIOT_API_KEY não definida.")

PLATFORM      = "br1"
QUEUE         = "RANKED_FLEX_SR"
FLEX_QUEUE_ID = 440
CALL_DELAY    = 1.3

BASE_URL = f"https://{PLATFORM}.api.riotgames.com"

DATA_DIR         = Path(__file__).parent / "data"
SNAPSHOTS_CSV    = DATA_DIR / "snapshots.csv"
PLAYER_LP_CSV    = DATA_DIR / "player_lp.csv"

SNAPSHOTS_HEADER = [
    "timestamp_utc", "players_in_game", "total_tracked",
    "challenger_count", "gm_count",
    "games_detected_by_lp",   # jogadores cujo LP mudou desde o snapshot anterior
    "lp_wins_detected",       # subconjunto: LP subiu  (provável vitória)
    "lp_losses_detected",     # subconjunto: LP caiu   (provável derrota)
]
PLAYER_LP_HEADER = ["timestamp_utc", "puuid", "tier", "lp"]

session = requests.Session()
session.headers.update({"X-Riot-Token": API_KEY})
start_time = time.time()


def elapsed() -> str:
    s = int(time.time() - start_time)
    return f"{s // 60}m{s % 60:02d}s"


def get_with_retry(url: str, max_retries: int = 6) -> requests.Response:
    for attempt in range(max_retries):
        resp = session.get(url)
        if resp.status_code in (200, 404):
            return resp
        if resp.status_code == 429:
            wait = int(resp.headers.get("Retry-After", "10")) + 2
            print(f"  [{elapsed()}] Rate limit — aguardando {wait}s...", flush=True)
            time.sleep(wait)
            continue
        if resp.status_code in (500, 502, 503, 504):
            print(f"  [{elapsed()}] HTTP {resp.status_code} transitório, tentativa {attempt+1}/{max_retries}...", flush=True)
            time.sleep(3 * (attempt + 1))
            continue
        print(f"  [{elapsed()}] HTTP {resp.status_code} inesperado: {url}", flush=True)
        return resp
    raise RuntimeError(f"Falha após {max_retries} tentativas: {url}")


def fetch_league(tier_url: str) -> list[dict]:
    resp = get_with_retry(tier_url)
    resp.raise_for_status()
    time.sleep(CALL_DELAY)
    return resp.json().get("entries", [])


def is_in_flex_game(puuid: str) -> bool:
    url = f"{BASE_URL}/lol/spectator/v5/active-games/by-summoner/{puuid}"
    resp = get_with_retry(url)
    time.sleep(CALL_DELAY)
    if resp.status_code == 404:
        return False
    if resp.status_code != 200:
        return False
    return resp.json().get("gameQueueConfigId") == FLEX_QUEUE_ID


def ensure_csvs():
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    if not SNAPSHOTS_CSV.exists():
        with SNAPSHOTS_CSV.open("w", newline="") as f:
            csv.writer(f).writerow(SNAPSHOTS_HEADER)
    if not PLAYER_LP_CSV.exists():
        with PLAYER_LP_CSV.open("w", newline="") as f:
            csv.writer(f).writerow(PLAYER_LP_HEADER)


def load_previous_lp() -> dict[str, int]:
    """Lê o LP mais recente de cada jogador do player_lp.csv."""
    if not PLAYER_LP_CSV.exists():
        return {}
    prev: dict[str, int] = {}
    with PLAYER_LP_CSV.open(newline="") as f:
        for row in csv.DictReader(f):
            prev[row["puuid"]] = int(row["lp"])   # sobrescreve → fica o mais recente
    return prev


def save_player_lp(ts: str, players: list[tuple[str, str, int]]):
    """Acrescenta linhas (timestamp, puuid, tier, lp) ao player_lp.csv."""
    with PLAYER_LP_CSV.open("a", newline="") as f:
        w = csv.writer(f)
        for puuid, tier, lp in players:
            w.writerow([ts, puuid, tier, lp])


def save_snapshot(ts: str, in_game: int, total: int,
                  n_chall: int, n_gm: int,
                  games_lp: int, wins_lp: int, losses_lp: int):
    with SNAPSHOTS_CSV.open("a", newline="") as f:
        csv.writer(f).writerow([
            ts, in_game, total, n_chall, n_gm,
            games_lp, wins_lp, losses_lp,
        ])


def main():
    ensure_csvs()

    print(f"[{elapsed()}] Buscando lista Challenger + Grão-Mestre (Flex BR)...", flush=True)
    challengers = fetch_league(f"{BASE_URL}/lol/league/v4/challengerleagues/by-queue/{QUEUE}")
    gm_players  = fetch_league(f"{BASE_URL}/lol/league/v4/grandmasterleagues/by-queue/{QUEUE}")

    total = len(challengers) + len(gm_players)
    print(f"[{elapsed()}] Challenger: {len(challengers)} | Grão-Mestre: {len(gm_players)} | Total: {total}", flush=True)
    print(f"[{elapsed()}] Tempo estimado: ~{int(total * CALL_DELAY // 60)}m{int(total * CALL_DELAY % 60):02d}s", flush=True)

    # Carrega LP do snapshot anterior para comparação
    prev_lp = load_previous_lp()
    is_first_run = len(prev_lp) == 0
    if is_first_run:
        print(f"[{elapsed()}] Primeira execução — sem LP anterior para comparar. Próximo ciclo já terá delta.", flush=True)
    else:
        print(f"[{elapsed()}] LP anterior carregado para {len(prev_lp)} jogadores.", flush=True)

    all_players = [(e, "challenger") for e in challengers] + [(e, "gm") for e in gm_players]

    in_game      = 0
    checked      = 0
    errors       = 0
    games_lp     = 0   # jogadores com delta de LP != 0
    wins_lp      = 0   # LP subiu
    losses_lp    = 0   # LP caiu
    current_lp_snapshot: list[tuple[str, str, int]] = []

    LOG_INTERVAL = 50

    for i, (entry, tier) in enumerate(all_players, start=1):
        puuid = entry.get("puuid")
        lp    = entry.get("leaguePoints", 0)

        if puuid is None:
            errors += 1
            continue

        # Registra LP atual
        current_lp_snapshot.append((puuid, tier, lp))

        # Detecta delta de LP em relação ao snapshot anterior
        if not is_first_run and puuid in prev_lp:
            delta = lp - prev_lp[puuid]
            if delta > 0:
                games_lp  += 1
                wins_lp   += 1
            elif delta < 0:
                games_lp  += 1
                losses_lp += 1
            # delta == 0 → nenhum jogo detectado nesse intervalo para esse jogador

        checked += 1

        # Verifica se está em partida agora
        if is_in_flex_game(puuid):
            in_game += 1

        if checked % LOG_INTERVAL == 0 or i == len(all_players):
            eta_s = int((total - checked) * CALL_DELAY)
            print(
                f"[{elapsed()}] {checked}/{total} ({checked/total*100:.0f}%) — "
                f"em jogo agora: {in_game} | jogos detectados (LP): {games_lp} "
                f"(+{wins_lp}W / -{losses_lp}L) | ETA: ~{eta_s//60}m{eta_s%60:02d}s",
                flush=True,
            )

    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")
    save_player_lp(ts, current_lp_snapshot)
    save_snapshot(ts, in_game, checked, len(challengers), len(gm_players),
                  games_lp, wins_lp, losses_lp)

    print(f"\n[{elapsed()}] ✅ Concluído!", flush=True)
    print(f"[{elapsed()}] Em partida Flex agora:        {in_game}/{checked}", flush=True)
    if not is_first_run:
        print(f"[{elapsed()}] Jogos detectados por LP:     {games_lp}  (+{wins_lp}W / -{losses_lp}L)", flush=True)
    print(f"[{elapsed()}] Erros/sem PUUID:              {errors}", flush=True)
    print(f"[{elapsed()}] Snapshot salvo.", flush=True)


if __name__ == "__main__":
    main()
