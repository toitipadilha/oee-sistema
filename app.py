from flask import Flask, render_template, request, redirect, url_for, session, jsonify, flash
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime, date, timedelta
from functools import wraps
import json
import os

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'oee-sistema-secret-2024')
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///oee.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)

# ─── MODELS ──────────────────────────────────────────────────────────────────

class Usuario(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    senha_hash = db.Column(db.String(200), nullable=False)
    perfil = db.Column(db.String(20), default='operador')  # admin, gestor, operador
    ativo = db.Column(db.Boolean, default=True)
    criado_em = db.Column(db.DateTime, default=datetime.utcnow)

    def set_senha(self, senha):
        self.senha_hash = generate_password_hash(senha)

    def check_senha(self, senha):
        return check_password_hash(self.senha_hash, senha)


class Maquina(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(100), nullable=False)
    codigo = db.Column(db.String(30), unique=True, nullable=False)
    setor = db.Column(db.String(100))
    tempo_ciclo_ideal = db.Column(db.Float, default=60.0)  # segundos por peça
    ativa = db.Column(db.Boolean, default=True)
    criado_em = db.Column(db.DateTime, default=datetime.utcnow)


class RegistroProducao(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    maquina_id = db.Column(db.Integer, db.ForeignKey('maquina.id'), nullable=False)
    usuario_id = db.Column(db.Integer, db.ForeignKey('usuario.id'), nullable=False)
    data = db.Column(db.Date, nullable=False, default=date.today)
    turno = db.Column(db.String(10), nullable=False)  # Manhã, Tarde, Noite
    hora_inicio = db.Column(db.Time, nullable=False)
    hora_fim = db.Column(db.Time, nullable=False)
    pecas_produzidas = db.Column(db.Integer, default=0)
    pecas_boas = db.Column(db.Integer, default=0)
    pecas_refugo = db.Column(db.Integer, default=0)
    tempo_parada_min = db.Column(db.Float, default=0)  # minutos parados no turno
    criado_em = db.Column(db.DateTime, default=datetime.utcnow)
    maquina = db.relationship('Maquina', backref='registros')
    usuario = db.relationship('Usuario', backref='registros')

    @property
    def tempo_total_min(self):
        dt_inicio = datetime.combine(date.today(), self.hora_inicio)
        dt_fim = datetime.combine(date.today(), self.hora_fim)
        if dt_fim < dt_inicio:
            dt_fim += timedelta(days=1)
        return (dt_fim - dt_inicio).total_seconds() / 60

    @property
    def disponibilidade(self):
        tt = self.tempo_total_min
        if tt == 0:
            return 0
        return max(0, (tt - self.tempo_parada_min) / tt * 100)

    @property
    def performance(self):
        tt = self.tempo_total_min
        tempo_operacao = tt - self.tempo_parada_min
        if tempo_operacao == 0:
            return 0
        maquina = Maquina.query.get(self.maquina_id)
        ciclo_ideal_min = maquina.tempo_ciclo_ideal / 60
        tempo_ideal = self.pecas_produzidas * ciclo_ideal_min
        return min(100, tempo_ideal / tempo_operacao * 100)

    @property
    def qualidade(self):
        if self.pecas_produzidas == 0:
            return 0
        return self.pecas_boas / self.pecas_produzidas * 100

    @property
    def oee(self):
        return (self.disponibilidade / 100) * (self.performance / 100) * (self.qualidade / 100) * 100


class Parada(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    maquina_id = db.Column(db.Integer, db.ForeignKey('maquina.id'), nullable=False)
    usuario_id = db.Column(db.Integer, db.ForeignKey('usuario.id'), nullable=False)
    data = db.Column(db.Date, nullable=False, default=date.today)
    turno = db.Column(db.String(10), nullable=False)
    hora_inicio = db.Column(db.Time, nullable=False)
    hora_fim = db.Column(db.Time)
    motivo = db.Column(db.String(200), nullable=False)
    categoria = db.Column(db.String(50))  # Mecânica, Elétrica, Setup, Falta de material, etc.
    observacao = db.Column(db.Text)
    criado_em = db.Column(db.DateTime, default=datetime.utcnow)
    maquina = db.relationship('Maquina', backref='paradas')
    usuario = db.relationship('Usuario', backref='paradas')

    @property
    def duracao_min(self):
        if not self.hora_fim:
            return None
        dt_inicio = datetime.combine(date.today(), self.hora_inicio)
        dt_fim = datetime.combine(date.today(), self.hora_fim)
        if dt_fim < dt_inicio:
            dt_fim += timedelta(days=1)
        return (dt_fim - dt_inicio).total_seconds() / 60


# ─── AUTH DECORATOR ──────────────────────────────────────────────────────────

def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'usuario_id' not in session:
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated

def admin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'usuario_id' not in session:
            return redirect(url_for('login'))
        if session.get('perfil') not in ['admin', 'gestor']:
            flash('Acesso negado.', 'error')
            return redirect(url_for('dashboard'))
        return f(*args, **kwargs)
    return decorated


# ─── ROUTES ──────────────────────────────────────────────────────────────────

@app.route('/')
def index():
    if 'usuario_id' in session:
        return redirect(url_for('dashboard'))
    return redirect(url_for('login'))


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form.get('email', '').strip().lower()
        senha = request.form.get('senha', '')
        usuario = Usuario.query.filter_by(email=email, ativo=True).first()
        if usuario and usuario.check_senha(senha):
            session['usuario_id'] = usuario.id
            session['nome'] = usuario.nome
            session['perfil'] = usuario.perfil
            return redirect(url_for('dashboard'))
        flash('E-mail ou senha incorretos.', 'error')
    return render_template('login.html')


@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))


@app.route('/dashboard')
@login_required
def dashboard():
    hoje = date.today()
    maquinas = Maquina.query.filter_by(ativa=True).all()

    # OEE do dia
    registros_hoje = RegistroProducao.query.filter_by(data=hoje).all()

    stats = {
        'oee': 0, 'disponibilidade': 0, 'performance': 0, 'qualidade': 0,
        'pecas_boas': 0, 'pecas_refugo': 0, 'total_paradas_min': 0,
        'num_registros': len(registros_hoje)
    }

    if registros_hoje:
        stats['oee'] = sum(r.oee for r in registros_hoje) / len(registros_hoje)
        stats['disponibilidade'] = sum(r.disponibilidade for r in registros_hoje) / len(registros_hoje)
        stats['performance'] = sum(r.performance for r in registros_hoje) / len(registros_hoje)
        stats['qualidade'] = sum(r.qualidade for r in registros_hoje) / len(registros_hoje)
        stats['pecas_boas'] = sum(r.pecas_boas for r in registros_hoje)
        stats['pecas_refugo'] = sum(r.pecas_refugo for r in registros_hoje)
        stats['total_paradas_min'] = sum(r.tempo_parada_min for r in registros_hoje)

    # Paradas do dia
    paradas_hoje = Parada.query.filter_by(data=hoje).order_by(Parada.hora_inicio.desc()).limit(10).all()

    # OEE últimos 7 dias para gráfico
    oee_semana = []
    for i in range(6, -1, -1):
        d = hoje - timedelta(days=i)
        regs = RegistroProducao.query.filter_by(data=d).all()
        oee_val = sum(r.oee for r in regs) / len(regs) if regs else 0
        oee_semana.append({'data': d.strftime('%d/%m'), 'oee': round(oee_val, 1)})

    # Status por máquina
    maquinas_status = []
    for m in maquinas:
        reg = RegistroProducao.query.filter_by(maquina_id=m.id, data=hoje).first()
        maquinas_status.append({
            'maquina': m,
            'oee': round(reg.oee, 1) if reg else None,
            'pecas_boas': reg.pecas_boas if reg else 0,
            'status': 'ok' if reg and reg.oee >= 65 else ('alerta' if reg and reg.oee >= 50 else ('critico' if reg else 'sem_dados'))
        })

    return render_template('dashboard.html',
        stats=stats,
        paradas_hoje=paradas_hoje,
        oee_semana=json.dumps(oee_semana),
        maquinas_status=maquinas_status,
        hoje=hoje
    )


@app.route('/apontar', methods=['GET', 'POST'])
@login_required
def apontar():
    maquinas = Maquina.query.filter_by(ativa=True).all()
    if request.method == 'POST':
        maquina_id = request.form.get('maquina_id')
        turno = request.form.get('turno')
        data_str = request.form.get('data')
        hora_inicio_str = request.form.get('hora_inicio')
        hora_fim_str = request.form.get('hora_fim')
        pecas_produzidas = int(request.form.get('pecas_produzidas', 0))
        pecas_refugo = int(request.form.get('pecas_refugo', 0))
        tempo_parada = float(request.form.get('tempo_parada_min', 0))

        pecas_boas = pecas_produzidas - pecas_refugo
        data = datetime.strptime(data_str, '%Y-%m-%d').date()
        hora_inicio = datetime.strptime(hora_inicio_str, '%H:%M').time()
        hora_fim = datetime.strptime(hora_fim_str, '%H:%M').time()

        reg = RegistroProducao(
            maquina_id=maquina_id,
            usuario_id=session['usuario_id'],
            data=data,
            turno=turno,
            hora_inicio=hora_inicio,
            hora_fim=hora_fim,
            pecas_produzidas=pecas_produzidas,
            pecas_boas=pecas_boas,
            pecas_refugo=pecas_refugo,
            tempo_parada_min=tempo_parada
        )
        db.session.add(reg)
        db.session.commit()
        flash('Produção registrada com sucesso!', 'success')
        return redirect(url_for('apontar'))

    hoje = date.today().strftime('%Y-%m-%d')
    hora_atual = datetime.now().strftime('%H:%M')
    return render_template('apontar.html', maquinas=maquinas, hoje=hoje, hora_atual=hora_atual)


@app.route('/paradas', methods=['GET', 'POST'])
@login_required
def paradas():
    maquinas = Maquina.query.filter_by(ativa=True).all()
    if request.method == 'POST':
        maquina_id = request.form.get('maquina_id')
        turno = request.form.get('turno')
        data_str = request.form.get('data')
        hora_inicio_str = request.form.get('hora_inicio')
        hora_fim_str = request.form.get('hora_fim', '')
        motivo = request.form.get('motivo')
        categoria = request.form.get('categoria')
        observacao = request.form.get('observacao', '')

        data = datetime.strptime(data_str, '%Y-%m-%d').date()
        hora_inicio = datetime.strptime(hora_inicio_str, '%H:%M').time()
        hora_fim = datetime.strptime(hora_fim_str, '%H:%M').time() if hora_fim_str else None

        parada = Parada(
            maquina_id=maquina_id,
            usuario_id=session['usuario_id'],
            data=data,
            turno=turno,
            hora_inicio=hora_inicio,
            hora_fim=hora_fim,
            motivo=motivo,
            categoria=categoria,
            observacao=observacao
        )
        db.session.add(parada)
        db.session.commit()
        flash('Parada registrada!', 'success')
        return redirect(url_for('paradas'))

    paradas_lista = Parada.query.order_by(Parada.data.desc(), Parada.hora_inicio.desc()).limit(50).all()
    hoje = date.today().strftime('%Y-%m-%d')
    hora_atual = datetime.now().strftime('%H:%M')
    return render_template('paradas.html', maquinas=maquinas, paradas=paradas_lista, hoje=hoje, hora_atual=hora_atual)


@app.route('/relatorios')
@login_required
def relatorios():
    # Filtros
    data_ini_str = request.args.get('data_ini', (date.today() - timedelta(days=30)).strftime('%Y-%m-%d'))
    data_fim_str = request.args.get('data_fim', date.today().strftime('%Y-%m-%d'))
    maquina_id = request.args.get('maquina_id', '')

    data_ini = datetime.strptime(data_ini_str, '%Y-%m-%d').date()
    data_fim = datetime.strptime(data_fim_str, '%Y-%m-%d').date()

    query = RegistroProducao.query.filter(
        RegistroProducao.data >= data_ini,
        RegistroProducao.data <= data_fim
    )
    if maquina_id:
        query = query.filter_by(maquina_id=maquina_id)

    registros = query.order_by(RegistroProducao.data.desc()).all()
    maquinas = Maquina.query.filter_by(ativa=True).all()

    # OEE por máquina
    oee_por_maquina = {}
    for r in registros:
        mid = r.maquina_id
        if mid not in oee_por_maquina:
            oee_por_maquina[mid] = {'nome': r.maquina.nome, 'oees': [], 'pecas': 0, 'refugo': 0}
        oee_por_maquina[mid]['oees'].append(r.oee)
        oee_por_maquina[mid]['pecas'] += r.pecas_boas
        oee_por_maquina[mid]['refugo'] += r.pecas_refugo

    resumo_maquinas = []
    for mid, dados in oee_por_maquina.items():
        media_oee = sum(dados['oees']) / len(dados['oees']) if dados['oees'] else 0
        resumo_maquinas.append({
            'nome': dados['nome'],
            'oee': round(media_oee, 1),
            'pecas': dados['pecas'],
            'refugo': dados['refugo']
        })
    resumo_maquinas.sort(key=lambda x: x['oee'], reverse=True)

    # OEE por dia para gráfico
    oee_por_dia = {}
    for r in registros:
        d = r.data.strftime('%d/%m')
        if d not in oee_por_dia:
            oee_por_dia[d] = []
        oee_por_dia[d].append(r.oee)
    oee_diario = [{'data': d, 'oee': round(sum(v)/len(v), 1)} for d, v in oee_por_dia.items()]
    oee_diario.sort(key=lambda x: x['data'])

    return render_template('relatorios.html',
        registros=registros,
        maquinas=maquinas,
        resumo_maquinas=resumo_maquinas,
        oee_diario=json.dumps(oee_diario),
        data_ini=data_ini_str,
        data_fim=data_fim_str,
        maquina_id_sel=maquina_id
    )


@app.route('/maquinas', methods=['GET', 'POST'])
@admin_required
def maquinas():
    if request.method == 'POST':
        acao = request.form.get('acao')
        if acao == 'criar':
            m = Maquina(
                nome=request.form.get('nome'),
                codigo=request.form.get('codigo'),
                setor=request.form.get('setor'),
                tempo_ciclo_ideal=float(request.form.get('tempo_ciclo_ideal', 60))
            )
            db.session.add(m)
            db.session.commit()
            flash('Máquina cadastrada!', 'success')
        elif acao == 'toggle':
            mid = request.form.get('id')
            m = Maquina.query.get(mid)
            if m:
                m.ativa = not m.ativa
                db.session.commit()
    maquinas_list = Maquina.query.order_by(Maquina.ativa.desc(), Maquina.nome).all()
    return render_template('maquinas.html', maquinas=maquinas_list)


@app.route('/usuarios', methods=['GET', 'POST'])
@admin_required
def usuarios():
    if request.method == 'POST':
        acao = request.form.get('acao')
        if acao == 'criar':
            u = Usuario(
                nome=request.form.get('nome'),
                email=request.form.get('email').lower(),
                perfil=request.form.get('perfil', 'operador')
            )
            u.set_senha(request.form.get('senha'))
            db.session.add(u)
            db.session.commit()
            flash('Usuário criado!', 'success')
        elif acao == 'toggle':
            uid = request.form.get('id')
            u = Usuario.query.get(uid)
            if u and u.id != session['usuario_id']:
                u.ativo = not u.ativo
                db.session.commit()
    usuarios_list = Usuario.query.order_by(Usuario.ativo.desc(), Usuario.nome).all()
    return render_template('usuarios.html', usuarios=usuarios_list)


@app.route('/api/exportar-csv')
@login_required
def exportar_csv():
    from flask import Response
    data_ini_str = request.args.get('data_ini', (date.today() - timedelta(days=30)).strftime('%Y-%m-%d'))
    data_fim_str = request.args.get('data_fim', date.today().strftime('%Y-%m-%d'))
    data_ini = datetime.strptime(data_ini_str, '%Y-%m-%d').date()
    data_fim = datetime.strptime(data_fim_str, '%Y-%m-%d').date()

    registros = RegistroProducao.query.filter(
        RegistroProducao.data >= data_ini,
        RegistroProducao.data <= data_fim
    ).all()

    linhas = ['Data,Turno,Máquina,Setor,Peças Produzidas,Peças Boas,Refugo,Tempo Parada (min),Disponibilidade (%),Performance (%),Qualidade (%),OEE (%)']
    for r in registros:
        linhas.append(f"{r.data},{r.turno},{r.maquina.nome},{r.maquina.setor or ''},"
                      f"{r.pecas_produzidas},{r.pecas_boas},{r.pecas_refugo},{r.tempo_parada_min:.1f},"
                      f"{r.disponibilidade:.1f},{r.performance:.1f},{r.qualidade:.1f},{r.oee:.1f}")

    csv_content = '\n'.join(linhas)
    return Response(
        csv_content,
        mimetype='text/csv',
        headers={'Content-Disposition': f'attachment; filename=oee_{data_ini_str}_{data_fim_str}.csv'}
    )


# ─── INIT DB ─────────────────────────────────────────────────────────────────

def init_db():
    with app.app_context():
        db.create_all()
        if not Usuario.query.filter_by(email='admin@fabrica.com').first():
            admin = Usuario(nome='Administrador', email='admin@fabrica.com', perfil='admin')
            admin.set_senha('admin123')
            db.session.add(admin)
            # Máquinas de exemplo
            m1 = Maquina(nome='Torno CNC 01', codigo='TCN-001', setor='Usinagem', tempo_ciclo_ideal=45)
            m2 = Maquina(nome='Prensa Hidráulica', codigo='PRS-001', setor='Prensagem', tempo_ciclo_ideal=30)
            m3 = Maquina(nome='Centro de Usinagem', codigo='CUS-001', setor='Usinagem', tempo_ciclo_ideal=120)
            db.session.add_all([m1, m2, m3])
            db.session.commit()
            print("✅ Banco criado. Login: admin@fabrica.com / admin123")

if __name__ == '__main__':
    init_db()
    app.run(debug=True, host='0.0.0.0', port=5000)
