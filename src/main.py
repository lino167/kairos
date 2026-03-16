import asyncio
import os
import time
import hashlib
from dotenv import load_dotenv
from playwright.async_api import async_playwright

from .utils import load_json, save_json, send_telegram_alert
from .analyzer import KairosAnalyzer
from .scraper import KairosScraper
from .database import KairosDatabase
from .bet365_scraper import Bet365Scraper
from .sofascore_prelive_scraper import SofaScorePreLiveScraper

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
PATTERNS_LOG_FILE = os.path.join(DATA_DIR, "patterns_log.json")

async def main():
    # Validação inteligente por provedor
    required_keys = [TELEGRAM_TOKEN, TELEGRAM_CHAT_ID]
    if AI_PROVIDER == "gemini":
        required_keys.append(GEMINI_API_KEY)
    elif AI_PROVIDER == "deepseek":
        required_keys.append(DEEPSEEK_API_KEY)

    if not all(required_keys) or any(k == "INSIRA_SUA_CHAVE_AQUI" for k in required_keys):
        print(f"❌ Erro: Chaves de API para {AI_PROVIDER.upper()} ausentes ou padrão no arquivo .env")
        return

    os.makedirs(DATA_DIR, exist_ok=True)
    sent_alerts = load_json(SENT_ALERTS_FILE)
    processed_gids = set()

    analyzer = KairosAnalyzer(GEMINI_API_KEY, provider_type=AI_PROVIDER)
    if AI_PROVIDER == "deepseek":
        analyzer.set_deepseek_key(DEEPSEEK_API_KEY)

    scraper = KairosScraper()
    db = KairosDatabase()
    b365_scraper = Bet365Scraper()
    sofa_pre = SofaScorePreLiveScraper()

    print(f"[*] Analisador iniciado com provedor: {AI_PROVIDER.upper()}")
    print("\n==================================================")
    print("🚀 KAIROS ULTIMATE: MONITORAMENTO MODULAR INICIADO")
    print("==================================================\n")

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        context = await browser.new_context(
            viewport={'width': 1280, 'height': 720},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36"
        )

        main_page = await context.new_page()

        while True:
            try:
                # v2.10: Verificar se a página principal ainda está aberta
                if main_page.is_closed():
                    print("    [*] Página principal fechada. Recriando...")
                    main_page = await context.new_page()

                # v2.9: Coletar IDs de jogos live
                game_ids = await scraper.get_live_game_ids(main_page)
                
                for i, gid in enumerate(game_ids[:15]):
                    print(f"[{time.strftime('%H:%M:%S')}] Escaneando {len(game_ids)} partidas live...")
                    print(f"  [{i+1}/{len(game_ids)}] Analisando {gid}...")
                    
                    try:
                        snapshot = await scraper.scan_game_details(main_page, gid)
                        if not snapshot: continue

                        # Só gera alerta em anomalias de "Red" (intensidade alta)
                        # v2.9: scan_game_details já filtra por is_red3 se configurado lá, 
                        # mas aqui mantemos a lógica de hash para evitar alertas repetidos no mesmo score
                        unified_timeline = [] 
                        
                        # Extrair drops para o hash e resumo
                        drops_per_market = {}
                        for m_name, m_data in snapshot["markets"].items():
                            drops = [h for h in m_data['history'] if h.get('drop_info')]
                            drops_per_market[m_name] = len(drops)
                            for d in drops:
                                unified_timeline.append({
                                    "type": "DROP",
                                    "market": m_name,
                                    "time": d["time"],
                                    "score": d["score"],
                                    "selection": d["drop_info"]["selection"],
                                    "value": d["drop_info"]["value"]
                                })

                        market_intensity = "".join([f"{k}{v}" for k, v in drops_per_market.items()])
                        alert_hash = hashlib.md5(f"{gid}_{snapshot['live_score']}_{market_intensity}".encode()).hexdigest()

                        if alert_hash in sent_alerts:
                            print(f"      [.] Alerta já enviado para este placar/intensidade. Pulando.")
                            continue
                        
                        if gid in processed_gids:
                            print(f"      [.] Partida já analisada nesta sessão. Pulando.")
                            continue

                        print(f"      [*] Anomalia detectada! Linha do tempo unificada com {len(unified_timeline)} eventos.")

                        # --- ENRIQUECIMENTO SEQUENCIAL (BET365 ONLY) ---
                        b365_data = None
                        ai_analysis_raw = ""
                        
                        try:
                            match_name = snapshot.get("match_name", "")
                            home, away = "", ""
                            
                            if " vs " in match_name:
                                home, away = match_name.split(" vs ", 1)
                            elif " - " in match_name:
                                home, away = match_name.split(" - ", 1)
                            elif "-" in match_name:
                                home, away = match_name.split("-", 1)
                            
                            if home and away:
                                # 1. Bet365 Live
                                print(f"      [*] [BET365] Iniciando busca live para: {home} vs {away}")
                                b365_page = await context.new_page()
                                try:
                                    b365_res = await b365_scraper.search_match(b365_page, home, away)
                                    if b365_res["found"]:
                                        print(f"      [*] [BET365] Partida encontrada. Extraindo estatísticas e odds ao vivo...")
                                        b365_data = await b365_scraper.get_live_stats(b365_page)
                                except Exception as be:
                                    print(f"      [!] [BET365] Erro durante o processo: {be}")
                                finally:
                                    await b365_page.close()

                                if not b365_data:
                                    print(f"      [!] [BET365] Abortando: Dados live não encontrados ou insuficientes.")
                                    continue

                                # Snapshot Enrichment
                                snapshot["bet365_data"] = b365_data
                                snapshot["sofascore_prelive_data"] = None # Removido conforme solicitado

                                print(f"      [*] Sucesso! Enviando para IA para análise híbrida...")
                                ai_analysis_raw = await analyzer.analyze_cross_market(snapshot)

                                # Processar Resposta da IA (JSON Robust Extraction)
                                import json, re
                                ai_data = {}
                                try:
                                    json_match = re.search(r'\{.*\}', ai_analysis_raw, re.DOTALL)
                                    clean_json = json_match.group(0) if json_match else ai_analysis_raw
                                    ai_data = json.loads(clean_json)
                                except:
                                    ai_data = {
                                        "category": "#AnaliseTecnica",
                                        "technical_insight": ai_analysis_raw[:800],
                                        "confidence": "5",
                                        "betting_tip": "Consultar Mercado",
                                        "danger_level": "N/A"
                                    }

                                # Garantir chaves padrão
                                ai_data.setdefault("category", "#Pattern")
                                ai_data.setdefault("technical_insight", "...")
                                ai_data.setdefault("betting_tip", "Aguardar")
                                ai_data.setdefault("confidence", "5")

                                # Log e DB
                                db.save_snapshot(snapshot, ai_data, intensity="Red2/3")

                                # Resumo de Mercados
                                drops_summary = ""
                                market_counts = {}
                                for e in unified_timeline:
                                    if e["type"] == "DROP":
                                        market_counts[e["market"]] = market_counts.get(e["market"], 0) + 1
                                for m_name, count in market_counts.items():
                                    status = " (SUSPENSO)" if snapshot["markets"].get(m_name, {}).get("is_suspended") else ""
                                    drops_summary += f"• *{m_name}*{status}: {count} queda(s)\n"

                                # Alerta Telegram
                                event_url = f"https://dropping-odds.com/event.php?id={gid}"
                                msg = (
                                    f"🛰️ *KAIROS DEEP INTELLIGENCE (v2.9.1)* 🛰️\n\n"
                                    f"🏆 *Campeonato:* {snapshot.get('league_name', 'Desconhecido')}\n"
                                    f"⚽ *Partida:* {snapshot['match_name']}\n"
                                    f"🔢 *Placar Live:* `{snapshot['live_score']}`\n"
                                    f"🔗 [Ver na Dropping Odds]({event_url})\n\n"
                                    f"📊 *ANÁLISE ({ai_data.get('category', '#Pattern')}):*\n"
                                    f"• *Insight:* {ai_data.get('technical_insight', '...')}\n"
                                    f"• *Risco:* `{ai_data.get('danger_level', 'Médio')}`\n\n"
                                    f"💰 *BET SUGGESTION:* `{ai_data.get('betting_tip', 'N/A')}`\n"
                                    f"⭐ *Confiança:* `{ai_data.get('confidence', '5')}/10`\n\n"
                                    f"🔥 *PRESSÃO AO VIVO (BET365):*\n"
                                    f"• AP: `{b365_data.get('ataques_perigosos', {}).get('home', '0')} - {b365_data.get('ataques_perigosos', {}).get('away', '0')}`\n"
                                    f"• Remates No Alvo: `{b365_data.get('remates_alvo', {}).get('home', '0')} - {b365_data.get('remates_alvo', {}).get('away', '0')}`\n"
                                    f"• ODDS: `({b365_data.get('odds', {}).get('home', 'N/A')}) ({b365_data.get('odds', {}).get('draw', 'N/A')}) ({b365_data.get('odds', {}).get('away', 'N/A')})`\n"
                                    f"🔗 [Acessar Partida na Bet365]({b365_data.get('direct_link', '#')})\n\n"
                                    f"📝 *Contexto dos Mercados:*\n{drops_summary or '• Sem drops recentes.'}\n"
                                )
                                await asyncio.to_thread(send_telegram_alert, TELEGRAM_TOKEN, TELEGRAM_CHAT_ID, msg)

                                sent_alerts[alert_hash] = time.time()
                                save_json(SENT_ALERTS_FILE, sent_alerts)
                                processed_gids.add(gid)

                        except Exception as me:
                            print(f"      [!] Erro no fluxo sequencial: {me}")
                            continue

                    except Exception as e:
                        print(f"    [!] Erro processando partida {gid}: {e}")
                        continue

            except Exception as e:
                print(f"🚀 Erro no loop global: {e}")
                await asyncio.sleep(10)

            print(f"\n[Aguardando {30}s para próximo ciclo...]")
            await asyncio.sleep(30)

if __name__ == "__main__":
    asyncio.run(main())
