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

PLATFORM   = "br1"
QUEUE      = "RANKED_FLEX_SR"
FLEX_QUEUE_ID = 440

CSV_PATH = Path(__file__).parent / "data" / "snapshots.csv"
CSV_HEADER = ["timestamp_utc", "players_in_game", "total_tracked", "challenger_count", "gm_count"]

# Delay conservador entre chamadas individuais (chave personal: ~20 req/s,
# mas vamos ser cuidadosos para não estourar o limite de 100 req/2 min).
CALL_DELAY = 1.3

BASE_URL = f"https://{PLATFORM}.api.riotgames.com"

session = requests.Session()
session.headers.update({"X-Riot-Token": API_KEY})


def get_with_retry(url: str, max_retries: int = 6) -> requests.Response:
    for attempt in range(max_retries):
        resp = session.get(url)
        if resp.status_code in (200, 404):
            return resp
        if resp.status_code == 429:
            wait = int(resp.headers.get("Retry-After", "10")) + 2
            print(f"  Rate limit — aguardando {wait}s...")
            time.sleep(wait)
            continue
        if resp.status_code in (500, 502, 503, 504):
            time.sleep(3 * (attempt + 1))
            continue
        print(f"  HTTP {resp.status_code} em {url}")
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
    url = f"{BASE_URL}/lol/spectator/v5/by-summoner/{puuid}"
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

    print("Buscando lista Challenger + Grão-Mestre (Flex BR)...")
    challengers = fetch_league(f"{BASE_URL}/lol/league/v4/challengerleagues/by-queue/{QUEUE}")
    gm_players  = fetch_league(f"{BASE_URL}/lol/league/v4/grandmasterleagues/by-queue/{QUEUE}")

    print(f"Challenger: {len(challengers)} | Grão-Mestre: {len(gm_players)}")

    all_players = [(e, "challenger") for e in challengers] + [(e, "gm") for e in gm_players]
    in_game = 0
    checked = 0

    for entry, _ in all_players:
        puuid = entry.get("puuid") or resolve_puuid(entry["summonerId"])
        if puuid is None:
            continue
        checked += 1
        if is_in_flex_game(puuid):
            in_game += 1

    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")
    append_snapshot(ts, in_game, checked, len(challengers), len(gm_players))

    print(f"[{ts}] {in_game}/{checked} jogadores em partida Flex agora. Salvo em {CSV_PATH}.")


if __name__ == "__main__":
    main()
