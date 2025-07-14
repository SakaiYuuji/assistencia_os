# Versão WebApp do sistema de Assistência Técnica (Flask)

from flask import Flask, render_template, request, redirect, url_for, session, flash, send_file
import sqlite3
import hashlib
from datetime import datetime
from fpdf import FPDF
import os

app = Flask(__name__)
app.secret_key = 'segredo_super_secreto'
DB_NOME = 'assistencia.db'

def inicializar_banco():
    conn = sqlite3.connect(DB_NOME)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS usuarios (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        nome TEXT NOT NULL,
        login TEXT UNIQUE NOT NULL,
        senha TEXT NOT NULL,
        admin INTEGER DEFAULT 0
    )''')
    c.execute('''CREATE TABLE IF NOT EXISTS ordens_servico (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        codigo_os TEXT,
        cliente TEXT,
        telefone TEXT,
        equipamento TEXT,
        numero_serie TEXT,
        itens_internos TEXT,
        defeito TEXT,
        data_entrada TEXT,
        responsavel TEXT
    )''')
    c.execute("SELECT COUNT(*) FROM usuarios")
    if c.fetchone()[0] == 0:
        senha = hashlib.sha256("admin".encode()).hexdigest()
        c.execute("INSERT INTO usuarios (nome, login, senha, admin) VALUES (?, ?, ?, 1)",
                  ("Administrador", "admin", senha))
    conn.commit()
    conn.close()

def verificar_login(usuario, senha):
    senha_hash = hashlib.sha256(senha.encode()).hexdigest()
    conn = sqlite3.connect(DB_NOME)
    c = conn.cursor()
    c.execute("SELECT * FROM usuarios WHERE login=? AND senha=?", (usuario, senha_hash))
    resultado = c.fetchone()
    conn.close()
    return resultado

def salvar_ordem(codigo_os, cliente, telefone, equipamento, numero_serie, itens_internos, defeito, responsavel):
    data_entrada = datetime.now().strftime("%d/%m/%Y %H:%M")
    conn = sqlite3.connect(DB_NOME)
    c = conn.cursor()
    c.execute('''INSERT INTO ordens_servico
        (codigo_os, cliente, telefone, equipamento, numero_serie, itens_internos, defeito, data_entrada, responsavel)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)''',
        (codigo_os, cliente, telefone, equipamento, numero_serie, itens_internos, defeito, data_entrada, responsavel))
    conn.commit()
    conn.close()

def gerar_pdf_os(dados):
    codigo_os, cliente, telefone, equipamento, numero_serie, itens_internos, defeito, responsavel = dados
    data_entrada = datetime.now().strftime("%d/%m/%Y %H:%M")
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", 'B', 14)
    pdf.cell(190, 10, f"Ordem de Serviço - {codigo_os}", ln=True, align='C')
    pdf.set_font("Arial", '', 12)
    pdf.cell(0, 10, f"Cliente: {cliente}", ln=True)
    pdf.cell(0, 10, f"Telefone: {telefone}", ln=True)
    pdf.cell(0, 10, f"Equipamento: {equipamento}", ln=True)
    pdf.cell(0, 10, f"Nº de Série: {numero_serie}", ln=True)
    pdf.multi_cell(0, 10, f"Itens Internos:\n{itens_internos}")
    pdf.multi_cell(0, 10, f"Defeito Relatado:\n{defeito}")
    pdf.cell(0, 10, f"Data de Entrada: {data_entrada}", ln=True)
    pdf.cell(0, 10, f"Responsável: {responsavel}", ln=True)
    pdf.ln(15)
    pdf.cell(0, 10, "Assinatura do Cliente: _________________________", ln=True)
    arquivo = f"{codigo_os}_{cliente.replace(' ', '_')}.pdf"
    pdf.output(arquivo)
    return arquivo

@app.route('/', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        usuario = request.form['usuario']
        senha = request.form['senha']
        user = verificar_login(usuario, senha)
        if user:
            session['usuario'] = user[1]
            return redirect(url_for('nova_os'))
        else:
            flash('Usuário ou senha inválidos')
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.pop('usuario', None)
    return redirect(url_for('login'))

@app.route('/nova_os', methods=['GET', 'POST'])
def nova_os():
    if 'usuario' not in session:
        return redirect(url_for('login'))
    if request.method == 'POST':
        codigo_os = f"OS-{datetime.now().strftime('%Y%m%d%H%M%S')}"
        cliente = request.form['cliente']
        telefone = request.form['telefone']
        equipamento = request.form['equipamento']
        numero_serie = request.form['numero_serie']
        itens = request.form['itens']
        defeito = request.form['defeito']
        responsavel = session['usuario']
        salvar_ordem(codigo_os, cliente, telefone, equipamento, numero_serie, itens, defeito, responsavel)
        arquivo = gerar_pdf_os((codigo_os, cliente, telefone, equipamento, numero_serie, itens, defeito, responsavel))
        return send_file(arquivo, as_attachment=True)
    return render_template('nova_os.html', usuario=session['usuario'])

if __name__ == '__main__':
    inicializar_banco()
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
