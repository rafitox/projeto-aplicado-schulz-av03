"""Carregamento de módulos cujo nome de arquivo começa com dígito.

O roteiro da AV03 exige os arquivos ``04_classes.py`` e ``05_main.py``. Um
nome que começa com dígito não é um identificador Python válido, então
``import 04_classes`` é um ``SyntaxError`` e a instrução ``import`` não
resolve.

Este módulo resolve o impasse carregando o arquivo por caminho com
``importlib.util.spec_from_file_location`` e registrando o módulo em
``sys.modules`` **antes** de executá-lo — o registro prévio é necessário
porque ``dataclass`` e as anotações de tipo resolvem o módulo de origem da
classe por esse dicionário durante a execução do arquivo.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

__all__ = ["RAIZ_PROJETO", "carregar_modulo"]

#: Raiz do projeto — a pasta que contém ``04_classes.py`` e ``05_main.py``.
RAIZ_PROJETO = Path(__file__).resolve().parent.parent


def carregar_modulo(nome_arquivo: str, raiz: Path | None = None) -> ModuleType:
    """Carrega um módulo Python a partir de um arquivo do projeto.

    Args:
        nome_arquivo: Nome do arquivo com extensão, por exemplo ``"04_classes"``.
        raiz: Pasta onde procurar o arquivo. Por padrão, a raiz do projeto.

    Returns:
        O módulo carregado e registrado em ``sys.modules``.

    Raises:
        FileNotFoundError: Se o arquivo não existir.
        ImportError: Se o arquivo não puder ser convertido em módulo.
    """
    base = Path(raiz) if raiz is not None else RAIZ_PROJETO
    caminho = base / f"{nome_arquivo}.py"

    if not caminho.is_file():
        raise FileNotFoundError(f"módulo não encontrado: {caminho}")

    especificacao = importlib.util.spec_from_file_location(nome_arquivo, caminho)
    if especificacao is None or especificacao.loader is None:
        raise ImportError(f"não foi possível carregar o módulo: {caminho}")

    modulo = importlib.util.module_from_spec(especificacao)
    # Precisa estar em sys.modules ANTES de exec_module: as annotations de
    # dataclass resolvem sys.modules[cls.__module__] durante a execução.
    sys.modules[nome_arquivo] = modulo
    try:
        especificacao.loader.exec_module(modulo)
    except Exception:
        sys.modules.pop(nome_arquivo, None)
        raise
    return modulo
