import os
import uuid
import hashlib
import shutil
import sqlite3
from functools import wraps
from datetime import datetime
from flask import Flask, render_template, request, redirect, url_for, flash, session, send_file
from werkzeug.security import generate_password_hash, check_password_hash

# Importações do ReportLab para um estilo mais profissional
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import cm
from reportlab.pdfgen import canvas
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle, StyleSheet1
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from reportlab.lib.utils import ImageReader # Para logos, se houver

app = Flask(__name__)
app.secret_key = 'aB3c#D5e@F7g$H9i!J1k%L2m^N4o&P6q*R8s+T0u=VwXyZ' # Mude para uma chave secreta forte e aleatória
DB = 'assistencia.db'
PDF_DIR = 'PDFs'  # Diretório para salvar os PDFs

# Certifique-se de que o diretório de PDFs exista ao iniciar a aplicação
if not os.path.exists(PDF_DIR):
    os.makedirs(PDF_DIR)

BACKUP_DIR = os.path.join(os.path.abspath(os.path.dirname(__file__)), 'server_backups')
# Garante que o diretório de backup exista ao iniciar a aplicação
os.makedirs(BACKUP_DIR, exist_ok=True)

# Função auxiliar para listar backups disponíveis no servidor
def get_available_server_backups():
    backups = []
    if os.path.exists(BACKUP_DIR):
        for filename in os.listdir(BACKUP_DIR):
            if filename.startswith('assistencia_backup_') and filename.endswith('.db'):
                filepath = os.path.join(BACKUP_DIR, filename)
                # O timestamp está no nome do arquivo: assistencia_backup_YYYYMMDD_HHMMSS.db
                try:
                    # Extrair a parte do timestamp e formatar para algo legível
                    timestamp_str = filename.replace('assistencia_backup_', '').replace('.db', '')
                    backup_date = datetime.strptime(timestamp_str, '%Y%m%d_%H%M%S').strftime('%d/%m/%Y %H:%M:%S')
                    backups.append({'filename': filename, 'date': backup_date, 'filepath': filepath})
                except ValueError:
                    # Ignorar arquivos que não seguem o padrão de nome esperado
                    pass
    # Opcional: ordenar por data mais recente
    backups.sort(key=lambda x: datetime.strptime(x['date'], '%d/%m/%Y %H:%M:%S'), reverse=True)
    return backups

# Garante que o diretório de PDFs exista
if not os.path.exists(PDF_DIR):
    os.makedirs(PDF_DIR)

def inicializar_banco():
    conn = sqlite3.connect(DB)
    c = conn.cursor()

    # Tabela de Usuários (agora inclui clientes com permissao='cliente')
    c.execute('''
        CREATE TABLE IF NOT EXISTS usuarios (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nome TEXT NOT NULL,
            login TEXT NOT NULL UNIQUE,
            senha TEXT NOT NULL,
            permissao TEXT NOT NULL,
            id_cliente INTEGER,
            FOREIGN KEY (id_cliente) REFERENCES clientes(id)
        )
    ''')

    # Adiciona a coluna id_cliente se ela não existir
    try:
        c.execute("ALTER TABLE usuarios ADD COLUMN id_cliente INTEGER REFERENCES clientes(id)")
    except sqlite3.OperationalError as e:
        if "duplicate column name" not in str(e):
            print(f"Erro ao adicionar coluna id_cliente: {e}")

    # Remove a tabela clientes_web (agora obsoleta)
    c.execute("DROP TABLE IF EXISTS clientes_web")

    # Tabela de Clientes
    c.execute('''
        CREATE TABLE IF NOT EXISTS clientes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nome TEXT NOT NULL,
            cpf TEXT NOT NULL UNIQUE,
            telefone TEXT
        )
    ''')

    # Tabela de Ordens de Serviço
    c.execute('''
        CREATE TABLE IF NOT EXISTS ordens_servico (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            codigo_os TEXT NOT NULL UNIQUE,
            id_cliente INTEGER NOT NULL,
            cliente TEXT NOT NULL,
            telefone TEXT,
            equipamento TEXT NOT NULL,
            numero_serie TEXT NOT NULL,
            itens_internos TEXT NOT NULL,
            defeito TEXT NOT NULL,
            solucao TEXT DEFAULT '',
            status TEXT DEFAULT 'Aberta',
            data_entrada TEXT NOT NULL,
            responsavel TEXT NOT NULL,
            valor_orcamento REAL DEFAULT 0.0,
            valor_servico_executado REAL DEFAULT 0.0,
            pecas_adicionadas TEXT DEFAULT '',
            valor_pecas REAL DEFAULT 0.0,
            nome_aprovacao_cliente TEXT DEFAULT '',
            data_aprovacao_cliente TEXT DEFAULT '',
            FOREIGN KEY (id_cliente) REFERENCES clientes(id)
        )
    ''')

    # Cria um usuário admin padrão se não houver nenhum
    c.execute("SELECT COUNT(*) FROM usuarios WHERE permissao='admin'")
    if c.fetchone()[0] == 0:
        hashed_password = generate_password_hash('05022013', method='pbkdf2:sha256')
        c.execute("INSERT INTO usuarios (nome, login, senha, permissao) VALUES (?, ?, ?, ?)",
                  ('Administrador', 'admin', hashed_password, 'admin'))
        conn.commit()
        print("Usuário administrador padrão criado (login: admin, senha: admin)")

    conn.close()

def gerar_pdf_os(os_dados):
    pdf_file_path = os.path.join(PDF_DIR, f"{os_dados['codigo_os']}.pdf")
    os.makedirs(os.path.dirname(pdf_file_path), exist_ok=True)

    # 1. Configurar a folha de estilos
    styles = getSampleStyleSheet()
    # Crie uma nova folha de estilos vazia para seus estilos personalizados
    # Isso garante que não haverá conflitos de nomes de estilo
    custom_styles = StyleSheet1()

    # Adicione estilos personalizados
    custom_styles.add(ParagraphStyle(name='Title', fontSize=24, spaceAfter=20, alignment=TA_CENTER, fontName='Helvetica-Bold'))
    custom_styles.add(ParagraphStyle(name='Subtitle', fontSize=16, spaceAfter=10, alignment=TA_CENTER, fontName='Helvetica-Bold', textColor=colors.darkblue))
    custom_styles.add(ParagraphStyle(name='Heading1', fontSize=14, spaceBefore=12, spaceAfter=6, fontName='Helvetica-Bold', textColor=colors.darkblue))
    custom_styles.add(ParagraphStyle(name='BodyText', fontSize=10, spaceAfter=4, fontName='Helvetica'))
    custom_styles.add(ParagraphStyle(name='BodyTextBold', fontSize=10, spaceAfter=4, fontName='Helvetica-Bold'))
    custom_styles.add(ParagraphStyle(name='SmallText', fontSize=8, spaceAfter=2, fontName='Helvetica'))
    custom_styles.add(ParagraphStyle(name='SignatureLine', fontSize=10, spaceBefore=30, alignment=TA_CENTER, fontName='Helvetica'))
    custom_styles.add(ParagraphStyle(name='SignatureText', fontSize=10, spaceAfter=10, alignment=TA_CENTER, fontName='Helvetica'))
    
    # Novo estilo para cabeçalhos de seção com fundo sombreado
    custom_styles.add(ParagraphStyle(name='SectionHeader', fontSize=12, spaceBefore=10, spaceAfter=5, fontName='Helvetica-Bold', textColor=colors.black, alignment=TA_LEFT))


    # 2. Configurar o SimpleDocTemplate
    doc = SimpleDocTemplate(pdf_file_path, pagesize=A4,
                            rightMargin=cm, leftMargin=cm,
                            topMargin=3.0*cm, bottomMargin=2.5*cm) # Margens ajustadas para o novo cabeçalho

    elements = []

    # --- Função para Cabeçalho e Rodapé ---
    def header_footer(canvas_obj, doc_obj):
        canvas_obj.saveState()
        
        # Header - Título principal "Ordem de Serviço"
        canvas_obj.setFont('Helvetica-Bold', 24)
        canvas_obj.drawCentredString(A4[0]/2.0, A4[1] - 1.5*cm, "Ordem de Serviço") # Ajustado para centralizar

        # Código da OS abaixo do título principal
        canvas_obj.setFont('Helvetica-Bold', 12)
        canvas_obj.drawCentredString(A4[0]/2.0, A4[1] - 2.2*cm, f"OS: {os_dados['codigo_os']}") # Ajustado para centralizar e menor

        # Linha divisória
        line_y_position = A4[1] - 2.8*cm 
        canvas_obj.line(cm, line_y_position, A4[0] - cm, line_y_position) 

        # Footer
        canvas_obj.setFont('Helvetica', 8)
        canvas_obj.drawCentredString(A4[0]/2.0, cm, f"Página {doc_obj.page}")
        canvas_obj.restoreState()

    # --- Conteúdo do Documento (Flowables) ---

    # Espaçamento inicial para o conteúdo não colidir com o cabeçalho fixo
    elements.append(Spacer(1, 1.0*cm)) # Deve ser igual ao topMargin do SimpleDocTemplate

    # Informações da Empresa (movidas para o corpo do documento)
    elements.append(Paragraph("<b>ZTB Studio</b>", custom_styles['BodyTextBold']))
    elements.append(Paragraph("Endereço: Rua Joinville, 90 - Recife - PE", custom_styles['BodyText']))
    elements.append(Paragraph("Telefone: (81) 99696-2824 | E-mail: augusto_pe@hotmail.com", custom_styles['BodyText']))
    elements.append(Spacer(1, 0.8*cm)) # Espaço após as informações da empresa

    # Informações Básicas da OS
    data_os_info = [
        [Paragraph("<b>Data de Entrada:</b>", custom_styles['BodyTextBold']), Paragraph(os_dados['data_entrada'], custom_styles['BodyText'])],
        [Paragraph("<b>Responsável (Abertura):</b>", custom_styles['BodyTextBold']), Paragraph(os_dados['responsavel'], custom_styles['BodyText'])]
    ]
    table_style_basic = TableStyle([
        ('ALIGN', (0,0), (-1,-1), 'LEFT'),
        ('VALIGN', (0,0), (-1,-1), 'TOP'),
        ('LEFTPADDING', (0,0), (-1,-1), 0),
        ('RIGHTPADDING', (0,0), (-1,-1), 0),
        ('BOTTOMPADDING', (0,0), (-1,-1), 2),
    ])
    elements.append(Table(data_os_info, colWidths=[4*cm, None], style=table_style_basic))
    elements.append(Spacer(1, 0.5*cm))

    # Dados do Cliente
    # Cabeçalho de seção sombreado
    elements.append(Table([[Paragraph("Dados do Cliente", custom_styles['SectionHeader'])]],
                          colWidths=[A4[0]-2*cm],
                          style=TableStyle([
                              ('BACKGROUND', (0,0), (-1,-1), colors.lightgrey),
                              ('TEXTCOLOR', (0,0), (-1,-1), colors.black),
                              ('ALIGN', (0,0), (-1,-1), 'LEFT'),
                              ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
                              ('LEFTPADDING', (0,0), (-1,-1), 5),
                              ('RIGHTPADDING', (0,0), (-1,-1), 5),
                              ('TOPPADDING', (0,0), (-1,-1), 2),
                              ('BOTTOMPADDING', (0,0), (-1,-1), 2),
                          ])))
    data_cliente = [
        [Paragraph("<b>Nome:</b>", custom_styles['BodyTextBold']), Paragraph(os_dados['cliente'], custom_styles['BodyText'])],
        [Paragraph("<b>Telefone:</b>", custom_styles['BodyTextBold']), Paragraph(os_dados['telefone'] or 'N/A', custom_styles['BodyText'])]
    ]
    table_style_cliente = TableStyle([
        ('ALIGN', (0,0), (-1,-1), 'LEFT'),
        ('VALIGN', (0,0), (-1,-1), 'TOP'),
        ('LEFTPADDING', (0,0), (-1,-1), 0),
        ('RIGHTPADDING', (0,0), (-1,-1), 0),
        ('BOTTOMPADDING', (0,0), (-1,-1), 2),
    ])
    elements.append(Table(data_cliente, colWidths=[4*cm, None], style=table_style_cliente))
    elements.append(Spacer(1, 0.5*cm))

    # Dados do Equipamento
    elements.append(Table([[Paragraph("Dados do Equipamento", custom_styles['SectionHeader'])]],
                          colWidths=[A4[0]-2*cm],
                          style=TableStyle([
                              ('BACKGROUND', (0,0), (-1,-1), colors.lightgrey),
                              ('TEXTCOLOR', (0,0), (-1,-1), colors.black),
                              ('ALIGN', (0,0), (-1,-1), 'LEFT'),
                              ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
                              ('LEFTPADDING', (0,0), (-1,-1), 5),
                              ('RIGHTPADDING', (0,0), (-1,-1), 5),
                              ('TOPPADDING', (0,0), (-1,-1), 2),
                              ('BOTTOMPADDING', (0,0), (-1,-1), 2),
                          ])))
    data_equipamento = [
        [Paragraph("<b>Equipamento:</b>", custom_styles['BodyTextBold']), Paragraph(os_dados['equipamento'], custom_styles['BodyText'])],
        [Paragraph("<b>Número de Série:</b>", custom_styles['BodyTextBold']), Paragraph(os_dados['numero_serie'], custom_styles['BodyText'])],
    ]
    table_style_equipamento = TableStyle([
        ('ALIGN', (0,0), (-1,-1), 'LEFT'),
        ('VALIGN', (0,0), (-1,-1), 'TOP'),
        ('LEFTPADDING', (0,0), (-1,-1), 0),
        ('RIGHTPADDING', (0,0), (-1,-1), 0),
        ('BOTTOMPADDING', (0,0), (-1,-1), 2),
    ])
    elements.append(Table(data_equipamento, colWidths=[5*cm, None], style=table_style_equipamento))
    elements.append(Spacer(1, 0.5*cm))

    # Itens Internos (com borda)
    elements.append(Table([[Paragraph("Itens Internos", custom_styles['SectionHeader'])]],
                          colWidths=[A4[0]-2*cm],
                          style=TableStyle([
                              ('BACKGROUND', (0,0), (-1,-1), colors.lightgrey),
                              ('TEXTCOLOR', (0,0), (-1,-1), colors.black),
                              ('ALIGN', (0,0), (-1,-1), 'LEFT'),
                              ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
                              ('LEFTPADDING', (0,0), (-1,-1), 5),
                              ('RIGHTPADDING', (0,0), (-1,-1), 5),
                              ('TOPPADDING', (0,0), (-1,-1), 2),
                              ('BOTTOMPADDING', (0,0), (-1,-1), 2),
                          ])))
    elements.append(Table([[Paragraph(os_dados['itens_internos'], custom_styles['BodyText'])]],
                          colWidths=[A4[0]-2*cm],
                          style=TableStyle([
                              ('GRID', (0,0), (-1,-1), 0.5, colors.black), # Adiciona borda
                              ('LEFTPADDING', (0,0), (-1,-1), 5),
                              ('RIGHTPADDING', (0,0), (-1,-1), 5),
                              ('TOPPADDING', (0,0), (-1,-1), 5),
                              ('BOTTOMPADDING', (0,0), (-1,-1), 5),
                          ])))
    elements.append(Spacer(1, 0.5*cm))

    # Defeito Relatado (com borda)
    elements.append(Table([[Paragraph("Defeito Relatado", custom_styles['SectionHeader'])]],
                          colWidths=[A4[0]-2*cm],
                          style=TableStyle([
                              ('BACKGROUND', (0,0), (-1,-1), colors.lightgrey),
                              ('TEXTCOLOR', (0,0), (-1,-1), colors.black),
                              ('ALIGN', (0,0), (-1,-1), 'LEFT'),
                              ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
                              ('LEFTPADDING', (0,0), (-1,-1), 5),
                              ('RIGHTPADDING', (0,0), (-1,-1), 5),
                              ('TOPPADDING', (0,0), (-1,-1), 2),
                              ('BOTTOMPADDING', (0,0), (-1,-1), 2),
                          ])))
    elements.append(Table([[Paragraph(os_dados['defeito'], custom_styles['BodyText'])]],
                          colWidths=[A4[0]-2*cm],
                          style=TableStyle([
                              ('GRID', (0,0), (-1,-1), 0.5, colors.black), # Adiciona borda
                              ('LEFTPADDING', (0,0), (-1,-1), 5),
                              ('RIGHTPADDING', (0,0), (-1,-1), 5),
                              ('TOPPADDING', (0,0), (-1,-1), 5),
                              ('BOTTOMPADDING', (0,0), (-1,-1), 5),
                          ])))
    elements.append(Spacer(1, 0.5*cm))

    # Resumo Financeiro - Título "Valores"
    elements.append(Table([[Paragraph("Valores", custom_styles['SectionHeader'])]],
                          colWidths=[A4[0]-2*cm],
                          style=TableStyle([
                              ('BACKGROUND', (0,0), (-1,-1), colors.lightgrey),
                              ('TEXTCOLOR', (0,0), (-1,-1), colors.black),
                              ('ALIGN', (0,0), (-1,-1), 'LEFT'),
                              ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
                              ('LEFTPADDING', (0,0), (-1,-1), 5),
                              ('RIGHTPADDING', (0,0), (-1,-1), 5),
                              ('TOPPADDING', (0,0), (-1,-1), 2),
                              ('BOTTOMPADDING', (0,0), (-1,-1), 2),
                          ])))
    data_financeiro = [
        [Paragraph("<b>Valor Orçado:</b>", custom_styles['BodyTextBold']), Paragraph(f"R$ {os_dados['valor_orcamento']:.2f}", custom_styles['BodyTextBold'])]
    ]
    valor_total_final = os_dados.get('valor_servico_executado', 0.0) + os_dados.get('valor_pecas', 0.0)
    if os_dados.get('valor_servico_executado') is not None and os_dados.get('valor_servico_executado') > 0:
        data_financeiro.append([Paragraph("<b>Valor do Serviço Executado:</b>", custom_styles['BodyTextBold']), Paragraph(f"R$ {os_dados['valor_servico_executado']:.2f}", custom_styles['BodyText'])])
        data_financeiro.append([Paragraph("<b>Valor Total Estimado/Final:</b>", custom_styles['BodyTextBold']), Paragraph(f"R$ {valor_total_final:.2f}", custom_styles['BodyTextBold'])])
    
    table_style_financeiro = TableStyle([
        ('ALIGN', (0,0), (-1,-1), 'LEFT'),
        ('VALIGN', (0,0), (-1,-1), 'TOP'),
        ('LEFTPADDING', (0,0), (-1,-1), 0),
        ('RIGHTPADDING', (0,0), (-1,-1), 0),
        ('BOTTOMPADDING', (0,0), (-1,-1), 2),
        ('LINEBELOW', (0,-1), (-1,-1), 0.5, colors.black), # Linha abaixo do total
    ])
    elements.append(Table(data_financeiro, colWidths=[6*cm, None], style=table_style_financeiro))
    elements.append(Spacer(1, 0.8*cm))

    # Aprovação do Cliente - Removido para corresponder à imagem, que só tem a linha de assinatura
    # elements.append(Paragraph("APROVAÇÃO DO CLIENTE:", custom_styles['Heading1']))
    # if os_dados.get('nome_aprovacao_cliente'):
    #     elements.append(Paragraph(f"<b>Aprovado por:</b> {os_dados['nome_aprovacao_cliente']}", custom_styles['BodyText']))
    #     elements.append(Paragraph(f"<b>Data da Aprovação:</b> {os_dados['data_aprovacao_cliente']}", custom_styles['BodyText']))
    # else:
    #     elements.append(Paragraph("Aguardando aprovação do cliente.", custom_styles['BodyText']))
    # elements.append(Spacer(1, 1.5*cm)) # Mais espaço para assinatura

    # Linhas de Assinatura
    elements.append(Spacer(1, 2.0*cm)) # Espaço antes da assinatura
    elements.append(Paragraph("_______________________________________", custom_styles['SignatureLine']))
    elements.append(Paragraph("Assinatura do Cliente", custom_styles['SignatureText']))
    elements.append(Spacer(1, 0.5*cm))
    # elements.append(Paragraph("_______________________________________", custom_styles['SignatureLine']))
    # elements.append(Paragraph("Assinatura do Responsável (Técnico/Atendente)", custom_styles['SignatureText'])) # Removido para corresponder à imagem

    # Construir o PDF com o cabeçalho/rodapé
    doc.build(elements, onFirstPage=header_footer, onLaterPages=header_footer)

    return pdf_file_path

# --- Rotas do Flask (restante do seu código, inalterado) ---

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
        id_cliente = request.form['id_cliente']
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


        # Seleciona todos os campos existentes e os novos para atualização
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
        # Seleciona todos os campos, incluindo os de peças e aprovação, e dados do cliente
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
    pdf_path = os.path.join(PDF_DIR, f"{codigo_os}.pdf")
    if os.path.exists(pdf_path):
        return send_file(pdf_path, as_attachment=False) # as_attachment=False para visualizar no navegador
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
            c.execute("UPDATE ordens_servico SET nome_aprovacao_cliente=?, data_aprovacao_cliente=?, status='Aprovada pelo Cliente' WHERE codigo_os=?", 
                      (nome_aprovacao, data_aprovacao, codigo_os))
            conn.commit()

            # Atualiza os_dados para refletir a aprovação imediatamente na tela
            os_dados['nome_aprovacao_cliente'] = nome_aprovacao
            os_dados['data_aprovacao_cliente'] = data_aprovacao
            os_dados['status'] = 'Aprovada pelo Cliente' # Atualiza o status para o PDF

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

# --- ROTAS DE AUTENTICAÇÃO E DASHBOARD ---
@app.route('/')
def index():
    return redirect(url_for('login'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        login_input = request.form['login']
        senha = request.form['senha']

        conn = sqlite3.connect(DB)
        c = conn.cursor()
        # Busca usuário interno ou cliente
        c.execute("SELECT id, nome, login, senha, permissao, id_cliente FROM usuarios WHERE login = ?", (login_input,))
        usuario = c.fetchone()
        conn.close()

        if usuario and check_password_hash(usuario[3], senha): # usuario[3] é a senha hashed
            session['usuario_id'] = usuario[0]
            session['usuario_nome'] = usuario[1]
            session['login'] = usuario[2]
            session['permissao'] = usuario[4]
            session['id_cliente'] = usuario[5] # Armazena o id_cliente se for um cliente

            if session['permissao'] == 'cliente':
                flash('Login de cliente realizado com sucesso!', 'success')
                return redirect(url_for('cliente_dashboard'))
            else:
                flash('Login de usuário interno realizado com sucesso!', 'success')
                return redirect(url_for('dashboard'))
        else:
            flash('Login ou senha incorretos.', 'danger')
    return render_template('login.html')


@app.route('/logout')
def logout():
    session.clear()
    flash('Você foi desconectado.', 'info')
    return redirect(url_for('login'))

@app.route('/dashboard')
def dashboard():
    if 'usuario_id' not in session or session['permissao'] == 'cliente':
        flash('Você não tem permissão para acessar esta página.', 'danger')
        return redirect(url_for('login'))
    
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM ordens_servico")
    total_os = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM ordens_servico WHERE status='Aberta'")
    os_abertas = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM ordens_servico WHERE status='Em Análise'")
    os_em_analise = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM ordens_servico WHERE status='Finalizada'")
    os_finalizadas = c.fetchone()[0]
    conn.close()

    return render_template('dashboard.html', 
                           usuario=session['usuario_nome'], 
                           permissao=session['permissao'],
                           total_os=total_os,
                           os_abertas=os_abertas,
                           os_em_analise=os_em_analise,
                           os_finalizadas=os_finalizadas)

@app.route('/cliente_dashboard')
def cliente_dashboard():
    # Apenas clientes logados podem acessar este dashboard
    if 'usuario_id' not in session or session.get('permissao') != 'cliente' or session.get('id_cliente') is None:
        flash('Você precisa estar logado como cliente para acessar esta página.', 'danger')
        return redirect(url_for('login'))

    conn = sqlite3.connect(DB)
    c = conn.cursor()
    # Pega todas as OSs associadas ao id_cliente do usuário logado
    c.execute("""
        SELECT 
            id, codigo_os, id_cliente, cliente, equipamento, numero_serie, itens_internos, 
            defeito, solucao, status, data_entrada, responsavel, valor_orcamento,
            valor_servico_executado, pecas_adicionadas, valor_pecas,
            nome_aprovacao_cliente, data_aprovacao_cliente
        FROM ordens_servico
        WHERE id_cliente = ?
        ORDER BY id DESC
    """, (session['id_cliente'],))
    ordens = c.fetchall()
    conn.close()

    return render_template('cliente_dashboard.html', usuario=session['usuario_nome'], ordens=ordens)


# --- ROTAS DE GERENCIAMENTO DE USUÁRIOS INTERNOS ---
@app.route('/cadastrar_usuario', methods=['GET', 'POST'])
def cadastrar_usuario():
    # Somente administradores podem cadastrar outros usuários internos
    if 'permissao' not in session or session['permissao'] != 'admin':
        flash('Você não tem permissão para acessar esta página.', 'warning')
        return redirect(url_for('dashboard'))

    if request.method == 'POST':
        nome = request.form['nome'].strip()
        login = request.form['login'].strip()
        senha = request.form['senha'].strip()
        permissao = request.form['permissao']

        if not nome or not login or not senha or not permissao:
            flash('Todos os campos são obrigatórios.', 'danger')
            return render_template('cadastrar_usuario.html')

        hashed_password = generate_password_hash(senha, method='pbkdf2:sha256')

        conn = sqlite3.connect(DB)
        c = conn.cursor()
        try:
            c.execute("INSERT INTO usuarios (nome, login, senha, permissao) VALUES (?, ?, ?, ?)",
                      (nome, login, hashed_password, permissao))
            conn.commit()
            flash('Usuário cadastrado com sucesso!', 'success')
            return redirect(url_for('listar_usuarios'))
        except sqlite3.IntegrityError:
            flash('Erro: Já existe um usuário com este login.', 'danger')
        except Exception as e:
            flash(f'Erro ao cadastrar usuário: {e}', 'danger')
        finally:
            conn.close()
    return render_template('cadastrar_usuario.html')

@app.route('/listar_usuarios')
def listar_usuarios():
    # Somente administradores podem listar usuários
    if 'permissao' not in session or session['permissao'] != 'admin':
        flash('Você não tem permissão para acessar esta página.', 'warning')
        return redirect(url_for('dashboard'))

    conn = sqlite3.connect(DB) # CORRIGIDO: Usando DB
    c = conn.cursor()
    # Não lista usuários com permissão 'cliente' aqui
    c.execute("SELECT id, nome, login, permissao FROM usuarios WHERE permissao != 'cliente' ORDER BY nome")
    # Para passar como dicionário (facilita acesso no template)
    usuarios_db = c.fetchall()
    usuarios = [
        {'id': u[0], 'nome': u[1], 'login': u[2], 'permissao': u[3]}
        for u in usuarios_db
    ]
    conn.close()
    return render_template('listar_usuarios.html', usuarios=usuarios)

@app.route('/editar_usuario/<int:usuario_id>', methods=['GET', 'POST'])
def editar_usuario(usuario_id):
    # Somente administradores podem editar usuários
    if 'permissao' not in session or session['permissao'] != 'admin':
        flash('Você não tem permissão para acessar esta página.', 'warning')
        return redirect(url_for('dashboard'))

    conn = sqlite3.connect(DB) # CORRIGIDO: Usando DB
    c = conn.cursor()

    if request.method == 'POST':
        nome = request.form['nome'].strip()
        login = request.form['login'].strip()
        senha_nova = request.form['senha_nova'].strip()
        permissao = request.form['permissao']

        if not nome or not login or not permissao:
            flash('Nome, Login e Permissão são campos obrigatórios.', 'danger')
            # Re-seleciona o usuário para re-renderizar
            c.execute("SELECT id, nome, login, permissao FROM usuarios WHERE id = ?", (usuario_id,))
            usuario_info = c.fetchone()
            conn.close()
            return render_template('editar_usuario.html', usuario={'id': usuario_info[0], 'nome': usuario_info[1], 'login': usuario_info[2], 'permissao': usuario_info[3]})

        try:
            # Verifica se o novo login já existe para outro usuário
            c.execute("SELECT id FROM usuarios WHERE login = ? AND id != ?", (login, usuario_id))
            if c.fetchone():
                flash('Erro: Já existe outro usuário com este login.', 'danger')
                # Re-seleciona o usuário para re-renderizar
                c.execute("SELECT id, nome, login, permissao FROM usuarios WHERE id = ?", (usuario_id,))
                usuario_info = c.fetchone()
                conn.close()
                return render_template('editar_usuario.html', usuario={'id': usuario_info[0], 'nome': usuario_info[1], 'login': usuario_info[2], 'permissao': usuario_info[3]})

            if senha_nova:
                hashed_senha_nova = generate_password_hash(senha_nova, method='pbkdf2:sha256')
                c.execute("UPDATE usuarios SET nome=?, login=?, senha=?, permissao=? WHERE id=?",
                          (nome, login, hashed_senha_nova, permissao, usuario_id))
            else:
                c.execute("UPDATE usuarios SET nome=?, login=?, permissao=? WHERE id=?",
                          (nome, login, permissao, usuario_id))
            conn.commit()
            flash('Usuário atualizado com sucesso!', 'success')
            return redirect(url_for('listar_usuarios'))
        except Exception as e:
            flash(f'Erro ao atualizar usuário: {e}', 'danger')
        finally:
            conn.close()
            
    else: # Método GET
        c.execute("SELECT id, nome, login, permissao FROM usuarios WHERE id = ?", (usuario_id,))
        usuario_info = c.fetchone()
        conn.close()
        if not usuario_info:
            flash("Usuário não encontrado.", 'danger')
            return redirect(url_for('listar_usuarios'))
        
        usuario = {
            'id': usuario_info[0],
            'nome': usuario_info[1],
            'login': usuario_info[2],
            'permissao': usuario_info[3]
        }
        return render_template('editar_usuario.html', usuario=usuario)
from functools import wraps

def login_required(*permissoes):
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if 'usuario_id' not in session or (permissoes and session.get('permissao') not in permissoes):
                flash('Você não tem permissão para acessar esta página.', 'danger')
                return redirect(url_for('login'))
            return f(*args, **kwargs)
        return decorated_function
    return decorator

# Rota Excluir Usuário
@app.route('/excluir_usuario/<int:usuario_id>', methods=['POST'])
@login_required('admin')
def excluir_usuario(usuario_id):
    conn = sqlite3.connect('assistencia.db')
    cursor = conn.cursor()
    try:
        # Verifica se o usuário a ser excluído não é o próprio usuário logado
        if session.get('usuario_id') == usuario_id:
            flash('Você não pode excluir seu próprio usuário enquanto estiver logado.', 'danger')
            return redirect(url_for('listar_usuarios'))

        # Primeiro, verifica se o usuário existe
        cursor.execute("SELECT id, nome FROM usuarios WHERE id = ?", (usuario_id,))
        usuario_db = cursor.fetchone()

        if usuario_db:
            # Se o usuário for um cliente com acesso web, o id_cliente será nulo nesta tabela.
            # A exclusão aqui é apenas do registro na tabela 'usuarios'.
            # A tabela 'clientes' e as ordens de serviço associadas ao cliente não são afetadas.
            cursor.execute("DELETE FROM usuarios WHERE id = ?", (usuario_id,))
            conn.commit()
            flash(f'Usuário "{usuario_db[1]}" excluído com sucesso!', 'success')
        else:
            flash('Usuário não encontrado.', 'danger')
    except Exception as e:
        conn.rollback()
        flash(f'Erro ao excluir usuário: {e}', 'danger')
    finally:
        conn.close()
    return redirect(url_for('listar_usuarios'))

# --- ROTAS DE GERENCIAMENTO DE CLIENTES ---
@app.route('/cadastrar_cliente', methods=['GET', 'POST'])
def cadastrar_cliente():
    if 'permissao' not in session or session['permissao'] not in ['admin', 'atendente']:
        flash('Você não tem permissão para acessar esta página.', 'warning')
        return redirect(url_for('dashboard'))

    if request.method == 'POST':
        nome = request.form['nome'].strip()
        cpf = request.form['cpf'].strip()
        telefone = request.form['telefone'].strip()
        
        criar_acesso_web = request.form.get('criar_acesso_web')
        login_web = request.form.get('login_web', '').strip()
        senha_web = request.form.get('senha_web', '').strip()

        if not nome or not cpf:
            flash('Nome e CPF são campos obrigatórios para o cliente.', 'danger')
            return render_template('cadastrar_cliente.html')

        conn = sqlite3.connect(DB)
        c = conn.cursor()
        try:
            # Insere o cliente na tabela 'clientes'
            c.execute("INSERT INTO clientes (nome, cpf, telefone) VALUES (?, ?, ?)",
                      (nome, cpf, telefone))
            
            cliente_id = c.lastrowid # Pega o ID do cliente recém-criado
            
            # Se for para criar acesso web, insere na tabela 'usuarios'
            if criar_acesso_web:
                if not login_web or not senha_web:
                    flash('Login e Senha para o acesso web são obrigatórios ao marcar "Criar Acesso Web".', 'danger')
                    conn.rollback() # Desfaz a inserção do cliente
                    return render_template('cadastrar_cliente.html')
                
                hashed_senha_web = generate_password_hash(senha_web, method='pbkdf2:sha256')
                c.execute("INSERT INTO usuarios (nome, login, senha, permissao, id_cliente) VALUES (?, ?, ?, ?, ?)",
                          (nome, login_web, hashed_senha_web, 'cliente', cliente_id))
                flash(f'Acesso web criado para o cliente {nome} com login: {login_web}!', 'success')
            
            conn.commit()
            flash('Cliente cadastrado com sucesso!', 'success')
            return redirect(url_for('listar_clientes'))

        except sqlite3.IntegrityError as e:
            if "UNIQUE constraint failed: clientes.cpf" in str(e):
                flash('Erro: Já existe outro cliente com este CPF.', 'danger')
            elif "UNIQUE constraint failed: usuarios.login" in str(e):
                flash('Erro: Já existe um usuário com este login web. Escolha outro.', 'danger')
            else:
                flash(f'Erro de integridade ao cadastrar cliente: {e}', 'danger')
            conn.rollback() # Garante que a transação seja desfeita em caso de erro
        except Exception as e:
            flash(f'Erro ao cadastrar cliente ou acesso web: {e}', 'danger')
            conn.rollback()
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
    # Junta com usuarios para verificar se o cliente tem acesso web
    c.execute("""
        SELECT 
            c.id, 
            c.nome, 
            c.cpf, 
            c.telefone, 
            u.id IS NOT NULL AS tem_acesso_web 
        FROM clientes c
        LEFT JOIN usuarios u ON c.id = u.id_cliente AND u.permissao = 'cliente'
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
        
        criar_acesso_web = request.form.get('criar_acesso_web') # Checkbox para criar/manter acesso
        login_web = request.form.get('login_web', '').strip()
        senha_web = request.form.get('senha_web', '').strip()
        
        if not nome or not cpf:
            flash('Nome e CPF são campos obrigatórios para o cliente.', 'danger')
            # Busca novamente os dados para re-renderizar
            c.execute("SELECT id, nome, cpf, telefone FROM clientes WHERE id=?", (id,))
            cliente_info = c.fetchone()
            c.execute("SELECT login FROM usuarios WHERE id_cliente=? AND permissao='cliente'", (id,))
            cliente_web_info = c.fetchone()
            conn.close()
            return render_template('editar_cliente.html', cliente=cliente_info, 
                                   cliente_web_login=cliente_web_info[0] if cliente_web_info else None,
                                   permissao=session['permissao'])

        try:
            # Atualiza dados do cliente
            c.execute("UPDATE clientes SET nome=?, cpf=?, telefone=? WHERE id=?", 
                      (nome, cpf, telefone, id))
            conn.commit()
            flash('Dados do cliente atualizados com sucesso!', 'success')

            # Lógica para acesso web na tabela usuarios
            c.execute("SELECT id, login FROM usuarios WHERE id_cliente=? AND permissao='cliente'", (id,))
            acesso_web_existente = c.fetchone()

            if criar_acesso_web: # Se o checkbox "Criar Acesso Web" está marcado
                if not acesso_web_existente: # E não existe um acesso web para este cliente
                    if not login_web or not senha_web:
                        flash('Login e Senha para o acesso web são obrigatórios para criar um novo acesso.', 'danger')
                    else:
                        hashed_senha_web = generate_password_hash(senha_web, method='pbkdf2:sha256')
                        c.execute("INSERT INTO usuarios (nome, login, senha, permissao, id_cliente) VALUES (?, ?, ?, ?, ?)",
                                  (nome, login_web, hashed_senha_web, 'cliente', id))
                        conn.commit()
                        flash(f'Acesso web criado para o cliente {nome} com login: {login_web}!', 'success')
                else: # Já existe um acesso web, então tenta atualizar (se houver dados novos)
                    update_login = False
                    update_senha = False
                    if login_web and login_web != acesso_web_existente[1]: # Se o login foi fornecido e é diferente
                        update_login = True
                    if senha_web: # Se uma nova senha foi fornecida
                        update_senha = True
                    
                    if update_login and update_senha:
                        hashed_senha_web = generate_password_hash(senha_web, method='pbkdf2:sha256')
                        c.execute("UPDATE usuarios SET login=?, senha=? WHERE id=?",
                                  (login_web, hashed_senha_web, acesso_web_existente[0]))
                        conn.commit()
                        flash('Login e senha do acesso web atualizados!', 'success')
                    elif update_login:
                        c.execute("UPDATE usuarios SET login=? WHERE id=?",
                                  (login_web, acesso_web_existente[0]))
                        conn.commit()
                        flash('Login do acesso web atualizado!', 'success')
                    elif update_senha:
                        hashed_senha_web = generate_password_hash(senha_web, method='pbkdf2:sha256')
                        c.execute("UPDATE usuarios SET senha=? WHERE id=?",
                                  (hashed_senha_web, acesso_web_existente[0]))
                        conn.commit()
                        flash('Senha do acesso web atualizada!', 'success')
                    elif login_web == acesso_web_existente[1] and not senha_web:
                        flash('Nenhuma alteração detectada no acesso web.', 'info')
                    elif login_web and login_web != acesso_web_existente[1] and not update_senha:
                        flash('Erro: Já existe um usuário com este novo login web. Escolha outro.', 'danger')

            else: # Se o checkbox "Criar Acesso Web" NÃO está marcado
                if acesso_web_existente and (login_web or senha_web): # Se desmarcou mas tentou mudar dados
                    flash('Acesso web existente. Para editar, marque a opção "Criar/Editar Acesso Web". Para excluir, a funcionalidade ainda não está disponível.', 'info')

        except sqlite3.IntegrityError as e:
            if "UNIQUE constraint failed: clientes.cpf" in str(e):
                flash('Erro: Já existe outro cliente com este CPF.', 'danger')
            elif "UNIQUE constraint failed: usuarios.login" in str(e):
                flash('Erro: Já existe um usuário com este login web. Escolha outro.', 'danger')
            else:
                 flash(f'Erro de integridade: {e}', 'danger')
            conn.rollback() # Garante que a transação seja desfeita em caso de erro
        except Exception as e:
            flash(f'Erro ao atualizar cliente ou acesso web: {e}', 'danger')
            conn.rollback()
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
        
        # Busca o login web do cliente na tabela 'usuarios'
        c.execute("SELECT login FROM usuarios WHERE id_cliente=? AND permissao='cliente'", (id,))
        cliente_web_info = c.fetchone()
        conn.close()

        return render_template('editar_cliente.html', 
                               cliente=cliente_info, 
                               cliente_web_login=cliente_web_info[0] if cliente_web_info else None,
                               permissao=session['permissao']) # Passa permissao para o template

@app.route('/alterar_senha_cliente', methods=['GET', 'POST'])
def alterar_senha_cliente():
    # Verifica se o usuário está logado
    if 'usuario_id' not in session:
        flash('Você precisa estar logado para alterar sua senha.', 'danger')
        return redirect(url_for('login'))
    
    conn = None
    try:
        conn = sqlite3.connect(DB) # CORRIGIDO: Usando DB
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
            
            # Redireciona para o dashboard apropriado após a alteração
            if session.get('permissao') == 'cliente':
                return redirect(url_for('cliente_dashboard'))
            else:
                return redirect(url_for('dashboard'))

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
    
    # Em caso de erro grave, redireciona para o dashboard (ou login se não estiver logado)
    if 'permissao' in session and session['permissao'] == 'cliente':
        return redirect(url_for('cliente_dashboard'))
    elif 'permissao' in session:
        return redirect(url_for('dashboard'))
    else:
        return redirect(url_for('login'))

# Rota Excluir Cliente
@app.route('/excluir_cliente/<int:cliente_id>', methods=['POST'])
@login_required('admin', 'atendente')
def excluir_cliente(cliente_id):
    conn = sqlite3.connect('assistencia.db')
    cursor = conn.cursor()
    try:
        # 1. Verificar se o cliente existe
        cursor.execute("SELECT nome FROM clientes WHERE id = ?", (cliente_id,))
        cliente_db = cursor.fetchone()
        if not cliente_db:
            flash('Cliente não encontrado.', 'danger')
            return redirect(url_for('listar_clientes'))

        cliente_nome = cliente_db[0]

        # 2. Verificar se o cliente tem ordens de serviço associadas
        cursor.execute("SELECT COUNT(*) FROM ordens_servico WHERE id_cliente = ?", (cliente_id,))
        count_os = cursor.fetchone()[0]

        if count_os > 0:
            flash(f'Não é possível excluir o cliente "{cliente_nome}" porque ele possui {count_os} ordem(ns) de serviço associada(s). Remova ou reassocie as OSs primeiro.', 'danger')
            return redirect(url_for('listar_clientes'))

        # 3. Se não houver OSs, remover o acesso web do cliente (se existir)
        cursor.execute("DELETE FROM usuarios WHERE id_cliente = ? AND permissao = 'cliente'", (cliente_id,))

        # 4. Excluir o cliente da tabela 'clientes'
        cursor.execute("DELETE FROM clientes WHERE id = ?", (cliente_id,))
        conn.commit()

        flash(f'Cliente "{cliente_nome}" e seu acesso web (se existia) excluídos com sucesso!', 'success')

    except Exception as e:
        conn.rollback()
        flash(f'Erro ao excluir cliente: {e}', 'danger')
    finally:
        conn.close()
    return redirect(url_for('listar_clientes'))

# Rota para Download do Banco de Dados como Backup
@app.route('/baixar_backup_db')
@login_required('admin')
def baixar_backup_db():
    db_path = 'assistencia.db' # Caminho do seu banco de dados ativo

    if not os.path.exists(db_path):
        flash('Arquivo do banco de dados não encontrado no servidor.', 'danger')
        return redirect(url_for('gerenciar_backup'))

    try:
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        download_filename = f'assistencia_db_backup_{timestamp}.db'

        return send_file(db_path, as_attachment=True, download_name=download_filename, mimetype='application/x-sqlite3')
    except Exception as e:
        flash(f'Erro ao preparar o download do backup: {e}', 'danger')
        return redirect(url_for('gerenciar_backup'))

# Rota para Gerenciar Backups (apenas para Admin) - AGORA ENVIA A LISTA DE BACKUPS
@app.route('/gerenciar_backup', methods=['GET', 'POST'])
@login_required('admin')
def gerenciar_backup():
    if request.method == 'POST':
        backup_dir = request.form.get('backup_dir')
        if not backup_dir:
            flash('Por favor, forneça um diretório para o backup.', 'danger')
            return redirect(url_for('gerenciar_backup'))

        # Tentar criar o diretório se não existir
        try:
            os.makedirs(backup_dir, exist_ok=True)
        except OSError as e:
            flash(f'Erro ao criar o diretório de backup: {e}', 'danger')
            # Retorna para a página com a lista de backups atualizada
            return render_template('gerenciar_backup.html', 
                                   last_backup_dir=backup_dir, 
                                   available_backups=get_available_server_backups())

        db_path = 'assistencia.db' 
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        # Use o BACKUP_DIR configurado para salvar o backup
        backup_filename = f'assistencia_backup_{timestamp}.db'
        backup_filepath = os.path.join(BACKUP_DIR, backup_filename) # Salva no BACKUP_DIR definido
        
        try:
            shutil.copy2(db_path, backup_filepath)
            flash(f'Backup do banco de dados realizado com sucesso em: {backup_filepath}', 'success')
        except Exception as e:
            flash(f'Erro ao realizar o backup: {e}', 'danger')
        
        # Retorna para a página com a lista de backups atualizada
        return render_template('gerenciar_backup.html', 
                               last_backup_dir=backup_dir, 
                               available_backups=get_available_server_backups())

    # GET request: Carrega e exibe a lista de backups
    available_backups = get_available_server_backups()
    return render_template('gerenciar_backup.html', last_backup_dir='', available_backups=available_backups)


# Rota para Restaurar Backup (apenas para Admin) - AGORA RECEBE UM ARQUIVO DA LISTA
@app.route('/restaurar_backup', methods=['POST'])
@login_required('admin')
def restaurar_backup():
    # O valor enviado do formulário será o nome do arquivo de backup (filename)
    chosen_backup_filename = request.form.get('chosen_backup_filename') 
    
    if not chosen_backup_filename:
        flash('Por favor, selecione um arquivo de backup para restaurar.', 'danger')
        return redirect(url_for('gerenciar_backup'))

    backup_file_path = os.path.join(BACKUP_DIR, chosen_backup_filename)

    if not os.path.exists(backup_file_path):
        flash('Arquivo de backup não encontrado no caminho especificado no servidor.', 'danger')
        return redirect(url_for('gerenciar_backup'))

    # Verifica se o arquivo é um .db para segurança extra, embora a listagem já deva garantir isso
    if not backup_file_path.endswith('.db'):
        flash('O arquivo selecionado não é um arquivo de banco de dados válido (.db).', 'danger')
        return redirect(url_for('gerenciar_backup'))

    db_path = 'assistencia.db' # Caminho do seu banco de dados ativo

    try:
        # **PASSO CRÍTICO**: Fechar todas as conexões existentes antes de substituir o arquivo
        # Em uma aplicação Flask simples, isso pode ser feito garantindo que o SQLite
        # não esteja com conexões abertas no momento do shutil.copy2
        # Idealmente, a aplicação seria reiniciada após esta operação.

        # Criar um backup de segurança do DB atual antes de restaurar
        timestamp_prev = datetime.now().strftime('%Y%m%d_%H%M%S')
        temp_backup_filename = f'assistencia_PRE_RESTAURACAO_{timestamp_prev}.db'
        temp_backup_filepath = os.path.join(os.path.dirname(db_path), temp_backup_filename)
        
        shutil.copy2(db_path, temp_backup_filepath)
        flash(f'Backup de segurança do banco de dados atual criado em: {temp_backup_filepath}', 'info')

        # Realizar a restauração
        shutil.copy2(backup_file_path, db_path)
        flash('Banco de dados restaurado com sucesso! É ALTAMENTE RECOMENDADO REINICIAR O SERVIDOR DO FLASK AGORA.', 'success')
    except Exception as e:
        flash(f'Erro ao restaurar o backup: {e}. Certifique-se de que o arquivo não está em uso e o caminho está correto.', 'danger')
    
    return redirect(url_for('gerenciar_backup'))

if __name__ == '__main__':
    inicializar_banco()
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=True)