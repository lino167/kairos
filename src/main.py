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

# Mercado Permitidos (Whitelist)
ALLOWED_MARKETS = {
    "Both teams to Score?",
    "First Half Goals 0.5",
    "First Half Goals 1.5",
    "First Half Goals 2.5",
    "Half Time",
    "Match Odds",
    "Over/Under 1.5 Goals",
    "Over/Under 2.5 Goals",
    "Over/Under 3.5 Goals",
    "Over/Under 4.5 Goals",
    "Over/Under 5.5 Goals",
    "Over/Under 6.5 Goals"
}

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
            # Garantir que a página principal ainda está aberta
            if page.is_closed():
                print("[!] Página principal fechada. Recriando...")
                page = await context.new_page()

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
                            # Filtro de Mercado (Whitelist)
                            if m_name not in ALLOWED_MARKETS:
                                continue

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
                        
                        # Extrair apenas o primeiro time para a busca no SokkerPro
                        # Algumas vezes o Excapper usa " vs ", outras vezes " - "
                        if " vs " in teams:
                            home = teams.split(" vs ")[0].strip()
                            away = teams.split(" vs ")[1].strip()
                        elif " - " in teams:
                            home = teams.split(" - ")[0].strip()
                            away = teams.split(" - ")[1].strip()
                        else:
                            home, away = teams.strip(), ""
                        
                        print(f"      [*] Buscando no SokkerPro por: '{home}'")
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
                        
                        try:
                            current_odd = float(primary_anomaly['details']['odds'])
                        except:
                            current_odd = 0.0

                        market_name_up = primary_anomaly['market'].upper()
                        selection_up = primary_anomaly['selection'].upper()
                        current_min = sp_data.get("minute", 0) if sp_data else 0
                        
                        # 1. Detector "HT Smart Money" & Over 0.5 HT Sneak
                        if "HALF TIME" in market_name_up or "1ST HALF" in market_name_up:
                            if "OVER 0.5" in selection_up and last_score == "0-0" and 35 <= current_min <= 45:
                                manipulation_labels.append("HT_GOAL_SNEAK (Golo no final do 1º tempo?)")
                                level = 3
                            else:
                                manipulation_labels.append("HT_SMART_MONEY (Fluxo no 1º Tempo)")
                                level = 3

                        # 2. Detector "Late Goal Anomaly" (Final de Jogo + Pressão Baixa + Volume Alto)
                        if match['is_live'] and current_min >= 80 and "OVER" in market_name_up:
                            if avg_appm <= LOW_PRESSURE_LIMIT:
                                manipulation_labels.append("LATE_GOAL_ANOMALY (Fluxo tardio sem pressão)")
                                level = 3

                        # 3. Detector "Correct Score Dive" (Placares Atípicos)
                        if "CORRECT SCORE" in market_name_up:
                            atypical_scores = ["3-2", "2-3", "4-1", "1-4", "3-3"]
                            if any(score in selection_up for score in atypical_scores):
                                manipulation_labels.append(f"CORRECT_SCORE_DIVE ({selection_up})")
                                level = 3

                        # 4. Detector "HT/FT Turnaround" (Viradas)
                        if "HT/FT" in market_name_up:
                            if "/" in selection_up:
                                parts = selection_up.split("/")
                                if len(parts) >= 2 and parts[0].strip() != parts[1].strip(): 
                                    manipulation_labels.append(f"HT_FT_TURNAROUND ({selection_up})")
                                    level = 3

                        # 5. Detector "High Odds Sniper" (Odds Altas > 4.0)
                        if current_odd >= 4.0:
                            if not is_ocean: 
                                manipulation_labels.append(f"HIGH_ODDS_SNIPER (Odd: {current_odd})")
                                level = 3
                            else:
                                manipulation_labels.append("FAVORITE_DIVERGENCE (Dinheiro no Underdog?)")
                                level = 3

                        # 6. Detector "Match Odds Focus"
                        if "MATCH ODDS" in market_name_up or "MATCH RESULT" in market_name_up:
                            if not any("HIGH_ODDS" in l for l in manipulation_labels):
                                manipulation_labels.append("MATCH_ODDS_FOCUS (Fluxo no Principal)")
                                if pct_change >= 10: level = 3

                        # 7. Detector "Cesto de Lixo" (Heurística Geral)
                        if match['is_live'] and avg_appm <= LOW_PRESSURE_LIMIT and primary_anomaly['details']['change_eur'] >= MONEY_SPARK_POOL * 4:
                            if not any("LATE_GOAL" in l for l in manipulation_labels):
                                manipulation_labels.append("CESTO_DE_LIXO (Suspeita manipulação final)")
                                level = 3

                        # 8. Detector "Pre-Game Drop" (Liquidez Piscina + Queda > 20% sem jogo iniciado)
                        if primary_anomaly['details']['score'] == "0-0" and not is_ocean:
                            if pct_change >= PRE_GAME_DROP_LIMIT:
                                manipulation_labels.append("PRE_GAME_SMART_MONEY (Info Privilegiada?)")
                                level = 3

                        # 9. Detector "Drop Institucional" (Oceano + Volume Massivo + Drop Cirúrgico)
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

                        # 6. Análise IA (Apenas Nível 3 e se houver dados do SokkerPro)
                        ai_data = {"betting_tip": "N/A", "reasoning": "Nível de prioridade insuficiente ou falta de dados SP.", "suggested_odd": "N/A"}
                        if level == 3 and sp_data:
                            snapshot = {
                                "match_name": teams,
                                "live_score": last_score,
                                "is_live": match["is_live"], # Informar à IA se é LIVE ou PRÉ
                                "primary_anomaly": primary_anomaly,
                                "all_anomalies": found_anomalies, # Cross-Market data
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
                                # Extração robusta de JSON procurando pelos delimitadores { e }
                                start = ai_raw.find('{')
                                end = ai_raw.rfind('}') + 1
                                if start != -1 and end != 0:
                                    json_str = ai_raw[start:end]
                                    ai_data = json.loads(json_str)
                                else:
                                    raise ValueError("Delimitadores JSON não encontrados")
                            except Exception as e:
                                print(f"      [!] Falha ao processar JSON da IA: {e}")
                                # Fallback: se falhar o JSON, limpa a string e tenta exibir o máximo possível
                                cleaned_raw = ai_raw.replace("```json", "").replace("```", "").strip()
                                ai_data = {
                                    "betting_tip": "BACK/LAY (Ver Detalhes)",
                                    "reasoning": (cleaned_raw[:450] + "...") if len(cleaned_raw) > 450 else cleaned_raw,
                                    "suggested_odd": "Live",
                                    "risk": "Médio",
                                    "confidence": "7"
                                }

                        # 7. Alerta Telegram (Deep Intelligence Edition)
                        league = match.get("league", "Futebol")
                        excapper_url = match.get("url", "https://www.excapper.com")
                        time_info = match["time_text"]
                        
                        # Estrelas de confiança
                        try:
                            conf_val = int(ai_data.get("confidence", 7))
                        except:
                            conf_val = 7
                        stars = "⭐" * (conf_val // 2 if conf_val > 1 else 1)

                        # Formatação do Alerta
                        msg = (
                            f"🛰️ <b>KAIROS DEEP INTELLIGENCE (v2.9.1)</b> 🛰️\n\n"
                            f"🏆 <b>Campeonato:</b> {league}\n"
                            f"⚽ <b>Partida:</b> {teams}\n"
                            f"{ '🔢 <b>Placar Live:</b> ' + last_score + ' (' + time_info + ')' if match['is_live'] else '🕒 <b>Início:</b> ' + time_info }\n"
                            f'🔗 <a href="{excapper_url}">VER NO EXCAPPER</a>\n\n'
                            f"📊 <b>ANÁLISE (#AjusteBrutal):</b>\n"
                            f"• <b>Insight:</b> {ai_data.get('reasoning', 'N/A')}\n"
                            f"• <b>Risco:</b> {ai_data.get('risk', 'Médio')}\n\n"
                            f"💰 <b>BET SUGGESTION:</b> {ai_data.get('betting_tip', 'N/A').upper()} @ {ai_data.get('suggested_odd', 'Live')}\n"
                            f"⭐️ <b>Confiança:</b> {conf_val}/10 {stars}\n\n"
                            f"📝 <b>Contexto dos Mercados:</b>\n"
                            f"• {primary_anomaly['market']}: {primary_anomaly['reason']}\n"
                        )

                        if manipulation_labels:
                            msg += f"• ⚠️ <b>Sinais:</b> {', '.join(manipulation_labels)}\n"

                        msg += f'\n🔗 <a href="{primary_anomaly["bf_url"]}">ABRIR NA BETFAIR</a>'

                        if send_telegram_alert(TELEGRAM_TOKEN, TELEGRAM_CHAT_ID, msg):
                            print(f"      [OK] Alerta enviado com sucesso para {teams}!")
                            sent_alerts[alert_hash] = time.time()
                            save_json(SENT_ALERTS_FILE, sent_alerts)
                        else:
                            print(f"      [X] Falha ao enviar alerta para {teams}. Verifique logs do Telegram acima.")

                    except Exception as e:
                        print(f"      [!] Erro na análise da partida {gid}: {f'{e.__class__.__name__}: {e}'}")

                print(f"[*] Ciclo finalizado. Aguardando 60s...")
                await asyncio.sleep(60)

            except Exception as e:
                print(f"🚀 Erro no ciclo global: {e}")
                await asyncio.sleep(10)

if __name__ == "__main__":
    asyncio.run(main())
