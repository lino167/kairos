import json
import os
import requests

def load_json(filepath):
    """Carrega dados JSON com tratamento de erro."""
    if os.path.exists(filepath):
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {} if "alerts" in filepath else []
    return {} if "alerts" in filepath else []

def save_json(filepath, data):
    """Salva dados JSON de forma segura."""
    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4, ensure_ascii=False)

def send_telegram_alert(token, chat_id, message):
    """Envia alerta formatado para o Telegram."""
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {"chat_id": chat_id, "text": message, "parse_mode": "HTML"}
    try:
        response = requests.post(url, json=payload, timeout=12)
        if response.status_code != 200:
            print(f"    [!] Erro resposta Telegram ({response.status_code}): {response.text}")
        return response.status_code == 200
    except Exception as e:
        print(f"    [!] Erro crítico de conexão com Telegram: {e}")
        return False
