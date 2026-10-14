"""Le contrat OpenAPI est complet : schema sortant et erreurs sur chaque operation."""

from app.main import app

_SUCCESS = {"200", "201", "202", "204"}


def test_every_operation_documents_output_and_errors():
    """Chaque operation a un succes type et au moins une erreur documentee."""
    schema = app.openapi()
    assert schema["info"]["version"] == "1.0.0"
    seen = set()
    for path, methods in schema["paths"].items():
        for method, operation in methods.items():
            if method not in {"get", "post", "patch", "put", "delete"}:
                continue
            operation_id = operation["operationId"]
            assert operation_id not in seen, operation_id
            seen.add(operation_id)
            responses = operation["responses"]
            success = [code for code in responses if code in _SUCCESS]
            errors = [code for code in responses if code.isdigit() and int(code) >= 400]
            assert success, f"{method} {path} sans reponse de succes"
            assert errors, f"{method} {path} sans erreur documentee"
            for code in success:
                if code == "204":
                    continue
                content = responses[code].get("content", {}).get("application/json", {})
                assert "schema" in content, f"{operation_id} sans schema sortant"
            for code in errors:
                example = responses[code]["content"]["application/json"]
                assert "schema" in example or "examples" in example


def test_error_component_shape_is_stable():
    """Les exemples d'erreur exposent code et message."""
    schema = app.openapi()
    sample = schema["paths"]["/api/v1/health"]["get"]["responses"]["503"]
    example = sample["content"]["application/json"]["examples"]["upstream_unavailable"]["value"]
    assert example["error"]["code"] == "upstream_unavailable"
    assert "message" in example["error"]
