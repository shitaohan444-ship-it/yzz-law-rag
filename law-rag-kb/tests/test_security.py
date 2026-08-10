import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.core.authorization import _can_access_row
from app.core.config import settings
from app.core.security import Principal, _flatten_permissions
from app.ingest.service import IngestResult
from app.main import app
from app.rag import retrieve


TOKEN = "test-only-service-token-0123456789abcdef"
USER = Principal(
    user_id=7,
    employee_id=17,
    department_id=5,
    role_codes=frozenset({"lawyer"}),
)
ADMIN = Principal(
    user_id=1,
    employee_id=10,
    department_id=5,
    role_codes=frozenset({"rag_admin"}),
    is_admin=True,
)


def _doc(**overrides):
    row = {
        "id": 100,
        "permission_level": "public",
        "source_department_id": None,
        "author_employee_id": None,
        "created_by": None,
        "case_id": None,
        "source_type": "legal_document",
    }
    row.update(overrides)
    return row


class AuthorizationPolicyTests(unittest.TestCase):
    def test_false_permission_flag_does_not_grant_admin(self) -> None:
        self.assertNotIn("rag.admin", _flatten_permissions({"rag.admin": False}))
        self.assertIn("rag.admin", _flatten_permissions({"rag.admin": True}))

    def test_permission_levels_are_fail_closed(self) -> None:
        self.assertTrue(_can_access_row(USER, _doc(), set(), None))
        self.assertTrue(
            _can_access_row(USER, _doc(permission_level="internal"), set(), None)
        )
        self.assertTrue(
            _can_access_row(
                USER,
                _doc(permission_level="department", source_department_id=5),
                set(),
                None,
            )
        )
        self.assertFalse(
            _can_access_row(
                USER,
                _doc(permission_level="department", source_department_id=6),
                set(),
                None,
            )
        )
        self.assertTrue(
            _can_access_row(
                USER,
                _doc(permission_level="private", author_employee_id=17),
                set(),
                None,
            )
        )
        self.assertFalse(
            _can_access_row(USER, _doc(permission_level="unexpected"), set(), None)
        )

    def test_case_binding_cannot_be_bypassed_by_public_permission(self) -> None:
        case_doc = _doc(case_id=23, source_type="case_material")

        self.assertFalse(_can_access_row(USER, case_doc, {99}, None))
        self.assertTrue(_can_access_row(USER, case_doc, {23}, None))

    def test_unbound_case_material_is_owner_only(self) -> None:
        material = _doc(source_type="case_material", created_by=7)

        self.assertTrue(_can_access_row(USER, material, set(), None))
        self.assertFalse(
            _can_access_row(USER, dict(material, created_by=8), set(), None)
        )

    def test_case_scope_remains_a_hard_boundary_for_admin(self) -> None:
        other_case = _doc(case_id=24, source_type="case_material")

        self.assertFalse(_can_access_row(ADMIN, other_case, {23, 24}, 23))
        self.assertTrue(
            _can_access_row(
                ADMIN, _doc(case_id=23, source_type="case_material"), {23, 24}, 23
            )
        )

    @patch("app.rag.retrieve.hybrid_recall")
    def test_empty_authorized_scope_never_runs_retrieval(self, recall_mock) -> None:
        self.assertEqual(retrieve.search("query", doc_ids=[]), [])
        recall_mock.assert_not_called()


class SecurityApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.client = TestClient(app)

    def _auth_headers(self, *, with_user: bool = True) -> dict[str, str]:
        headers = {"Authorization": f"Bearer {TOKEN}"}
        if with_user:
            headers["X-RAG-User-Id"] = "7"
        return headers

    @patch.object(settings, "rag_service_token", TOKEN)
    @patch.object(settings, "auth_enabled", True)
    def test_read_requires_service_token_and_user_context(self) -> None:
        missing_token = self.client.post("/search", json={"query": "合同"})
        self.assertEqual(missing_token.status_code, 401)

        missing_user = self.client.post(
            "/search",
            headers=self._auth_headers(with_user=False),
            json={"query": "合同"},
        )
        self.assertEqual(missing_user.status_code, 401)

    @patch("app.api.search.retrieve.search", return_value=[])
    @patch("app.api.search.authorized_doc_ids", return_value=[16])
    @patch("app.core.security.load_user_principal", return_value=USER)
    @patch.object(settings, "rag_service_token", TOKEN)
    @patch.object(settings, "auth_enabled", True)
    def test_search_uses_server_authorized_document_scope(
        self, _principal_mock, authorize_mock, search_mock
    ) -> None:
        response = self.client.post(
            "/search",
            headers=self._auth_headers(),
            json={"query": "合同", "doc_ids": [16, 17]},
        )

        self.assertEqual(response.status_code, 200)
        authorize_mock.assert_called_once_with(
            USER,
            [16, 17],
            case_id_scope=None,
            category_ids=None,
            knowledge_types=None,
            effective_on=None,
            effectivity_status=None,
            cause_code=None,
        )
        search_mock.assert_called_once_with(
            "合同", doc_ids=[16], top_k=None, min_score=None
        )

    @patch("app.api.documents.ingest_service.get_document_status")
    @patch("app.api.documents.can_access_document", return_value=False)
    @patch("app.core.security.load_user_principal", return_value=USER)
    @patch.object(settings, "rag_service_token", TOKEN)
    @patch.object(settings, "auth_enabled", True)
    def test_unauthorized_document_is_hidden_as_not_found(
        self, _principal_mock, _access_mock, status_mock
    ) -> None:
        response = self.client.get("/documents/17", headers=self._auth_headers())

        self.assertEqual(response.status_code, 404)
        status_mock.assert_not_called()

    @patch("app.api.documents.ingest_service.ingest_document")
    @patch.object(settings, "rag_service_token", TOKEN)
    @patch.object(settings, "auth_enabled", True)
    def test_ingest_accepts_service_identity_without_user_header(
        self, ingest_mock
    ) -> None:
        ingest_mock.return_value = IngestResult(23, "success", chunk_count=1)

        response = self.client.post(
            "/documents/23/ingest",
            headers=self._auth_headers(with_user=False),
        )

        self.assertEqual(response.status_code, 200)
        ingest_mock.assert_called_once_with(23, force=False)

    @patch("app.api.chat.chat_service.chat")
    @patch("app.core.security.load_user_principal", return_value=USER)
    @patch.object(settings, "rag_service_token", TOKEN)
    @patch.object(settings, "auth_enabled", True)
    def test_chat_rejects_spoofed_body_user_id(
        self, _principal_mock, chat_mock
    ) -> None:
        response = self.client.post(
            "/chat",
            headers=self._auth_headers(),
            json={"question": "测试", "user_id": 8},
        )

        self.assertEqual(response.status_code, 403)
        chat_mock.assert_not_called()

    @patch("app.api.health._check_model_path", return_value="ok")
    @patch("app.api.health._check_milvus", return_value="ok")
    @patch("app.api.health._check_minio", return_value="ok")
    @patch("app.api.health._check_pg", return_value="ok")
    @patch.object(settings, "rag_service_token", "")
    @patch.object(settings, "auth_enabled", False)
    @patch.object(settings, "app_env", "production")
    def test_production_without_auth_is_not_ready(self, *_mocks) -> None:
        response = self.client.get("/ready")

        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json()["authentication"], "misconfigured")

    def test_security_headers_and_request_size_limit(self) -> None:
        response = self.client.get("/health")
        self.assertEqual(response.headers["x-content-type-options"], "nosniff")
        self.assertEqual(response.headers["x-frame-options"], "DENY")

        oversized = self.client.post(
            "/search",
            content=b"x" * (settings.max_request_body_bytes + 1),
            headers={"content-type": "application/json"},
        )
        self.assertEqual(oversized.status_code, 413)


if __name__ == "__main__":
    unittest.main()
