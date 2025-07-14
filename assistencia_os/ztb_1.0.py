import tkinter as tk
from tkinter import messagebox
from fpdf import FPDF
import webbrowser
from datetime import datetime
import os
import unicodedata
import sqlite3
import subprocess
import sys

def remover_acentos(txt):
    return ''.join(c for c in unicodedata.normalize('NFKD', txt) if not unicodedata.combining(c))

def carregar_num_os():
    if os.path.exists("os_contador.txt"):
        with open("os_contador.txt", "r") as f:
            return int(f.read())
    return 1

def salvar_num_os(numero):
    with open("os_contador.txt", "w") as f:
        f.write(str(numero))

def abrir_pdf(caminho_pdf):
    if sys.platform.startswith('win'):
        os.startfile(caminho_pdf)
    elif sys.platform.startswith('linux'):
        subprocess.call(["xdg-open", caminho_pdf])
    elif sys.platform.startswith('darwin'):
        subprocess.call(["open", caminho_pdf])

def criar_base_dados():
    conn = sqlite3.connect("ordens.db")
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS ordens_servico (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            codigo_os TEXT,
            nome_cliente TEXT,
            telefone TEXT,
            equipamento TEXT,
            numero_serie TEXT,
            defeito TEXT,
            data_entrada TEXT,
            nome_arquivo_pdf TEXT
        )
    ''')
    conn.commit()
    conn.close()

def salvar_no_banco(codigo_os, nome, telefone, equipamento, num_serie, defeito, data_entrada, nome_pdf):
    conn = sqlite3.connect("ordens.db")
    c = conn.cursor()
    c.execute('''
        INSERT INTO ordens_servico (
            codigo_os, nome_cliente, telefone, equipamento, numero_serie,
            defeito, data_entrada, nome_arquivo_pdf
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    ''', (codigo_os, nome, telefone, equipamento, num_serie, defeito, data_entrada, nome_pdf))
    conn.commit()
    conn.close()

def gerar_os():
    nome = entry_nome.get()
    telefone = entry_telefone.get()
    equipamento = entry_equip.get()
    defeito = entry_defeito.get()
    num_serie = entry_serie.get()

    if not all([nome, telefone, equipamento, defeito, num_serie]):
        messagebox.showerror("Erro", "Preencha todos os campos!")
        return

    numero_os = carregar_num_os()
    codigo_os = f"OS-{numero_os:03}"
    salvar_num_os(numero_os + 1)

    data_entrada = datetime.now().strftime("%d/%m/%Y %H:%M")
    nome_sem_acentos = remover_acentos(nome.replace(" ", "_"))
    nome_arquivo = f"{codigo_os}_{nome_sem_acentos}.pdf"
    caminho_completo = os.path.abspath(nome_arquivo)

    # Gerar PDF
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", 'B', 16)
    pdf.cell(190, 10, f"Ordem de Serviço - {codigo_os}", ln=True, align='C')

    pdf.set_font("Arial", size=12)
    pdf.ln(10)
    pdf.cell(40, 10, "Cliente:")
    pdf.cell(100, 10, nome, ln=True)
    pdf.cell(40, 10, "Telefone:")
    pdf.cell(100, 10, telefone, ln=True)
    pdf.cell(40, 10, "Equipamento:")
    pdf.cell(100, 10, equipamento, ln=True)
    pdf.cell(40, 10, "Nº de Série:")
    pdf.cell(100, 10, num_serie, ln=True)
    pdf.cell(40, 10, "Defeito:")
    pdf.multi_cell(140, 10, defeito)
    pdf.cell(40, 10, "Data de Entrada:")
    pdf.cell(100, 10, data_entrada, ln=True)
    pdf.ln(20)
    pdf.cell(180, 10, "Assinatura do Cliente: ___________________________", ln=True)

    try:
        pdf.output(caminho_completo)
        abrir_pdf(caminho_completo)
        messagebox.showinfo("PDF Gerado", f"PDF salvo em:\n{caminho_completo}")
    except Exception as e:
        messagebox.showerror("Erro ao gerar PDF", str(e))
        return

    # Salvar no banco
    salvar_no_banco(codigo_os, nome, telefone, equipamento, num_serie, defeito, data_entrada, nome_arquivo)

    # WhatsApp
    mensagem = (
        f"Olá {nome},\n"
        f"Seu equipamento foi recebido com sucesso!\n"
        f"Nº da Ordem de Serviço: {codigo_os}\n"
        f"Equipamento: {equipamento}\n"
        f"Nº de Série: {num_serie}\n"
        f"Defeito informado: {defeito}\n"
        f"Data da entrada: {data_entrada}\n"
        "Acompanhe conosco qualquer novidade. 👍"
    )

    telefone_formatado = telefone.strip().replace(" ", "").replace("-", "").replace("(", "").replace(")", "")
    link_whatsapp = f"https://wa.me/55{telefone_formatado}?text={mensagem.replace(' ', '%20').replace('\n', '%0A')}"
    webbrowser.open(link_whatsapp)

# INÍCIO do programa
criar_base_dados()

# Interface gráfica
janela = tk.Tk()
janela.title("Entrada de Equipamentos")

tk.Label(janela, text="Nome do Cliente").grid(row=0, column=0, sticky='w')
entry_nome = tk.Entry(janela, width=40)
entry_nome.grid(row=0, column=1)

tk.Label(janela, text="Telefone (WhatsApp)").grid(row=1, column=0, sticky='w')
entry_telefone = tk.Entry(janela, width=40)
entry_telefone.grid(row=1, column=1)

tk.Label(janela, text="Equipamento").grid(row=2, column=0, sticky='w')
entry_equip = tk.Entry(janela, width=40)
entry_equip.grid(row=2, column=1)

tk.Label(janela, text="Número de Série").grid(row=3, column=0, sticky='w')
entry_serie = tk.Entry(janela, width=40)
entry_serie.grid(row=3, column=1)

tk.Label(janela, text="Defeito Relatado").grid(row=4, column=0, sticky='w')
entry_defeito = tk.Entry(janela, width=40)
entry_defeito.grid(row=4, column=1)

tk.Button(janela, text="Gerar OS e Enviar WhatsApp", command=gerar_os).grid(row=5, column=0, columnspan=2, pady=10)

janela.mainloop()
