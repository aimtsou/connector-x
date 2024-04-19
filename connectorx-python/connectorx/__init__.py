from __future__ import annotations

import importlib
import urllib.parse

from importlib.metadata import version
from pathlib import Path
from typing import Literal, TYPE_CHECKING, overload, Generic, TypeVar

from .connectorx import (
    read_sql as _read_sql,
    partition_sql as _partition_sql,
    read_sql2 as _read_sql2,
    get_meta as _get_meta,
)

if TYPE_CHECKING:
    import pandas as pd
    import polars as pl
    import modin.pandas as mpd
    import dask.dataframe as dd
    import pyarrow as pa

    # only for typing hints
    from .connectorx import _DataframeInfos, _ArrowInfos


__version__ = version(__name__)

import os

dir_path = os.path.dirname(os.path.realpath(__file__))
# check whether it is in development env or installed
if (
    not os.path.basename(os.path.abspath(os.path.join(dir_path, "..")))
    == "connectorx-python"
):
    os.environ.setdefault("J4RS_BASE_PATH", os.path.join(dir_path, "dependencies"))

os.environ.setdefault(
    "CX_REWRITER_PATH", os.path.join(dir_path, "dependencies/federated-rewriter.jar")
)

Protocol = Literal["csv", "binary", "cursor", "simple", "text"]


_BackendT = TypeVar("_BackendT")


def rewrite_conn(
    conn: str | Connection, protocol: Protocol | None = None
) -> tuple[str, Protocol]:
    conn = str(conn)

    if not protocol:
        # note: redshift/clickhouse are not compatible with the 'binary' protocol, and use other database
        # drivers to connect. set a compatible protocol and masquerade as the appropriate backend.
        backend, connection_details = conn.split(":", 1) if conn else ("", "")
        if "redshift" in backend:
            conn = f"postgresql:{connection_details}"
            protocol = "cursor"
        elif "clickhouse" in backend:
            conn = f"mysql:{connection_details}"
            protocol = "text"
        else:
            protocol = "binary"
    return conn, protocol


def get_meta(
    conn: str,
    query: str,
    protocol: Protocol | None = None,
) -> pd.DataFrame:
    """
    Get metadata (header) of the given query (only for pandas)

    Parameters
    ==========
    conn
      the connection string.
    query
      a SQL query or a list of SQL queries.
    protocol
      backend-specific transfer protocol directive; defaults to 'binary' (except for redshift
      connection strings, where 'cursor' will be used instead).

    """
    conn, protocol = rewrite_conn(conn, protocol)
    result = _get_meta(conn, protocol, query)
    df = reconstruct_pandas(result)
    return df


def partition_sql(
    conn: str | Connection,
    query: str,
    partition_on: str,
    partition_num: int,
    partition_range: tuple[int, int] | None = None,
) -> list[str]:
    """
    Partition the sql query

    Parameters
    ==========
    conn
      the connection string.
    query
      a SQL query or a list of SQL queries.
    partition_on
      the column on which to partition the result.
    partition_num
      how many partitions to generate.
    partition_range
      the value range of the partition column.
    """
    partition_query = {
        "query": query,
        "column": partition_on,
        "min": partition_range and partition_range[0],
        "max": partition_range and partition_range[1],
        "num": partition_num,
    }
    return _partition_sql(conn, partition_query)


def read_sql_pandas(
    sql: list[str] | str,
    con: str | Connection | dict[str, str] | dict[str, Connection],
    index_col: str | None = None,
    protocol: Protocol | None = None,
    partition_on: str | None = None,
    partition_range: tuple[int, int] | None = None,
    partition_num: int | None = None,
) -> pd.DataFrame:
    """
    Run the SQL query, download the data from database into a dataframe.
    First several parameters are in the same name and order with `pandas.read_sql`.

    Parameters
    ==========
    Please refer to `read_sql`

    Examples
    ========
    Read a DataFrame from a SQL query using a single thread:

    >>> # from pandas import read_sql
    >>> from connectorx import read_sql_pandas as read_sql
    >>> postgres_url = "postgresql://username:password@server:port/database"
    >>> query = "SELECT * FROM lineitem"
    >>> read_sql(query, postgres_url)

    """
    return read_sql(
        con,
        sql,
        return_type="pandas",
        protocol=protocol,
        partition_on=partition_on,
        partition_range=partition_range,
        partition_num=partition_num,
        index_col=index_col,
    )


# default return pd.DataFrame
@overload
def read_sql(
    conn: str | Connection | dict[str, str] | dict[str, Connection],
    query: list[str] | str,
    *,
    protocol: Protocol | None = None,
    partition_on: str | None = None,
    partition_range: tuple[int, int] | None = None,
    partition_num: int | None = None,
    index_col: str | None = None,
) -> pd.DataFrame:
    ...


@overload
def read_sql(
    conn: str | Connection | dict[str, str] | dict[str, Connection],
    query: list[str] | str,
    *,
    return_type: Literal["pandas"],
    protocol: Protocol | None = None,
    partition_on: str | None = None,
    partition_range: tuple[int, int] | None = None,
    partition_num: int | None = None,
    index_col: str | None = None,
) -> pd.DataFrame:
    ...


@overload
def read_sql(
    conn: str | Connection | dict[str, str] | dict[str, Connection],
    query: list[str] | str,
    *,
    return_type: Literal["arrow", "arrow2"],
    protocol: Protocol | None = None,
    partition_on: str | None = None,
    partition_range: tuple[int, int] | None = None,
    partition_num: int | None = None,
    index_col: str | None = None,
) -> pa.Table:
    ...


@overload
def read_sql(
    conn: str | Connection | dict[str, str] | dict[str, Connection],
    query: list[str] | str,
    *,
    return_type: Literal["modin"],
    protocol: Protocol | None = None,
    partition_on: str | None = None,
    partition_range: tuple[int, int] | None = None,
    partition_num: int | None = None,
    index_col: str | None = None,
) -> mpd.DataFrame:
    ...


@overload
def read_sql(
    conn: str | Connection | dict[str, str] | dict[str, Connection],
    query: list[str] | str,
    *,
    return_type: Literal["dask"],
    protocol: Protocol | None = None,
    partition_on: str | None = None,
    partition_range: tuple[int, int] | None = None,
    partition_num: int | None = None,
    index_col: str | None = None,
) -> dd.DataFrame:
    ...


@overload
def read_sql(
    conn: str | Connection | dict[str, str] | dict[str, Connection],
    query: list[str] | str,
    *,
    return_type: Literal["polars", "polars2"],
    protocol: Protocol | None = None,
    partition_on: str | None = None,
    partition_range: tuple[int, int] | None = None,
    partition_num: int | None = None,
    index_col: str | None = None,
) -> pl.DataFrame:
    ...


def read_sql(
    conn: str | Connection | dict[str, str] | dict[str, Connection],
    query: list[str] | str,
    *,
    return_type: Literal[
        "pandas", "polars", "polars2", "arrow", "arrow2", "modin", "dask"
    ] = "pandas",
    protocol: Protocol | None = None,
    partition_on: str | None = None,
    partition_range: tuple[int, int] | None = None,
    partition_num: int | None = None,
    index_col: str | None = None,
) -> pd.DataFrame | mpd.DataFrame | dd.DataFrame | pl.DataFrame | pa.Table:
    """
    Run the SQL query, download the data from database into a dataframe.

    Parameters
    ==========
    conn
      the connection string, or dict of connection string mapping for federated query.
    query
      a SQL query or a list of SQL queries.
    return_type
      the return type of this function; one of "arrow(2)", "pandas", "modin", "dask" or "polars(2)".
    protocol
      backend-specific transfer protocol directive; defaults to 'binary' (except for redshift
      connection strings, where 'cursor' will be used instead).
    partition_on
      the column on which to partition the result.
    partition_range
      the value range of the partition column.
    partition_num
      how many partitions to generate.
    index_col
      the index column to set; only applicable for return type "pandas", "modin", "dask".

    Examples
    ========
    Read a DataFrame from a SQL query using a single thread:

    >>> postgres_url = "postgresql://username:password@server:port/database"
    >>> query = "SELECT * FROM lineitem"
    >>> read_sql(postgres_url, query)

    Read a DataFrame in parallel using 10 threads by automatically partitioning the provided SQL on the partition column:

    >>> postgres_url = "postgresql://username:password@server:port/database"
    >>> query = "SELECT * FROM lineitem"
    >>> read_sql(postgres_url, query, partition_on="partition_col", partition_num=10)

    Read a DataFrame in parallel using 2 threads by explicitly providing two SQL queries:

    >>> postgres_url = "postgresql://username:password@server:port/database"
    >>> queries = ["SELECT * FROM lineitem WHERE partition_col <= 10", "SELECT * FROM lineitem WHERE partition_col > 10"]
    >>> read_sql(postgres_url, queries)

    """
    if isinstance(query, list) and len(query) == 1:
        query = query[0]
        query = remove_ending_semicolon(query)

    if isinstance(conn, dict):
        conn = {k: str(v) for k, v in conn.items()}

        assert partition_on is None and isinstance(
            query, str
        ), "Federated query does not support query partitioning for now"
        assert (
            protocol is None
        ), "Federated query does not support specifying protocol for now"

        query = remove_ending_semicolon(query)

        result = _read_sql2(query, conn)
        df = reconstruct_arrow(result)
        if return_type == "pandas":
            df = df.to_pandas(date_as_object=False, split_blocks=False)
        if return_type == "polars":
            pl = try_import_module("polars")

            try:
                # api change for polars >= 0.8.*
                df = pl.from_arrow(df)
            except AttributeError:
                df = pl.DataFrame.from_arrow(df)
        return df

    conn = str(conn)
    if isinstance(query, str):
        query = remove_ending_semicolon(query)

        if partition_on is None:
            queries = [query]
            partition_query = None
        else:
            partition_query = {
                "query": query,
                "column": partition_on,
                "min": partition_range[0] if partition_range else None,
                "max": partition_range[1] if partition_range else None,
                "num": partition_num,
            }
            queries = None
    elif isinstance(query, list):
        queries = [remove_ending_semicolon(subquery) for subquery in query]
        partition_query = None

        if partition_on is not None:
            raise ValueError("Partition on multiple queries is not supported.")
    else:
        raise ValueError("query must be either str or a list of str")

    conn, protocol = rewrite_conn(conn, protocol)

    if return_type in {"modin", "dask", "pandas"}:
        try_import_module("pandas")

        result = _read_sql(
            conn,
            "pandas",
            queries=queries,
            protocol=protocol,
            partition_query=partition_query,
        )
        df = reconstruct_pandas(result)

        if index_col is not None:
            df.set_index(index_col, inplace=True)

        if return_type == "modin":
            mpd = try_import_module("modin.pandas")
            df = mpd.DataFrame(df)
        elif return_type == "dask":
            dd = try_import_module("dask.dataframe")
            df = dd.from_pandas(df, npartitions=1)

    elif return_type in {"arrow", "arrow2", "polars", "polars2"}:
        try_import_module("pyarrow")

        result = _read_sql(
            conn,
            "arrow2" if return_type in {"arrow2", "polars", "polars2"} else "arrow",
            queries=queries,
            protocol=protocol,
            partition_query=partition_query,
        )
        df = reconstruct_arrow(result)
        if return_type in {"polars", "polars2"}:
            pl = try_import_module("polars")
            try:
                df = pl.DataFrame.from_arrow(df)
            except AttributeError:
                # api change for polars >= 0.8.*
                df = pl.from_arrow(df)
    else:
        raise ValueError(return_type)

    return df


def reconstruct_arrow(result: _ArrowInfos) -> pa.Table:
    import pyarrow as pa

    names, ptrs = result
    if len(names) == 0:
        return pa.Table.from_arrays([])

    rbs = []
    for chunk in ptrs:
        rb = pa.RecordBatch.from_arrays(
            [pa.Array._import_from_c(*col_ptr) for col_ptr in chunk], names
        )
        rbs.append(rb)
    return pa.Table.from_batches(rbs)


def reconstruct_pandas(df_infos: _DataframeInfos) -> pd.DataFrame:
    import pandas as pd

    data = df_infos["data"]
    headers = df_infos["headers"]
    block_infos = df_infos["block_infos"]

    nrows = data[0][0].shape[-1] if isinstance(data[0], tuple) else data[0].shape[-1]
    blocks = []
    for binfo, block_data in zip(block_infos, data):
        if binfo.dt == 0:  # NumpyArray
            blocks.append(
                pd.core.internals.make_block(block_data, placement=binfo.cids)
            )
        elif binfo.dt == 1:  # IntegerArray
            blocks.append(
                pd.core.internals.make_block(
                    pd.core.arrays.IntegerArray(block_data[0], block_data[1]),
                    placement=binfo.cids[0],
                )
            )
        elif binfo.dt == 2:  # BooleanArray
            blocks.append(
                pd.core.internals.make_block(
                    pd.core.arrays.BooleanArray(block_data[0], block_data[1]),
                    placement=binfo.cids[0],
                )
            )
        elif binfo.dt == 3:  # DatetimeArray
            blocks.append(
                pd.core.internals.make_block(
                    pd.core.arrays.DatetimeArray(block_data), placement=binfo.cids
                )
            )
        else:
            raise ValueError(f"unknown dt: {binfo.dt}")

    block_manager = pd.core.internals.BlockManager(
        blocks, [pd.Index(headers), pd.RangeIndex(start=0, stop=nrows, step=1)]
    )
    df = pd.DataFrame(block_manager)
    return df


def remove_ending_semicolon(query: str) -> str:
    """
    Removes the semicolon if the query ends with it.

    Parameters
    ==========
    query
      SQL query

    """
    if query.endswith(";"):
        query = query[:-1]
    return query


def try_import_module(name: str):
    try:
        return importlib.import_module(name)
    except ModuleNotFoundError:
        raise ValueError(f"You need to install {name.split('.')[0]} first")


_ServerBackendT = TypeVar(
    "_ServerBackendT",
    bound=Literal[
        "postgres",
        "postgresql",
        "mysql",
        "mssql",
        "oracle",
        "duckdb",
    ],
)


class Connection(Generic[_BackendT]):
    connection: str

    @overload
    def __new__(
        cls,
        *,
        backend: Literal["sqlite"],
        db_path: str,
    ) -> Connection[Literal["sqlite"]]:
        ...

    @overload
    def __new__(
        cls,
        *,
        backend: Literal["bigquery"],
        db_path: str | Path,
    ) -> Connection[Literal["bigquery"]]: ...

    @overload
    def __new__(
        cls,
        *,
        backend: _ServerBackendT,
        username: str,
        password: str = "",
        server: str,
        port: int,
        database: str = "",
<<<<<<< HEAD
    ) -> Connection[_BackendWithoutSqliteT]:
        ...
=======
        database_options: dict[str, str] | None = None,
    ) -> Connection[_ServerBackendT]: ...
>>>>>>> 1eb4250d0 (support database options)

    def __new__(
        cls,
        *,
        backend: str,
        username: str = "",
        password: str = "",
        server: str = "",
        port: int | None = None,
        database: str = "",
        database_options: dict[str, str] | None = None,
        db_path: str | Path = "",
    ) -> Connection:
        self = super().__new__(cls)
        if backend == "sqlite":
            db_path = urllib.parse.quote(str(db_path))
            self.connection = f"{backend}://{db_path}"
        else:
            self.connection = (
                f"{backend}://{username}:{password}@{server}:{port}/{database}"
            )
            if database_options:
                self.connection += "?" + urllib.parse.urlencode(database_options)
        return self

    def __str__(self) -> str:
        return self.connection
