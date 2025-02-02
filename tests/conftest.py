"""``pytest`` configuration."""

import os

import pytest
import pytest_pgsql

from starlette.testclient import TestClient

DATA_DIR = os.path.join(os.path.dirname(__file__), "fixtures")


test_db = pytest_pgsql.TransactedPostgreSQLTestDB.create_fixture(
    "test_db", scope="session", use_restore_state=False
)


@pytest.fixture(scope="session")
def database_url(test_db):
    """
    Session scoped fixture to launch a postgresql database in a separate process.  We use psycopg2 to ingest test data
    because pytest-asyncio event loop is a function scoped fixture and cannot be called within the current scope.  Yields
    a database url which we pass to our application through a monkeypatched environment variable.
    """
    assert test_db.install_extension("postgis")
    test_db.run_sql_file(os.path.join(DATA_DIR, "landsat_wrs.sql"))
    assert test_db.has_table("landsat_wrs")

    test_db.run_sql_file(os.path.join(DATA_DIR, "my_data.sql"))
    assert test_db.has_table("my_data")

    test_db.run_sql_file(os.path.join(DATA_DIR, "nongeo_data.sql"))
    assert test_db.has_table("nongeo_data")

    test_db.connection.execute(
        "CREATE TABLE landsat AS SELECT geom, ST_Centroid(geom) as centroid, ogc_fid, id, pr, path, row from landsat_wrs;"
    )
    test_db.connection.execute("ALTER TABLE landsat ADD PRIMARY KEY (ogc_fid);")
    assert test_db.has_table("landsat")

    count_landsat = test_db.connection.execute(
        "SELECT COUNT(*) FROM landsat_wrs"
    ).scalar()
    count_landsat_centroid = test_db.connection.execute(
        "SELECT COUNT(*) FROM landsat"
    ).scalar()
    assert count_landsat == count_landsat_centroid

    test_db.run_sql_file(os.path.join(DATA_DIR, "canada.sql"))
    assert test_db.has_table("canada")

    return test_db.connection.engine.url


@pytest.fixture(autouse=True)
def app(database_url, monkeypatch):
    """Create app with connection to the pytest database."""
    monkeypatch.setenv("DATABASE_URL", str(database_url))
    monkeypatch.setenv("ONLY_SPATIAL_TABLES", "FALSE")
    monkeypatch.setenv(
        "TIFEATURES_TEMPLATE_DIRECTORY", os.path.join(DATA_DIR, "templates")
    )
    monkeypatch.setenv(
        "TIFEATURES_TABLE_CONFIG__public_my_data__datetimecol", "datetime"
    )
    monkeypatch.setenv("TIFEATURES_TABLE_CONFIG__public_my_data__geomcol", "geom")
    monkeypatch.setenv("TIFEATURES_TABLE_CONFIG__public_my_data__pk", "ogc_fid")
    monkeypatch.setenv(
        "TIFEATURES_TABLE_CONFIG__public_my_data_alt__datetimecol", "otherdt"
    )
    monkeypatch.setenv(
        "TIFEATURES_TABLE_CONFIG__public_my_data_alt__geomcol", "othergeom"
    )
    monkeypatch.setenv("TIFEATURES_TABLE_CONFIG__public_my_data_alt__pk", "id")
    monkeypatch.setenv("TIFEATURES_TABLE_CONFIG__public_landsat__geomcol", "geom")

    from tifeatures.main import app

    # Remove middlewares https://github.com/encode/starlette/issues/472
    app.user_middleware = []
    app.middleware_stack = app.build_middleware_stack()

    # register functions to app.state.function_catalog here

    with TestClient(app) as app:
        yield app
