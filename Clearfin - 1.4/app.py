import os
import time
import calendar
import holidays
from datetime import datetime, date
from collections import defaultdict
from flask import Flask, render_template, request, redirect, url_for, session, flash
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import text
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)

app.secret_key = os.getenv("SECRET_KEY", "chave_secreta_para_desenvolvimento")
app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE='Lax',
)

basedir = os.path.abspath(os.path.dirname(__file__))
database_url = os.getenv("DATABASE_URL", f"sqlite:///{os.path.join(basedir, 'financas.db')}")

if database_url.startswith("mysql://"):
    database_url = database_url.replace("mysql://", "mysql+pymysql://", 1)

app.config['SQLALCHEMY_DATABASE_URI'] = database_url

db = SQLAlchemy(app)

class Usuario(db.Model):
    __tablename__ = 'usuarios'
    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(100), nullable=False)
    usuario = db.Column(db.String(50), unique=True, nullable=False)
    senha = db.Column(db.String(255), nullable=False)

class Transacao(db.Model):
    __tablename__ = 'transacoes'
    id = db.Column(db.Integer, primary_key=True)
    usuario_id = db.Column(db.Integer, db.ForeignKey('usuarios.id'), nullable=False)
    descricao = db.Column(db.String(200), nullable=False)
    valor = db.Column(db.Float, nullable=False)
    tipo = db.Column(db.String(20), nullable=False)
    categoria = db.Column(db.String(50))
    forma_pagamento = db.Column(db.String(50))
    data_vencimento = db.Column(db.String(10), nullable=False)
    pago = db.Column(db.Integer, default=0)
    grupo_id = db.Column(db.String(50))

class Meta(db.Model):
    __tablename__ = 'metas'
    id = db.Column(db.Integer, primary_key=True)
    usuario_id = db.Column(db.Integer, db.ForeignKey('usuarios.id'), nullable=False)
    titulo = db.Column(db.String(100), nullable=False)
    valor_atual = db.Column(db.Float, default=0.0)
    valor_objetivo = db.Column(db.Float, nullable=False)
    icone = db.Column(db.String(10), default='🎯')

with app.app_context():
    db.create_all()
    try:
        with db.engine.connect() as conn:
            conn.execute(text("ALTER TABLE transacoes ADD COLUMN forma_pagamento VARCHAR(50);"))
            conn.commit()
    except Exception:
        pass

def obter_n_dia_util(ano, mes, n_dia_util):
    feriados_br = holidays.Brazil(years=ano)
    dias_uteis = 0
    dia = 1
    ultimo_dia = calendar.monthrange(ano, mes)[1]
    
    while dia <= ultimo_dia:
        data_atual = date(ano, mes, dia)
        if data_atual.weekday() < 5 and data_atual not in feriados_br:
            dias_uteis += 1
            if dias_uteis == n_dia_util:
                return data_atual
        dia += 1
    
    return date(ano, mes, ultimo_dia)

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        login_name = request.form.get('log_usuario')
        senha = request.form.get('log_senha')
        
        if not login_name or not senha:
            flash("Preencha todos os campos para entrar.")
            return redirect(url_for('login'))
            
        login_name = login_name.strip().lower()
        usuario = Usuario.query.filter_by(usuario=login_name).first()
        
        if usuario and check_password_hash(usuario.senha, senha):
            session['usuario_id'] = usuario.id
            session['usuario_nome'] = usuario.nome
            return redirect(url_for('index'))
        else:
            flash("Usuário ou senha incorretos.")
            
    return render_template('login.html')

@app.route('/cadastro', methods=['POST'])
def cadastro():
    nome_exibicao = request.form.get('cad_nome')
    login_name = request.form.get('cad_usuario')
    senha = request.form.get('cad_senha')
    
    if not nome_exibicao or not login_name or not senha:
        flash("Por favor, preencha todos os campos do cadastro.")
        return redirect(url_for('login'))
        
    nome_exibicao = nome_exibicao.strip()
    login_name = login_name.strip().lower()
    
    if " " in login_name:
        flash("O Nome de Login não pode conter espaços.")
        return redirect(url_for('login'))
        
    if len(senha) < 6:
        flash("A senha precisa ter pelo menos 6 caracteres.")
        return redirect(url_for('login'))
        
    if Usuario.query.filter_by(usuario=login_name).first():
        flash("Este Nome de Login já está em uso. Escolha outro.")
        return redirect(url_for('login'))
        
    senha_hash = generate_password_hash(senha)
    novo_usuario = Usuario(nome=nome_exibicao, usuario=login_name, senha=senha_hash)
    
    db.session.add(novo_usuario)
    db.session.commit()
    
    session['usuario_id'] = novo_usuario.id
    session['usuario_nome'] = novo_usuario.nome
    
    return redirect(url_for('index'))

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

@app.route('/')
def index():
    if 'usuario_id' not in session:
        return redirect(url_for('login'))
        
    usuario_id = session['usuario_id']
    aba_ativa = request.args.get('aba', 'dashboard')
    
    hoje = datetime.today().strftime("%Y-%m-%d")
    mes_atual = datetime.today().strftime("%Y-%m")
    
    transacoes = Transacao.query.filter_by(usuario_id=usuario_id).order_by(Transacao.data_vencimento.asc()).all()
    metas = Meta.query.filter_by(usuario_id=usuario_id).all()
    
    mes_selecionado = request.args.get('mes')
    ano_selecionado = request.args.get('ano')
    transacoes_mes = []
    total_entradas_mes = 0.0
    total_saidas_mes = 0.0

    if mes_selecionado and ano_selecionado:
        mes_str = str(mes_selecionado).zfill(2)
        mes_ano_filtro = f"{ano_selecionado}-{mes_str}"
        transacoes_mes = [t for t in transacoes if t.data_vencimento.startswith(mes_ano_filtro)]
        total_entradas_mes = sum(t.valor for t in transacoes_mes if t.tipo == 'receita')
        total_saidas_mes = sum(t.valor for t in transacoes_mes if t.tipo == 'despesa')

    saldo_real = 0.0
    contas_a_pagar = 0.0
    
    extrato_mensal = defaultdict(lambda: {'receitas': 0.0, 'despesas': 0.0, 'saldo_mes': 0.0, 'qtd': 0})
    extrato_futuro = defaultdict(lambda: {'receitas': 0.0, 'despesas': 0.0, 'saldo_mes': 0.0, 'lista': []})
    
    for t in transacoes:
        mes_ano = t.data_vencimento[:7]
        
        if mes_ano <= mes_atual:
            if t.pago == 1:
                if t.tipo == 'receita': saldo_real += t.valor
                else: saldo_real -= t.valor
            else:
                if t.tipo == 'despesa': contas_a_pagar += t.valor
            
            if t.tipo == 'receita':
                extrato_mensal[mes_ano]['receitas'] += t.valor
                extrato_mensal[mes_ano]['saldo_mes'] += t.valor
            else:
                extrato_mensal[mes_ano]['despesas'] += t.valor
                extrato_mensal[mes_ano]['saldo_mes'] -= t.valor
            extrato_mensal[mes_ano]['qtd'] += 1

        else:
            if t.tipo == 'receita':
                extrato_futuro[mes_ano]['receitas'] += t.valor
                extrato_futuro[mes_ano]['saldo_mes'] += t.valor
            else:
                extrato_futuro[mes_ano]['despesas'] += t.valor
                extrato_futuro[mes_ano]['saldo_mes'] -= t.valor
            extrato_futuro[mes_ano]['lista'].append(t)
            
    saldo_acumulado = saldo_real
    projecao_futura = []
    
    for mes_key in sorted(extrato_futuro.keys()):
        dados = extrato_futuro[mes_key]
        saldo_acumulado += dados['saldo_mes']
        projecao_futura.append({
            'mes': mes_key,
            'receitas': dados['receitas'],
            'despesas': dados['despesas'],
            'saldo_mes': dados['saldo_mes'],
            'saldo_projetado': saldo_acumulado,
            'transacoes': dados['lista']
        })

    ultimas_transacoes = []
    vistos = set()
    transacoes_recentes = sorted([t for t in transacoes if t.data_vencimento[:7] <= mes_atual], key=lambda x: x.id, reverse=True)
    
    for t in transacoes_recentes:
        nome_base = t.descricao.split(' (')[0]
        chave = (nome_base, t.valor)
        if chave not in vistos:
            vistos.add(chave)
            lote = [x for x in transacoes if x.descricao.split(' (')[0] == nome_base and x.valor == t.valor]
            if lote:
                ultimas_transacoes.append(min(lote, key=lambda x: x.id))
        if len(ultimas_transacoes) >= 3:
            break
    
    extrato_ordenado = dict(sorted(extrato_mensal.items(), reverse=True))
            
    return render_template('index.html', 
                           transacoes=transacoes, 
                           ultimas_transacoes=ultimas_transacoes,
                           metas=metas,
                           saldo=saldo_real, 
                           contas_a_pagar=contas_a_pagar,
                           aba_ativa=aba_ativa,
                           hoje=hoje,
                           mes_atual=mes_atual,
                           extrato_ordenado=extrato_ordenado,
                           projecao_futura=projecao_futura,
                           mes_selecionado=mes_selecionado,
                           ano_selecionado=ano_selecionado,
                           transacoes_mes=transacoes_mes,
                           total_entradas_mes=total_entradas_mes,
                           total_saidas_mes=total_saidas_mes)

@app.route('/adicionar', methods=['POST'])
def adicionar():
    if 'usuario_id' not in session:
        return redirect(url_for('login'))
    
    desc = request.form.get('descricao')
    valor_base = float(request.form.get('valor') or 0)
    comissao = float(request.form.get('valor_comissao') or 0)
    valor_total = valor_base + comissao
    
    tipo = request.form.get('tipo')
    categoria = request.form.get('categoria', 'Outros')
    forma_pagamento = request.form.get('forma_pagamento') or request.form.get('forma_recebimento')
    data = request.form.get('data_vencimento') or datetime.today().strftime("%Y-%m-%d")
    
    pago = 1 if request.form.get('pago') == 'on' else 0
    eh_parcelado = request.form.get('eh_parcelado') == 'on'
    qtd_parcelas_str = request.form.get('qtd_parcelas')
    tipo_repeticao = request.form.get('tipo_repeticao') or 'dia_fixo'
    qual_dia_util = int(request.form.get('qual_dia_util') or 5)
    
    grupo_id = str(int(time.time() * 1000))
    ano, mes, dia = map(int, data.split('-'))
    
    ciclos = int(qtd_parcelas_str) if (eh_parcelado and qtd_parcelas_str) else 1

    for i in range(ciclos):
        desc_final = f"{desc} ({i+1}/{ciclos})" if (eh_parcelado and ciclos > 1) else desc
        status_pago = pago if i == 0 else 0
        
        novo_mes = ((mes + i - 1) % 12) + 1
        novo_ano = ano + ((mes + i - 1) // 12)
        
        if eh_parcelado and tipo_repeticao == 'dia_util':
            data_final = obter_n_dia_util(novo_ano, novo_mes, qual_dia_util).strftime("%Y-%m-%d")
        else:
            ultimo_dia_do_mes = calendar.monthrange(novo_ano, novo_mes)[1]
            novo_dia = min(dia, ultimo_dia_do_mes)
            data_final = f"{novo_ano:04d}-{novo_mes:02d}-{novo_dia:02d}"
        
        nova_transacao = Transacao(
            usuario_id=session['usuario_id'],
            descricao=desc_final,
            valor=valor_total,
            tipo=tipo,
            categoria=categoria,
            forma_pagamento=forma_pagamento,
            data_vencimento=data_final,
            pago=status_pago,
            grupo_id=grupo_id
        )
        db.session.add(nova_transacao)
        
    db.session.commit()
    return redirect(url_for('index', aba='extrato'))

@app.route('/adicionar_meta', methods=['POST'])
def adicionar_meta():
    if 'usuario_id' not in session:
        return redirect(url_for('login'))
    
    titulo = request.form.get('titulo')
    valor_atual = float(request.form.get('valor_atual') or 0)
    valor_objetivo = float(request.form.get('valor_objetivo') or 0)
    icone = request.form.get('icone') or '🎯'
    
    nova_meta = Meta(
        usuario_id=session['usuario_id'],
        titulo=titulo,
        valor_atual=valor_atual,
        valor_objetivo=valor_objetivo,
        icone=icone
    )
    db.session.add(nova_meta)
    db.session.commit()
    
    return redirect(url_for('index', aba='metas'))

@app.route('/excluir_meta/<int:id>')
def excluir_meta(id):
    if 'usuario_id' not in session:
        return redirect(url_for('login'))
    
    meta = Meta.query.filter_by(id=id, usuario_id=session['usuario_id']).first()
    if meta:
        db.session.delete(meta)
        db.session.commit()
        
    return redirect(url_for('index', aba='metas'))

@app.route('/excluir_serie/<int:id>')
def excluir_serie(id):
    if 'usuario_id' not in session:
        return redirect(url_for('login'))
    
    t = Transacao.query.filter_by(id=id, usuario_id=session['usuario_id']).first()
    
    if t:
        if t.grupo_id:
            Transacao.query.filter(
                Transacao.grupo_id == t.grupo_id,
                Transacao.usuario_id == session['usuario_id'],
                Transacao.data_vencimento >= t.data_vencimento
            ).delete(synchronize_session=False)
        else:
            db.session.delete(t)
        db.session.commit()
        
    return redirect(request.referrer or url_for('index'))

@app.route('/alternar_status/<int:id>')
def alternar_status(id):
    if 'usuario_id' not in session:
        return redirect(url_for('login'))
    
    transacao = Transacao.query.filter_by(id=id, usuario_id=session['usuario_id']).first()
    if transacao:
        transacao.pago = 0 if transacao.pago == 1 else 1
        db.session.commit()
        
    return redirect(request.referrer or url_for('index', aba='extrato'))

@app.route('/deletar/<int:id>')
@app.route('/remover/<int:id>')
@app.route('/excluir/<int:id>', methods=['GET', 'POST'])
def excluir(id):
    if 'usuario_id' not in session:
        return redirect(url_for('login'))
        
    transacao = Transacao.query.filter_by(id=id, usuario_id=session['usuario_id']).first()
    if transacao:
        db.session.delete(transacao)
        db.session.commit()
        
    return redirect(request.referrer or url_for('index'))

@app.route('/detalhes/<mes_ano>')
def detalhes(mes_ano):
    if 'usuario_id' not in session: 
        return redirect(url_for('login'))
        
    transacoes_mes = Transacao.query.filter(
        Transacao.usuario_id == session['usuario_id'],
        Transacao.data_vencimento.like(f"{mes_ano}%")
    ).order_by(Transacao.data_vencimento.asc()).all()
    
    entradas = sum(t.valor for t in transacoes_mes if t.tipo == 'receita')
    saidas = sum(t.valor for t in transacoes_mes if t.tipo == 'despesa')
    saldo_final = entradas - saidas
    
    return render_template('detalhes.html', 
                           transacoes=transacoes_mes, 
                           mes_ano=mes_ano,
                           entradas=entradas,
                           saidas=saidas,
                           saldo_final=saldo_final)

@app.route('/editar/<int:id>', methods=['GET', 'POST'])
def editar(id):
    if 'usuario_id' not in session:
        return redirect(url_for('login'))
    
    transacao = Transacao.query.filter_by(id=id, usuario_id=session['usuario_id']).first()
    if not transacao:
        flash("Transação não encontrada.")
        return redirect(url_for('index'))
        
    if request.method == 'POST':
        transacao.descricao = request.form.get('descricao')
        transacao.valor = float(request.form.get('valor') or 0)
        transacao.categoria = request.form.get('categoria', 'Outros')
        transacao.forma_pagamento = request.form.get('forma_pagamento', 'Outros')
        transacao.data_vencimento = request.form.get('data_vencimento')
        transacao.pago = 1 if request.form.get('pago') == 'on' else 0
        
        db.session.commit()
        return redirect(url_for('index', aba='extrato'))
        
    return render_template('editar.html', transacao=transacao)

from datetime import date
from flask import request, redirect, url_for, session

@app.route('/depositar_meta/<int:id>', methods=['POST'])
def depositar_meta(id):
    valor = float(request.form.get('valor', 0))
    
    if valor > 0:
        meta = Meta.query.get_or_404(id)
        meta.valor_atual += valor
        
        # Cria a transação informando o usuario_id da sessão ativa
        nova_transacao = Transacao(
            usuario_id=session.get('usuario_id'), # Vincula a transação ao usuário logado
            descricao=f"Aporte: {meta.titulo}",
            valor=valor,
            tipo='despesa',
            categoria='Metas',
            data_vencimento=date.today().strftime('%Y-%m-%d'),
            pago=1,
            forma_pagamento='pix'
        )
        
        db.session.add(nova_transacao)
        db.session.commit()
        
    return redirect(url_for('index', aba='metas'))

if __name__ == '__main__':
    app.run(debug=True, host="0.0.0.0", port=5000)