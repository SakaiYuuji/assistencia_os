# Versão 2.0 do sistema de Assistência Técnica

import ttkbootstrap as ttk
from ttkbootstrap.constants import *
import sqlite3
import hashlib
import os
from tkinter import messagebox
from fpdf import FPDF
from datetime import datetime
import webbrowser

# Banco de dados inicial
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
    # Cria admin padrão se não houver nenhum usuário
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
    os.startfile(arquivo)

def tela_principal(usuario):
    root = ttk.Window(title="Sistema de OS - Principal", themename="superhero")
    root.geometry("600x600")

    ttk.Label(root, text=f"Bem-vindo, {usuario[1]}", font=("Arial", 14)).pack(pady=10)

    frame = ttk.Frame(root, padding=20)
    frame.pack(fill=BOTH, expand=YES)

    ttk.Label(frame, text="Cliente:").grid(row=0, column=0, sticky='w')
    cliente_entry = ttk.Entry(frame, width=40)
    cliente_entry.grid(row=0, column=1, pady=5)

    ttk.Label(frame, text="Telefone:").grid(row=1, column=0, sticky='w')
    telefone_entry = ttk.Entry(frame, width=40)
    telefone_entry.grid(row=1, column=1, pady=5)

    ttk.Label(frame, text="Equipamento:").grid(row=2, column=0, sticky='w')
    equipamento_entry = ttk.Entry(frame, width=40)
    equipamento_entry.grid(row=2, column=1, pady=5)

    ttk.Label(frame, text="Nº de Série:").grid(row=3, column=0, sticky='w')
    numero_serie_entry = ttk.Entry(frame, width=40)
    numero_serie_entry.grid(row=3, column=1, pady=5)

    ttk.Label(frame, text="Itens Internos:").grid(row=4, column=0, sticky='nw')
    itens_text = ttk.Text(frame, width=40, height=5)
    itens_text.grid(row=4, column=1, pady=5)

    ttk.Label(frame, text="Defeito Relatado:").grid(row=5, column=0, sticky='nw')
    defeito_text = ttk.Text(frame, width=40, height=5)
    defeito_text.grid(row=5, column=1, pady=5)

    def gerar_ordem():
        codigo_os = f"OS-{datetime.now().strftime('%Y%m%d%H%M%S')}"
        cliente = cliente_entry.get()
        telefone = telefone_entry.get()
        equipamento = equipamento_entry.get()
        numero_serie = numero_serie_entry.get()
        itens = itens_text.get("1.0", "end").strip()
        defeito = defeito_text.get("1.0", "end").strip()
        responsavel = usuario[1]

        if not all([cliente, telefone, equipamento, numero_serie, itens, defeito]):
            messagebox.showerror("Erro", "Preencha todos os campos!")
            return

        salvar_ordem(codigo_os, cliente, telefone, equipamento, numero_serie, itens, defeito, responsavel)
        gerar_pdf_os((codigo_os, cliente, telefone, equipamento, numero_serie, itens, defeito, responsavel))
        messagebox.showinfo("Sucesso", f"OS {codigo_os} criada com sucesso!")

    ttk.Button(root, text="Gerar Ordem de Serviço", command=gerar_ordem, bootstyle=SUCCESS).pack(pady=20)

    root.mainloop()

# Exemplo de uso:
if __name__ == '__main__':
    inicializar_banco()

    app = ttk.Window(themename="superhero")
    app.title("Login - Assistência Técnica")
    app.geometry("300x250")

    ttk.Label(app, text="Usuário:").pack(pady=5)
    usuario_entry = ttk.Entry(app)
    usuario_entry.pack()

    ttk.Label(app, text="Senha:").pack(pady=5)
    senha_entry = ttk.Entry(app, show="*")
    senha_entry.pack()

    def login():
        user = usuario_entry.get()
        pwd = senha_entry.get()
        usuario = verificar_login(user, pwd)
        if usuario:
            messagebox.showinfo("Sucesso", f"Bem-vindo, {usuario[1]}!")
            app.destroy()
            tela_principal(usuario)
        else:
            messagebox.showerror("Erro", "Usuário ou senha inválidos")

    ttk.Button(app, text="Entrar", command=login, bootstyle=SUCCESS).pack(pady=15)
    app.mainloop()