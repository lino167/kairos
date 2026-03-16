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

Para iniciar o monitoramento:

```bash
python -m src.main
```

## 📁 Estrutura do Projeto

```text
Kairos/
├── src/
│   ├── main.py        # Orquestrador do sistema
│   ├── analyzer.py    # Lógica de IA do Gemini
│   ├── scraper.py     # Automação Playwright
│   └── utils.py       # Funções auxiliares e notificações
├── data/              # Logs de anomalias (patterns_log.json)
├── .env               # Variáveis de ambiente secretas
└── requirements.txt   # Dependências do projeto
```

---
*Desenvolvido por Antigravity para Zacarias Ramos.*
