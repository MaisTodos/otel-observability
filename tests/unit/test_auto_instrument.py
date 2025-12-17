"""Testes unitários para o módulo auto_instrument."""

from unittest.mock import patch

import pytest

from otel_observability.auto_instrument import (
    auto_instrument,
    get_instrumented,
)


@pytest.mark.unit
class TestAutoInstrument:
    """Testes para auto_instrument."""

    def test_auto_instrument_all_libraries(self):
        """Testa auto-instrumentação de todas as bibliotecas."""
        with (
            patch("otel_observability.auto_instrument._instrument_httpx") as mock_httpx,
            patch("otel_observability.auto_instrument._instrument_requests") as mock_requests,
            patch("otel_observability.auto_instrument._instrument_sqlalchemy") as mock_sqlalchemy,
            patch("otel_observability.auto_instrument._instrument_psycopg2"),
            patch("otel_observability.auto_instrument._instrument_pymongo"),
            patch("otel_observability.auto_instrument._instrument_redis"),
            patch("otel_observability.auto_instrument._instrument_boto3"),
        ):
            auto_instrument()
            assert mock_httpx.called
            assert mock_requests.called
            assert mock_sqlalchemy.called

    def test_auto_instrument_specific_libraries(self):
        """Testa auto-instrumentação de bibliotecas específicas."""
        # Resetar _INSTRUMENTED antes do teste
        import otel_observability.auto_instrument as auto_instrument_module

        auto_instrument_module._INSTRUMENTED.clear()

        with (
            patch("otel_observability.auto_instrument._instrument_httpx") as mock_httpx,
            patch("otel_observability.auto_instrument._instrument_requests") as mock_requests,
            patch("otel_observability.auto_instrument._instrument_sqlalchemy") as mock_sqlalchemy,
        ):
            auto_instrument(libraries=["httpx", "requests"])

            mock_httpx.assert_called_once()
            mock_requests.assert_called_once()
            mock_sqlalchemy.assert_not_called()

    def test_auto_instrument_with_exclude(self):
        """Testa auto-instrumentação excluindo algumas bibliotecas."""
        # Resetar _INSTRUMENTED antes do teste
        import otel_observability.auto_instrument as auto_instrument_module

        auto_instrument_module._INSTRUMENTED.clear()

        with (
            patch("otel_observability.auto_instrument._instrument_httpx") as mock_httpx,
            patch("otel_observability.auto_instrument._instrument_requests") as mock_requests,
            patch("otel_observability.auto_instrument._instrument_boto3") as mock_boto3,
        ):
            auto_instrument(exclude=["boto3"])

            mock_httpx.assert_called_once()
            mock_requests.assert_called_once()
            mock_boto3.assert_not_called()

    def test_auto_instrument_handles_import_error(self):
        """Testa que ImportError é tratado silenciosamente."""
        # Resetar _INSTRUMENTED antes do teste
        import otel_observability.auto_instrument as auto_instrument_module

        auto_instrument_module._INSTRUMENTED.clear()

        with (
            patch(
                "otel_observability.auto_instrument._instrument_httpx",
                side_effect=ImportError("Not installed"),
            ),
            patch("otel_observability.auto_instrument._instrument_requests") as mock_requests,
        ):
            # Não deve levantar exceção
            auto_instrument(libraries=["httpx", "requests"])

            mock_requests.assert_called_once()

    def test_auto_instrument_handles_other_errors(self):
        """Testa que outros erros são tratados silenciosamente."""
        # Resetar _INSTRUMENTED antes do teste
        import otel_observability.auto_instrument as auto_instrument_module

        auto_instrument_module._INSTRUMENTED.clear()

        with (
            patch(
                "otel_observability.auto_instrument._instrument_httpx",
                side_effect=ValueError("Other error"),
            ),
            patch("otel_observability.auto_instrument._instrument_requests") as mock_requests,
        ):
            # Não deve levantar exceção
            auto_instrument(libraries=["httpx", "requests"])

            # httpx deve ter sido tentada (mesmo que tenha falhado)
            # requests deve ter sido chamada normalmente
            mock_requests.assert_called_once()

    def test_auto_instrument_idempotent(self):
        """Testa que auto_instrument é idempotente."""
        # Resetar _INSTRUMENTED antes do teste
        import otel_observability.auto_instrument as auto_instrument_module

        auto_instrument_module._INSTRUMENTED.clear()

        with patch("otel_observability.auto_instrument._instrument_httpx") as mock_httpx:
            auto_instrument(libraries=["httpx"])
            call_count_1 = mock_httpx.call_count

            # Chamar novamente
            auto_instrument(libraries=["httpx"])
            call_count_2 = mock_httpx.call_count

            # Deve ter sido chamado apenas uma vez
            assert call_count_1 == call_count_2


@pytest.mark.unit
class TestGetInstrumented:
    """Testes para get_instrumented."""

    def test_get_instrumented(self):
        """Testa obtenção de lista de bibliotecas instrumentadas."""
        with patch("otel_observability.auto_instrument._INSTRUMENTED", {"httpx", "requests"}):
            result = get_instrumented()

            assert isinstance(result, list)
            assert "httpx" in result
            assert "requests" in result

    def test_get_instrumented_empty(self):
        """Testa quando nenhuma biblioteca foi instrumentada."""
        with patch("otel_observability.auto_instrument._INSTRUMENTED", set()):
            result = get_instrumented()

            assert result == []
