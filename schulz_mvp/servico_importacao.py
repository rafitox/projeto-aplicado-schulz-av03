"""Gravação do resultado do ETL no banco SQLite.

Este módulo é a ponte entre a extração da planilha e a persistência. Ele
traduz os :class:`~schulz_mvp.etl.RegistroMedicao` em entidades do domínio e
as grava por meio do :class:`ServicoCalibracao`.

Regras que esta camada aplica:

* **Idempotência (RN21)** — a chave ``(origem_hash, origem_linha)`` impede
  que a reimportação do mesmo arquivo duplique medições. A reimportação
  informa quantas linhas eram novas e quantas já existiam; não é um erro.
* **Transação única** — todas as gravações de uma importação acontecem
  juntas. Uma falha no meio do lote não deixa metade dos registros no banco.
* **Rastreabilidade (RN22)** — cada medição guarda o arquivo, a linha de
  origem e o bloco a que pertence.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Optional

from ._loader import carregar_modulo

__all__ = ["ResultadoGravacao", "ServicoImportacao", "UNIDADE_PADRAO"]

#: ``04_classes`` não é importável com a instrução ``import`` porque o nome
#: começa com dígito.
classes = carregar_modulo("04_classes")

#: Unidade usada quando a planilha não informa a unidade da medição.
UNIDADE_PADRAO = "mm"


@dataclass
class ResultadoGravacao:
    """Resumo do que foi gravado em uma importação."""

    medicoes_inseridas: int = 0
    medicoes_existentes: int = 0
    pendencias_inseridas: int = 0
    tecnicos_criados: int = 0
    equipamentos_criados: int = 0
    id_tecnico: Optional[int] = None
    id_equipamento: Optional[int] = None
    id_padrao: Optional[int] = None
    observacoes: list = field(default_factory=list)

    @property
    def total_processado(self) -> int:
        """Total de linhas vistas na importação."""
        return self.medicoes_inseridas + self.medicoes_existentes

    def as_dict(self) -> dict:
        """Converte o resultado em dicionário serializável."""
        return {
            "medicoes_inseridas": self.medicoes_inseridas,
            "medicoes_existentes": self.medicoes_existentes,
            "pendencias_inseridas": self.pendencias_inseridas,
            "tecnicos_criados": self.tecnicos_criados,
            "equipamentos_criados": self.equipamentos_criados,
            "total_processado": self.total_processado,
            "observacoes": list(self.observacoes),
        }


class ServicoImportacao:
    """Grava o resultado de uma importação no banco.

    Args:
        servico: Instância de :class:`ServicoCalibracao` já ligada a uma
            conexão aberta.
    """

    def __init__(self, servico: Any) -> None:
        self.servico = servico

    def gravar(self, resultado: Any) -> ResultadoGravacao:
        """Grava um resultado de importação.

        Args:
            resultado: Instância de
                :class:`~schulz_mvp.etl.ResultadoImportacao`.

        Returns:
            O resumo da gravação.
        """
        resumo = ResultadoGravacao()
        metadados = resultado.metadados

        id_tecnico = self._garantir_tecnico(metadados, resumo)
        id_equipamento = self._garantir_equipamento(metadados, resumo)

        resumo.id_tecnico = id_tecnico
        resumo.id_equipamento = id_equipamento

        if id_tecnico is None or id_equipamento is None:
            # Sem técnico ou equipamento não há como relacionar a medição
            # (RN02). As pendências abaixo explicam o motivo.
            resumo.observacoes.append(
                "Medições não gravadas: a planilha não informa o metrologista "
                "ou o código da MMC necessários para relacionar o registro."
            )
            self._gravar_pendencias(resultado, resumo, None)
            return resumo

        for registro in resultado.registros:
            if not registro.tem_dados_obrigatorios:
                # A pendência específica da linha já foi levantada no ETL.
                continue

            if self.servico.medicoes.ja_importado(
                resultado.hash_arquivo, registro.linha_origem
            ):
                resumo.medicoes_existentes += 1
                continue

            medicao = classes.Medicao(
                id_tecnico=id_tecnico,
                id_equipamento=id_equipamento,
                id_padrao=resumo.id_padrao,
                caracteristica=registro.caracteristica,
                valor_nominal=float(registro.valor_nominal),
                tol_inferior=float(registro.tol_inferior),
                tol_superior=float(registro.tol_superior),
                valor_obtido=float(registro.valor_obtido),
                unidade=UNIDADE_PADRAO,
                data_medicao=metadados.get("data_medicao"),
                ordem_servico=metadados.get("ordem_servico"),
                plano_medicao=metadados.get("plano_medicao"),
                hora_medicao=metadados.get("hora_medicao"),
                desenho=metadados.get("desenho"),
                peca=metadados.get("peca"),
                medida_1=float(registro.valor_obtido),
                bloco=registro.bloco,
                origem_arquivo=resultado.arquivo,
                origem_linha=registro.linha_origem,
                origem_hash=resultado.hash_arquivo,
            )
            self.servico.registrar_medicao(medicao)
            resumo.medicoes_inseridas += 1

        self._gravar_pendencias(resultado, resumo, id_tecnico)

        if resumo.medicoes_existentes:
            resumo.observacoes.append(
                f"{resumo.medicoes_existentes} medição(ões) já estavam "
                "importadas deste arquivo e não foram duplicadas."
            )
        return resumo

    # -- cadastros de apoio ------------------------------------------------

    def _garantir_tecnico(self, metadados: dict, resumo: ResultadoGravacao) -> Optional[int]:
        """Cria ou reutiliza o cadastro do metrologista."""
        nome = metadados.get("metrologista")
        if not nome:
            return None
        codigo = str(metadados.get("mmc") or nome).strip()
        existente = self.servico.tecnicos.buscar_por_codigo(codigo)
        if existente is not None:
            return existente.id_tecnico
        id_tecnico = self.servico.registrar_tecnico(
            classes.Tecnico(nome=nome, matricula=codigo, setor="Metrologia")
        )
        resumo.tecnicos_criados += 1
        return id_tecnico

    def _garantir_equipamento(
        self, metadados: dict, resumo: ResultadoGravacao
    ) -> Optional[int]:
        """Cria ou reutiliza o cadastro do equipamento (MMC)."""
        codigo = metadados.get("mmc")
        if not codigo:
            return None
        existente = self.servico.equipamentos.buscar_por_codigo(str(codigo))
        if existente is not None:
            return existente.id_equipamento
        id_equipamento = self.servico.registrar_equipamento(
            classes.Equipamento(
                codigo_tag=str(codigo),
                descricao=f"Máquina de Medição por Coordenadas {codigo}",
                fabricante="Schulz",
            )
        )
        resumo.equipamentos_criados += 1
        return id_equipamento

    # -- pendências --------------------------------------------------------

    def _gravar_pendencias(
        self, resultado: Any, resumo: ResultadoGravacao, id_tecnico: Optional[int]
    ) -> None:
        """Persiste as pendências detectadas na extração."""
        for pendencia in resultado.pendencias:
            self.servico.registrar_pendencia(
                campo=pendencia.campo,
                descricao=pendencia.descricao,
                criticidade=pendencia.criticidade,
                id_tecnico=id_tecnico,
                origem_arquivo=resultado.arquivo,
            )
            resumo.pendencias_inseridas += 1
