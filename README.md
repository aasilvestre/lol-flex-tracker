# 🏆 LoL Flex Tracker — v1.0

Monitora automaticamente a atividade dos jogadores **Challenger e Grão-Mestre** na fila **Ranqueada Flex (BR1)**, identificando os horários e dias da semana com maior presença de jogadores de elite — para você evitar essas janelas e subir mais tranquilo.

---

## Como funciona

```
cron-job.org (todo :00)
    → dispara GitHub Actions via API
        → collector.py roda (~15 min)
            → commita data/ no repositório
                → Streamlit Cloud atualiza o dashboard
```

Dois sinais são coletados a cada hora:

| Sinal | Como funciona |
|-------|--------------|
| **Partidas ao vivo** | Spectator API verifica se cada jogador está em partida Flex no momento |
| **Jogos por delta de LP** | Compara o LP atual de cada jogador com o snapshot anterior — qualquer variação indica que um jogo aconteceu no intervalo |

Os dois sinais se complementam: o delta de LP captura jogos que terminaram entre coletas, enquanto a Spectator API captura quem está jogando agora.

---

## Estrutura do projeto

```
lol-flex-tracker/
├── .github/
│   └── workflows/
│       └── main.yml          # Workflow do GitHub Actions
├── data/
│   ├── snapshots.csv         # Um registro por hora (agregado)
│   └── player_lp.csv         # LP de cada jogador por hora (~700 linhas/hora)
├── collector.py              # Script de coleta (roda no GitHub Actions)
├── dashboard.py              # Dashboard Streamlit
├── requirements.txt          # Dependências Python
└── README.md
```

### Colunas do `snapshots.csv`

| Coluna | Descrição |
|--------|-----------|
| `timestamp_utc` | Data/hora da coleta em UTC |
| `players_in_game` | Jogadores em partida Flex ao vivo |
| `total_tracked` | Total de jogadores verificados no ciclo |
| `challenger_count` | Quantidade de Challengers no BR naquele momento |
| `gm_count` | Quantidade de Grão-Mestres no BR naquele momento |
| `games_detected_by_lp` | Jogadores cujo LP mudou desde o snapshot anterior |
| `lp_wins_detected` | Subconjunto: LP subiu (vitória provável) |
| `lp_losses_detected` | Subconjunto: LP caiu (derrota provável) |

---

## Serviços utilizados (todos gratuitos)

| Serviço | Função |
|---------|--------|
| **Riot Games API** | Dados de Challenger/GM e Spectator |
| **GitHub** | Repositório + execução do collector (Actions) |
| **cron-job.org** | Agendamento confiável (dispara o workflow toda hora) |
| **Streamlit Community Cloud** | Dashboard público |

---

## Setup completo do zero

### Pré-requisitos
- Conta no GitHub
- Conta no Streamlit Community Cloud (login com GitHub em https://share.streamlit.io)
- Conta no cron-job.org (https://cron-job.org)
- API Key da Riot Games (https://developer.riotgames.com)

> **Recomendado:** solicitar a **Personal API Key** no portal da Riot (gratuita, não expira). A chave de desenvolvimento expira a cada 24h e precisa ser trocada manualmente no secret do GitHub.

---

### Passo 1 — Criar o repositório no GitHub

1. Acesse https://github.com/new
2. Nome: `lol-flex-tracker` (pode ser público ou privado)
3. Faça upload de todos os arquivos mantendo a estrutura de pastas

---

### Passo 2 — Adicionar a API Key como secret

1. No repositório: **Settings → Secrets and variables → Actions**
2. **New repository secret**
3. Nome: `RIOT_API_KEY` / Valor: sua chave `RGAPI-...`

> Se estiver usando a chave de desenvolvimento (expira em 24h): repita esse passo todo dia gerando uma nova chave em https://developer.riotgames.com e atualizando o secret.

---

### Passo 3 — Configurar o cron-job.org

1. Cadastre-se em https://cron-job.org
2. **Create cronjob** com as seguintes configurações:

**Aba principal:**
| Campo | Valor |
|-------|-------|
| Title | `LoL Flex Tracker` |
| URL | `https://api.github.com/repos/SEU_USUARIO/lol-flex-tracker/actions/workflows/main.yml/dispatches` |
| Execution schedule | Every 1 hour |

**Aba Advanced → Headers** (adicionar 3 headers):
| Key | Value |
|-----|-------|
| `Authorization` | `Bearer ghp_SEU_TOKEN_AQUI` |
| `Accept` | `application/vnd.github+json` |
| `Content-Type` | `application/json` |

**Aba Advanced → Request body:**
```json
{"ref":"main"}
```

**Aba Advanced → Request method:** `POST`

3. Salve e clique em **Test run** — deve retornar **204 No Content**

> O token usado aqui é um **Personal Access Token (PAT)** do GitHub, não a API Key da Riot. Gere um em: GitHub → Settings → Developer settings → Personal access tokens → Tokens (classic) → escopo `workflow`.

---

### Passo 4 — Hospedar o dashboard no Streamlit Community Cloud

1. Acesse https://share.streamlit.io
2. **New app**
3. Preencha:
   - Repository: `seu-usuario/lol-flex-tracker`
   - Branch: `main`
   - Main file path: `dashboard.py`
4. **Deploy**

Em alguns minutos o dashboard estará disponível em uma URL pública.

---

## Manutenção

### Trocar a API Key (chave de desenvolvimento, expira a cada 24h)
1. Acesse https://developer.riotgames.com e copie a nova chave
2. GitHub → Settings → Secrets and variables → Actions → `RIOT_API_KEY` → Update secret
3. Cole a nova chave e salve

### Verificar se a coleta está rodando
- Aba **Actions** do repositório: deve ter um novo run a cada hora com label `workflow_dispatch`
- O arquivo `data/snapshots.csv` deve ganhar uma linha nova por hora

### Pausar a coleta
- No cron-job.org: desative o job com o toggle **Enable job**
- Ou no GitHub: Actions → selecione o workflow → **Disable workflow**

### Rodar manualmente
- GitHub → aba **Actions** → **Coletar dados Challenger/GM Flex BR** → **Run workflow**

---

## Limitações conhecidas

- **Granularidade de 1 hora:** jogadores que jogaram múltiplas partidas no intervalo aparecem como "1 jogo detectado" no delta de LP. O padrão acumulado ao longo de semanas continua preciso.
- **Detecção ao vivo:** a Spectator API só mostra partidas em andamento, não jogadores procurando partida.
- **Rate limit:** com a Personal API Key, cada ciclo completo leva ~15 minutos. Com a chave de desenvolvimento o comportamento é similar, mas com mais risco de throttling.
- **Buracos de dados:** se a chave expirar ou o workflow falhar, haverá ausência de dados naquele período.

---

## Dashboard

O dashboard possui 4 abas:

| Aba | Conteúdo |
|-----|----------|
| 🔥 Heatmap | Mapa de calor dia × hora com atividade combinada (ao vivo + delta LP) |
| 📈 Série temporal | Evolução dos dois sinais ao longo do tempo |
| ⚔️ Análise de LP | Jogos detectados por variação de LP, vitórias/derrotas inferidas |
| 🗃️ Dados brutos | Últimos 30 snapshots com todas as colunas |

