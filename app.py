# Extensao do sistema com gestao de usuarios, permissoes, e dashboard com layout profissional

from flask import Flask, render_template, request, redirect, url_for, session, flash, send_file
import sqlite3, os
from datetime import datetime
from fpdf import FPDF # Certifique-se de que fpdf está instalado (pip install fpdf)
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
# MUDE ESTA CHAVE PARA UMA STRING LONGA, ALEATÓRIA E SEGURA EM PRODUÇÃO!
app.secret_key = 'aB3c#D5e@F7g$H9i!J1k%L2m^N4o&P6q*R8s+T0u=VwXyZ'
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
        # Inserir o hash da senha 'admin' para o usuário padrão
        hashed_admin_senha = generate_password_hash("admin")
        c.execute("INSERT INTO usuarios (nome, login, senha, permissao) VALUES (?, ?, ?, ?)",
                  ("Administrador", "admin", hashed_admin_senha, "admin"))
    conn.commit()
    conn.close()

# -- INÍCIO DA FUNÇÃO DE GERAÇÃO DE PDF APRIMORADA --
class PDF(FPDF):
    def header(self):
        self.set_fill_color(30, 144, 255) # Azul Royal
        self.rect(0, 0, self.w, 20, 'F')
        self.set_text_color(255, 255, 255) # Texto branco
        self.set_font("Arial", "B", 16)
        self.cell(0, 10, "Ordem de Serviço", 0, 1, 'C', fill=False)
        self.ln(10)

    def footer(self):
        self.set_y(-15)
        self.set_font("Arial", "I", 8)
        self.set_text_color(128, 128, 128) # Cinza
        self.cell(0, 10, f"Página {self.page_no()}/{{nb}}", 0, 0, 'C')

def gerar_pdf_os(os_dados):
    pdf = PDF()
    pdf.alias_nb_pages()
    pdf.add_page()
    pdf.set_auto_page_break(auto=True, margin=15) # Margem para o rodapé

    pdf.set_text_color(0, 0, 0) # Texto preto

    # Título principal da OS
    pdf.set_font("Arial", "B", 14)
    pdf.cell(0, 10, f"OS: {os_dados['codigo_os']}", 0, 1, 'L')
    pdf.set_font("Arial", "", 10)
    pdf.cell(0, 7, f"Data de Entrada: {os_dados['data_entrada']}", 0, 1, 'L')
    pdf.cell(0, 7, f"Responsável: {os_dados['responsavel']}", 0, 1, 'L')
    pdf.ln(5)

    # Informações do Cliente
    pdf.set_fill_color(220, 220, 220) # Cinza claro para o fundo
    pdf.set_font("Arial", "B", 12)
    pdf.cell(0, 8, "Dados do Cliente", 0, 1, 'L', fill=True)
    pdf.set_font("Arial", "", 10)
    pdf.cell(0, 7, f"Nome: {os_dados['cliente']}", 0, 1, 'L')
    pdf.cell(0, 7, f"Telefone: {os_dados['telefone']}", 0, 1, 'L')
    pdf.ln(5)

    # Informações do Equipamento
    pdf.set_font("Arial", "B", 12)
    pdf.cell(0, 8, "Dados do Equipamento", 0, 1, 'L', fill=True)
    pdf.set_font("Arial", "", 10)
    pdf.cell(0, 7, f"Tipo: {os_dados['equipamento']}", 0, 1, 'L')
    pdf.cell(0, 7, f"Número de Série: {os_dados['numero_serie']}", 0, 1, 'L')
    pdf.ln(5)

    # Itens Internos
    pdf.set_font("Arial", "B", 12)
    pdf.cell(0, 8, "Itens Internos", 0, 1, 'L', fill=True)
    pdf.set_font("Arial", "", 10)
    # Caixa de texto para itens internos
    pdf.multi_cell(0, 6, os_dados['itens_internos'], border=1, align='L')
    pdf.ln(5)

    # Defeito Relatado
    pdf.set_font("Arial", "B", 12)
    pdf.cell(0, 8, "Defeito Relatado", 0, 1, 'L', fill=True)
    pdf.set_font("Arial", "", 10)
    # Caixa de texto para defeito
    pdf.multi_cell(0, 6, os_dados['defeito'], border=1, align='L')
    pdf.ln(5)

    # Solução Aplicada e Status (condicionais)
    if 'solucao' in os_dados and os_dados['solucao']:
        pdf.set_font("Arial", "B", 12)
        pdf.cell(0, 8, "Solução Aplicada", 0, 1, 'L', fill=True)
        pdf.set_font("Arial", "", 10)
        # Caixa de texto para solução
        pdf.multi_cell(0, 6, os_dados['solucao'], border=1, align='L')
        pdf.ln(5)

    if 'status' in os_dados and os_dados['status']:
        pdf.set_font("Arial", "B", 12)
        pdf.cell(0, 8, "Status da OS", 0, 1, 'L', fill=True)
        pdf.set_font("Arial", "BU", 12) # Negrito e sublinhado
        pdf.cell(0, 10, f"{os_dados['status']}", 0, 1, 'C')
        pdf.ln(10)

    # Linha de assinatura
    pdf.ln(15)
    pdf.line(20, pdf.get_y(), pdf.w - 20, pdf.get_y())
    pdf.set_font("Arial", "", 10)
    pdf.cell(0, 10, "Assinatura do Cliente", 0, 1, 'C')


    filename = f"{PDF_DIR}/{os_dados['codigo_os']}.pdf"
    pdf.output(filename)
    return filename
# -- FIM DA FUNÇÃO DE GERAÇÃO DE PDF APRIMORADA --


# Rotas e lógica (sem alterações aqui, permanecem como na última versão)
@app.route('/', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        login = request.form['usuario']
        senha = request.form['senha']
        conn = sqlite3.connect(DB)
        c = conn.cursor()
        c.execute("SELECT * FROM usuarios WHERE login=?", (login,))
        usuario = c.fetchone()
        conn.close()
        if usuario and check_password_hash(usuario[3], senha):
            session['usuario'] = usuario[1]
            session['permissao'] = usuario[4]
            return redirect(url_for('dashboard'))
        else:
            flash('Login inválido', 'danger')
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

@app.route('/dashboard')
def dashboard():
    if 'usuario' not in session:
        return redirect(url_for('login'))

    conn = sqlite3.connect(DB)
    c = conn.cursor()

    c.execute("SELECT COUNT(*) FROM ordens_servico")
    total_os = c.fetchone()[0]

    c.execute("SELECT COUNT(*) FROM ordens_servico WHERE status = 'Aberta'")
    os_abertas = c.fetchone()[0]

    c.execute("SELECT COUNT(*) FROM ordens_servico WHERE status = 'Em Análise'")
    os_em_analise = c.fetchone()[0]

    c.execute("SELECT COUNT(*) FROM ordens_servico WHERE status = 'Finalizada'")
    os_finalizadas = c.fetchone()[0]

    conn.close()

    return render_template('dashboard.html',
                           usuario=session['usuario'],
                           permissao=session['permissao'],
                           total_os=total_os,
                           os_abertas=os_abertas,
                           os_em_analise=os_em_analise,
                           os_finalizadas=os_finalizadas)

@app.route('/cadastrar_usuario', methods=['GET', 'POST'])
def cadastrar_usuario():
    if 'permissao' not in session or session['permissao'] != 'admin':
        flash('Você não tem permissão para acessar esta página.', 'warning')
        return redirect(url_for('dashboard'))

    if request.method == 'POST':
        nome = request.form['nome']
        login = request.form['login']
        senha = request.form['senha']
        permissao = request.form['permissao']

        if not nome or not login or not senha or not permissao:
            flash('Todos os campos são obrigatórios.', 'danger')
            return render_template('cadastrar_usuario.html')

        conn = sqlite3.connect(DB)
        c = conn.cursor()
        try:
            hashed_senha = generate_password_hash(senha)
            c.execute("INSERT INTO usuarios (nome, login, senha, permissao) VALUES (?, ?, ?, ?)",
                      (nome, login, hashed_senha, permissao))
            conn.commit()
            flash('Usuário cadastrado com sucesso!', 'success')
        except sqlite3.IntegrityError:
            flash('Erro: O login informado já existe. Por favor, escolha outro.', 'danger')
        except Exception as e:
            flash(f'Erro ao cadastrar usuário: {e}', 'danger')
        finally:
            conn.close()
    return render_template('cadastrar_usuario.html')

@app.route('/nova_os', methods=['GET', 'POST'])
def nova_os():
    if 'usuario' not in session:
        return redirect(url_for('login'))
    if request.method == 'POST':
        cliente = request.form['cliente']
        telefone = request.form['telefone']
        equipamento = request.form['equipamento']
        numero_serie = request.form['numero_serie']
        itens = request.form['itens']
        defeito = request.form['defeito']
        responsavel = session['usuario']
        data_entrada = datetime.now().strftime("%d/%m/%Y %H:%M")

        if not cliente or not telefone or not equipamento or not numero_serie or not itens or not defeito:
            flash('Todos os campos com (*) são obrigatórios.', 'danger')
            return render_template('nova_os.html', usuario=session['usuario'])

        clean_telefone = ''.join(filter(str.isdigit, telefone))
        if not clean_telefone.isdigit():
            flash('O campo Telefone deve conter apenas números (opcionalmente com formatação comum como parênteses e traços).', 'danger')
            return render_template('nova_os.html', usuario=session['usuario'])


        codigo_os = f"OS-{datetime.now().strftime('%Y%m%d%H%M%S')}"

        conn = sqlite3.connect(DB)
        c = conn.cursor()
        try:
            c.execute('''INSERT INTO ordens_servico
                (codigo_os, cliente, telefone, equipamento, numero_serie, itens_internos, defeito, data_entrada, responsavel)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)''',
                (codigo_os, cliente, telefone, equipamento, numero_serie, itens, defeito, data_entrada, responsavel))
            conn.commit()

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
            flash(f"OS {codigo_os} criada com sucesso!", 'success')
            return redirect(url_for('ver_pdf_os', codigo_os=codigo_os))
        except Exception as e:
            flash(f'Erro ao criar OS: {e}', 'danger')
        finally:
            conn.close()
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
        
        c.execute("SELECT * FROM ordens_servico WHERE id=?", (id,))
        os_info = c.fetchone()
        conn.close()

        if os_info:
            os_dados_atualizados = {
                'codigo_os': os_info[1],
                'cliente': os_info[2],
                'telefone': os_info[3],
                'equipamento': os_info[4],
                'numero_serie': os_info[5],
                'itens_internos': os_info[6],
                'defeito': os_info[7],
                'solucao': os_info[8],
                'status': os_info[9],
                'data_entrada': os_info[10],
                'responsavel': os_info[11]
            }
            gerar_pdf_os(os_dados_atualizados)

        flash("OS atualizada com sucesso!", 'success')
        return redirect(url_for('listar_os'))
    else:
        c.execute("SELECT * FROM ordens_servico WHERE id=?", (id,))
        os_info = c.fetchone()
        conn.close()
        if not os_info:
            flash("OS não encontrada.", 'danger')
            return redirect(url_for('listar_os'))
        return render_template('editar_os.html', os=os_info, usuario=session['usuario'])

@app.route('/ver_pdf/<codigo_os>')
def ver_pdf_os(codigo_os):
    pdf_path = f"{PDF_DIR}/{codigo_os}.pdf"
    if os.path.exists(pdf_path):
        return send_file(pdf_path, as_attachment=False)
    else:
        flash("PDF não encontrado.", 'danger')
        return redirect(url_for('dashboard'))

if __name__ == '__main__':
    inicializar_banco()
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=True)