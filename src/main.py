import asyncio
import os
import time
import hashlib
from dotenv import load_dotenv
from playwright.async_api import async_playwright

from .utils import load_json, save_json, send_telegram_alert
from .analyzer import KairosAnalyzer
from .database import KairosDatabase
from .bet365_scraper import Bet365Scraper
from .excapper_scraper import ExcapperScraper

# Carregar variáveis de ambiente
load_dotenv()

# Configuração
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY")
AI_PROVIDER = os.getenv("AI_PROVIDER", "deepseek")

DATA_DIR = "data"
SENT_ALERTS_FILE = os.path.join(DATA_DIR, "sent_alerts.json")

# Limites para Anomalias (Excapper)
MONEY_SPARK_THRESHOLD = 500.0 # Valor em EUR de entrada rápida
ODDS_SHIFT_THRESHOLD_PCT = 15 # Queda de 15% nas odds
MIN_MATCH_VOLUME_EUR = 1000.0 # Ignorar jogos com menos de 1000€ de volume total

async def main():
    required_keys = [TELEGRAM_TOKEN, TELEGRAM_CHAT_ID]
    # (Validação de chaves omitida para brevidade)
    
    os.makedirs(DATA_DIR, exist_ok=True)
    sent_alerts = load_json(SENT_ALERTS_FILE)
    processed_matches = set()

    analyzer = KairosAnalyzer(GEMINI_API_KEY, provider_type=AI_PROVIDER)
    db = KairosDatabase()
    b365_scraper = Bet365Scraper()
    excapper = ExcapperScraper()

    print(f"[*] Analisador iniciado com provedor: {AI_PROVIDER.upper()}")
    print("\n==================================================")
    print("🚀 KAIROS ULTIMATE: MONITORAMENTO EXCAPPER INICIADO")
    print(f"[*] Limite Volume: {MIN_MATCH_VOLUME_EUR}€ | Anomalia: {MONEY_SPARK_THRESHOLD}€")
    print("==================================================\n")

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        context = await browser.new_context(
            viewport={'width': 1280, 'height': 720},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36"
        )

        page = await context.new_page()

        while True:
            try:
                # 1. Obter jogos live do Excapper
                live_matches = await excapper.get_live_matches(page)
                print(f"[*] [CYCLE] Analisando {len(live_matches)} jogos ao vivo...")
                
                for match in live_matches:
                    gid = match["game_id"]
                    teams = match["teams"]
                    volume_raw = match["total_money"].replace("€", "").replace(",", "").strip()
                    volume = float(volume_raw) if volume_raw.replace(".", "").isdigit() else 0.0
                    
                    if volume < MIN_MATCH_VOLUME_EUR:
                        continue

                    print(f"[{time.strftime('%H:%M:%S')}] Investigando {teams} (Vol: {match['total_money']})...")
                    
                    try:
                        # 2. Extrair histórico de fluxo (TODOS os mercados)
                        all_markets_data = await excapper.get_match_flow(page, gid)
                        if not all_markets_data:
                            print(f"      [?] Nenhum dado de mercado extraído para {gid}.")
                            continue

                        print(f"      [+] {len(all_markets_data)} mercados extraídos. Verificando anomalias...")

                        # 3. Detectar Anomalias Significativas
                        found_anomalies = []
                        
                        for m_name, m_data in all_markets_data.items():
                            flow_history = m_data["flow"]
                            recent = flow_history[:2] # Olhar as 2 entradas mais recentes
                            
                            for entry in recent:
                                volume_spike = entry["change_eur"] >= MONEY_SPARK_THRESHOLD
                                
                                # Critério B: Queda brusca de odds (%)
                                pct_str = entry["change_pct"].replace("%", "").replace("-", "")
                                odds_shift = False
                                try:
                                    if pct_str and float(pct_str) >= ODDS_SHIFT_THRESHOLD_PCT:
                                        odds_shift = True
                                except: pass
                                
                                current_anomaly = None
                                if volume_spike and odds_shift:
                                    current_anomaly = f"COMBO: Fluxo {entry['change_eur']}€ + Queda {entry['change_pct']}"
                                elif volume_spike:
                                    current_anomaly = f"Fluxo Bruto: {entry['change_eur']}€"
                                elif odds_shift:
                                    current_anomaly = f"Queda Bruta Odds: {entry['change_pct']}"

                                if current_anomaly:
                                    market_info = f"[{m_name} | {entry['selection']}]"
                                    full_reason = f"{market_info} {current_anomaly}"
                                    
                                    if not any(a["reason"] == full_reason for a in found_anomalies):
                                        found_anomalies.append({
                                            "reason": full_reason,
                                            "market": m_name,
                                            "selection": entry["selection"],
                                            "details": entry,
                                            "short_id": f"{m_name}_{entry['selection']}",
                                            "bf_url": m_data["betfair_url"]
                                        })

                        if not found_anomalies:
                            continue

                        # Priorizar anomalia mais forte para o alerta
                        primary_anomaly = found_anomalies[0]
                        anomaly_reason = primary_anomaly["reason"]

                        last_score = primary_anomaly["details"]["score"]
                        alert_hash = hashlib.md5(f"{gid}_{last_score}_{primary_anomaly['short_id']}".encode()).hexdigest()

                        if alert_hash in sent_alerts:
                            print(f"      [.] Alerta já enviado para {primary_anomaly['short_id']}. Pulando.")
                            continue

                        print(f"      [!] ANOMALIA DETECTADA: {anomaly_reason}")

                        # 4. Enriquecimento via Bet365
                        b365_data = None
                        home, away = teams.split(" vs ") if " vs " in teams else (teams, "")
                        
                        b365_page = await context.new_page()
                        try:
                            b365_res = await b365_scraper.search_match(b365_page, home, away)
                            if b365_res["found"]:
                                b365_data = await b365_scraper.get_live_stats(b365_page)
                        finally:
                            await b365_page.close()

                        # 5. Análise IA e Alerta
                        snapshot = {
                            "match_name": teams,
                            "live_score": last_score,
                            "primary_anomaly": primary_anomaly,
                            "all_anomalies": found_anomalies,
                            "bet365_data": b365_data
                        }
                        
                        ai_analysis = await analyzer.analyze_cross_market(snapshot)
                        
                        # Alerta Telegram
                        msg = (
                            f"🛰️ *KAIROS MONEY FLOW ALERT* 🛰️\n\n"
                            f"⚽ *Partida:* {teams}\n"
                            f"🔢 *Placar:* `{last_score}`\n"
                            f"🏆 *Liga:* {match['league']}\n"
                            f"💶 *Vol. Total Jogo:* `{match['total_money']}`\n\n"
                            f"🚨 *MERCADO:* `{primary_anomaly['market']}`\n"
                            f"📍 *SELEÇÃO:* `{primary_anomaly['selection']}`\n"
                            f"📊 *ANOMALIA:* `{primary_anomaly['reason'].split('] ')[1]}`\n"
                            f"⏳ *MOMENTO:* {primary_anomaly['details']['time']}\n"
                            f"📉 *BETFAIR ODD:* `{primary_anomaly['details']['odds']}`\n\n"
                            f"🔥 *BET365 LIVE STATS:*\n"
                            f"• AP: `{b365_data['ataques_perigosos']['home'] if b365_data else '0'} - {b365_data['ataques_perigosos']['away'] if b365_data else '0'}`\n"
                            f"• Cantos: `{b365_data['escanteios']['home'] if b365_data else '0'} - {b365_data['escanteios']['away'] if b365_data else '0'}`\n\n"
                            f"🤖 *IA INSIGHT:* {ai_analysis[:450]}...\n\n"
                            f"🔗 [ABRIR NA BETFAIR]({primary_anomaly['bf_url']})\n"
                            f"🔎 [Ver no Excapper]({match['url']})"
                        )
                        
                        send_telegram_alert(TELEGRAM_TOKEN, TELEGRAM_CHAT_ID, msg)
                        sent_alerts[alert_hash] = time.time()
                        save_json(SENT_ALERTS_FILE, sent_alerts)

                    except Exception as e:
                        print(f"      [!] Erro na análise da partida {gid}: {f'{e.__class__.__name__}: {e}'}")

                print(f"[*] Ciclo finalizado. Aguardando 60s...")
                await asyncio.sleep(60)

            except Exception as e:
                print(f"🚀 Erro no ciclo global: {e}")
                await asyncio.sleep(10)

            except Exception as e:
                print(f"🚀 Erro no ciclo global: {e}")
                await asyncio.sleep(10)

if __name__ == "__main__":
    asyncio.run(main())
