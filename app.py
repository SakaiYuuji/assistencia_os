import sqlite3
import os
from datetime import datetime
from flask import Flask, render_template, request, redirect, url_for, session, flash, send_file
from fpdf import FPDF
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
app.secret_key = 'aB3c#D5e@F7g$H9i!J1k%L2m^N4o&P6q*R8s+T0u=VwXyZ'
DB = 'assistencia.db'
PDF_DIR = 'pdfs'
os.makedirs(PDF_DIR, exist_ok=True)

# Inicializa banco e cria tabelas com campos extras
def inicializar_banco():
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    
    # Tabela de Usuários Internos (admin, tecnico, atendente)
    c.execute('''CREATE TABLE IF NOT EXISTS usuarios (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        nome TEXT NOT NULL,
        login TEXT UNIQUE NOT NULL,
        senha TEXT NOT NULL,
        permissao TEXT DEFAULT 'admin' -- 'admin', 'tecnico', 'atendente'
    )''')

    # NOVO: Tabela de Clientes (dados gerais do cliente)
    c.execute('''CREATE TABLE IF NOT EXISTS clientes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        nome TEXT NOT NULL,
        cpf TEXT UNIQUE NOT NULL, -- CPF como identificador único para o cliente
        telefone TEXT
    )''')

    # NOVO: Tabela de Acessos Web para Clientes (login do cliente externo)
    c.execute('''CREATE TABLE IF NOT EXISTS clientes_web (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        id_cliente INTEGER NOT NULL,
        login TEXT UNIQUE NOT NULL,
        senha TEXT NOT NULL,
        FOREIGN KEY (id_cliente) REFERENCES clientes(id)
    )''')

    # Tabela de Ordens de Serviço (com FK para clientes)
    # Garante que a tabela é criada com todos os campos ou adiciona se já existir
    c.execute('''
        CREATE TABLE IF NOT EXISTS ordens_servico (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            codigo_os TEXT,
            id_cliente INTEGER, -- NOVO CAMPO: Chave estrangeira para a tabela 'clientes'
            cliente TEXT,       -- Mantido temporariamente para compatibilidade, será preenchido via id_cliente
            telefone TEXT,      -- Mantido temporariamente para compatibilidade, será preenchido via id_cliente
            equipamento TEXT,
            numero_serie TEXT,
            itens_internos TEXT,
            defeito TEXT,
            solucao TEXT DEFAULT '',
            status TEXT DEFAULT 'Aberta',
            data_entrada TEXT,
            responsavel TEXT,
            valor_orcamento REAL DEFAULT 0.0,
            valor_servico_executado REAL DEFAULT 0.0,
            pecas_adicionadas TEXT DEFAULT '',
            valor_pecas REAL DEFAULT 0.0,
            nome_aprovacao_cliente TEXT DEFAULT '',
            data_aprovacao_cliente TEXT DEFAULT '',
            FOREIGN KEY (id_cliente) REFERENCES clientes(id)
        )
    ''')
    
    # --- Verificações e ALTER TABLE para compatibilidade com bancos existentes ---
    c.execute("PRAGMA table_info(ordens_servico)")
    columns_os = [info[1] for info in c.fetchall()]

    if 'valor_orcamento' not in columns_os:
        c.execute("ALTER TABLE ordens_servico ADD COLUMN valor_orcamento REAL DEFAULT 0.0")
    if 'valor_servico_executado' not in columns_os:
        c.execute("ALTER TABLE ordens_servico ADD COLUMN valor_servico_executado REAL DEFAULT 0.0")
    if 'pecas_adicionadas' not in columns_os:
        c.execute("ALTER TABLE ordens_servico ADD COLUMN pecas_adicionadas TEXT DEFAULT ''")
    if 'valor_pecas' not in columns_os:
        c.execute("ALTER TABLE ordens_servico ADD COLUMN valor_pecas REAL DEFAULT 0.0")
    if 'nome_aprovacao_cliente' not in columns_os:
        c.execute("ALTER TABLE ordens_servico ADD COLUMN nome_aprovacao_cliente TEXT DEFAULT ''")
    if 'data_aprovacao_cliente' not in columns_os:
        c.execute("ALTER TABLE ordens_servico ADD COLUMN data_aprovacao_cliente TEXT DEFAULT ''")
    if 'id_cliente' not in columns_os: # Adiciona id_cliente para OS existentes
        c.execute("ALTER TABLE ordens_servico ADD COLUMN id_cliente INTEGER")
    if 'solucao' not in columns_os: # Garante que solucao tem default
        c.execute("ALTER TABLE ordens_servico ADD COLUMN solucao TEXT DEFAULT ''")

    # -----------------------------------------------------------------------------

    # Insere usuário admin padrão se não existir
    c.execute("SELECT COUNT(*) FROM usuarios")
    if c.fetchone()[0] == 0:
        hashed_admin_senha = generate_password_hash("admin")
        c.execute("INSERT INTO usuarios (nome, login, senha, permissao) VALUES (?, ?, ?, ?)",
                  ("Administrador", "admin", hashed_admin_senha, "admin"))
    conn.commit()
    conn.close()

# -- FUNÇÃO DE GERAÇÃO DE PDF APRIMORADA (com valor de orçamento, serviço executado, peças e APROVAÇÃO) --
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
    pdf.set_auto_page_break(auto=True, margin=15)

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
    pdf.cell(0, 7, f"Nome: {os_dados['cliente']}", 0, 1, 'L') # Usa o campo 'cliente' que virá do join
    pdf.cell(0, 7, f"Telefone: {os_dados['telefone']}", 0, 1, 'L') # Usa o campo 'telefone' que virá do join
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
    pdf.multi_cell(0, 6, os_dados['itens_internos'], border=1, align='L')
    pdf.ln(5)

    # Defeito Relatado
    pdf.set_font("Arial", "B", 12)
    pdf.cell(0, 8, "Defeito Relatado", 0, 1, 'L', fill=True)
    pdf.set_font("Arial", "", 10)
    pdf.multi_cell(0, 6, os_dados['defeito'], border=1, align='L')
    pdf.ln(5)

    # Solução Aplicada (condicionais)
    if 'solucao' in os_dados and os_dados['solucao']:
        pdf.set_font("Arial", "B", 12)
        pdf.cell(0, 8, "Solução Aplicada", 0, 1, 'L', fill=True)
        pdf.set_font("Arial", "", 10)
        pdf.multi_cell(0, 6, os_dados['solucao'], border=1, align='L')
        pdf.ln(5)
    
    # Peças e Materiais
    if ('pecas_adicionadas' in os_dados and os_dados['pecas_adicionadas']) or \
       ('valor_pecas' in os_dados and os_dados['valor_pecas'] is not None and os_dados['valor_pecas'] > 0):
        pdf.set_fill_color(240, 248, 255) # Azul claro para o fundo
        pdf.set_font("Arial", "B", 12)
        pdf.cell(0, 8, "Peças e Materiais", 0, 1, 'L', fill=True)
        pdf.set_font("Arial", "", 10)
        if 'pecas_adicionadas' in os_dados and os_dados['pecas_adicionadas']:
            pdf.multi_cell(0, 6, os_dados['pecas_adicionadas'], border=1, align='L')
        if 'valor_pecas' in os_dados and os_dados['valor_pecas'] is not None and os_dados['valor_pecas'] > 0:
            pdf.cell(0, 7, f"Valor das Peças: R$ {os_dados['valor_pecas']:.2f}", 0, 1, 'L')
        pdf.ln(5)

    # Valores (Orçamento e Serviço Executado)
    pdf.set_fill_color(200, 230, 255) # Azul claro para o fundo
    pdf.set_font("Arial", "B", 14)
    pdf.cell(0, 8, "Valores", 0, 1, 'L', fill=True)
    
    if 'valor_orcamento' in os_dados and os_dados['valor_orcamento'] is not None:
        pdf.set_font("Arial", "", 12)
        pdf.cell(0, 7, f"Valor Orçado: R$ {os_dados['valor_orcamento']:.2f}", 0, 1, 'L')
    
    # Se valor_servico_executado for diferente de 0 e diferente do orçado, mostra como final
    if 'valor_servico_executado' in os_dados and os_dados['valor_servico_executado'] is not None and os_dados['valor_servico_executado'] > 0 and os_dados['valor_servico_executado'] != os_dados['valor_orcamento']:
        pdf.set_font("Arial", "B", 14)
        pdf.set_text_color(0, 128, 0) # Verde escuro
        pdf.cell(0, 10, f"Valor do Serviço: R$ {os_dados['valor_servico_executado']:.2f}", 0, 1, 'L')
        pdf.set_text_color(0, 0, 0) # Retorna para preto
    
    # Calcula o valor total
    valor_total = 0.0
    # Prioriza valor_servico_executado para o cálculo do serviço, senão usa o orçado
    if 'valor_servico_executado' in os_dados and os_dados['valor_servico_executado'] is not None:
        valor_total += os_dados['valor_servico_executado']
    elif 'valor_orcamento' in os_dados and os_dados['valor_orcamento'] is not None:
        valor_total += os_dados['valor_orcamento']
        
    if 'valor_pecas' in os_dados and os_dados['valor_pecas'] is not None:
        valor_total += os_dados['valor_pecas']

    # Exibe o valor total se for maior que zero
    if valor_total > 0:
        pdf.set_font("Arial", "B", 16)
        pdf.set_text_color(0, 0, 128) # Azul escuro
        pdf.cell(0, 12, f"VALOR TOTAL: R$ {valor_total:.2f}", 0, 1, 'C')
        pdf.set_text_color(0, 0, 0) # Retorna para preto
    
    pdf.ln(5)

    # --- SEÇÃO DE APROVAÇÃO DO CLIENTE NO PDF ---
    if 'nome_aprovacao_cliente' in os_dados and os_dados['nome_aprovacao_cliente']:
        pdf.set_fill_color(220, 255, 220) # Verde claro para o fundo
        pdf.set_font("Arial", "B", 12)
        pdf.cell(0, 8, "Confirmação do Cliente", 0, 1, 'L', fill=True)
        pdf.set_font("Arial", "", 10)
        pdf.multi_cell(0, 6, f"Aprovado por: {os_dados['nome_aprovacao_cliente']}\nEm: {os_dados['data_aprovacao_cliente']}", border=1, align='L')
        pdf.ln(5)
    # --- FIM DA SEÇÃO DE APROVAÇÃO DO CLIENTE NO PDF ---

    # Status (condicionais)
    if 'status' in os_dados and os_dados['status']:
        pdf.set_font("Arial", "B", 12)
        pdf.set_text_color(255, 0, 0) # Cor vermelha para o status
        pdf.cell(0, 8, "Status da OS", 0, 1, 'L', fill=True)
        pdf.set_font("Arial", "BU", 12) # Negrito e sublinhado
        pdf.cell(0, 10, f"{os_dados['status']}", 0, 1, 'C')
        pdf.set_text_color(0, 0, 0) # Retorna para preto
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


# Rotas e lógica (atualizadas para incluir os novos campos de valor e peças)
@app.route('/', methods=['GET', 'POST'])
def login():
    if 'usuario_id' in session and 'permissao' in session: # Se já logado, redireciona
        if session['permissao'] == 'cliente':
            return redirect(url_for('cliente_dashboard'))
        else:
            return redirect(url_for('dashboard'))

    if request.method == 'POST':
        login_input = request.form['usuario']
        senha_input = request.form['senha']
        conn = sqlite3.connect(DB)
        c = conn.cursor()
        
        # Tenta autenticar como usuário interno (admin, tecnico, atendente)
        c.execute("SELECT id, nome, login, senha, permissao FROM usuarios WHERE login=?", (login_input,))
        usuario = c.fetchone()
        if usuario and check_password_hash(usuario[3], senha_input):
            session['usuario_id'] = usuario[0]
            session['usuario_nome'] = usuario[1]
            session['permissao'] = usuario[4]
            conn.close()
            return redirect(url_for('dashboard'))
        
        # Tenta autenticar como cliente web
        c.execute("SELECT cw.id, cw.id_cliente, c.nome, cw.senha FROM clientes_web cw JOIN clientes c ON cw.id_cliente = c.id WHERE cw.login=?", (login_input,))
        cliente_web = c.fetchone()
        if cliente_web and check_password_hash(cliente_web[3], senha_input):
            session['usuario_id'] = cliente_web[0] # id do clientes_web
            session['id_cliente_associado'] = cliente_web[1] # id da tabela clientes
            session['usuario_nome'] = cliente_web[2] # nome do cliente
            session['permissao'] = 'cliente'
            conn.close()
            return redirect(url_for('cliente_dashboard'))
        
        conn.close()
        flash('Login inválido', 'danger')
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

@app.route('/dashboard')
def dashboard():
    if 'usuario_id' not in session or session['permissao'] == 'cliente':
        flash('Acesso não autorizado.', 'danger')
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
                           usuario=session['usuario_nome'],
                           permissao=session['permissao'],
                           total_os=total_os,
                           os_abertas=os_abertas,
                           os_em_analise=os_em_analise,
                           os_finalizadas=os_finalizadas)

# --- NOVO: Dashboard para Clientes ---
@app.route('/cliente_dashboard')
def cliente_dashboard():
    if 'usuario_id' not in session or session['permissao'] != 'cliente':
        flash('Acesso não autorizado.', 'danger')
        return redirect(url_for('login'))

    id_cliente = session['id_cliente_associado']
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    # Seleciona as OS vinculadas a este id_cliente
    c.execute("""
        SELECT 
            os.id, os.codigo_os, c.nome, c.telefone, os.equipamento, os.numero_serie, os.itens_internos, 
            os.defeito, os.solucao, os.status, os.data_entrada, os.responsavel, os.valor_orcamento,
            os.valor_servico_executado, os.pecas_adicionadas, os.valor_pecas,
            os.nome_aprovacao_cliente, os.data_aprovacao_cliente
        FROM ordens_servico os
        JOIN clientes c ON os.id_cliente = c.id
        WHERE os.id_cliente = ? ORDER BY os.id DESC
    """, (id_cliente,))
    ordens = c.fetchall()
    conn.close()

    return render_template('cliente_dashboard.html',
                           usuario=session['usuario_nome'],
                           ordens=ordens)
# --- FIM DO NOVO: Dashboard para Clientes ---


@app.route('/cadastrar_usuario', methods=['GET', 'POST'])
def cadastrar_usuario():
    # Apenas admin pode cadastrar usuários internos
    if 'permissao' not in session or session['permissao'] != 'admin':
        flash('Você não tem permissão para acessar esta página.', 'warning')
        return redirect(url_for('dashboard'))

    if request.method == 'POST':
        nome = request.form['nome']
        login = request.form['login']
        senha = request.form['senha']
        permissao = request.form['permissao'] # 'admin', 'tecnico', 'atendente'

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
            flash('Usuário interno cadastrado com sucesso!', 'success')
        except sqlite3.IntegrityError:
            flash('Erro: O login informado já existe. Por favor, escolha outro.', 'danger')
        except Exception as e:
            flash(f'Erro ao cadastrar usuário: {e}', 'danger')
        finally:
            conn.close()
    return render_template('cadastrar_usuario.html')

@app.route('/editar_usuario/<int:usuario_id>', methods=['GET', 'POST'])
def editar_usuario(usuario_id):
    # Verifica se o usuário logado tem permissão para editar (ex: 'admin')
    if 'usuario_id' not in session or session.get('permissao') != 'admin':
        flash('Acesso negado. Você não tem permissão para editar usuários.', 'danger')
        return redirect(url_for('dashboard')) # Ou para a página de login

    conn = None
    try:
        conn = sqlite3.connect('seu_banco_de_dados.db') # Use o nome correto do seu DB
        cursor = conn.cursor()

        if request.method == 'POST':
            # Processa os dados do formulário de edição
            nome = request.form['nome']
            login = request.form['login']
            permissao = request.form['permissao']
            senha_nova = request.form.get('senha_nova') # Senha é opcional na edição

            # Verifica se o novo login já existe para outro usuário
            cursor.execute("SELECT id FROM usuarios WHERE login = ? AND id != ?", (login, usuario_id))
            if cursor.fetchone():
                flash('Erro: O login informado já está em uso por outro usuário.', 'danger')
                # Busca o usuário novamente para preencher o formulário com os dados atuais
                cursor.execute("SELECT id, nome, login, permissao FROM usuarios WHERE id = ?", (usuario_id,))
                usuario = cursor.fetchone()
                return render_template('editar_usuario.html', usuario=usuario)

            # Atualiza os dados do usuário
            if senha_nova:
                hashed_password = generate_password_hash(senha_nova, method='pbkdf2:sha256')
                cursor.execute("UPDATE usuarios SET nome = ?, login = ?, senha = ?, permissao = ? WHERE id = ?",
                               (nome, login, hashed_password, permissao, usuario_id))
            else:
                cursor.execute("UPDATE usuarios SET nome = ?, login = ?, permissao = ? WHERE id = ?",
                               (nome, login, permissao, usuario_id))
            conn.commit()
            flash('Usuário atualizado com sucesso!', 'success')
            return redirect(url_for('listar_usuarios')) # Redireciona para uma lista de usuários

        else: # Método GET: Exibe o formulário com os dados atuais
            cursor.execute("SELECT id, nome, login, permissao FROM usuarios WHERE id = ?", (usuario_id,))
            usuario = cursor.fetchone() # Retorna uma tupla ou None

            if usuario:
                # Converte a tupla para um dicionário para facilitar o acesso no template
                usuario_dict = {
                    'id': usuario[0],
                    'nome': usuario[1],
                    'login': usuario[2],
                    'permissao': usuario[3]
                }
                return render_template('editar_usuario.html', usuario=usuario_dict)
            else:
                flash('Usuário não encontrado.', 'danger')
                return redirect(url_for('listar_usuarios')) # Ou para o dashboard

    except sqlite3.Error as e:
        if conn: conn.rollback()
        flash(f'Ocorreu um erro no banco de dados: {e}', 'danger')
    except Exception as e:
        if conn: conn.rollback()
        flash(f'Ocorreu um erro inesperado: {e}', 'danger')
    finally:
        if conn: conn.close()
    
    return redirect(url_for('dashboard')) # Em caso de erro grave, redireciona

# Você também precisará de uma rota para listar usuários, se ainda não tiver
@app.route('/listar_usuarios')
def listar_usuarios():
    if 'usuario_id' not in session or session.get('permissao') != 'admin':
        flash('Acesso negado.', 'danger')
        return redirect(url_for('dashboard'))
    
    conn = sqlite3.connect('seu_banco_de_dados.db')
    cursor = conn.cursor()
    cursor.execute("SELECT id, nome, login, permissao FROM usuarios")
    usuarios = cursor.fetchall()
    conn.close()
    return render_template('listar_usuarios.html', usuarios=usuarios)

# --- NOVO: Rotas de Gerenciamento de Clientes (para Admin/Atendente) ---
@app.route('/cadastrar_cliente', methods=['GET', 'POST'])
def cadastrar_cliente():
    if 'permissao' not in session or session['permissao'] not in ['admin', 'atendente']:
        flash('Você não tem permissão para acessar esta página.', 'warning')
        return redirect(url_for('dashboard'))

    if request.method == 'POST':
        nome = request.form['nome'].strip()
        cpf = request.form['cpf'].strip()
        telefone = request.form['telefone'].strip()

        if not nome or not cpf:
            flash('Nome e CPF são campos obrigatórios.', 'danger')
            return render_template('cadastrar_cliente.html')
        
        conn = sqlite3.connect(DB)
        c = conn.cursor()
        try:
            c.execute("INSERT INTO clientes (nome, cpf, telefone) VALUES (?, ?, ?)",
                      (nome, cpf, telefone))
            conn.commit()
            flash('Cliente cadastrado com sucesso!', 'success')
            return redirect(url_for('listar_clientes')) # Redireciona para a lista de clientes após o sucesso
        except sqlite3.IntegrityError:
            flash('Erro: Já existe um cliente com este CPF.', 'danger')
        except Exception as e:
            flash(f'Erro ao cadastrar cliente: {e}', 'danger')
        finally:
            conn.close()
    return render_template('cadastrar_cliente.html')

@app.route('/listar_clientes')
def listar_clientes():
    if 'permissao' not in session or session['permissao'] not in ['admin', 'atendente', 'tecnico']:
        flash('Você não tem permissão para acessar esta página.', 'warning')
        return redirect(url_for('dashboard'))

    conn = sqlite3.connect(DB)
    c = conn.cursor()
    # Junta com clientes_web para verificar se o cliente tem acesso web
    c.execute("""
        SELECT c.id, c.nome, c.cpf, c.telefone, cw.login IS NOT NULL AS tem_acesso_web
        FROM clientes c
        LEFT JOIN clientes_web cw ON c.id = cw.id_cliente
        ORDER BY c.nome
    """)
    clientes = c.fetchall()
    conn.close()
    return render_template('listar_clientes.html', clientes=clientes)

@app.route('/editar_cliente/<int:id>', methods=['GET', 'POST'])
def editar_cliente(id):
    if 'permissao' not in session or session['permissao'] not in ['admin', 'atendente']:
        flash('Você não tem permissão para acessar esta página.', 'warning')
        return redirect(url_for('dashboard'))

    conn = sqlite3.connect(DB)
    c = conn.cursor()

    if request.method == 'POST':
        nome = request.form['nome'].strip()
        cpf = request.form['cpf'].strip()
        telefone = request.form['telefone'].strip()
        
        # Lógica para criação/edição de acesso web para o cliente
        criar_acesso_web = request.form.get('criar_acesso_web')
        login_web = request.form.get('login_web', '').strip()
        senha_web = request.form.get('senha_web', '').strip()
        
        if not nome or not cpf:
            flash('Nome e CPF são campos obrigatórios para o cliente.', 'danger')
            # Busca novamente os dados para re-renderizar
            c.execute("SELECT id, nome, cpf, telefone FROM clientes WHERE id=?", (id,))
            cliente_info = c.fetchone()
            c.execute("SELECT login FROM clientes_web WHERE id_cliente=?", (id,))
            cliente_web_info = c.fetchone()
            conn.close()
            return render_template('editar_cliente.html', cliente=cliente_info, cliente_web_login=cliente_web_info[0] if cliente_web_info else None)


        try:
            # Atualiza dados do cliente
            c.execute("UPDATE clientes SET nome=?, cpf=?, telefone=? WHERE id=?", 
                      (nome, cpf, telefone, id))
            conn.commit()
            flash('Dados do cliente atualizados com sucesso!', 'success')

            # Lógica para acesso web
            c.execute("SELECT id FROM clientes_web WHERE id_cliente=?", (id,))
            acesso_web_existente = c.fetchone()

            if criar_acesso_web and not acesso_web_existente:
                if not login_web or not senha_web:
                    flash('Login e Senha para o acesso web são obrigatórios.', 'danger')
                else:
                    hashed_senha_web = generate_password_hash(senha_web)
                    c.execute("INSERT INTO clientes_web (id_cliente, login, senha) VALUES (?, ?, ?)",
                              (id, login_web, hashed_senha_web))
                    conn.commit()
                    flash(f'Acesso web criado para o cliente {nome} com login: {login_web}!', 'success')
            elif criar_acesso_web and acesso_web_existente:
                 flash('Este cliente já possui acesso web. Desmarque "Criar Acesso Web" se quiser apenas editar os dados do cliente.', 'info')
            elif not criar_acesso_web and acesso_web_existente and (login_web or senha_web): # Se desmarcou mas tentou mudar dados
                 flash('Acesso web existente. Para criar novo acesso, exclua o existente primeiro (funcionalidade futura).', 'info')


        except sqlite3.IntegrityError:
            flash('Erro: Já existe outro cliente com este CPF.', 'danger')
        except Exception as e:
            flash(f'Erro ao atualizar cliente ou criar acesso web: {e}', 'danger')
        finally:
            conn.close()
            # Redireciona para evitar reenvio do form e atualiza a página
            return redirect(url_for('editar_cliente', id=id))
    else:
        # GET: Busca dados do cliente e se ele tem acesso web
        c.execute("SELECT id, nome, cpf, telefone FROM clientes WHERE id=?", (id,))
        cliente_info = c.fetchone()
        if not cliente_info:
            conn.close()
            flash("Cliente não encontrado.", 'danger')
            return redirect(url_for('listar_clientes'))
        
        c.execute("SELECT login FROM clientes_web WHERE id_cliente=?", (id,))
        cliente_web_info = c.fetchone()
        conn.close()

        return render_template('editar_cliente.html', 
                               cliente=cliente_info, 
                               cliente_web_login=cliente_web_info[0] if cliente_web_info else None,
                               permissao=session['permissao']) # Passa permissao para o template
@app.route('/alterar_senha_cliente', methods=['GET', 'POST'])
def alterar_senha_cliente():
    # Verifica se o usuário está logado e se é um 'cliente' (ou qualquer permissão que você defina para clientes)
    if 'usuario_id' not in session:
        flash('Você precisa estar logado para alterar sua senha.', 'danger')
        return redirect(url_for('login'))
    
    # Opcional: Se você quiser que apenas clientes com a permissão 'cliente' possam usar esta rota
    # if session.get('permissao') != 'cliente':
    #     flash('Acesso negado. Esta função é apenas para clientes.', 'danger')
    #     return redirect(url_for('dashboard'))

    conn = None
    try:
        conn = sqlite3.connect('seu_banco_de_dados.db') # Use o nome correto do seu DB
        cursor = conn.cursor()

        if request.method == 'POST':
            senha_atual = request.form['senha_atual']
            nova_senha = request.form['nova_senha']
            confirmar_nova_senha = request.form['confirmar_nova_senha']

            # 1. Buscar a senha hashed do usuário logado no DB
            cursor.execute("SELECT senha FROM usuarios WHERE id = ?", (session['usuario_id'],))
            usuario_db = cursor.fetchone()

            if not usuario_db:
                flash('Erro: Usuário não encontrado.', 'danger')
                return redirect(url_for('logout')) # Algo deu errado com a sessão
            
            senha_hashed_db = usuario_db[0]

            # 2. Verificar se a senha atual digitada corresponde à senha no DB
            if not check_password_hash(senha_hashed_db, senha_atual):
                flash('Senha atual incorreta.', 'danger')
                return render_template('alterar_senha_cliente.html')

            # 3. Verificar se a nova senha e a confirmação são iguais
            if nova_senha != confirmar_nova_senha:
                flash('A nova senha e a confirmação não coincidem.', 'danger')
                return render_template('alterar_senha_cliente.html')
            
            # 4. Verificar se a nova senha é diferente da antiga (opcional, mas boa prática)
            if check_password_hash(senha_hashed_db, nova_senha):
                flash('A nova senha não pode ser igual à senha atual.', 'warning')
                return render_template('alterar_senha_cliente.html')

            # 5. Gerar hash da nova senha e atualizar no DB
            hashed_nova_senha = generate_password_hash(nova_senha, method='pbkdf2:sha256')
            cursor.execute("UPDATE usuarios SET senha = ? WHERE id = ?",
                           (hashed_nova_senha, session['usuario_id']))
            conn.commit()
            flash('Sua senha foi alterada com sucesso!', 'success')
            return redirect(url_for('dashboard')) # Redireciona para o dashboard após a alteração

        else: # Método GET: Exibe o formulário
            return render_template('alterar_senha_cliente.html')

    except sqlite3.Error as e:
        if conn: conn.rollback()
        flash(f'Ocorreu um erro no banco de dados: {e}', 'danger')
    except Exception as e:
        if conn: conn.rollback()
        flash(f'Ocorreu um erro inesperado: {e}', 'danger')
    finally:
        if conn: conn.close()
    
    return redirect(url_for('dashboard')) # Em caso de erro grave, redireciona
    
# --- FIM DO NOVO: Rotas de Gerenciamento de Clientes ---

@app.route('/nova_os', methods=['GET', 'POST'])
def nova_os():
    if 'usuario_id' not in session or session['permissao'] == 'cliente':
        flash('Você não tem permissão para acessar esta página.', 'danger')
        return redirect(url_for('login'))
    
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    # Busca clientes para o dropdown
    c.execute("SELECT id, nome, cpf FROM clientes ORDER BY nome")
    clientes_cadastrados = c.fetchall()
    conn.close()

    if request.method == 'POST':
        id_cliente = request.form['id_cliente'] # NOVO: Pega o ID do cliente selecionado
        equipamento = request.form['equipamento']
        numero_serie = request.form['numero_serie']
        itens = request.form['itens']
        defeito = request.form['defeito']
        responsavel = session['usuario_nome']
        data_entrada = datetime.now().strftime("%d/%m/%Y %H:%M")
        valor_orcamento_str = request.form['valor_orcamento'].replace(',', '.') 

        if not id_cliente or not equipamento or not numero_serie or not itens or not defeito or not valor_orcamento_str:
            flash('Todos os campos com (*) são obrigatórios.', 'danger')
            return render_template('nova_os.html', usuario=session['usuario_nome'], clientes_cadastrados=clientes_cadastrados)

        try:
            valor_orcamento = float(valor_orcamento_str)
        except ValueError:
            flash('O campo "Valor do Orçamento" deve ser um número válido.', 'danger')
            return render_template('nova_os.html', usuario=session['usuario_nome'], clientes_cadastrados=clientes_cadastrados)

        codigo_os = f"OS-{datetime.now().strftime('%Y%m%d%H%M%S')}"

        conn = sqlite3.connect(DB)
        c = conn.cursor()
        try:
            # Pega nome e telefone do cliente selecionado
            c.execute("SELECT nome, telefone FROM clientes WHERE id=?", (id_cliente,))
            cliente_info = c.fetchone()
            cliente_nome = cliente_info[0]
            cliente_telefone = cliente_info[1]

            # Inclui id_cliente na inserção
            c.execute('''INSERT INTO ordens_servico
                (codigo_os, id_cliente, cliente, telefone, equipamento, numero_serie, itens_internos, defeito, data_entrada, responsavel, valor_orcamento, pecas_adicionadas, valor_pecas, nome_aprovacao_cliente, data_aprovacao_cliente)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
                (codigo_os, id_cliente, cliente_nome, cliente_telefone, equipamento, numero_serie, itens, defeito, data_entrada, responsavel, valor_orcamento, '', 0.0, '', ''))
            conn.commit()

            os_dados = { # Usa cliente_nome e cliente_telefone do DB para PDF
                'codigo_os': codigo_os,
                'cliente': cliente_nome, 
                'telefone': cliente_telefone,
                'equipamento': equipamento,
                'numero_serie': numero_serie,
                'itens_internos': itens,
                'defeito': defeito,
                'data_entrada': data_entrada,
                'responsavel': responsavel,
                'valor_orcamento': valor_orcamento,
                'valor_servico_executado': 0.0,
                'pecas_adicionadas': '',
                'valor_pecas': 0.0,
                'nome_aprovacao_cliente': '',
                'data_aprovacao_cliente': ''
            }
            gerar_pdf_os(os_dados)
            flash(f"OS **{codigo_os}** criada com sucesso! <a href='{url_for('ver_pdf_os', codigo_os=codigo_os)}' class='btn btn-sm btn-primary ms-3' target='_blank'>Visualizar/Imprimir OS</a>", 'success')
            return redirect(url_for('nova_os'))

        except Exception as e:
            flash(f'Erro ao criar OS: {e}', 'danger')
        finally:
            conn.close()
    return render_template('nova_os.html', usuario=session['usuario_nome'], clientes_cadastrados=clientes_cadastrados)

@app.route('/listar_os')
def listar_os():
    if 'usuario_id' not in session or session['permissao'] == 'cliente':
        flash('Você não tem permissão para acessar esta página.', 'danger')
        return redirect(url_for('login'))

    filtro_cliente_nome = request.args.get('cliente', '').strip() # Filtra por nome do cliente
    filtro_status = request.args.get('status', '').strip()

    conn = sqlite3.connect(DB)
    c = conn.cursor()

    query = """
        SELECT 
            os.id, os.codigo_os, c.nome, c.telefone, os.equipamento, os.numero_serie, os.itens_internos, 
            os.defeito, os.solucao, os.status, os.data_entrada, os.responsavel, os.valor_orcamento,
            os.valor_servico_executado, os.pecas_adicionadas, os.valor_pecas,
            os.nome_aprovacao_cliente, os.data_aprovacao_cliente
        FROM ordens_servico os
        JOIN clientes c ON os.id_cliente = c.id
    """
    params = []
    condicoes = []
    if filtro_cliente_nome:
        condicoes.append("c.nome LIKE ?")
        params.append(f"%{filtro_cliente_nome}%")
    if filtro_status:
        condicoes.append("os.status = ?")
        params.append(filtro_status)
    if condicoes:
        query += " WHERE " + " AND ".join(condicoes)
    query += " ORDER BY os.id DESC"

    c.execute(query, params)
    ordens = c.fetchall()
    conn.close()
    return render_template('listar_os.html', ordens=ordens, usuario=session['usuario_nome'], filtro_cliente=filtro_cliente_nome, filtro_status=filtro_status)


@app.route('/editar_os/<int:id>', methods=['GET', 'POST'])
def editar_os(id):
    if 'usuario_id' not in session or session['permissao'] == 'cliente':
        flash('Você não tem permissão para acessar esta página.', 'danger')
        return redirect(url_for('login'))
    
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    if request.method == 'POST':
        solucao = request.form['solucao']
        status = request.form['status']
        valor_orcamento_str = request.form['valor_orcamento'].replace(',', '.') 
        valor_servico_executado_str = request.form.get('valor_servico_executado', '0.0').replace(',', '.')
        pecas_adicionadas = request.form.get('pecas_adicionadas', '').strip()
        valor_pecas_str = request.form.get('valor_pecas', '0.0').replace(',', '.')
        
        try:
            valor_orcamento = float(valor_orcamento_str)
            valor_servico_executado = float(valor_servico_executado_str)
            valor_pecas = float(valor_pecas_str)
        except ValueError:
            flash('Os campos de valor devem ser números válidos.', 'danger')
            # Re-seleciona a OS para re-renderizar com dados atuais e a mensagem de erro
            c.execute("""
                SELECT 
                    os.id, os.codigo_os, c.nome, c.telefone, os.equipamento, os.numero_serie, os.itens_internos, 
                    os.defeito, os.solucao, os.status, os.data_entrada, os.responsavel, os.valor_orcamento,
                    os.valor_servico_executado, os.pecas_adicionadas, os.valor_pecas,
                    os.nome_aprovacao_cliente, os.data_aprovacao_cliente, os.id_cliente
                FROM ordens_servico os
                JOIN clientes c ON os.id_cliente = c.id
                WHERE os.id=?
            """, (id,))
            os_info = c.fetchone()
            conn.close()
            return render_template('editar_os.html', os=os_info, usuario=session['usuario_nome'])


        # NOVO: Seleciona todos os campos existentes e os novos para atualização
        # NOTA: nome_aprovacao_cliente e data_aprovacao_cliente NÃO são atualizados aqui,
        # apenas pela rota de aprovação pública.
        c.execute("UPDATE ordens_servico SET solucao=?, status=?, valor_orcamento=?, valor_servico_executado=?, pecas_adicionadas=?, valor_pecas=? WHERE id=?", 
                  (solucao, status, valor_orcamento, valor_servico_executado, pecas_adicionadas, valor_pecas, id))
        conn.commit()
        
        # Re-seleciona a OS para pegar o valor atualizado e gerar o PDF
        # Ajuste no SELECT para pegar as novas colunas e dados do cliente via JOIN
        c.execute("""
            SELECT 
                os.id, os.codigo_os, c.nome, c.telefone, os.equipamento, os.numero_serie, os.itens_internos, 
                os.defeito, os.solucao, os.status, os.data_entrada, os.responsavel, os.valor_orcamento,
                os.valor_servico_executado, os.pecas_adicionadas, os.valor_pecas,
                os.nome_aprovacao_cliente, os.data_aprovacao_cliente, os.id_cliente
            FROM ordens_servico os
            JOIN clientes c ON os.id_cliente = c.id
            WHERE os.id=?
        """, (id,))
        os_info = c.fetchone()
        conn.close()

        if os_info:
            os_dados_atualizados = {
                'codigo_os': os_info[1],
                'cliente': os_info[2], # Nome do cliente do JOIN
                'telefone': os_info[3], # Telefone do cliente do JOIN
                'equipamento': os_info[4],
                'numero_serie': os_info[5],
                'itens_internos': os_info[6],
                'defeito': os_info[7],
                'solucao': os_info[8],
                'status': os_info[9],
                'data_entrada': os_info[10],
                'responsavel': os_info[11],
                'valor_orcamento': os_info[12],
                'valor_servico_executado': os_info[13],
                'pecas_adicionadas': os_info[14],
                'valor_pecas': os_info[15],
                'nome_aprovacao_cliente': os_info[16],
                'data_aprovacao_cliente': os_info[17]
            }
            gerar_pdf_os(os_dados_atualizados)

        flash("OS atualizada com sucesso!", 'success')
        return redirect(url_for('listar_os'))
    else:
        # NOVO: Seleciona todos os campos, incluindo os de peças e aprovação, e dados do cliente
        c.execute("""
            SELECT 
                os.id, os.codigo_os, c.nome, c.telefone, os.equipamento, os.numero_serie, os.itens_internos, 
                os.defeito, os.solucao, os.status, os.data_entrada, os.responsavel, os.valor_orcamento,
                os.valor_servico_executado, os.pecas_adicionadas, os.valor_pecas,
                os.nome_aprovacao_cliente, os.data_aprovacao_cliente, os.id_cliente
            FROM ordens_servico os
            JOIN clientes c ON os.id_cliente = c.id
            WHERE os.id=?
        """, (id,))
        os_info = c.fetchone()
        conn.close()
        if not os_info:
            flash("OS não encontrada.", 'danger')
            return redirect(url_for('listar_os'))
        return render_template('editar_os.html', os=os_info, usuario=session['usuario_nome'])


@app.route('/ver_pdf/<codigo_os>')
def ver_pdf_os(codigo_os):
    pdf_path = f"{PDF_DIR}/{codigo_os}.pdf"
    if os.path.exists(pdf_path):
        return send_file(pdf_path, as_attachment=False)
    else:
        flash("PDF não encontrado.", 'danger')
        return redirect(url_for('dashboard'))

# --- ROTA PÚBLICA PARA VISUALIZAÇÃO E APROVAÇÃO DA OS PELO CLIENTE (Não logado) ---
@app.route('/os_cliente/<codigo_os>', methods=['GET', 'POST'])
def visualizar_os_publica(codigo_os):
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    # Pega todos os dados da OS, incluindo os campos de aprovação e dados do cliente
    c.execute("""
        SELECT 
            os.id, os.codigo_os, c.nome, c.telefone, os.equipamento, os.numero_serie, os.itens_internos, 
            os.defeito, os.solucao, os.status, os.data_entrada, os.responsavel, os.valor_orcamento,
            os.valor_servico_executado, os.pecas_adicionadas, os.valor_pecas,
            os.nome_aprovacao_cliente, os.data_aprovacao_cliente
        FROM ordens_servico os
        JOIN clientes c ON os.id_cliente = c.id
        WHERE os.codigo_os=?
    """, (codigo_os,))
    os_info_tuple = c.fetchone()

    if not os_info_tuple:
        conn.close()
        return "Ordem de Serviço não encontrada.", 404
    
    # Converte a tupla para dicionário para facilitar o acesso no template
    os_fields = [
        'id', 'codigo_os', 'cliente', 'telefone', 'equipamento', 'numero_serie',
        'itens_internos', 'defeito', 'solucao', 'status', 'data_entrada', 'responsavel',
        'valor_orcamento', 'valor_servico_executado', 'pecas_adicionadas', 'valor_pecas',
        'nome_aprovacao_cliente', 'data_aprovacao_cliente'
    ]
    os_dados = dict(zip(os_fields, os_info_tuple))

    if request.method == 'POST':
        nome_aprovacao = request.form.get('nome_aprovacao_cliente', '').strip()
        if not nome_aprovacao:
            flash('Por favor, digite seu nome para aprovar a Ordem de Serviço.', 'danger')
            return render_template('visualizar_os_publica.html', os=os_dados)
        
        data_aprovacao = datetime.now().strftime("%d/%m/%Y %H:%M")

        try:
            c.execute("UPDATE ordens_servico SET nome_aprovacao_cliente=?, data_aprovacao_cliente=? WHERE codigo_os=?", 
                      (nome_aprovacao, data_aprovacao, codigo_os))
            conn.commit()

            # Atualiza os_dados para refletir a aprovação imediatamente na tela
            os_dados['nome_aprovacao_cliente'] = nome_aprovacao
            os_dados['data_aprovacao_cliente'] = data_aprovacao

            # Regera o PDF para incluir a informação de aprovação
            gerar_pdf_os(os_dados)

            flash('Ordem de Serviço aprovada com sucesso!', 'success')
            
        except Exception as e:
            flash(f'Erro ao registrar aprovação: {e}', 'danger')
        finally:
            conn.close()
            # Após o POST, renderiza a mesma página atualizada
            return render_template('visualizar_os_publica.html', os=os_dados)
    
    conn.close()
    return render_template('visualizar_os_publica.html', os=os_dados)
# --- FIM DA ROTA PÚBLICA ---


if __name__ == '__main__':
    inicializar_banco()
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=True)