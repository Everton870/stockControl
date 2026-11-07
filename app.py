
import math
import sqlite3
from pathlib import Path

from flask import Flask, redirect, render_template, request, url_for

app = Flask(__name__)
DB_PATH = Path(__file__).resolve().parent / "estoque.db"


# FORMATAÇÃO MONETÁRIA
@app.template_filter("moeda")
def formatar_moeda(valor):
    valor = float(valor)
    return f"{valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


# CONEXÃO COM O BANCO DE DADOS
def conectar():
    conexao = sqlite3.connect(DB_PATH)
    conexao.row_factory = sqlite3.Row
    conexao.execute("PRAGMA foreign_keys = ON")
    return conexao


# VALIDAÇÃO DE PREÇO
def ler_preco(valor):
    preco = float(valor)
    if not math.isfinite(preco) or preco < 0:
        raise ValueError("Preço inválido")
    return preco


# PÁGINA INICIAL
@app.route("/")
def inicio():
    return render_template("index.html")


# CADASTRO DE PRODUTOS
@app.route("/cadastro", methods=["GET", "POST"])
def cadastro():
    if request.method == "POST":
        nome = request.form.get("nome", "").strip()
        categoria = request.form.get("categoria", "").strip()

        try:
            quantidade = int(request.form.get("quantidade", ""))
            preco = ler_preco(request.form.get("preco", ""))
        except (ValueError, TypeError):
            return "Quantidade ou preço inválido!", 400

        if not nome or not categoria or quantidade < 0:
            return "Preencha os campos corretamente!", 400

        conexao = conectar()
        try:
            conexao.execute(
                "INSERT OR IGNORE INTO categorias (nome) VALUES (?)",
                (categoria,)
            )

            categoria_registro = conexao.execute(
                "SELECT id FROM categorias WHERE nome = ?",
                (categoria,)
            ).fetchone()

            if categoria_registro is None:
                raise sqlite3.IntegrityError("Categoria não encontrada")

            conexao.execute(
                """
                INSERT INTO produtos
                (nome, categoria_id, quantidade, preco)
                VALUES (?, ?, ?, ?)
                """,
                (nome, categoria_registro["id"], quantidade, preco)
            )

            conexao.commit()

        except sqlite3.Error:
            conexao.rollback()
            app.logger.exception("Erro ao cadastrar produto")
            return "Não foi possível cadastrar o produto.", 500

        finally:
            conexao.close()

        return redirect(url_for("cadastro", sucesso=1))

    return render_template("cadastro.html")


# CONSULTA DE PRODUTOS
@app.route("/consulta")
def consulta():
    conexao = conectar()

    try:
        produtos = conexao.execute("""
            SELECT
                produtos.id,
                produtos.nome,
                categorias.nome AS categoria,
                produtos.quantidade,
                produtos.preco
            FROM produtos
            LEFT JOIN categorias
                ON produtos.categoria_id = categorias.id
            ORDER BY produtos.id
        """).fetchall()

    finally:
        conexao.close()

    return render_template("consulta.html", produtos=produtos)


# ENTRADA E SAÍDA DE ESTOQUE
@app.route("/movimentacao", methods=["GET", "POST"])
def movimentacao():
    mensagem = None
    erro = None

    conexao = conectar()

    try:
        if request.method == "POST":
            try:
                produto_id = int(
                    request.form.get("produto_id", "")
                )

                tipo = request.form.get("tipo", "")

                quantidade = int(
                    request.form.get("quantidade", "")
                )

                if tipo not in ("entrada", "saida") or quantidade <= 0:
                    raise ValueError("Movimentação inválida")

                conexao.execute("BEGIN IMMEDIATE")

                produto = conexao.execute(
                    "SELECT quantidade FROM produtos WHERE id = ?",
                    (produto_id,)
                ).fetchone()

                if produto is None:
                    erro = "Produto não encontrado."

                elif tipo == "saida" and quantidade > produto["quantidade"]:
                    erro = "Estoque insuficiente para esta saída."

                else:
                    diferenca = (
                        quantidade if tipo == "entrada" else -quantidade
                    )

                    nova_quantidade = produto["quantidade"] + diferenca

                    conexao.execute(
                        """
                        UPDATE produtos
                        SET quantidade = ?
                        WHERE id = ?
                        """,
                        (nova_quantidade, produto_id)
                    )

                    conexao.execute(
                        """
                        INSERT INTO movimentacoes
                        (produto_id, tipo, quantidade)
                        VALUES (?, ?, ?)
                        """,
                        (produto_id, tipo, quantidade)
                    )

                    conexao.commit()
                    mensagem = "Movimentação registrada com sucesso!"

                if erro:
                    conexao.rollback()

            except (ValueError, TypeError):
                conexao.rollback()
                erro = "Preencha os campos corretamente."

            except sqlite3.Error:
                conexao.rollback()
                app.logger.exception("Erro ao registrar movimentação")
                erro = "Não foi possível registrar a movimentação."

        produtos = conexao.execute(
            """
            SELECT id, nome, quantidade
            FROM produtos
            ORDER BY nome
            """
        ).fetchall()

    finally:
        conexao.close()

    return render_template(
        "movimentacao.html",
        produtos=produtos,
        mensagem=mensagem,
        erro=erro
    )


# EDIÇÃO DE PRODUTOS
@app.route("/editar/<int:produto_id>", methods=["GET", "POST"])
def editar_produto(produto_id):
    conexao = conectar()

    try:
        produto = conexao.execute("""
            SELECT
                produtos.id,
                produtos.nome,
                categorias.nome AS categoria,
                produtos.quantidade,
                produtos.preco
            FROM produtos
            LEFT JOIN categorias
                ON produtos.categoria_id = categorias.id
            WHERE produtos.id = ?
        """, (produto_id,)).fetchone()

        if produto is None:
            return "Produto não encontrado.", 404

        if request.method == "POST":
            nome = request.form.get("nome", "").strip()
            categoria = request.form.get("categoria", "").strip()

            try:
                preco = ler_preco(request.form.get("preco", ""))
            except (ValueError, TypeError):
                return "Preço inválido.", 400

            if not nome or not categoria:
                return "Preencha os campos corretamente.", 400

            try:
                conexao.execute(
                    "INSERT OR IGNORE INTO categorias (nome) VALUES (?)",
                    (categoria,)
                )

                categoria_registro = conexao.execute(
                    "SELECT id FROM categorias WHERE nome = ?",
                    (categoria,)
                ).fetchone()

                if categoria_registro is None:
                    raise sqlite3.IntegrityError(
                        "Categoria não encontrada"
                    )

                conexao.execute(
                    """
                    UPDATE produtos
                    SET nome = ?, categoria_id = ?, preco = ?
                    WHERE id = ?
                    """,
                    (
                        nome,
                        categoria_registro["id"],
                        preco,
                        produto_id
                    )
                )

                conexao.commit()

            except sqlite3.Error:
                conexao.rollback()
                app.logger.exception("Erro ao editar produto")
                return "Não foi possível atualizar o produto.", 500

            return redirect(url_for("consulta"))

        return render_template("editar.html", produto=produto)

    finally:
        conexao.close()


# HISTÓRICO DE MOVIMENTAÇÕES
@app.route("/historico")
def historico():
    conexao = conectar()

    try:
        movimentacoes = conexao.execute("""
            SELECT
                movimentacoes.id,
                produtos.nome AS produto,
                movimentacoes.tipo,
                movimentacoes.quantidade,
                movimentacoes.data
            FROM movimentacoes
            INNER JOIN produtos
                ON movimentacoes.produto_id = produtos.id
            ORDER BY
                movimentacoes.data DESC,
                movimentacoes.id DESC
        """).fetchall()

    finally:
        conexao.close()

    return render_template(
        "historico.html",
        movimentacoes=movimentacoes
    )


# RELATÓRIO DE ESTOQUE
@app.route("/relatorio")
def relatorio():
    conexao = conectar()

    try:
        produtos = conexao.execute("""
            SELECT
                produtos.id,
                produtos.nome,
                categorias.nome AS categoria,
                produtos.quantidade,
                produtos.preco,
                (produtos.quantidade * produtos.preco) AS valor_total
            FROM produtos
            LEFT JOIN categorias
                ON produtos.categoria_id = categorias.id
            ORDER BY produtos.nome
        """).fetchall()

        totais = conexao.execute("""
            SELECT
                COUNT(*) AS total_produtos,
                COALESCE(SUM(quantidade), 0) AS total_unidades,
                COALESCE(SUM(quantidade * preco), 0) AS valor_estoque
            FROM produtos
        """).fetchone()

    finally:
        conexao.close()

    return render_template(
        "relatorio.html",
        produtos=produtos,
        totais=totais
    )


# EXECUÇÃO DO SISTEMA
if __name__ == "__main__":
    app.run(debug=True)
