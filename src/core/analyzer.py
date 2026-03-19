"""
analyzer.py — Módulo de Análise IA do Kairos (v3.1)
Suporta: Gemini, DeepSeek, Claude (stub)
Inclui prompt enriquecido com contexto Smart Money, tier de liga e dados cruzados.
"""

import google.generativeai as genai
import asyncio
import json
from abc import ABC, abstractmethod


class BaseAIProvider(ABC):
    @abstractmethod
    async def analyze(self, snapshot: dict) -> str:
        pass

    def _prepare_prompt(self, snapshot: dict) -> str:
        is_live   = snapshot.get("is_live", False)
        status    = "🔴 LIVE" if is_live else "🔵 PRÉ-JOGO"
        score     = snapshot.get("live_score", "N/A")
        match_min = snapshot.get("current_minute", 0)

        # ── Contexto de Liga e Smart Money ─────────────────────────────────
        sm          = snapshot.get("smart_money_result", {})
        sm_profile  = sm.get("league_profile", {})
        sm_tier     = sm_profile.get("tier", "UNKNOWN")
        sm_spark    = sm_profile.get("spark_threshold", 0)
        sm_disp     = sm_profile.get("disp_threshold", 0)
        sm_signals  = sm.get("signals", [])
        sm_label    = sm.get("summary_label", "Sem sinais SM")

        league_ctx  = (
            f"LIGA/CONTEXTO DE LIQUIDEZ:\n"
            f"  • Tier: {sm_tier} | Limiar Anomalia: {sm_spark}€ | Limiar Desproporção: {sm_disp}€\n"
            f"  • Resumo Smart Money: {sm_label}\n"
        )

        if sm_signals:
            league_ctx += "  • Sinais Detectados:\n"
            for sig in sm_signals:
                league_ctx += f"    — [{sig.get('label')}] {sig.get('description', '')}\n"

        # ── Dados DroppingOdds (fonte de drops) ──────────────────────────────
        do_drops = snapshot.get("dropping_odds_drops", [])
        do_context_text = snapshot.get("dropping_context_text", "")

        if do_drops:
            drop_ctx = "DROPS DE ODDS DETECTADOS (DroppingOdds.com):\n"
            for drop in do_drops[:6]:
                signals = ", ".join(drop.get("signals", []))
                sig_text = f" | [!] SINAIS: {signals}" if signals else ""
                drop_ctx += (
                    f"  • [{drop.get('table', 'N/A')}] {drop.get('selection', 'N/A')} → "
                    f"Abertura: {drop.get('open_odd', 0):.2f} | Atual: {drop.get('current_odd', 0):.2f} | "
                    f"Queda: -{drop.get('drop_pct', 0):.1f}% {drop.get('severity', '')}{sig_text}\n"
                )
        elif do_context_text:
            drop_ctx = f"CONTEXTO DROPPINGODDS:\n{do_context_text}\n"
        else:
            drop_ctx = ""

        # ── Fluxo Excapper (fluxo de dinheiro associado) ──────────────────────
        exc_markets = snapshot.get("excapper_markets", {})
        exc_flow_text = snapshot.get("primary_excapper_market", "")
        pri_flow = snapshot.get("primary_excapper_flow", [])

        if pri_flow:
            exc_ctx = f"FLUXO DE DINHEIRO (Excapper — mercado: {exc_flow_text}):\n"
            for entry in pri_flow[:5]:
                exc_ctx += (
                    f"  • [{entry.get('time', 'N/A')} | {entry.get('score', 'N/A')}] "
                    f"{entry.get('selection', 'N/A')}: "
                    f"{entry.get('change_eur', 0):.0f}€ | Odd {entry.get('odds', 'N/A')} ({entry.get('change_pct', 'N/A')})\n"
                )
        else:
            exc_ctx = "FLUXO EXCAPPER: Não disponível (link não encontrado na página do jogo).\n"

        # ── Fluxo Principal (Excapper via análise clássica) ───────────────────
        primary      = snapshot.get("primary_anomaly", {})
        all_anomalies = snapshot.get("all_anomalies", [])
        det           = primary.get("details", {})

        flow_ctx = (
            f"FLUXO PRINCIPAL DETECTADO:\n"
            f"  • Mercado: {primary.get('market')} | Seleção: {primary.get('selection')}\n"
            f"  • Volume Entrada: {det.get('change_eur', 0)}€\n"
            f"  • Queda de Odd: {det.get('change_pct', 'N/A')} | Odd Atual: {det.get('odds', 'N/A')}\n"
            f"  • Placar no Momento do Fluxo: {det.get('score', 'N/A')}\n"
            f"  • Razão Detectada: {primary.get('reason', 'N/A')}\n"
        )

        if len(all_anomalies) > 1:
            flow_ctx += "ANOMALIAS CRUZADAS (mesmo jogo, outros mercados):\n"
            for anom in all_anomalies:
                if anom["short_id"] != primary["short_id"]:
                    adet = anom.get("details", {})
                    flow_ctx += (
                        f"  • {anom['market']} [{anom['selection']}] → "
                        f"{adet.get('change_eur', 0)}€ / Odd: {adet.get('odds', 'N/A')} / "
                        f"Queda: {adet.get('change_pct', 'N/A')}\n"
                    )

        # ── SokkerPro Live ──────────────────────────────────────────────────
        sp_live = snapshot.get("sokkerpro_live", {})
        if is_live and sp_live:
            appm5_h  = sp_live.get("appm_5m", {}).get("home", "N/A")
            appm5_a  = sp_live.get("appm_5m", {}).get("away", "N/A")
            appm10_h = sp_live.get("appm_10m", {}).get("home", "N/A")
            appm10_a = sp_live.get("appm_10m", {}).get("away", "N/A")
            ap_h     = sp_live.get("ataques_perigosos", {}).get("home", "N/A")
            ap_a     = sp_live.get("ataques_perigosos", {}).get("away", "N/A")
            posse_h  = sp_live.get("posse", {}).get("home", "N/A")
            posse_a  = sp_live.get("posse", {}).get("away", "N/A")
            sp_ctx = (
                f"DADOS DE CAMPO LIVE (SokkerPro):\n"
                f"  • Pressão 5m:  Casa {appm5_h} × Fora {appm5_a}\n"
                f"  • Pressão 10m: Casa {appm10_h} × Fora {appm10_a}\n"
                f"  • Ataques Perigosos: Casa {ap_h} × Fora {ap_a}\n"
                f"  • Posse de Bola: Casa {posse_h}% × Fora {posse_a}%\n"
            )
        elif is_live:
            sp_ctx = "DADOS DE CAMPO LIVE: Indisponíveis no momento.\n"
        else:
            sp_ctx = "DADOS DE CAMPO: [PRÉ-JOGO] Sem dados live ainda.\n"

        # ── SokkerPro Pre-Live (histórico) ──────────────────────────────────
        sp_pre = snapshot.get("sokkerpro_pre", {})
        if sp_pre:
            pre_ctx = (
                f"HISTÓRICO (H2H / Pré-Live):\n"
                f"  • Média Gols: {sp_pre.get('avg_goals', 'N/A')}\n"
                f"  • Média Cantos: {sp_pre.get('avg_corners', 'N/A')}\n"
            )
        else:
            pre_ctx = "HISTÓRICO: Indisponível.\n"

        # ── Contexto Estratégico ────────────────────────────────────────────
        strat        = snapshot.get("strategic_context", {})
        is_ocean     = strat.get("is_ocean", False)
        avg_appm     = strat.get("avg_appm", 0)
        is_div       = strat.get("is_divergence", False)
        manip_labels = strat.get("manipulation_labels", [])
        liquidity    = "OCÉANO (Alta Liquidez)" if is_ocean else "PISCINA (Baixa Liquidez)"
        divergence   = "✅ SIM — CONTRADIÇÃO (fluxo ≠ campo)" if is_div else "❌ NÃO — CONFIRMAÇÃO (fluxo = campo)"

        strat_ctx = (
            f"CONTEXTO ESTRATÉGICO:\n"
            f"  • Liquidez: {liquidity}\n"
            f"  • Pressão Média (APPM): {avg_appm:.2f}\n"
            f"  • Divergência Fluxo vs Campo: {divergence}\n"
        )
        if manip_labels:
            strat_ctx += "  • Sinais de Manipulação Detectados:\n"
            for lbl in manip_labels:
                strat_ctx += f"    — {lbl}\n"

        # ── SISTEMA DE PROMPT ───────────────────────────────────────────────
        # Ajusta instruções conforme o status do jogo
        has_dropping_data = bool(do_drops)
        has_excapper_flow = bool(pri_flow)

        if is_live:
            mission = (
                "MISSÃO DE ANÁLISE (LIVE):\n"
                "1. DROPS: Analise os drops de odds nas tabelas do DroppingOdds — são moves de sharp ou mercado natural?\n"
                "2. FLUXO vs DROP: O fluxo de dinheiro do Excapper confirma os drops detectados? Os dois apontam para a mesma direção?\n"
                "3. TIMING: O minuto do jogo é crítico? (pressão no 75+, HT, final de set)?\n"
                "4. CROSS-TABLE: Se drops aparecem em múltiplas tabelas (1X2 + Total) simultaneamente, é sinal mais forte.\n"
                "5. SMART MONEY: Os sinais de desproporção, pico tardio ou drop HT são convergentes com o drop?\n"
                "6. VEREDITO: Movimento de 'Sharp Bettor' (insider/sindicato) ou correção natural de mercado?\n"
            )
        else:
            mission = (
                "MISSÃO DE ANÁLISE (PRÉ-JOGO):\n"
                "1. DROPS PRÉ-JOGO: A queda de odd nas tabelas sem jogo iniciado indica insider ou modelo quant?\n"
                "2. CROSS-TABLE: Múltiplos mercados com drop simultâneo (1X2 + Total + HT) reforçam o sinal.\n"
                "3. FLUXO EXCAPPER: O dinheiro confirma a direção dos drops? Qual mercado recebe mais volume?\n"
                "4. CONTEXTO: H2H e médias históricas justificam o movimento?\n"
                "5. VEREDITO: É movimento de sindicato (Oceano) ou apostador sharp isolado (Piscina)?\n"
            )

        # Instrução de formato — mais campos para enriquecer o alerta
        output_schema = (
            "FORMATO DE SAÍDA (JSON ESTRITO — sem texto fora das chaves):\n"
            "{\n"
            '  "category": "#KAIROS_ANALYSIS",\n'
            '  "verdict": "SHARP_ACTION / INSTITUTIONAL_FLOW / NOISE / SUSPICIOUS",\n'
            '  "risk": "Baixo / Médio / Alto",\n'
            '  "confidence": <número inteiro 1-10>,\n'
            '  "reasoning": "<análise técnica direta, max 500 chars. Mencione a correlação fluxo×campo e o sinal mais forte>",\n'
            '  "betting_tip": "<ação exata: ex: BACK OVER 2.5 / LAY Home / BACK Away AH +0.5>",\n'
            '  "suggested_odd": "<odd mínima aceitável ou \'Live\' se muito volátil>",\n'
            '  "stake_suggestion": "<percentual da banca ou \'Mínimo\' / \'Normal\' / \'Alto\'>",\n'
            '  "alert_headline": "<frase de impacto de até 80 chars para cabeçalho do alerta>"\n'
            "}"
        )

        return (
            "Você é o KAIROS — sistema de análise de Smart Money, drops de odds e fluxo institucional.\n"
            "Sua missão é cruzar dados de DroppingOdds (drops de odds) com fluxo de dinheiro (Excapper)\n"
            "para gerar análises profissionais e acionáveis, detectando movimentos de insiders e sharp bettors.\n\n"
            f"═══════════════════════════════════════\n"
            f"PARTIDA: {snapshot['match_name']}\n"
            f"STATUS: {status} | Minuto: {match_min}' | Placar: {score}\n"
            f"═══════════════════════════════════════\n\n"
            f"{drop_ctx}\n"
            f"{exc_ctx}\n"
            f"{league_ctx}\n"
            f"{flow_ctx}\n"
            f"{strat_ctx}\n"
            f"{sp_ctx}\n"
            f"{pre_ctx}\n"
            f"{mission}\n"
            f"{output_schema}"
        )


# ── Gemini ─────────────────────────────────────────────────────────────────────
class GeminiProvider(BaseAIProvider):
    def __init__(self, api_key):
        genai.configure(api_key=api_key)
        self.model_names = [
            "models/gemini-2.0-flash",
            "models/gemini-flash-latest",
            "models/gemini-pro-latest",
        ]
        self.current_idx = 0

    async def analyze(self, snapshot: dict) -> str:
        prompt = self._prepare_prompt(snapshot)
        for _ in range(len(self.model_names)):
            model_name = self.model_names[self.current_idx]
            try:
                print(f"    [*] [Gemini] Tentando {model_name}...")
                model = genai.GenerativeModel(
                    model_name,
                    generation_config={
                        "temperature": 0.3,     # mais determinístico para JSON
                        "top_p": 0.9,
                        "max_output_tokens": 1024,
                    }
                )
                response = await asyncio.to_thread(model.generate_content, prompt)
                if hasattr(response, "text") and response.text:
                    return response.text.strip()
            except Exception as e:
                print(f"    [!] Gemini {model_name} falhou: {e}")
            self.current_idx = (self.current_idx + 1) % len(self.model_names)
        return json.dumps({"error": "Gemini Providers failed"})


# ── DeepSeek ───────────────────────────────────────────────────────────────────
class DeepSeekProvider(BaseAIProvider):
    def __init__(self, api_key):
        self.api_key  = api_key
        self.base_url = "https://api.deepseek.com"

    async def analyze(self, snapshot: dict) -> str:
        import aiohttp
        prompt = self._prepare_prompt(snapshot)
        print("    [*] [DeepSeek] Iniciando análise...")
        try:
            async with aiohttp.ClientSession() as session:
                payload = {
                    "model": "deepseek-chat",
                    "messages": [
                        {
                            "role": "system",
                            "content": (
                                "Você é um analista expert em Smart Money e fluxo institucional de apostas esportivas. "
                                "Responda SOMENTE com o JSON solicitado, sem nenhum texto adicional fora das chaves."
                            )
                        },
                        {"role": "user", "content": prompt},
                    ],
                    "stream": False,
                    "temperature": 0.2,
                }
                headers = {
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                }
                async with session.post(
                    f"{self.base_url}/chat/completions",
                    json=payload,
                    headers=headers,
                    timeout=aiohttp.ClientTimeout(total=30),
                ) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        return data["choices"][0]["message"]["content"].strip()
                    else:
                        error_text = await resp.text()
                        print(f"    [!] Erro DeepSeek API: {resp.status} → {error_text}")
        except Exception as e:
            print(f"    [!] Falha na conexão com DeepSeek: {e}")
        return json.dumps({"error": "DeepSeek analysis failed"})


# ── Claude (stub) ──────────────────────────────────────────────────────────────
class ClaudeProvider(BaseAIProvider):
    async def analyze(self, snapshot: dict) -> str:
        return json.dumps({
            "category": "#KAIROS_ANALYSIS",
            "verdict": "NOISE",
            "risk": "Alto",
            "confidence": 1,
            "reasoning": "Claude Provider não configurado. Configure ANTHROPIC_API_KEY.",
            "betting_tip": "N/A",
            "suggested_odd": "N/A",
            "stake_suggestion": "Mínimo",
            "alert_headline": "Provider Claude sem configuração",
        })


# ── KairosAnalyzer (interface pública) ─────────────────────────────────────────
class KairosAnalyzer:
    def __init__(self, api_key, provider_type="gemini"):
        self.providers = {
            "gemini":   GeminiProvider(api_key),
            "deepseek": DeepSeekProvider(api_key),
            "claude":   ClaudeProvider(),
        }
        self.provider = self.providers.get(provider_type, self.providers["gemini"])
        print(f"[*] Analisador iniciado com provedor: {provider_type.upper()}")

    def set_deepseek_key(self, key):
        if "deepseek" in self.providers:
            self.providers["deepseek"].api_key = key

    async def analyze_cross_market(self, snapshot: dict) -> str:
        return await self.provider.analyze(snapshot)
