# 🏆 LoL Challenger/GM Tracker — Flex BR (versão cloud)

Monitora automaticamente quantos jogadores Challenger e Grão-Mestre estão em
partida de Ranqueada Flex (BR1) a cada hora. Os dados ficam versionados no
próprio repositório e o dashboard é servido gratuitamente pelo Streamlit Cloud.

```
GitHub Actions (coleta horária)
        │  commita data/snapshots.csv
        ▼
GitHub Repository
        │  lê o CSV
        ▼
Streamlit Community Cloud (dashboard público ou privado)
```

---

## Pré-requisitos

- Conta no **GitHub** (gratuita)
- **Personal API Key da Riot** (não expira — solicite em https://developer.riotgames.com/)
- Conta no **Streamlit Community Cloud** — cadastro em https://share.streamlit.io (gratuito, faz login com o GitHub)

---

## Passo 1 — Criar o repositório no GitHub

1. Acesse https://github.com/new
2. Nome sugerido: `lol-flex-tracker`
3. Pode ser **público** ou **privado** — com repositório público o GitHub Actions
   tem minutos ilimitados no plano gratuito; privado tem 2.000 min/mês (suficiente
   para coleta horária).
4. Crie o repositório e faça upload de todos estes arquivos mantendo a estrutura:

```
lol-flex-tracker/
├── .github/
│   └── workflows/
│       └── collect.yml
├── data/
│   └── snapshots.csv      ← começa só com o cabeçalho; os dados acumulam aqui
├── collector.py
├── dashboard.py
└── requirements.txt
```

---

## Passo 2 — Adicionar a API Key como secret

1. No seu repositório, vá em **Settings → Secrets and variables → Actions**.
2. Clique em **New repository secret**.
3. Nome: `RIOT_API_KEY`
4. Valor: sua Personal API Key da Riot (começa com `RGAPI-...`)
5. Salve.

> A chave fica criptografada no GitHub e nunca aparece nos logs nem no código.

---

## Passo 3 — Ativar o GitHub Actions

O workflow já está configurado para rodar automaticamente todo início de hora.
Para testar imediatamente sem esperar:

1. Vá na aba **Actions** do repositório.
2. Clique no workflow **"Coletar dados Challenger/GM Flex BR"**.
3. Clique em **"Run workflow"** → **"Run workflow"** (botão verde).
4. Acompanhe os logs em tempo real. A execução leva alguns minutos (o coletor
   precisa checar centenas de jogadores respeitando o rate limit da API).
5. Após concluir, veja em `data/snapshots.csv` — haverá uma nova linha.

---

## Passo 4 — Hospedar o dashboard no Streamlit Community Cloud

1. Acesse https://share.streamlit.io e entre com sua conta GitHub.
2. Clique em **"New app"**.
3. Preencha:
   - **Repository:** `seu-usuario/lol-flex-tracker`
   - **Branch:** `main`
   - **Main file path:** `dashboard.py`
4. Clique em **"Deploy"**.
5. Em alguns minutos, você terá uma URL pública (ex:
   `https://seu-usuario-lol-flex-tracker.streamlit.app`) com o dashboard
   atualizado automaticamente a cada push (ou seja, a cada coleta horária).

---

## Como os dados crescem

Cada execução do Actions acrescenta **1 linha** ao CSV. Em um mês de coleta
contínua (24 execuções/dia × 30 dias) você terá ~720 linhas — um arquivo
pequeno (~50 KB), sem nenhum problema para o git.

---

## Dicas

- **Forçar uma coleta manual:** aba Actions → Run workflow.
- **Pausar a coleta:** aba Actions → selecione o workflow → "Disable workflow".
- **Ver os dados brutos:** abra `data/snapshots.csv` diretamente no GitHub.
- **Rodar o dashboard localmente:**
  ```bash
  pip install -r requirements.txt
  streamlit run dashboard.py
  ```
