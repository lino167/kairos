import google.generativeai as genai
import asyncio
import json
from abc import ABC, abstractmethod

class BaseAIProvider(ABC):
    @abstractmethod
    async def analyze(self, snapshot: dict) -> str:
        pass

    def _prepare_prompt(self, snapshot: dict) -> str:
        # --- Contexto Excapper (Money Flow) ---
        primary = snapshot.get("primary_anomaly", {})
        flow_str = f"DETALHE DO FLUXO:\n  • Mercado: {primary.get('market')} | Seleção: {primary.get('selection')}\n"
        flow_str += f"  • Anomalia: {primary.get('reason')}\n"
        flow_str += f"  • Link Betfair: {primary.get('bf_url')}\n"

        # --- Contexto SokkerPro (Live Stats) ---
        sp_live = snapshot.get("sokkerpro_live", {})
        sp_str = "DADOS DE CAMPO (SOKKERPRO LIVE):\n"
        if sp_live:
            sp_str += f"  • Pressão 5m: {sp_live['appm_5m']['home']} (Casa) vs {sp_live['appm_5m']['away']} (Fora)\n"
            sp_str += f"  • Pressão 10m: {sp_live['appm_10m']['home']} (Casa) vs {sp_live['appm_10m']['away']} (Fora)\n"
            sp_str += f"  • AP (Ataques Perigosos): {sp_live['ataques_perigosos']['home']} vs {sp_live['ataques_perigosos']['away']}\n"
            sp_str += f"  • Posse: {sp_live['posse']['home']}% vs {sp_live['posse']['away']}%\n"
        else:
            sp_str += "  • Dados de tempo real indisponíveis.\n"

        # --- Contexto SokkerPro (Pre-Live) ---
        sp_pre = snapshot.get("sokkerpro_pre", {})
        pre_str = "MÉDIAS PRÉ-JOGO:\n"
        if sp_pre:
            pre_str += f"  • Gols: {sp_pre.get('avg_goals', 'N/A')}\n"
            pre_str += f"  • Cantos: {sp_pre.get('avg_corners', 'N/A')}\n"

        # --- Contexto Estratégico (Oceano vs Divergência) ---
        strat = snapshot.get("strategic_context", {})
        liquidity = "OCÉANO (Alta Liquidez)" if strat.get("is_ocean") else "PISCINA (Baixa Liquidez)"
        divergence = "SIM (CONTRADIÇÃO)" if strat.get("is_divergence") else "NÃO (CONFIRMAÇÃO)"
        manipulation = ", ".join(strat.get("manipulation_labels", [])) or "Nenhum sinal claro"

        strat_str = f"CONTEXTO ESTRATÉGICO:\n"
        strat_str += f"  • Liquidez: {liquidity}\n"
        strat_str += f"  • Divergência entre Fluxo e Campo: {divergence}\n"
        strat_str += f"  • SINAIS TÉCNICOS/MANIPULAÇÃO: {manipulation}\n"

        return (
            f"Você é o KAIROS, um Analista Profissional de Movimentação Financeira Institucional de futebol (Smart Money).\n"
            f"Sua missão é identificar se uma anomalia de mercado é 'Institutional Flow' (grandes sindicatos) ou 'Sharp Info' (informação privilegiada).\n\n"
            f"JOGO: {snapshot['match_name']}\n"
            f"PLACAR: {snapshot['live_score']}\n\n"
            f"{strat_str}\n"
            f"{flow_str}\n"
            f"{sp_str}\n"
            f"{pre_str}\n\n"
            f"REGRAS DE ANÁLISE PROFISSIONAL:\n"
            f"1. VISÃO INSTITUCIONAL: No OCÉANO, movimentos de 5-8% com volumes >€50k são orquestrados por sindicatos. Valide se a estatística apóia ou se o mercado antecipa algo.\n"
            f"2. VISÃO DE MANIPULAÇÃO: Na PISCINA, busque por 'Informação Privilegiada' (drops sem motivo técnico).\n"
            f"3. DIVERGÊNCIA CROSS-MARKET: Se o preço do O/U e BTTS estiverem descorrelacionados, exponha o erro de precificação.\n"
            f"4. OVERREACTION FLUX: Identifique se o dinheiro institucional está 'corrigindo' um movimento exagerado do varejo após um gol ou cartão.\n\n"
            f"SAÍDA OBRIGATÓRIA EM JSON ESTRITO (Sem markdown extra):\n"
            f"{{\n"
            f"  \"category\": \"#KAIROS_INSTITUTIONAL\",\n"
            f"  \"confidence\": \"1-10\",\n"
            f"  \"reasoning\": \"Explicação curta e clara (max 500 caracteres) do porquê desta entrada.\",\n"
            f"  \"betting_tip\": \"ENTRADA DIRETA (Ex: BACK OVER 2.5 / LAY HOME)\",\n"
            f"  \"suggested_odd\": \"Odd mínima/ideal para entrar\"\n"
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
