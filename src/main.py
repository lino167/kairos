import asyncio
import os
import time
import hashlib
from dotenv import load_dotenv
from playwright.async_api import async_playwright

from .utils import load_json, save_json, send_telegram_alert
from .analyzer import KairosAnalyzer
from .sokkerpro_scraper import SokkerProScraper
from .excapper_scraper import ExcapperScraper

# Carregar variáveis de ambiente
load_dotenv()

# Configuração
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
AI_PROVIDER = os.getenv("AI_PROVIDER", "gemini")

DATA_DIR = "data"
SENT_ALERTS_FILE = os.path.join(DATA_DIR, "sent_alerts.json")

# Limites Estratégicos (Piscina vs Oceano)
MONEY_SPARK_POOL = 500.0      # Gatilho para ligas menores
MONEY_SPARK_OCEAN = 10000.0   # Gatilho para grandes ligas
ODDS_SHIFT_MIN = 10           # Queda mínima de 10%
OCEAN_LIQUIDITY_MIN = 50000.0 # Acima disso é "Oceano"
MIN_MATCH_VOLUME_EUR = 100.0   # Volume mínimo para analisar o jogo
MONEY_SPARK_THRESHOLD = 500.0  # Compatibilidade com prints antigos

# Níveis de Socorro (SokkerPro)
PRESSURE_EXPLOSIVE = 1.0      # APPM acima disso é pressão forte
PRESSURE_DIVERGENCE = 0.4      # Abaixo disso com volume alto é divergência
LOW_PRESSURE_LIMIT = 0.2       # Pressão quase nula ("Cesto de Lixo")
RESISTANT_ODD_LIMIT = 1.5      # Pressão muito alta mas a odd não baixa

# Tempos de Jogo
LATE_GAME_MIN = 80            # Minutos finais para "Cesto de Lixo"
PRE_GAME_DROP_LIMIT = 20       # Queda de 20% pré-jogo é suspeito

# Limites Institucionais (Oceano v2.3)
INSTITUTIONAL_VOL_BARRIER = 50000.0 # IA só acorda se vol anomalia > 50k em jogos grandes
OCEAN_DROP_MIN = 5.0                # Drop institucional (5-8%)
LARGE_TOTAL_VOL = 200000.0          # Volume total para ser "Grande Jogo"

async def main():
    required_keys = [TELEGRAM_TOKEN, TELEGRAM_CHAT_ID]
    # (Validação de chaves omitida para brevidade)
    
    os.makedirs(DATA_DIR, exist_ok=True)
    sent_alerts = load_json(SENT_ALERTS_FILE)

    analyzer = KairosAnalyzer(GEMINI_API_KEY, provider_type=AI_PROVIDER)
    sp_scraper = SokkerProScraper()
    excapper = ExcapperScraper()

    print(f"[*] Analisador iniciado com provedor: {AI_PROVIDER.upper()}")
    print("\n==================================================")
    print("🚀 KAIROS ULTIMATE: MONITORAMENTO EXCAPPER + SOKKERPRO")
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
                # 1. Obter jogos live do Excapper (Money Flow Source)
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
                            recent = flow_history[:2]
                            # 1. Definir Liquidez (Piscina vs Oceano)
                            total_vol = float(match['total_money'].replace('€', '').replace(',', '').strip() or 0)
                            is_ocean = total_vol >= OCEAN_LIQUIDITY_MIN
                            
                            for entry in recent:
                                # Limite dinâmico de volume conforme liquidez
                                vol_threshold = MONEY_SPARK_OCEAN if is_ocean else MONEY_SPARK_POOL
                                volume_spike = entry["change_eur"] >= vol_threshold
                                
                                pct_str = entry["change_pct"].replace("%", "").replace("-", "")
                                odds_shift = False
                                try:
                                    if pct_str and float(pct_str) >= ODDS_SHIFT_MIN:
                                        odds_shift = True
                                except: pass
                                
                                current_anomaly = None
                                if volume_spike or odds_shift:
                                    type_str = "OCÉANO" if is_ocean else "PISCINA"
                                    reason = f"[{type_str}] "
                                    if volume_spike and odds_shift: reason += f"COMBO: {entry['change_eur']}€ + Queda {entry['change_pct']}"
                                    elif volume_spike: reason += f"Fluxo: {entry['change_eur']}€"
                                    else: reason += f"Queda Odds: {entry['change_pct']}"
                                    current_anomaly = reason # Assign the constructed reason to current_anomaly

                                if current_anomaly:
                                    if not any(a["reason"] == f"[{m_name} | {entry['selection']}] {current_anomaly}" for a in found_anomalies):
                                        found_anomalies.append({
                                            "reason": f"[{m_name} | {entry['selection']}] {current_anomaly}",
                                            "market": m_name,
                                            "selection": entry["selection"],
                                            "details": entry,
                                            "short_id": f"{m_name}_{entry['selection']}",
                                            "bf_url": m_data["betfair_url"]
                                        })

                        if not found_anomalies:
                            continue

                        primary_anomaly = found_anomalies[0]
                        last_score = primary_anomaly["details"]["score"]
                        alert_hash = hashlib.md5(f"{gid}_{last_score}_{primary_anomaly['short_id']}".encode()).hexdigest()

                        if alert_hash in sent_alerts:
                            print(f"      [.] Alerta já enviado para {primary_anomaly['short_id']}. Pulando.")
                            continue

                        print(f"      [!] ANOMALIA DETECTADA: {primary_anomaly['reason']}")

                        # 4. Enriquecimento via SokkerPro (Stats & Pressure)
                        sp_data = None
                        pre_stats = None
                        home, away = teams.split(" vs ") if " vs " in teams else (teams, "")
                        
                        sp_page = await context.new_page()
                        try:
                            sp_res = await sp_scraper.search_match(sp_page, home, away)
                            if sp_res["found"]:
                                sp_data = await sp_scraper.get_live_stats(sp_page)
                                pre_stats = await sp_scraper.get_prelive_stats(sp_page)
                        finally:
                            await sp_page.close()

                        # 5. Lógica de Níveis de Prioridade e Detecção de Manipulação
                        level = 1
                        avg_appm = 0
                        is_late_game = False
                        if sp_data:
                            avg_appm = (sp_data['appm_5m']['home'] + sp_data['appm_5m']['away']) / 2
                            # Nota: No momento o Excapper não retorna o minuto atual no snippet simplificado,
                            # mas podemos inferir se o jogo está no final ou verificar no SokkerPro se disponível futuramente.
                        
                        # Detectores de Manipulação (Smart Money)
                        manipulation_labels = []
                        pct_change = float(primary_anomaly['details']['change_pct'].replace("%", "").replace("-", "") or 0)
                        
                        # 1. Detector "Cesto de Lixo" (Late Game + Vol Alto + Pressão Baixa)
                        # Assumindo que o Excapper indica o tempo no flow ou que sp_data tenha tempo
                        # Aqui usaremos uma heurística se o APPM for muito baixo mas o volume alto:
                        if avg_appm <= LOW_PRESSURE_LIMIT and primary_anomaly['details']['change_eur'] >= MONEY_SPARK_POOL * 2:
                            manipulation_labels.append("CESTO_DE_LIXO (Suspeita manipulação final)")
                            level = 3

                        # 2. Detector "Odd Resistente" (Pressão Alta + Odd Estática/Subindo)
                        if avg_appm >= RESISTANT_ODD_LIMIT:
                            # Se a mudança de odd for positiva ou queda irrelevante (< 5%)
                            if pct_change < 5:
                                manipulation_labels.append("ODD_RESISTENTE (Smart Money segurando)")
                                level = 3

                        # 3. Detector "Pre-Game Drop" (Liquidez Piscina + Queda > 20% sem jogo iniciado)
                        if primary_anomaly['details']['score'] == "0-0" and not is_ocean:
                            if pct_change >= PRE_GAME_DROP_LIMIT:
                                manipulation_labels.append("PRE_GAME_SMART_MONEY (Info Privilegiada?)")
                                level = 3

                        # 4. Detector "Drop Institucional" (Oceano + Volume Massivo + Drop Cirúrgico)
                        is_institutional = False
                        if is_ocean:
                            vol_anomaly = primary_anomaly['details']['change_eur']
                            if vol_anomaly >= INSTITUTIONAL_VOL_BARRIER and OCEAN_DROP_MIN <= pct_change <= 15:
                                manipulation_labels.append(f"INSTITUTIONAL_SMART_MONEY (Vol: {vol_anomaly}€)")
                                is_institutional = True
                                level = 3

                        # Definição de Nível Padrão se não marcado como manipulação
                        if level < 3:
                            if sp_data:
                                if avg_appm >= PRESSURE_EXPLOSIVE or avg_appm <= PRESSURE_DIVERGENCE:
                                    level = 3
                                else:
                                    level = 2
                            else:
                                # Em jogos grandes, só acorda se for institucional ou volume muito anômalo
                                if is_ocean:
                                    if primary_anomaly['details']['change_eur'] >= INSTITUTIONAL_VOL_BARRIER:
                                        level = 3
                                    else:
                                        level = 2
                                else:
                                    if primary_anomaly['details']['change_eur'] >= MONEY_SPARK_POOL * 2:
                                        level = 3
                                    else:
                                        level = 2

                        # Filtro Final de Custo (Oceano): Só acorda IA se for institucional ou volume absurdamente alto
                        if is_ocean and level == 3 and not is_institutional:
                            if primary_anomaly['details']['change_eur'] < INSTITUTIONAL_VOL_BARRIER:
                                print(f"      [.] Oceano detectado mas volume ({primary_anomaly['details']['change_eur']}€) abaixo do barreira institucional (€50k).")
                                level = 2

                        if level == 1:
                            print(f"      [.] Nível 1 (Ruído). Pulando.")
                            continue
                            
                        print(f"      [!] GAILHO NÍVEL {level} DETECTADO. Manipulação: {manipulation_labels or 'Nenhuma'}")

                        # 6. Análise IA (Apenas Nível 3)
                        ai_data = {"betting_tip": "N/A", "reasoning": "Nível de prioridade insuficiente.", "suggested_odd": "N/A"}
                        if level == 3:
                            snapshot = {
                                "match_name": teams,
                                "live_score": last_score,
                                "primary_anomaly": primary_anomaly,
                                "all_anomalies": found_anomalies,
                                "sokkerpro_live": sp_data,
                                "sokkerpro_pre": pre_stats,
                                "strategic_context": {
                                    "is_ocean": is_ocean,
                                    "avg_appm": avg_appm,
                                    "is_divergence": avg_appm <= PRESSURE_DIVERGENCE,
                                    "manipulation_labels": manipulation_labels
                                }
                            }
                            ai_raw = await analyzer.analyze_cross_market(snapshot)
                            try:
                                # Tentar extrair JSON da resposta (limpando possíveis markdowns da IA)
                                json_str = ai_raw.strip()
                                if "```json" in json_str:
                                    json_str = json_str.split("```json")[1].split("```")[0].strip()
                                elif "```" in json_str:
                                    json_str = json_str.split("```")[1].split("```")[0].strip()
                                
                                ai_data = json.loads(json_str)
                            except:
                                ai_data = {"betting_tip": "BACK/LAY (Ver Análise)", "reasoning": ai_raw[:200], "suggested_odd": "Live"}

                        # 7. Alerta Telegram (Claro e Direto)
                        
                        # Definir cor/emoji por nível
                        status_emoji = "🔴" if level == 3 else "🟡"
                        manip_str = f"⚠️ *SINAL:* `{', '.join(manipulation_labels)}`" if manipulation_labels else ""
                        
                        msg = (
                            f"{status_emoji} *KAIROS V2.4 - OPORTUNIDADE*\n"
                            f"━━━━━━━━━━━━━━━━━━━━\n"
                            f"⚽ *{teams}*\n"
                            f"🔢 Placar: `{last_score}` | Vol: `{match['total_money']}`\n"
                            f"━━━━━━━━━━━━━━━━━━━━\n"
                            f"🎯 *INDICAÇÃO:* `{ai_data.get('betting_tip', 'N/A').upper()}`\n"
                            f"💰 *ODD SUGERIDA:* `{ai_data.get('suggested_odd', 'N/A')}`\n"
                            f"💡 *PORQUÊ:* {ai_data.get('reasoning', 'N/A')}\n"
                            f"━━━━━━━━━━━━━━━━━━━━\n"
                            f"📊 *DADOS DE CAMPO (SP):*\n"
                            f"🔥 Pressão (5m): `{sp_data['appm_5m']['home'] if sp_data else 0}-{sp_data['appm_5m']['away'] if sp_data else 0}`\n"
                            f"💣 AP: `{sp_data['ataques_perigosos']['home'] if sp_data else 0} - {sp_data['ataques_perigosos']['away'] if sp_data else 0}`\n"
                            f"{manip_str}\n"
                            f"━━━━━━━━━━━━━━━━━━━━\n"
                            f"🔗 *[ABRIR NA BETFAIR]({primary_anomaly['bf_url']})*"
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

if __name__ == "__main__":
    asyncio.run(main())
