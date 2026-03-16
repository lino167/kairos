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

# ... (rest of imports)

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
    processed_gids = set() # v3.2: Track gids already analyzed by AI

    # Inicializa o Analisador com o Provedor Escolhido
    analyzer = KairosAnalyzer(GEMINI_API_KEY, provider_type=AI_PROVIDER)
    if AI_PROVIDER == "deepseek":
        analyzer.set_deepseek_key(DEEPSEEK_API_KEY)

    scraper = KairosScraper(headless=True)
    db = KairosDatabase()

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=scraper.headless)
        context = await browser.new_context(viewport={'width': 1280, 'height': 800})
        page = await context.new_page()

        print("\n" + "="*50)
        print("🚀 KAIROS ULTIMATE: MONITORAMENTO MODULAR INICIADO")
        print("="*50 + "\n", flush=True)

        while True:
            try:
                game_ids = await scraper.get_live_game_ids(page)
                print(f"[{time.strftime('%H:%M:%S')}] Escaneando {len(game_ids)} partidas live...", flush=True)

                for i, gid in enumerate(game_ids):
                    print(f"  [{i+1}/{len(game_ids)}] Analisando {gid}...", flush=True)

                    snapshot = await scraper.scan_game_details(page, gid)

                    if snapshot:
                        # --- v1.7: Unificação e Tratamento de Dados (Unified Timeline) ---
                        unified_timeline = []
                        for m_name, m_data in snapshot["markets"].items():
                            history = m_data.get("history", [])
                            for idx, entry in enumerate(history):
                                if entry.get("drop_info") or m_data.get("is_suspended"):
                                    drop = entry.get("drop_info")
                                    prev_val = "N/A"
                                    
                                    # Tentar pegar o valor anterior (linha abaixo, pois a tabela é descendente)
                                    if drop and (idx + 1) < len(history):
                                        prev_val = history[idx+1].get("selection_values", {}).get(drop["selection"], "N/A")

                                    event = {
                                        "time": entry.get("time", "N/A"),
                                        "score": entry.get("score", "0-0"),
                                        "market": m_name,
                                        "selection": drop["selection"] if drop else "SIDE",
                                        "prev_value": prev_val,
                                        "curr_value": drop["value"] if drop else "N/A",
                                        "line": entry.get("line", "N/A"),
                                        "penalty": entry.get("penalty", False),
                                        "red_card": entry.get("red_card", False),
                                        "type": "DROP" if drop else "SUSPENSION",
                                        "state": entry.get("state", "Live")
                                    }
                                    unified_timeline.append(event)

                        # Ordenar timeline por tempo (tentar converter para int se possível)
                        def get_time_sort(e):
                            try: return int(e["time"])
                            except: return 0
                        unified_timeline.sort(key=get_time_sort)
                        snapshot["unified_timeline"] = unified_timeline

                        # Hash de Intensidade Real: Baseado na contagem de DROPS por mercado
                        # Só gera novo alerta se o número de células vermelhas mudar
                        drops_per_market = {k: len([h for h in v['history'] if h.get('drop_info')]) for k, v in snapshot["markets"].items()}
                        market_intensity = "".join([f"{k}{v}" for k, v in drops_per_market.items()])

                        alert_hash = hashlib.md5(f"{gid}_{snapshot['live_score']}_{market_intensity}".encode()).hexdigest()

                        if alert_hash not in sent_alerts and gid not in processed_gids:
                            print(f"      [*] Anomalia detectada! Linha do tempo unificada com {len(unified_timeline)} eventos.", flush=True)

                            ai_analysis_raw = await analyzer.analyze_cross_market(snapshot)

                            # Robust JSON Extraction
                            import json, re
                            ai_data = {}
                            try:
                                # Tenta extrair o bloco JSON se estiver dentro de markdown
                                json_match = re.search(r'\{.*\}', ai_analysis_raw, re.DOTALL)
                                clean_json = json_match.group(0) if json_match else ai_analysis_raw
                                ai_data = json.loads(clean_json)

                                # Se o JSON for válido mas contiver erro do provedor
                                if "error" in ai_data:
                                    ai_data["technical_insight"] = f"Erro no Provedor: {ai_data['error']}"
                                    ai_data["betting_tip"] = "N/A"
                                    ai_data["category"] = "#ProviderError"

                            except Exception as e:
                                print(f"      [!] Falha ao parsear JSON da IA: {e}")
                                print(f"      [DEBUG] Raw AI Output: {ai_analysis_raw[:200]}...")
                                ai_data = {
                                    "category": "#AnaliseTecnica",
                                    "technical_insight": ai_analysis_raw[:800], # Usa o texto bruto como insight
                                    "confidence": "??",
                                    "betting_tip": "Consultar Mercado",
                                    "danger_level": "N/A"
                                }

                            # Garantir que chaves críticas existam para o template
                            ai_data.setdefault("category", "#Pattern")
                            ai_data.setdefault("technical_insight", "Sem detalhes técnicos no momento.")
                            ai_data.setdefault("betting_tip", "Aguardar confirmação")
                            ai_data.setdefault("danger_level", "Desconhecido")
                            ai_data.setdefault("confidence", "5")

                            # Log Pattern
                            patterns = load_json(PATTERNS_LOG_FILE)
                            patterns.append({
                                "timestamp": time.time(),
                                "match_id": gid,
                                "snapshot": {k: v for k, v in snapshot.items() if k != 'cell_el'},
                                "ai_analysis": ai_data
                            })
                            save_json(PATTERNS_LOG_FILE, patterns)

                            # Salvar no Banco de Dados SQLite (v1.5)
                            db.save_snapshot(snapshot, ai_data, intensity="Red2/3")

                            # Formatar Resumo da Timeline
                            drops_summary = ""
                            market_counts = {}
                            for e in unified_timeline:
                                if e["type"] == "DROP":
                                    market_counts[e["market"]] = market_counts.get(e["market"], 0) + 1

                            for m_name, count in market_counts.items():
                                status = " (SUSPENSO)" if snapshot["markets"][m_name].get("is_suspended") else ""
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
                                f"📝 *Contexto dos Mercados:*\n{drops_summary or '• Sem drops recentes, apenas suspensão.'}\n"
                            )
                            await asyncio.to_thread(send_telegram_alert, TELEGRAM_TOKEN, TELEGRAM_CHAT_ID, msg)

                            sent_alerts[alert_hash] = time.time()
                            processed_gids.add(gid) # v3.2: Mark gid as analyzed
                            save_json(SENT_ALERTS_FILE, sent_alerts)

                # --- v3.0: Finalização de Partidas Pendentes ---
                pending_ids = db.get_pending_matches()
                if pending_ids:
                    print(f"\n      [*] Verificando resultado final de {len(pending_ids)} partidas pendentes...")
                    for p_gid in pending_ids:
                        final_score = await scraper.check_final_score(page, p_gid)
                        if final_score:
                            db.finalize_match(p_gid, final_score)
                        await asyncio.sleep(0.2) # Delay mais rápido

                print(f"\n[{time.strftime('%H:%M:%S')}] Ciclo completo. Aguardando 45s...\n", flush=True)
                await asyncio.sleep(45)

            except Exception as e:
                print(f"🚀 Erro no loop: {e}", flush=True)
                await asyncio.sleep(5)

if __name__ == "__main__":
    asyncio.run(main())
