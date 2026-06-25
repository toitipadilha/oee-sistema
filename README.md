# OEE Pro — Sistema de Eficiência Industrial
**Toiti Sistemas · MVP v1.0**

Sistema web para cálculo e monitoramento de OEE (Overall Equipment Effectiveness) em pequenas e médias fábricas.

---

## Funcionalidades

- ✅ Login com perfis: Admin / Gestor / Operador
- 📊 Dashboard com OEE em tempo real (Disponibilidade × Performance × Qualidade)
- ✅ Apontamento de produção por turno (celular, tablet ou computador)
- ⏸ Registro de paradas com categorias
- 📈 Relatórios com filtro por período e máquina
- ↓ Exportação CSV
- 🏭 Cadastro de máquinas com tempo de ciclo ideal
- 👤 Gestão de usuários

---

## Instalação no AWS Lightsail (Debian/Ubuntu)

```bash
# 1. Clonar / enviar os arquivos para o servidor
cd /home/admin/
mkdir oee_sistema && cd oee_sistema

# 2. Instalar dependências
pip3 install -r requirements.txt --break-system-packages

# 3. Rodar pela primeira vez (cria o banco e usuário admin)
python3 app.py

# Login padrão:
# E-mail: admin@fabrica.com
# Senha:  admin123
# ⚠ TROQUE A SENHA após o primeiro login!
```

---

## Produção com Gunicorn + Nginx

```bash
# Instalar gunicorn
pip3 install gunicorn --break-system-packages

# Rodar com gunicorn
gunicorn -w 2 -b 127.0.0.1:5000 app:app --daemon

# Configuração Nginx /etc/nginx/sites-available/oee
server {
    listen 80;
    server_name SEU_DOMINIO.com.br;

    location / {
        proxy_pass http://127.0.0.1:5000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
}
```

---

## Variáveis de Ambiente

```bash
export SECRET_KEY="troque-por-uma-chave-segura-aqui"
```

---

## Estrutura do Projeto

```
oee_system/
├── app.py              # Aplicação principal (Flask + SQLAlchemy)
├── requirements.txt    # Dependências Python
├── instance/
│   └── oee.db          # Banco SQLite (criado automaticamente)
└── templates/
    ├── base.html       # Layout base (nav + topbar)
    ├── login.html      # Tela de login
    ├── dashboard.html  # Dashboard principal
    ├── apontar.html    # Registro de produção
    ├── paradas.html    # Registro de paradas
    ├── relatorios.html # Relatórios + exportação
    ├── maquinas.html   # Cadastro de máquinas
    └── usuarios.html   # Gestão de usuários
```

---

## Fórmula OEE

```
OEE = Disponibilidade × Performance × Qualidade

Disponibilidade = (Tempo Total - Tempo Parado) / Tempo Total
Performance     = (Peças × Ciclo Ideal) / Tempo Operando
Qualidade       = Peças Boas / Peças Produzidas
```

Meta de referência: OEE ≥ 65% (indústria em geral)

---

## Portfólio / Comercialização

- **Portfólio Toiti Sistemas:** hospedar em subdomínio `oee.toitisistemas.com.br`
- **Demo para clientes:** criar usuário demo read-only
- **Implantação:** R$ 5.000 ~ 15.000
- **Mensalidade SaaS:** R$ 300 ~ 1.500/mês

---

*Desenvolvido por Toiti Sistemas — toitisistemas.com.br*
