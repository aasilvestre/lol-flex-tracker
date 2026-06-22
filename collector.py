"""
Coleta um snapshot dos jogadores Challenger/Grão-Mestre da fila Flex (BR1)
que estão em partida no momento e acrescenta uma linha em data/snapshots.csv.

Projetado para ser chamado pelo GitHub Actions uma vez por hora — não entra
em loop; termina após o único ciclo de varredura.
"""

import csv
import os
import time
from datetime import datetime, timezone
from pathlib import Path

import requests

API_KEY = os.environ.get("RIOT_API_KEY", "")
if not API_KEY:
    raise SystemExit(
        "Variável de ambiente RIOT_API_KEY não definida. "
        "Defina-a como secret no GitHub Actions ou no seu .env local."
    )

PLATFORM      = "br1"
QUEUE         = "RANKED_FLEX_SR"
FLEX_QUEUE_ID = 440

CSV_PATH   = Path(__file__).parent / "data" / "snapshots.csv"
CSV_HEADER = ["timestamp_utc", "players_in_game", "total_tracked", "challenger_count", "gm_count"]

# Delay conservador entre chamadas individuais para respeitar 100 req/2 min
CALL_DELAY = 1.3

BASE_URL = f"https://{PLATFORM}.api.riotgames.com"

session = requests.Session()
session.headers.update({"X-Riot-Token": API_KEY})

start_time = time.time()


def elapsed() -> str:
    """Retorna o tempo decorrido desde o início do script, ex: '2m14s'."""
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
        # Qualquer outro status (403, 401, etc.) — loga e retorna para tratamento
        print(f"  [{elapsed()}] HTTP {resp.status_code} inesperado em {url}", flush=True)
        return resp
    raise RuntimeError(f"Falha após {max_retries} tentativas: {url}")


def fetch_league(tier_url: str) -> list[dict]:
    resp = get_with_retry(tier_url)
    resp.raise_for_status()
    time.sleep(CALL_DELAY)
    return resp.json().get("entries", [])


def resolve_puuid(summoner_id: str) -> str | None:
    url = f"{BASE_URL}/lol/summoner/v4/summoners/{summoner_id}"
    resp = get_with_retry(url)
    time.sleep(CALL_DELAY)
    if resp.status_code != 200:
        return None
    return resp.json().get("puuid")


def is_in_flex_game(puuid: str) -> bool:
    url = f"{BASE_URL}/lol/spectator/v5/active-games/by-summoner/{puuid}"
    resp = get_with_retry(url)
    time.sleep(CALL_DELAY)
    if resp.status_code == 404:
        return False
    if resp.status_code != 200:
        return False
    return resp.json().get("gameQueueConfigId") == FLEX_QUEUE_ID


def ensure_csv():
    CSV_PATH.parent.mkdir(parents=True, exist_ok=True)
    if not CSV_PATH.exists():
        with CSV_PATH.open("w", newline="") as f:
            csv.writer(f).writerow(CSV_HEADER)


def append_snapshot(timestamp: str, in_game: int, total: int, n_chall: int, n_gm: int):
    with CSV_PATH.open("a", newline="") as f:
        csv.writer(f).writerow([timestamp, in_game, total, n_chall, n_gm])


def main():
    ensure_csv()

    print(f"[{elapsed()}] Buscando lista Challenger + Grão-Mestre (Flex BR)...", flush=True)
    challengers = fetch_league(f"{BASE_URL}/lol/league/v4/challengerleagues/by-queue/{QUEUE}")
    gm_players  = fetch_league(f"{BASE_URL}/lol/league/v4/grandmasterleagues/by-queue/{QUEUE}")

    total = len(challengers) + len(gm_players)
    print(f"[{elapsed()}] Challenger: {len(challengers)} | Grão-Mestre: {len(gm_players)} | Total: {total}", flush=True)
    print(f"[{elapsed()}] Tempo estimado para varredura completa: ~{int(total * CALL_DELAY // 60)}m{int(total * CALL_DELAY % 60):02d}s", flush=True)
    print(f"[{elapsed()}] Iniciando verificação de partidas ativas...", flush=True)

    all_players = [(e, "challenger") for e in challengers] + [(e, "gm") for e in gm_players]
    in_game  = 0
    checked  = 0
    errors   = 0

    # Intervalo de progresso: a cada 50 jogadores
    LOG_INTERVAL = 50

    for i, (entry, tier) in enumerate(all_players, start=1):
        puuid = entry.get("puuid") or resolve_puuid(entry["summonerId"])
        if puuid is None:
            errors += 1
            continue

        checked += 1
        playing = is_in_flex_game(puuid)
        if playing:
            in_game += 1

        # Log de progresso a cada LOG_INTERVAL jogadores
        if checked % LOG_INTERVAL == 0 or i == len(all_players):
            pct     = checked / total * 100
            eta_s   = int((total - checked) * CALL_DELAY)
            print(
                f"[{elapsed()}] {checked}/{total} ({pct:.0f}%) — "
                f"em jogo: {in_game} | erros: {errors} | "
                f"ETA: ~{eta_s // 60}m{eta_s % 60:02d}s",
                flush=True,
            )

    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")
    append_snapshot(ts, in_game, checked, len(challengers), len(gm_players))

    print(f"", flush=True)
    print(f"[{elapsed()}] ✅ Concluído!", flush=True)
    print(f"[{elapsed()}] Jogadores em partida Flex agora: {in_game}/{checked}", flush=True)
    print(f"[{elapsed()}] Erros/sem PUUID: {errors}", flush=True)
    print(f"[{elapsed()}] Snapshot salvo em {CSV_PATH}", flush=True)


if __name__ == "__main__":
    main()
