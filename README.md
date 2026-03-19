# Kairos Ultimate Monitor 🚀

Monitor de anomalias em mercados de apostas esportivas alimentado por Inteligência Artificial (Gemini 1.5 Flash). O Kairos realiza varreduras 24/7 no site dropping-odds.com, identificando quedas bruscas de odds (Dropping Odds) e analisando o contexto da partida para encontrar valor real.

## ✨ Funcionalidades

- **Monitoramento Multimercado**: Varredura em 1X2, Total (Gols), Handicap, HT Total e HT 1X2.
- **Deep AI Analysis**: Integração com Gemini 1.5 para análise quantitativa de padrões.
- **Histórico para ML**: Registro automático de cada anomalia em `data/patterns_log.json` para futuro treinamento de modelos preditivos.
- **Alertas Telegram**: Notificações em tempo real com relatórios técnicos detalhados.
- **Arquitetura Modular**: Código organizado e fácil de expandir.

## 🛠️ Instalação

### 1. Requisitos
- Python 3.10+
- Chave de API do Google Gemini
- Bot do Telegram (Token e Chat ID)

### 2. Configuração do Ambiente
Clone o repositório e crie um ambiente virtual:

```bash
python -m venv venv
source venv/bin/activate  # Linux/Mac
# ou
.\venv\Scripts\activate  # Windows
```

Instale as dependências:
```bash
pip install -r requirements.txt
playwright install chromium
```

### 3. Configuração (.env)
Edite o arquivo `.env` na raiz do projeto com suas chaves:
```env
TELEGRAM_TOKEN=seu_token
TELEGRAM_CHAT_ID=seu_id
GEMINI_API_KEY=sua_chave_gemini
```

## 🚀 Como Usar

Para iniciar o monitoramento principal (DroppingOdds):
```bash
python -m src.main --mode dropping
```

Para o monitoramento legado (Excapper + SokkerPro):
```bash
python -m src.main --mode legacy
```

## 📁 Estrutura do Projeto

```text
Kairos/
├── src/
│   ├── main.py              # Roteador principal (Entrada)
│   ├── config.py            # Central de limites e configurações
│   ├── core/
│   │   ├── analyzer.py      # Lógica de IA (Gemini/DeepSeek)
│   │   ├── smart_money.py   # Análise Smart Money e Volume
│   │   └── utils.py         # JSON e Telegram Helpers
│   ├── scrapers/
│   │   ├── dropping_odds.py # Scraper DroppingOdds.com
│   │   ├── excapper.py      # Scraper Money Flow
│   │   └── sokkerpro.py     # Scraper de Stats de Campo
│   └── flows/
│       ├── dropping_flow.py # Fluxo sugerido (DO -> Excapper -> AI)
│       └── legacy_flow.py   # Fluxo legado (Excapper -> SP -> AI)
├── data/                    # Logs de anomalias (sent_alerts.json)
├── .env                     # Variáveis de ambiente
└── requirements.txt         # Dependências do projeto
```

---
*Desenvolvido por Antigravity para Zacarias Ramos.*
