# Extensao do sistema com gestao de usuarios e permissoes + templates com layout profissional

from flask import Flask, render_template, request, redirect, url_for, session, flash
import sqlite3, os
from datetime import datetime
from fpdf import FPDF

app = Flask(__name__)
app.secret_key = 'segredo'
DB = 'assistencia.db'

# Inicializa banco e cria tabelas com campos extras

def inicializar_banco():
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS usuarios (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        nome TEXT NOT NULL,
        login TEXT UNIQUE NOT NULL,
        senha TEXT NOT NULL,
        permissao TEXT DEFAULT 'admin'
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
        solucao TEXT,
        status TEXT DEFAULT 'Aberta',
        data_entrada TEXT,
        responsavel TEXT
    )''')
    c.execute("SELECT COUNT(*) FROM usuarios")
    if c.fetchone()[0] == 0:
        c.execute("INSERT INTO usuarios (nome, login, senha, permissao) VALUES (?, ?, ?, ?)",
                  ("Administrador", "admin", "admin", "admin"))
    conn.commit()
    conn.close()

# Rotas e lógica
@app.route('/', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        login = request.form['usuario']
        senha = request.form['senha']
        conn = sqlite3.connect(DB)
        c = conn.cursor()
        c.execute("SELECT * FROM usuarios WHERE login=? AND senha=?", (login, senha))
        usuario = c.fetchone()
        conn.close()
        if usuario:
            session['usuario'] = usuario[1]
            session['permissao'] = usuario[4]
            return redirect(url_for('nova_os'))
        else:
            flash('Login inválido')
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

@app.route('/cadastrar_usuario', methods=['GET', 'POST'])
def cadastrar_usuario():
    if 'permissao' not in session or session['permissao'] != 'admin':
        return redirect(url_for('login'))
    if request.method == 'POST':
        nome = request.form['nome']
        login = request.form['login']
        senha = request.form['senha']
        permissao = request.form['permissao']
        conn = sqlite3.connect(DB)
        c = conn.cursor()
        try:
            c.execute("INSERT INTO usuarios (nome, login, senha, permissao) VALUES (?, ?, ?, ?)",
                      (nome, login, senha, permissao))
            conn.commit()
            flash('Usuário cadastrado com sucesso')
        except:
            flash('Erro ao cadastrar usuário')
        conn.close()
    return render_template('cadastrar_usuario.html')

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
        data_entrada = datetime.now().strftime("%d/%m/%Y %H:%M")

        conn = sqlite3.connect(DB)
        c = conn.cursor()
        c.execute('''INSERT INTO ordens_servico
            (codigo_os, cliente, telefone, equipamento, numero_serie, itens_internos, defeito, data_entrada, responsavel)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)''',
            (codigo_os, cliente, telefone, equipamento, numero_serie, itens, defeito, data_entrada, responsavel))
        conn.commit()
        conn.close()
        flash(f"OS {codigo_os} criada com sucesso!")
        return redirect(url_for('nova_os'))
    return render_template('nova_os.html', usuario=session['usuario'])

if __name__ == '__main__':
    inicializar_banco()
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=True)
