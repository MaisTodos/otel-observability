.PHONY: install format lint test help

help: ## Mostra esta mensagem de ajuda
	@echo "Comandos disponíveis:"
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-20s\033[0m %s\n", $$1, $$2}'

install: ## Instala o projeto e dependências
	@echo "📦 Instalando projeto..."
	poetry install --no-root || pip install -e .
	@echo "✅ Instalação concluída!"

format: ## Formata o código com ruff
	@echo "🎨 Formatando código..."
	ruff format .

lint: ## Verifica o código com ruff
	@echo "🔍 Verificando código..."
	ruff check . --fix

test: ## Executa os testes
	@echo "🧪 Executando testes..."
	pytest

check: lint test ## Executa lint e testes
