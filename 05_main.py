"""Script principal de demonstração do MVP de calibração (Schulz S.A.).

Entrega 03 (AV03) do Projeto Aplicado I. Executa o fluxo funcional completo:

1. recria o banco SQLite a partir de ``03_banco.sql``;
2. cadastra técnico, equipamento e padrão de medição;
3. registra três medições — uma aprovada exatamente no limite, uma reprovada
   e uma com campo obrigatório ausente, que gera pendência;
4. executa a consulta relacional com JOIN de 4 tabelas;
5. imprime o relatório de calibração no terminal;
6. demonstra a recusa de aprovação de uma medição com pendência em aberto
   (RN13) e a aprovação de uma medição sem pendências.

Uso:
    python 05_main.py
    python 05_main.py --banco outro.db
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent
sys.path.insert(0, str(RAIZ))

from schulz_mvp import relatorio  # noqa: E402
from schulz_mvp._loader import carregar_modulo  # noqa: E402

#: ``04_classes`` não pode ser importado com a instrução ``import`` porque o
#: nome começa com dígito. O carregador resolve isso por caminho.
classes = carregar_modulo("04_classes")


def semear(servico) -> None:
    """Cadastra os dados de demonstração.

    As três medições cobrem os caminhos relevantes do MVP: aprovação no
    limite exato, reprovação por desvio e pendência por dado ausente.
    """
    id_tecnico = servico.registrar_tecnico(
        classes.Tecnico(nome="João da Silva", matricula="TEC001", setor="Metrologia")
    )
    id_equipamento = servico.registrar_equipamento(
        classes.Equipamento(
            codigo_tag="MMC001",
            descricao="Máquina de Medição por Coordenadas",
            fabricante="Schulz",
            modelo="MMC-01",
            numero_serie="SN000001",
        )
    )
    id_padrao = servico.registrar_padrao(
        classes.Padrao(
            codigo="PAD001",
            modelo="Bloco-padrão 50 mm",
            fabricante="Schulz",
            numero_serie="BS000050",
            ultima_calibracao="2026-01-15",
            proxima_calibracao="2027-01-15",
            certificado_padrao="CERTPAD2026001",
        )
    )

    # Medição 1 — aprovada exatamente sobre o limite superior.
    servico.registrar_medicao(
        classes.Medicao(
            id_tecnico=id_tecnico,
            id_equipamento=id_equipamento,
            id_padrao=id_padrao,
            ordem_servico="OS2026001",
            plano_medicao="PM001",
            data_medicao="2026-10-04",
            hora_medicao="14:30:00",
            desenho="DES001",
            peca="PCA001",
            caracteristica="Diâmetro",
            valor_nominal=50.00,
            tol_inferior=-0.05,
            tol_superior=0.05,
            medida_1=50.02,
            medida_2=50.01,
            valor_obtido=50.05,
            unidade="mm",
        )
    )

    # Medição 2 — reprovada: desvio de 0.12 mm sobre tolerância de 0.10 mm.
    servico.registrar_medicao(
        classes.Medicao(
            id_tecnico=id_tecnico,
            id_equipamento=id_equipamento,
            id_padrao=id_padrao,
            ordem_servico="OS2026001",
            plano_medicao="PM001",
            data_medicao="2026-10-04",
            hora_medicao="14:30:00",
            desenho="DES001",
            peca="PCA002",
            caracteristica="Comprimento",
            valor_nominal=100.00,
            tol_inferior=-0.10,
            tol_superior=0.10,
            medida_1=100.12,
            medida_2=100.11,
            valor_obtido=100.115,
            unidade="mm",
        )
    )

    # Medição 3 — dado obrigatório ausente: gera pendência e bloqueia a
    # aprovação (RN13/RN19).
    id_terceira = servico.registrar_medicao(
        classes.Medicao(
            id_tecnico=id_tecnico,
            id_equipamento=id_equipamento,
            ordem_servico="OS2026002",
            plano_medicao="PM002",
            data_medicao="2026-10-05",
            hora_medicao="09:15:00",
            desenho="DES002",
            peca="PCA003",
            caracteristica="Rugosidade",
            valor_nominal=1.60,
            tol_inferior=-0.20,
            tol_superior=0.20,
            valor_obtido=1.55,
            unidade="um",
        )
    )
    servico.registrar_pendencia(
        campo="padrao",
        descricao=(
            "Medição sem padrão de referência vinculado — rastreabilidade "
            "metrológica não pode ser evidenciada (RN18)."
        ),
        criticidade="ALTA",
        id_medicao=id_terceira,
        id_tecnico=id_tecnico,
    )
    return id_terceira


def main() -> int:
    """Executa a demonstração completa."""
    analisador = argparse.ArgumentParser(
        description="Demonstração do MVP de calibração — Schulz S.A. (AV03)"
    )
    analisador.add_argument(
        "--banco",
        default=str(RAIZ / "calibracao.db"),
        help="Caminho do arquivo SQLite (padrão: calibracao.db na raiz do projeto)",
    )
    argumentos = analisador.parse_args()

    caminho_banco = Path(argumentos.banco)
    if caminho_banco.exists():
        caminho_banco.unlink()

    print("=" * 78)
    print("PROJETO APLICADO I - SCHULZ S.A. - ENTREGA 03 (AV03)")
    print("MVP Parte 1: POO + persistencia SQLite + regras metrologicas")
    print("=" * 78)

    with classes.ConexaoSQLite(caminho_banco, criar_schema=True) as conexao:
        servico = classes.ServicoCalibracao(conexao)

        print("\n[1/6] Cadastros e medicoes de demonstracao...")
        id_com_pendencia = semear(servico)

        print("[2/6] Consulta relacional (JOIN de 4 tabelas)...")
        registros = servico.consultar_relatorio()

        print("[3/6] Relatorio de calibracao no terminal...")
        relatorio.imprimir_relatorio(registros)

        print("\n[4/6] Quantidade de medicoes por tecnico...")
        for linha in servico.medicoes.contar_por_tecnico():
            print(f"  {linha['tecnico']}: {linha['quantidade_medicoes']} medicao(oes)")

        print("\n[5/6] Aprovacao tecnica:")
        print("  Medicao 1 -> aprovando...")
        aprovada = servico.aprovar_medicao(
            id_medicao=1, usuario="João da Silva", certificado_numero="CERT2026001"
        )
        print(f"  Situacao: {aprovada.status_resultado()}, "
              f"certificado {aprovada.certificado_numero}, "
              f"aprovado por {aprovada.usuario_aprovacao}")

        print(f"  Medicao {id_com_pendencia} -> tentando aprovar...")
        try:
            servico.aprovar_medicao(
                id_medicao=id_com_pendencia,
                usuario="João da Silva",
                certificado_numero="CERT2026002",
            )
            print("  ERRO: a aprovacao deveria ter sido recusada.")
            return 1
        except classes.PendenciaAbertaError as erro:
            print(f"  Recusada corretamente (RN13): {erro}")

        print("\n[6/6] Pendencias em aberto:")
        for pendencia in servico.pendencias.listar_abertas():
            print(f"  [{pendencia['criticidade']}] {pendencia['campo']}: "
                  f"{pendencia['descricao']}")

        print("\nHistorico de acoes:")
        for linha in servico.historico.listar_todos():
            print(f"  {linha['data_hora']}  {linha['acao']:<24} {linha['detalhe'] or ''}")

        relatorio.imprimir_resumo(servico.resumo())

    print(f"\nBanco SQLite gerado em: {caminho_banco}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
