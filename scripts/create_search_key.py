#!/usr/bin/env python3
"""
CLI para criar uma API key scoped para busca no Typesense.

Esta key só permite operações de busca (documents:search) e é segura
para ser exposta no frontend ou compartilhada com desenvolvedores.

Usage:
    # Criar key com descrição padrão
    python scripts/create_search_key.py

    # Criar key com descrição customizada
    python scripts/create_search_key.py --description "Key para portal prod"

    # Listar keys existentes
    python scripts/create_search_key.py --list

    # Deletar uma key existente
    python scripts/create_search_key.py --delete <key_id>
"""

import argparse
import json
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

from typesense_dgb import get_client


def parse_arguments() -> argparse.Namespace:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="Cria uma API key scoped para busca no Typesense",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Exemplos:
  # Criar key com descrição padrão
  python create_search_key.py

  # Criar key com descrição customizada
  python create_search_key.py --description "Key para portal prod"

  # Listar keys existentes
  python create_search_key.py --list

  # Deletar uma key
  python create_search_key.py --delete 1
        """,
    )

    parser.add_argument(
        "--description",
        type=str,
        default="Search-only key for portal and developers",
        help="Descrição da key (default: 'Search-only key for portal and developers')",
    )

    parser.add_argument(
        "--collections",
        type=str,
        default="*",
        help="Coleções permitidas, separadas por vírgula (default: '*' para todas)",
    )

    parser.add_argument(
        "--list",
        action="store_true",
        help="Lista todas as API keys existentes",
    )

    parser.add_argument(
        "--delete",
        type=int,
        metavar="KEY_ID",
        help="Deleta uma API key pelo ID",
    )

    parser.add_argument(
        "--json",
        action="store_true",
        help="Saída em formato JSON (útil para automação)",
    )

    return parser.parse_args()


def list_keys(client, json_output: bool = False) -> None:
    """Lista todas as API keys existentes."""
    try:
        keys = client.keys.retrieve()

        if json_output:
            print(json.dumps(keys, indent=2))
            return

        if not keys.get("keys"):
            logger.info("Nenhuma API key encontrada")
            return

        logger.info("API Keys existentes:")
        logger.info("-" * 80)
        for key in keys["keys"]:
            logger.info(f"  ID: {key['id']}")
            logger.info(f"  Descrição: {key.get('description', 'N/A')}")
            logger.info(f"  Ações: {key.get('actions', [])}")
            logger.info(f"  Coleções: {key.get('collections', [])}")
            logger.info(f"  Prefixo: {key.get('value_prefix', 'N/A')}...")
            logger.info("-" * 80)

    except Exception as e:
        logger.error(f"Erro ao listar keys: {e}")
        sys.exit(1)


def delete_key(client, key_id: int) -> None:
    """Deleta uma API key pelo ID."""
    try:
        client.keys[key_id].delete()
        logger.info(f"Key {key_id} deletada com sucesso")
    except Exception as e:
        logger.error(f"Erro ao deletar key {key_id}: {e}")
        sys.exit(1)


def create_search_key(
    client,
    description: str,
    collections: str,
    json_output: bool = False,
) -> None:
    """Cria uma API key scoped para busca."""
    try:
        # Parse collections
        collections_list = [c.strip() for c in collections.split(",")]

        key_schema = {
            "description": description,
            "actions": ["documents:search"],
            "collections": collections_list,
        }

        logger.info("Criando API key com as seguintes configurações:")
        logger.info(f"  Descrição: {description}")
        logger.info(f"  Ações: ['documents:search']")
        logger.info(f"  Coleções: {collections_list}")

        key = client.keys.create(key_schema)

        if json_output:
            print(json.dumps(key, indent=2))
            return

        logger.info("=" * 80)
        logger.info("API Key criada com sucesso!")
        logger.info("=" * 80)
        logger.info(f"  ID: {key['id']}")
        logger.info(f"  Descrição: {key['description']}")
        logger.info(f"  Valor: {key['value']}")
        logger.info("=" * 80)
        logger.info("")
        logger.info("IMPORTANTE: Guarde o valor da key acima!")
        logger.info("Ele não poderá ser recuperado depois.")
        logger.info("")
        logger.info("Use esta key para o secret typesense-read-conn:")
        logger.info("")
        print(f'  {{"host":"<HOST>","port":8108,"protocol":"http","apiKey":"{key["value"]}"}}')
        logger.info("")

    except Exception as e:
        logger.error(f"Erro ao criar key: {e}")
        sys.exit(1)


def main() -> None:
    """Main function."""
    try:
        args = parse_arguments()

        client = get_client()

        if args.list:
            list_keys(client, args.json)
            return

        if args.delete is not None:
            delete_key(client, args.delete)
            return

        logger.info("=" * 80)
        logger.info("Criação de API Key Scoped para Busca")
        logger.info("=" * 80)

        create_search_key(
            client,
            args.description,
            args.collections,
            args.json,
        )

    except KeyboardInterrupt:
        logger.info("\nOperação cancelada pelo usuário")
        sys.exit(1)
    except Exception as e:
        logger.error(f"Erro inesperado: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
