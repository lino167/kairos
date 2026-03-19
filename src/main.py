import asyncio
import sys
import argparse
from src.flows.dropping_flow import main as dropping_main
from src.flows.legacy_flow import main as legacy_main

async def run():
    parser = argparse.ArgumentParser(description="Kairos Intelligence Betting Bot")
    parser.add_argument(
        "--mode", 
        choices=["dropping", "legacy"], 
        default="dropping",
        help="Escolha o fluxo de monitoramento (default: dropping)"
    )
    
    args = parser.parse_args()
    
    if args.mode == "dropping":
        print("[*] Iniciando modo Monitoramento DroppingOdds (Recomendado)...")
        await dropping_main()
    else:
        print("[*] Iniciando modo Monitoramento Legado (Excapper + SokkerPro)...")
        await legacy_main()

if __name__ == "__main__":
    try:
        asyncio.run(run())
    except KeyboardInterrupt:
        print("\n[!] Encerrado pelo usuário.")
    except Exception as e:
        print(f"\n[!] Erro fatal: {e}")
