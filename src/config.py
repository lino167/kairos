import os
from dotenv import load_dotenv

# Carregar variáveis de ambiente
load_dotenv()

# ── Credenciais e Conexão ──────────────────────────────────────────────────
TELEGRAM_TOKEN    = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID  = os.getenv("TELEGRAM_CHAT_ID")
GEMINI_API_KEY    = os.getenv("GEMINI_API_KEY")
DEEPSEEK_API_KEY  = os.getenv("DEEPSEEK_API_KEY")
AI_PROVIDER       = os.getenv("AI_PROVIDER", "gemini")

# ── Diretórios e Arquivos ──────────────────────────────────────────────────
BASE_DIR          = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR          = os.path.join(BASE_DIR, "data")
SENT_ALERTS_FILE  = os.path.join(DATA_DIR, "sent_alerts.json")

# ── Gatilhos de Queda de Odds (DroppingOdds) ───────────────────────────────
DROP_MIN_PCT          = 5.0     # Mínimo para ser listado como alerta
DROP_STRONG_PCT       = 10.0    # Considerado queda forte
DROP_ALERT_PCT        = 15.0    # Drop crítico (vermelho)
AI_TRIGGER_DROP       = 5.5     # Mínimo para enviar para análise da IA
CYCLE_SLEEP_SEC       = 90      # Pausa entre ciclos de varredura

# ── Limites Estratégicos (Smart Money / Excapper) ──────────────────────────
MIN_MATCH_VOLUME_EUR  = 100.0   # Volume mínimo para o jogo existir no radar
MONEY_SPARK_POOL      = 500.0   # Gatilho de volume para ligas menores (Piscina)
MONEY_SPARK_OCEAN     = 10000.0  # Gatilho para grandes ligas (Oceano)
OCEAN_LIQUIDITY_MIN   = 50000.0  # Acima disso o jogo é classificado como Oceano

# ── Parâmetros de Pressão (SokkerPro) ──────────────────────────────────────
PRESSURE_EXPLOSIVE    = 1.0     # APPM explosivo (perigo iminente)
PRESSURE_DIVERGENCE   = 0.4     # Limiar para detectar fluxo sem pressão de campo
LOW_PRESSURE_LIMIT    = 0.2     # "Cesto de Lixo" - sem reação do time
LATE_GAME_MIN         = 80      # Minutos finais para análise de encerramento

# ── Configuração de Navegação ──────────────────────────────────────────────
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)
HEADLESS = True
VIEWPORT = {"width": 1366, "height": 768}
