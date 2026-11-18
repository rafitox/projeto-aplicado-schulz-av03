"""Pacote do MVP de calibração da Schulz S.A. (Projeto Aplicado I — AV03).

Reúne as camadas que ficam **fora** do módulo ``04_classes.py``:

* ``_loader`` — carrega módulos com prefixo numérico (``04_classes``);
* ``leitor_planilha`` — leitura de planilhas Excel em memória de grade;
* ``etl`` — extração, transformação e validação dos dados de medição;
* ``servico_importacao`` — gravação do resultado do ETL no SQLite;
* ``relatorio`` — renderização do relatório de calibração no terminal;
* ``webapp`` — interface web Flask para upload de planilhas.

A dependência é unidirecional::

    webapp -> servico_importacao -> etl -> leitor_planilha -> 04_classes -> stdlib

``04_classes.py`` nunca importa este pacote, e ``etl.py`` nunca importa o
Flask: é isso que permite ao mesmo ETL rodar no Colab e no webapp.
"""

__all__ = ["__version__"]

__version__ = "0.1.0"
