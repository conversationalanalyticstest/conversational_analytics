"""Tests de `ops.semantic_view_registry` (T008, T031): versionado, activacion y retencion.

Usa una semantic view minima propia (`SV_OPS_TEST*`, sobre `DIM_PRODUCT`, sin
`AI_VERIFIED_QUERIES`) en vez de la de produccion (`SV_PHARMA_SALES`): el mecanismo de
versionado es generico y no depende del contenido de la semantic view, y cada despliegue real
tarda segundos en vez de minutos (Principio I).
"""

from __future__ import annotations

import uuid
from collections.abc import Callable
from typing import Any

import pytest

from conversational_analytics.ops import semantic_view_registry as svr

BASE_NAME = "SV_OPS_TEST"

_DDL_TEMPLATE = f"""
USE ROLE CICD_DEMO_ROLE;
USE WAREHOUSE COMPUTE_WH;
USE SCHEMA CICD_DEMO.DATA;

CREATE OR ALTER SEMANTIC VIEW {BASE_NAME}
  TABLES (
    PRODUCT AS DIM_PRODUCT PRIMARY KEY (PRODUCT_ID)
  )
  DIMENSIONS (
    PRODUCT.PRODUCT_ID AS PRODUCT_ID
  )
;
"""


def _commit_sha() -> str:
    return uuid.uuid4().hex[:12]


@pytest.fixture(scope="module", autouse=True)
def _cleanup_sv_ops_test(sf_conn: Any) -> Any:
    """Borra al final del modulo los objetos fisicos y filas de `SV_OPS_TEST*` creados por
    estos tests: son objetos de usar y tirar, no artefactos de produccion."""
    yield
    with sf_conn.cursor() as cur:
        cur.execute(
            "SELECT OBJECT_NAME FROM CICD_DEMO.DEVOPS.SEMANTIC_VIEW_VERSIONS "
            f"WHERE BASE_NAME = '{BASE_NAME}'"
        )
        object_names = [row[0] for row in cur.fetchall()]
        for object_name in object_names:
            cur.execute(f"DROP SEMANTIC VIEW IF EXISTS CICD_DEMO.DATA.{object_name}")
        cur.execute(
            f"DELETE FROM CICD_DEMO.DEVOPS.SEMANTIC_VIEW_ACTIVE WHERE BASE_NAME = '{BASE_NAME}'"
        )


# ---------------------------------------------------------------------------
# deploy_version / activate_version / resolve_active (T008)
# ---------------------------------------------------------------------------


@pytest.mark.writes_db
def test_deploy_version_creates_object_and_registers_row(
    fetch_one: Callable[[str], Any],
) -> None:
    sha = _commit_sha()
    object_name = svr.deploy_version(
        base_name=BASE_NAME, ddl_template=_DDL_TEMPLATE, commit_sha=sha, is_candidate=True
    )
    expected_object_name = f"{BASE_NAME}_V{sha[:7].upper()}"
    assert object_name == expected_object_name

    row = fetch_one(
        "SELECT OBJECT_NAME, COMMIT_SHA, IS_CANDIDATE "
        "FROM CICD_DEMO.DEVOPS.SEMANTIC_VIEW_VERSIONS "
        f"WHERE BASE_NAME = '{BASE_NAME}' AND COMMIT_SHA = '{sha}'"
    )
    assert row == (expected_object_name, sha, True)


@pytest.mark.writes_db
def test_drop_candidate_removes_object_without_touching_registry(
    sf_conn: Any, fetch_one: Callable[[str], Any]
) -> None:
    sha = _commit_sha()
    object_name = svr.deploy_version(
        base_name=BASE_NAME, ddl_template=_DDL_TEMPLATE, commit_sha=sha, is_candidate=True
    )

    svr.drop_candidate(object_name=object_name)

    with sf_conn.cursor() as cur:
        cur.execute(f"SHOW SEMANTIC VIEWS LIKE '{object_name}' IN SCHEMA CICD_DEMO.DATA")
        assert cur.fetchone() is None  # el objeto fisico ya no existe

    row = fetch_one(
        "SELECT OBJECT_NAME FROM CICD_DEMO.DEVOPS.SEMANTIC_VIEW_VERSIONS "
        f"WHERE BASE_NAME = '{BASE_NAME}' AND COMMIT_SHA = '{sha}'"
    )
    assert row == (object_name,)  # la fila de registro se conserva (solo se borra el objeto)


@pytest.mark.writes_db
def test_activate_version_updates_pointer_and_resolve_active(
    fetch_one: Callable[[str], Any],
) -> None:
    sha = _commit_sha()
    svr.deploy_version(
        base_name=BASE_NAME, ddl_template=_DDL_TEMPLATE, commit_sha=sha, is_candidate=False
    )
    svr.activate_version(base_name=BASE_NAME, commit_sha=sha, updated_by="pytest")

    active_object_name = svr.resolve_active(base_name=BASE_NAME)
    assert active_object_name == f"{BASE_NAME}_V{sha[:7].upper()}"

    row = fetch_one(
        "SELECT ACTIVE_OBJECT_NAME, ACTIVE_COMMIT_SHA, UPDATED_BY "
        f"FROM CICD_DEMO.DEVOPS.SEMANTIC_VIEW_ACTIVE WHERE BASE_NAME = '{BASE_NAME}'"
    )
    assert row == (active_object_name, sha, "pytest")


@pytest.mark.writes_db
def test_activate_version_raises_for_unknown_commit() -> None:
    with pytest.raises(LookupError):
        svr.activate_version(base_name=BASE_NAME, commit_sha="0000000", updated_by="pytest")


@pytest.mark.writes_db
def test_activate_version_recreates_purged_object(sf_conn: Any) -> None:
    sha = _commit_sha()
    object_name = svr.deploy_version(
        base_name=BASE_NAME, ddl_template=_DDL_TEMPLATE, commit_sha=sha, is_candidate=False
    )
    # Simula purga por retencion: borra el objeto fisico; la fila del historico se conserva.
    with sf_conn.cursor() as cur:
        cur.execute(f"DROP SEMANTIC VIEW IF EXISTS CICD_DEMO.DATA.{object_name}")

    svr.activate_version(base_name=BASE_NAME, commit_sha=sha, updated_by="pytest")

    with sf_conn.cursor() as cur:
        cur.execute(f"SHOW SEMANTIC VIEWS LIKE '{object_name}' IN SCHEMA CICD_DEMO.DATA")
        assert cur.fetchone() is not None


@pytest.mark.writes_db
def test_resolve_active_raises_for_unknown_base_name() -> None:
    with pytest.raises(LookupError):
        svr.resolve_active(base_name=f"SV_DOES_NOT_EXIST_{uuid.uuid4().hex[:8]}")


# ---------------------------------------------------------------------------
# cleanup_old_versions (T031/US5)
# ---------------------------------------------------------------------------


@pytest.mark.writes_db
def test_cleanup_old_versions_keeps_last_n_and_never_drops_active(
    sf_conn: Any, fetch_all: Callable[[str], list[tuple[Any, ...]]]
) -> None:
    base_name = f"SV_OPS_CLEANUP_{uuid.uuid4().hex[:8].upper()}"
    ddl_template = _DDL_TEMPLATE.replace(BASE_NAME, base_name)

    shas = [_commit_sha() for _ in range(4)]
    object_names = [
        svr.deploy_version(
            base_name=base_name, ddl_template=ddl_template, commit_sha=sha, is_candidate=False
        )
        for sha in shas
    ]
    # Activa a proposito la version mas antigua, para comprobar que nunca se borra aunque no
    # este entre las `keep_last` mas recientes.
    svr.activate_version(base_name=base_name, commit_sha=shas[0], updated_by="pytest")

    try:
        dropped = svr.cleanup_old_versions(base_name=base_name, keep_last=2)

        # Se conservan las 2 mas recientes (object_names[2], object_names[3]) + la activa
        # (object_names[0]); solo debe purgarse el objeto fisico de object_names[1].
        assert dropped == [object_names[1]]

        rows = fetch_all(
            "SELECT OBJECT_NAME FROM CICD_DEMO.DEVOPS.SEMANTIC_VIEW_VERSIONS "
            f"WHERE BASE_NAME = '{base_name}'"
        )
        # Las filas del historico nunca se borran, solo el objeto fisico.
        assert {row[0] for row in rows} == set(object_names)

        with sf_conn.cursor() as cur:
            cur.execute(f"SHOW SEMANTIC VIEWS LIKE '{object_names[1]}' IN SCHEMA CICD_DEMO.DATA")
            assert cur.fetchone() is None  # purgado

            cur.execute(f"SHOW SEMANTIC VIEWS LIKE '{object_names[0]}' IN SCHEMA CICD_DEMO.DATA")
            assert cur.fetchone() is not None  # activa: se conserva
    finally:
        with sf_conn.cursor() as cur:
            for object_name in object_names:
                cur.execute(f"DROP SEMANTIC VIEW IF EXISTS CICD_DEMO.DATA.{object_name}")
            cur.execute(
                f"DELETE FROM CICD_DEMO.DEVOPS.SEMANTIC_VIEW_ACTIVE WHERE BASE_NAME = '{base_name}'"
            )
