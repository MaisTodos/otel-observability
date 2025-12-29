"""
Exemplo completo de funis de conversão com métricas.

Este exemplo demonstra como implementar um funil de checkout completo:
1. Checkout iniciado
2. Informações de pagamento coletadas
3. Pagamento processado com sucesso
4. Pedido criado

Execute:
    export OTEL_SERVICE_NAME=funnel-example
    export OTEL_ENVIRONMENT=development
    export OTEL_SERVICE_VERSION=1.0.0
    export DD_DOGSTATSD_ENABLED=true
    python examples/funnel_metrics_example.py
"""

import random
import time
from typing import Any

from otel_observability.metrics import track_funnel_step


class CheckoutFunnel:
    """Classe que implementa um funil de checkout completo."""

    def __init__(self):
        self.orders = {}

    def start_checkout(self, cart_id: str, user_id: str) -> dict[str, Any]:
        """
        Etapa 1: Usuário inicia checkout.

        Args:
            cart_id: ID do carrinho
            user_id: ID do usuário

        Returns:
            Dict com status do checkout
        """
        print(f"🛒 Checkout iniciado: cart_id={cart_id}, user_id={user_id}")

        # Rastrear etapa do funil
        track_funnel_step(
            "checkout",
            "start",
            tags=["region:us-east-1", "payment_method:unknown"],
        )

        # Simular alguns abandonos (não chegam na próxima etapa)
        if random.random() < 0.2:  # 20% abandonam
            print("  ⚠️  Usuário abandonou checkout")
            return {"status": "abandoned"}

        return {
            "status": "started",
            "cart_id": cart_id,
            "checkout_id": f"checkout_{cart_id}",
        }

    def collect_payment_info(self, checkout_id: str, payment_method: str) -> dict[str, Any]:
        """
        Etapa 2: Coletar informações de pagamento.

        Args:
            checkout_id: ID do checkout
            payment_method: Método de pagamento (credit_card, paypal, etc.)

        Returns:
            Dict com informações de pagamento
        """
        print(f"💳 Informações de pagamento coletadas: method={payment_method}")

        # Rastrear etapa do funil
        track_funnel_step(
            "checkout",
            "payment_info_collected",
            tags=["region:us-east-1", f"payment_method:{payment_method}"],
        )

        # Simular alguns abandonos
        if random.random() < 0.15:  # 15% abandonam
            print("  ⚠️  Usuário abandonou após coletar informações")
            return {"status": "abandoned"}

        return {
            "status": "payment_info_collected",
            "checkout_id": checkout_id,
            "payment_method": payment_method,
        }

    def process_payment(
        self, checkout_id: str, amount: float, payment_method: str
    ) -> dict[str, Any]:
        """
        Etapa 3: Processar pagamento.

        Args:
            checkout_id: ID do checkout
            amount: Valor do pagamento
            payment_method: Método de pagamento

        Returns:
            Dict com resultado do pagamento
        """
        print(f"💵 Processando pagamento: amount=${amount:.2f}, method={payment_method}")

        # Simular processamento
        time.sleep(0.1)

        # Simular falhas de pagamento (10% de taxa de falha)
        if random.random() < 0.1:
            print("  ❌ Pagamento falhou")
            track_funnel_step(
                "checkout",
                "payment_failed",
                tags=["region:us-east-1", f"payment_method:{payment_method}"],
            )
            return {"status": "payment_failed", "error": "insufficient_funds"}

        # Pagamento bem-sucedido
        print("  ✅ Pagamento processado com sucesso")
        track_funnel_step(
            "checkout",
            "payment_success",
            tags=["region:us-east-1", f"payment_method:{payment_method}"],
        )

        return {
            "status": "payment_success",
            "checkout_id": checkout_id,
            "transaction_id": f"txn_{checkout_id}",
        }

    def create_order(self, checkout_id: str, cart_id: str, amount: float) -> dict[str, Any]:
        """
        Etapa 4: Criar pedido.

        Args:
            checkout_id: ID do checkout
            cart_id: ID do carrinho
            amount: Valor do pedido

        Returns:
            Dict com informações do pedido
        """
        print(f"📦 Criando pedido: cart_id={cart_id}, amount=${amount:.2f}")

        # Simular criação de pedido
        time.sleep(0.05)

        order_id = f"order_{cart_id}"
        self.orders[order_id] = {
            "order_id": order_id,
            "cart_id": cart_id,
            "amount": amount,
            "status": "created",
        }

        # Rastrear etapa final do funil
        track_funnel_step(
            "checkout",
            "completed",
            tags=["region:us-east-1"],
        )

        print(f"  ✅ Pedido criado: order_id={order_id}")

        return {
            "status": "completed",
            "order_id": order_id,
            "amount": amount,
        }

    def run_complete_checkout(
        self, cart_id: str, user_id: str, amount: float, payment_method: str
    ) -> dict[str, Any]:
        """
        Executar funil completo de checkout.

        Args:
            cart_id: ID do carrinho
            user_id: ID do usuário
            amount: Valor do checkout
            payment_method: Método de pagamento

        Returns:
            Dict com resultado final
        """
        print("\n🛍️  Iniciando checkout completo:")
        print(f"   cart_id={cart_id}, user_id={user_id}, amount=${amount:.2f}")

        # Etapa 1: Iniciar checkout
        checkout = self.start_checkout(cart_id, user_id)
        if checkout.get("status") == "abandoned":
            return {"status": "abandoned", "stage": "start"}

        checkout_id = checkout["checkout_id"]

        # Etapa 2: Coletar informações de pagamento
        payment_info = self.collect_payment_info(checkout_id, payment_method)
        if payment_info.get("status") == "abandoned":
            return {"status": "abandoned", "stage": "payment_info"}

        # Etapa 3: Processar pagamento
        payment_result = self.process_payment(checkout_id, amount, payment_method)
        if payment_result.get("status") == "payment_failed":
            return {"status": "payment_failed", "stage": "payment"}

        # Etapa 4: Criar pedido
        order = self.create_order(checkout_id, cart_id, amount)

        return {
            "status": "completed",
            "order_id": order["order_id"],
            "amount": amount,
        }


def simulate_multiple_checkouts(num_checkouts: int = 10):
    """Simular múltiplos checkouts para gerar dados de funil."""
    print(f"\n📊 Simulando {num_checkouts} checkouts...\n")

    funnel = CheckoutFunnel()
    payment_methods = ["credit_card", "paypal", "debit_card"]

    results = {
        "completed": 0,
        "abandoned": 0,
        "payment_failed": 0,
    }

    for i in range(num_checkouts):
        cart_id = f"cart_{i+1}"
        user_id = f"user_{random.randint(1, 100)}"
        amount = round(random.uniform(10.0, 100.0), 2)
        payment_method = random.choice(payment_methods)

        result = funnel.run_complete_checkout(cart_id, user_id, amount, payment_method)

        if result["status"] == "completed":
            results["completed"] += 1
        elif result["status"] == "abandoned":
            results["abandoned"] += 1
        elif result["status"] == "payment_failed":
            results["payment_failed"] += 1

        # Pequeno delay entre checkouts
        time.sleep(0.1)

    return results


def main():
    """Executar exemplo de funil de conversão."""
    print("🚀 Exemplo de Funil de Conversão - Checkout\n")

    try:
        # Simular múltiplos checkouts
        results = simulate_multiple_checkouts(num_checkouts=20)

        # Resumo
        print("\n" + "=" * 50)
        print("📈 Resumo do Funil:")
        print("=" * 50)
        print(f"  ✅ Completados: {results['completed']}")
        print(f"  ⚠️  Abandonados: {results['abandoned']}")
        print(f"  ❌ Falhas de pagamento: {results['payment_failed']}")
        print(f"  📊 Total: {sum(results.values())}")

        # Calcular taxas de conversão (estimadas)
        total = sum(results.values())
        if total > 0:
            completion_rate = (results["completed"] / total) * 100
            print(f"\n  💰 Taxa de conversão: {completion_rate:.1f}%")

        print("\n✅ Exemplo executado com sucesso!")
        print("\n💡 Próximos passos no Datadog:")
        print("   1. Acesse Metrics → Explorer")
        print("   2. Procure por: app.funnel.checkout.*")
        print("   3. Visualize as métricas:")
        print("      - app.funnel.checkout.start")
        print("      - app.funnel.checkout.payment_info_collected")
        print("      - app.funnel.checkout.payment_success")
        print("      - app.funnel.checkout.completed")
        print("   4. Crie um Dashboard com fórmula de conversão:")
        print("      (sum:app.funnel.checkout.completed / ")
        print("       sum:app.funnel.checkout.start) * 100")

    except Exception as e:
        print(f"\n❌ Erro ao executar exemplo: {e}")
        print("\n💡 Verifique:")
        print("   1. Se o Datadog Agent está rodando (localhost:8125)")
        print("   2. Se DD_DOGSTATSD_ENABLED=true")
        print(
            "   3. Se a biblioteca datadog está instalada: pip install otel-observability[metrics]"
        )


if __name__ == "__main__":
    main()
