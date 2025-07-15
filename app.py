# Extensao do sistema com gestao de usuarios, permissoes, e dashboard com layout profissional

from flask import Flask, render_template, request, redirect, url_for, session, flash, send_file
import sqlite3, os
from datetime import datetime
from fpdf import FPDF

app = Flask(__name__)
app.secret_key = 'segredo'
DB = 'assistencia.db'
PDF_DIR = 'pdfs'
os.makedirs(PDF_DIR, exist_ok=True)

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

# Função para gerar o PDF da OS
def gerar_pdf_os(os_dados):
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", size=12)
    pdf.cell(200, 10, txt=f"Ordem de Serviço - {os_dados['codigo_os']}", ln=True, align='C')
    pdf.ln(10)
    pdf.cell(200, 10, txt=f"Cliente: {os_dados['cliente']}", ln=True)
    pdf.cell(200, 10, txt=f"Telefone: {os_dados['telefone']}", ln=True)
    pdf.cell(200, 10, txt=f"Equipamento: {os_dados['equipamento']}", ln=True)
    pdf.cell(200, 10, txt=f"Número de Série: {os_dados['numero_serie']}", ln=True)
    pdf.multi_cell(0, 10, txt=f"Itens Internos: {os_dados['itens_internos']}")
    pdf.multi_cell(0, 10, txt=f"Defeito Informado: {os_dados['defeito']}")
    pdf.cell(200, 10, txt=f"Data de Entrada: {os_dados['data_entrada']}", ln=True)
    pdf.cell(200, 10, txt=f"Responsável: {os_dados['responsavel']}", ln=True)
    filename = f"{PDF_DIR}/{os_dados['codigo_os']}.pdf"
    pdf.output(filename)
    return filename

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
            return redirect(url_for('dashboard'))
        else:
            flash('Login inválido')
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

@app.route('/dashboard')
def dashboard():
    if 'usuario' not in session:
        return redirect(url_for('login'))
    return render_template('dashboard.html', usuario=session['usuario'], permissao=session['permissao'])

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

        os_dados = {
            'codigo_os': codigo_os,
            'cliente': cliente,
            'telefone': telefone,
            'equipamento': equipamento,
            'numero_serie': numero_serie,
            'itens_internos': itens,
            'defeito': defeito,
            'data_entrada': data_entrada,
            'responsavel': responsavel
        }
        gerar_pdf_os(os_dados)
        flash(f"OS {codigo_os} criada com sucesso!")
        return redirect(url_for('ver_pdf_os', codigo_os=codigo_os))
    return render_template('nova_os.html', usuario=session['usuario'])

@app.route('/listar_os')
def listar_os():
    if 'usuario' not in session:
        return redirect(url_for('login'))

    filtro_cliente = request.args.get('cliente', '').strip()
    filtro_status = request.args.get('status', '').strip()

    conn = sqlite3.connect(DB)
    c = conn.cursor()

    query = "SELECT * FROM ordens_servico"
    params = []
    condicoes = []
    if filtro_cliente:
        condicoes.append("cliente LIKE ?")
        params.append(f"%{filtro_cliente}%")
    if filtro_status:
        condicoes.append("status = ?")
        params.append(filtro_status)
    if condicoes:
        query += " WHERE " + " AND ".join(condicoes)
    query += " ORDER BY id DESC"

    c.execute(query, params)
    ordens = c.fetchall()
    conn.close()
    return render_template('listar_os.html', ordens=ordens, usuario=session['usuario'], filtro_cliente=filtro_cliente, filtro_status=filtro_status)

@app.route('/editar_os/<int:id>', methods=['GET', 'POST'])
def editar_os(id):
    if 'usuario' not in session:
        return redirect(url_for('login'))
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    if request.method == 'POST':
        solucao = request.form['solucao']
        status = request.form['status']
        c.execute("UPDATE ordens_servico SET solucao=?, status=? WHERE id=?", (solucao, status, id))
        conn.commit()
        conn.close()
        flash("OS atualizada com sucesso!")
        return redirect(url_for('listar_os'))
    else:
        c.execute("SELECT * FROM ordens_servico WHERE id=?", (id,))
        os_info = c.fetchone()
        conn.close()
        return render_template('editar_os.html', os=os_info, usuario=session['usuario'])

@app.route('/ver_pdf/<codigo_os>')
def ver_pdf_os(codigo_os):
    pdf_path = f"{PDF_DIR}/{codigo_os}.pdf"
    if os.path.exists(pdf_path):
        return send_file(pdf_path, as_attachment=False)
    else:
        flash("PDF não encontrado.")
        return redirect(url_for('dashboard'))

if __name__ == '__main__':
    inicializar_banco()
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=True)
