"""
Service module for processing and managing Purchase Order (PO) data using pymssql and SQLAlchemy.

This module provides functionalities to:
- Read PO data from Excel or CSV files into Pandas DataFrames.
- Sanitize DataFrame column names for SQL compatibility.
- Create a standardized PO DataFrame based on column mappings.
- Map Pandas data types to SQL Server data types.
- Create a SQL table for PO data if it doesn't exist, based on a DataFrame's schema.
- Load a Pandas DataFrame containing PO data into the specified SQL table,
  handling 'append' or 'replace' strategies.

It uses SQLAlchemy with the pymssql dialect for bulk loading and pymssql for DDL operations.
Database utilities (connection, existence checks) come from `database_service`.
Configuration via env vars: SQL_SERVER_NAME, SQL_DATABASE_NAME, SQL_USERNAME, SQL_PASSWORD.
"""
import os
import pandas as pd
import logging
import re
from io import BytesIO
from sqlalchemy import create_engine
from sqlalchemy.exc import SQLAlchemyError
from urllib.parse import quote_plus
import pymssql
from shared_code.database_service import get_sql_connection

from . import database_service as general_db_service


def read_po_file_to_dataframe(file_bytes: bytes, filename: str) -> pd.DataFrame | None:
    """
    Reads PO data (CSV or Excel) into a DataFrame, sanitizing column names.
    """
    try:
        bio = BytesIO(file_bytes)
        if filename.lower().endswith('.csv'):
            df = pd.read_csv(bio, na_filter=False, dtype=str)
        elif filename.lower().endswith(('.xls', '.xlsx')):
            df = pd.read_excel(bio, na_filter=False, dtype=str)
        else:
            raise ValueError("Unsupported file type. Provide CSV or Excel.")
        original = list(df.columns)
        df.columns = [re.sub(r'\W+', '_', str(c)).strip('_') for c in df.columns]
        changes = [f"{o}->{n}" for o,n in zip(original, df.columns) if o!=n]
        if changes:
            logging.info(f"Sanitized PO columns: {', '.join(changes)}")
        return df
    except Exception as e:
        logging.error(f"Error reading PO file {filename}: {e}", exc_info=True)
        return None


def create_standardized_po_dataframe(df_original: pd.DataFrame, column_mappings: dict, target_schema_keys: list) -> pd.DataFrame | None:
    """
    Build standardized DataFrame with target_schema_keys using column_mappings.
    """
    if df_original is None:
        logging.warning("Original DataFrame is None.")
        return None
    if df_original.empty:
        return pd.DataFrame(columns=target_schema_keys)
    df_std = pd.DataFrame()
    for key in target_schema_keys:
        source = column_mappings.get(key)
        if source and source in df_original:
            df_std[key] = df_original[source]
        else:
            df_std[key] = pd.NA
            logging.info(f"Column {key} not mapped; filled with NA.")
    return df_std


def pandas_dtype_to_sql_type(dtype: str) -> str:
    d = dtype.lower()
    if 'int' in d: return 'BIGINT'
    if 'float' in d or 'decimal' in d: return 'FLOAT'
    if 'bool' in d: return 'BIT'
    if 'datetime' in d: return 'DATETIME2'
    if 'date' in d: return 'DATE'
    if 'time' in d: return 'TIME'
    return 'VARCHAR(MAX)'


def create_po_table_from_dataframe(conn: pymssql.Connection, df_standardized: pd.DataFrame, table_name: str) -> bool:
    """
    Create PO table if missing, using explicit and inferred column types.
    """
    if not conn or df_standardized is None:
        logging.error("Connection or DataFrame not provided.")
        return False
    if general_db_service.check_if_table_exists(conn, table_name):
        return True
    cols = ["[id] INT IDENTITY(1,1) PRIMARY KEY"]
    explicit = {'OrderDate':'DATE'}
    for col in df_standardized.columns:
        col_sql = re.sub(r'\W+', '_', col)
        if col_sql.lower()=='id':
            continue
        if col in explicit:
            sql_type = explicit[col]
        else:
            sql_type = pandas_dtype_to_sql_type(str(df_standardized[col].dtype)) + ' NULL'
        cols.append(f"[{col_sql}] {sql_type}")
    ddl = f"CREATE TABLE dbo.{table_name} ({', '.join(cols)});"
    try:
        cur = conn.cursor()
        cur.execute(ddl)
        conn.commit()
        return True
    except pymssql.Error as e:
        conn.rollback()
        logging.error(f"Error creating PO table {table_name}: {e}", exc_info=True)
        return False
    finally:
        cur.close()


def load_po_dataframe_to_sql(df_standardized: pd.DataFrame, table_name: str, if_exists_strategy='replace') -> bool:
    """
    Load DataFrame into SQL table via SQLAlchemy+pymssql.
    """
    if df_standardized is None:
        return False
    df = df_standardized.copy()
    # drop 'id' if present
    drop = next((c for c in df.columns if c.lower()=='id'), None)
    if drop: df.drop(columns=[drop], inplace=True)
    # handle empty df
    if df.empty:
        if if_exists_strategy=='replace':
            conn = general_db_service.get_sql_connection()
            if general_db_service.check_if_table_exists(conn, table_name):
                cur=conn.cursor(); cur.execute(f"DELETE FROM dbo.{table_name}"); conn.commit(); cur.close()
            conn.close()
        return True
    # build engine
    user=os.environ.get('SQL_USERNAME'); pwd=os.environ.get('SQL_PASSWORD')
    srv=os.environ.get('SQL_SERVER_NAME'); db=os.environ.get('SQL_DATABASE_NAME')
    if not all([user,pwd,srv,db]):
        logging.error("Missing env vars for SQLAlchemy engine.")
        return False
    try:
        url=f"mssql+pymssql://{user}:{quote_plus(pwd)}@{srv}:{1433}/{db}"
        engine=create_engine(url)
        if if_exists_strategy=='replace':
            conn=general_db_service.get_sql_connection(); cur=conn.cursor(); cur.execute(f"DELETE FROM dbo.{table_name}"); conn.commit(); cur.close(); conn.close()
        df.to_sql(name=table_name, con=engine, if_exists='append', index=False, schema='dbo', chunksize=1000)
        return True
    except SQLAlchemyError as e:
        logging.error(f"Error loading PO data: {e}", exc_info=True)
        return False
    except Exception as e:
        logging.error(f"Unexpected error loading PO: {e}", exc_info=True)
        return False
    finally:
        try: engine.dispose()
        except: pass






def get_po_data_by_number(po_number: str) -> dict | None:
    """
    Queries the Master PO SQL table for all line items under the given PONumber.
    Returns None if no rows are found, else returns:
    {
      "po_number": "<po_number>",
      "line_items": [
        {
          "description": "<ItemName>",
          "quantity": <Quantity as number>,
          "unit_price": <UnitPrice as number>
        },
        ...
      ]
    }
    """
    table = os.getenv("PO_MASTER_TABLE_NAME", "MasterPOData")
    sql = (
        f"SELECT ItemName, Quantity, UnitPrice "
        f"FROM dbo.{table} "
        f"WHERE PONumber = %s"
    )
    try:
        conn = get_sql_connection()
        cursor = conn.cursor(as_dict=True)
        cursor.execute(sql, (po_number,))
        rows = cursor.fetchall()
        cursor.close()
        conn.close()
        if not rows:
            return None

        # Normalize numeric types if returned as Decimal
        def _to_py(val):
            try: return float(val)
            except: return val

        return {
            "po_number": po_number,
            "line_items": [
                {
                    "description": row["ItemName"],
                    "quantity": _to_py(row["Quantity"]),
                    "unit_price": _to_py(row["UnitPrice"])
                }
                for row in rows
            ]
        }
    except Exception as e:
        logging.error(f"Error fetching PO '{po_number}' data: {e}", exc_info=True)
        return None
