"""
Download e processamento do dataset govbrnews.
"""

import logging
from datetime import datetime, timedelta, timezone

import pandas as pd
from datasets import load_dataset

from typesense_dgb.utils import calculate_published_week

logger = logging.getLogger(__name__)

DATASET_PATH = "nitaibezerra/govbrnews"


def download_and_process_dataset(
    mode: str = "full",
    days: int = 7,
    dataset_path: str = DATASET_PATH,
    limit: int | None = None,
) -> pd.DataFrame:
    """
    Baixa o dataset do HuggingFace e converte para pandas DataFrame.

    Args:
        mode: 'full' para dataset completo ou 'incremental' para dados recentes
        days: Número de dias para olhar para trás no modo incremental (default: 7)
        dataset_path: Caminho do dataset no HuggingFace
        limit: Limita número de registros (útil para testes rápidos)

    Returns:
        DataFrame processado com colunas adicionais para indexação

    Raises:
        Exception: Se ocorrer erro no download ou processamento
    """
    try:
        logger.info(f"Baixando dataset govbrnews do HuggingFace (modo: {mode})...")
        dataset = load_dataset(dataset_path, split="train")
        logger.info(f"Dataset baixado com sucesso. Total de registros: {len(dataset)}")

        # Converte para pandas DataFrame
        df = dataset.to_pandas()

        # Limita registros se especificado (útil para testes)
        if limit is not None and limit > 0:
            logger.info(f"Limitando a {limit} registros para teste...")
            df = df.head(limit)

        # Converte published_at e extracted_at para datetime
        df["published_at"] = pd.to_datetime(df["published_at"], errors="coerce")
        df["extracted_at"] = pd.to_datetime(df["extracted_at"], errors="coerce")

        # Filtra para modo incremental
        if mode == "incremental":
            # Usa datetime com timezone (Brasília UTC-3)
            cutoff_date = datetime.now(timezone(timedelta(hours=-3))) - timedelta(
                days=days
            )
            initial_count = len(df)
            df = df[df["published_at"] >= cutoff_date]
            logger.info(f"Modo incremental: Filtrando dados dos últimos {days} dias")
            logger.info(f"Data de corte: {cutoff_date.strftime('%Y-%m-%d %H:%M:%S')}")
            logger.info(
                f"Registros após filtro: {len(df)} (removidos {initial_count - len(df)} registros antigos)"
            )

            if len(df) == 0:
                logger.warning(
                    f"Nenhum registro encontrado nos últimos {days} dias. Nada a processar."
                )
                return df

        # Extrai ano e mês para faceting
        df["published_year"] = df["published_at"].dt.year
        df["published_month"] = df["published_at"].dt.month

        # Converte datetime para Unix timestamp (segundos) para Typesense
        df["published_at_ts"] = df["published_at"].apply(
            lambda x: int(x.timestamp()) if pd.notna(x) else 0
        )
        df["extracted_at_ts"] = df["extracted_at"].apply(
            lambda x: int(x.timestamp()) if pd.notna(x) else 0
        )

        # Calcula semana ISO 8601 (formato YYYYWW)
        logger.info("Calculando semanas ISO 8601 para otimização temporal...")
        df["published_week"] = df["published_at_ts"].apply(calculate_published_week)

        # Log de estatísticas
        valid_weeks = df["published_week"].notna().sum()
        logger.info(
            f"Semana de publicação calculada para {valid_weeks}/{len(df)} registros"
        )

        logger.info("Dataset processado com sucesso")
        return df

    except Exception as e:
        logger.error(f"Erro ao baixar/processar dataset: {e}")
        raise
