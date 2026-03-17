import google.generativeai as genai
import asyncio
import json
from abc import ABC, abstractmethod

class BaseAIProvider(ABC):
    @abstractmethod
    async def analyze(self, snapshot: dict) -> str:
        pass

    def _prepare_prompt(self, snapshot: dict) -> str:
        # --- Contexto do Jogo ---
        is_live = snapshot.get("is_live", False)
        status = "LIVE 🔴" if is_live else "PRE-LIVE 🔵"
        
        # --- Contexto Excapper (Cross-Market Flow) ---
        primary = snapshot.get("primary_anomaly", {})
        all_anomalies = snapshot.get("all_anomalies", [])
        
        flow_str = f"DETALHE DO FLUXO PRINCIPAL:\n  • Mercado: {primary.get('market')} | Seleção: {primary.get('selection')}\n"
        flow_str += f"  • Anomalia: {primary.get('reason')}\n"
        
        if len(all_anomalies) > 1:
            flow_str += "CROSS-MARKET (Outras anomalias no mesmo jogo):\n"
            for anom in all_anomalies:
                if anom['short_id'] != primary['short_id']:
                    flow_str += f"  • {anom['market']} ({anom['selection']}): {anom['reason']}\n"

        # --- Contexto SokkerPro (Live Stats) ---
        sp_live = snapshot.get("sokkerpro_live", {})
        sp_str = "DADOS DE CAMPO (SOKKERPRO LIVE):\n"
        if is_live and sp_live:
            sp_str += f"  • Pressão 5m: {sp_live['appm_5m']['home']} (Casa) vs {sp_live['appm_5m']['away']} (Fora)\n"
            sp_str += f"  • Pressão 10m: {sp_live['appm_10m']['home']} (Casa) vs {sp_live['appm_10m']['away']} (Fora)\n"
            sp_str += f"  • AP (Ataques Perigosos): {sp_live['ataques_perigosos']['home']} vs {sp_live['ataques_perigosos']['away']}\n"
            sp_str += f"  • Posse: {sp_live['posse']['home']}% vs {sp_live['posse']['away']}%\n"
        elif is_live:
            sp_str += "  • Dados de tempo real indisponíveis no momento.\n"
        else:
            sp_str += "  • [JOGO PRÉ-LIVE] Estátisticas de campo não aplicáveis ainda.\n"

        # --- Contexto SokkerPro (Pre-Live/Histórico) ---
        sp_pre = snapshot.get("sokkerpro_pre", {})
        pre_str = "MÉDIAS HISTÓRICAS (PRE-LIVE):\n"
        if sp_pre:
            pre_str += f"  • Média Geral Gols: {sp_pre.get('avg_goals', 'N/A')}\n"
            pre_str += f"  • Média Cantos (H2H): {sp_pre.get('avg_corners', 'N/A')}\n"

        # --- Contexto Estratégico ---
        strat = snapshot.get("strategic_context", {})
        liquidity = "OCÉANO (Alta Liquidez)" if strat.get("is_ocean") else "PISCINA (Baixa Liquidez)"
        divergence = "SIM (CONTRADIÇÃO)" if strat.get("is_divergence") else "NÃO (CONFIRMAÇÃO)"
        manipulation = ", ".join(strat.get("manipulation_labels", [])) or "Nenhum sinal claro"

        strat_str = f"CONTEXTO ESTRATÉGICO:\n"
        strat_str += f"  • Liquidez: {liquidity}\n"
        strat_str += f"  • Divergência Fluxo vs Campo: {divergence}\n"
        strat_str += f"  • SINAIS TÉCNICOS: {manipulation}\n"

        return (
            f"Você é o KAIROS, um Analista Expert em 'Smart Money' e Fluxo Institucional da Betfair.\n"
            f"Sua missão é validar se a anomalia financeira detectada é um movimento real de 'Dinheiro Inteligente' ou apenas ruído de mercado.\n\n"
            f"JOGO: {snapshot['match_name']}\n"
            f"STATUS: {status}\n"
            f"PLACAR ATUAL: {snapshot['live_score']}\n\n"
            f"{strat_str}\n"
            f"{flow_str}\n"
            f"{sp_str}\n"
            f"{pre_str}\n"
            f"MISSÃO DE ANÁLISE:\n"
            f"1. ANALISE A CORRELAÇÃO: O volume no mercado principal faz sentido com as outras anomalias (anomalias cruzadas)?\n"
            f"2. LIVE VS DATA: Se LIVE, a pressão (APPM) justifica a queda da odd? Se PRE-LIVE, o 'drop' é puramente financeiro/info privilegiada?\n"
            f"3. VEREDITO: Identifique 'Institutional Flow' (sindicatos no Oceano) ou 'Sharp Action' (insiders na Piscina).\n\n"
            f"SAÍDA OBRIGATÓRIA EM JSON ESTRITO:\n"
            f"{{\n"
            f"  \"category\": \"#KAIROS_ANALYSIS\",\n"
            f"  \"risk\": \"Baixo/Médio/Alto\",\n"
            f"  \"confidence\": \"1-10\",\n"
            f"  \"reasoning\": \"Raciocínio profissional e técnico (Max 600 caracteres). Comece direto no ponto, focando no 'Ajuste Brutal' ou anomalia detectada.\",\n"
            f"  \"betting_tip\": \"AÇÃO (Ex: Kastamonuspor AH +0.5 / BACK OVER 1.5)\",\n"
            f"  \"suggested_odd\": \"Odd mínima ou cenário (Ex: @ Live / @ 1.80)\"\n"
            f"}}"
        )

class GeminiProvider(BaseAIProvider):
    def __init__(self, api_key):
        genai.configure(api_key=api_key)
        # Modelos detectados como disponiveis no ambiente do usuario
        self.model_names = ['models/gemini-flash-latest', 'models/gemini-2.0-flash', 'models/gemini-pro-latest']
        self.current_idx = 0

    async def analyze(self, snapshot: dict) -> str:
        prompt = self._prepare_prompt(snapshot)

        for _ in range(len(self.model_names)):
            model_name = self.model_names[self.current_idx]
            try:
                print(f"    [*] [Gemini] Tentando com {model_name}...")
                model = genai.GenerativeModel(model_name)
                response = await asyncio.to_thread(model.generate_content, prompt)

                if hasattr(response, 'text') and response.text:
                    return response.text.strip()
            except Exception as e:
                print(f"    [!] Gemini {model_name} falhou: {e}")

            self.current_idx = (self.current_idx + 1) % len(self.model_names)

        return json.dumps({"error": "Gemini Providers failed"})

class DeepSeekProvider(BaseAIProvider):
    def __init__(self, api_key):
        self.api_key = api_key
        self.base_url = "https://api.deepseek.com"

    async def analyze(self, snapshot: dict) -> str:
        import aiohttp
        prompt = self._prepare_prompt(snapshot)

        print(f"    [*] [DeepSeek] Iniciando análise...")
        try:
            async with aiohttp.ClientSession() as session:
                payload = {
                    "model": "deepseek-chat",
                    "messages": [
                        {"role": "system", "content": "Você é um analista técnico de apostas."},
                        {"role": "user", "content": prompt}
                    ],
                    "stream": False
                }
                headers = {
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json"
                }
                async with session.post(f"{self.base_url}/chat/completions", json=payload, headers=headers) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        return data['choices'][0]['message']['content'].strip()
                    else:
                        error_text = await resp.text()
                        print(f"    [!] Erro DeepSeek API: {resp.status} - {error_text}")
        except Exception as e:
            print(f"    [!] Falha na conexão com DeepSeek: {e}")

        return json.dumps({"error": "DeepSeek analysis failed"})

class ClaudeProvider(BaseAIProvider):
    async def analyze(self, snapshot: dict) -> str:
        # Stub para futura implementação
        return json.dumps({"technical_insight": "Claude Provider não configurado (API Key ausente).", "betting_tip": "N/A", "danger_level": "Alto"})

class KairosAnalyzer:
    def __init__(self, api_key, provider_type="gemini"):
        self.providers = {
            "gemini": GeminiProvider(api_key),
            "deepseek": DeepSeekProvider(api_key), # Reutiliza a chave se for informada
            "claude": ClaudeProvider()
        }
        self.provider = self.providers.get(provider_type, self.providers["gemini"])
        print(f"[*] Analisador iniciado com provedor: {provider_type.upper()}")

    def set_deepseek_key(self, key):
        if "deepseek" in self.providers:
            self.providers["deepseek"].api_key = key

    async def analyze_cross_market(self, snapshot):
        return await self.provider.analyze(snapshot)
