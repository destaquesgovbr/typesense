#!/usr/bin/env python3
"""
CLI para carregar dados do govbrnews no Typesense.

Este script baixa o dataset govbrnews do HuggingFace e indexa no Typesense.

Usage:
    # Carga completa (todos os dados)
    python scripts/load_data.py --mode full

    # Carga incremental (últimos 7 dias)
    python scripts/load_data.py --mode incremental --days 7

    # Carga completa forçada (sobrescreve dados existentes)
    python scripts/load_data.py --mode full --force
"""

import argparse
import logging
import sys

from dotenv import load_dotenv

# Carrega variáveis de ambiente do .env
load_dotenv()

# Configuração de logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

from typesense_dgb import (
    create_collection,
    download_and_process_dataset,
    index_documents,
    wait_for_typesense,
)
from typesense_dgb.indexer import run_test_queries


def parse_arguments() -> argparse.Namespace:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="Carrega dataset govbrnews no Typesense",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Exemplos:
  # Carga completa (só funciona em coleção vazia)
  python load_data.py --mode full

  # Carga completa forçada (sobrescreve dados existentes)
  python load_data.py --mode full --force

  # Carga incremental (últimos 7 dias)
  python load_data.py --mode incremental --days 7

  # Carga incremental (últimos 30 dias)
  python load_data.py --mode incremental --days 30
        """,
    )

    parser.add_argument(
        "--mode",
        type=str,
        choices=["full", "incremental"],
        default="full",
        help='Modo de carga: "full" carrega tudo, "incremental" carrega dados recentes (default: full)',
    )

    parser.add_argument(
        "--days",
        type=int,
        default=7,
        help="Número de dias para olhar para trás no modo incremental (default: 7)",
    )

    parser.add_argument(
        "--force",
        action="store_true",
        help="Força modo full em coleções não vazias (use com cuidado!)",
    )

    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Limita número de registros (útil para testes rápidos)",
    )

    return parser.parse_args()


def main() -> None:
    """Main function."""
    try:
        args = parse_arguments()

        logger.info("=" * 80)
        logger.info("Iniciando carregamento de dados GovBR News no Typesense")
        logger.info(f"Modo: {args.mode}")
        if args.mode == "incremental":
            logger.info(f"Janela de tempo: Últimos {args.days} dias")
        if args.limit:
            logger.info(f"Limite de registros: {args.limit}")
        logger.info("=" * 80)

        # Aguarda Typesense ficar pronto
        client = wait_for_typesense()
        if not client:
            logger.error("Não foi possível conectar ao Typesense")
            sys.exit(1)

        # Cria coleção
        create_collection(client)

        # Baixa e processa dataset
        df = download_and_process_dataset(mode=args.mode, days=args.days, limit=args.limit)

        # Indexa documentos
        index_documents(client, df, mode=args.mode, force=args.force)

        # Executa consultas de teste
        run_test_queries(client)

        logger.info("=" * 80)
        logger.info("Carregamento de dados concluído com sucesso!")
        logger.info("=" * 80)

    except Exception as e:
        logger.error(f"Falha no carregamento de dados: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
