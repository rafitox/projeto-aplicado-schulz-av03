"""Ponto de entrada do webapp de calibração da Schulz S.A.

Entrega 03 (AV03) do Projeto Aplicado I. Sobe a aplicação Flask para
desenvolvimento local.

Uso:
    python 07_webapp.py
    python 07_webapp.py --port 8080 --banco outro.db

A aplicação escuta apenas em ``127.0.0.1`` (loopback) por padrão: um
sistema que recebe planilhas da empresa não deve ficar exposto na rede
sem autenticação, que está fora do escopo desta entrega (RNF01).
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent
sys.path.insert(0, str(RAIZ))

from schulz_mvp.webapp import criar_aplicacao  # noqa: E402


def main() -> int:
    """Sobe o webapp."""
    analisador = argparse.ArgumentParser(
        description="Webapp de calibração — Schulz S.A. (AV03)"
    )
    analisador.add_argument(
        "--port", type=int, default=5000, help="Porta HTTP (padrão: 5000)"
    )
    analisador.add_argument(
        "--host", default="127.0.0.1", help="Endereço de escuta (padrão: 127.0.0.1)"
    )
    analisador.add_argument(
        "--banco",
        default=str(RAIZ / "calibracao.db"),
        help="Caminho do arquivo SQLite (padrão: calibracao.db na raiz do projeto)",
    )
    analisador.add_argument(
        "--debug", action="store_true", help="Ativa o modo de depuração do Flask"
    )
    argumentos = analisador.parse_args()

    aplicacao = criar_aplicacao(argumentos.banco)

    print("=" * 70)
    print("MVP de Calibração — Schulz S.A. — Entrega 03 (AV03)")
    print("=" * 70)
    print(f"  Banco de dados : {argumentos.banco}")
    print(f"  Endereço       : http://{argumentos.host}:{argumentos.port}")
    print("  Encerrar       : Ctrl+C")
    print("=" * 70)

    aplicacao.run(
        host=argumentos.host,
        port=argumentos.port,
        debug=argumentos.debug,
        use_reloader=False,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
