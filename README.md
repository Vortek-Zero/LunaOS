# 🌙 LunaOS

> Um sistema operacional moderno e eficiente desenvolvido em Python com interface web responsiva.

[![Python](https://img.shields.io/badge/Python-3.8+-blue?style=for-the-badge&logo=python)](https://www.python.org/)
[![HTML5](https://img.shields.io/badge/HTML5-E34F26?style=for-the-badge&logo=html5)](https://html.spec.whatwg.org/)
[![JavaScript](https://img.shields.io/badge/JavaScript-F7DF1E?style=for-the-badge&logo=javascript)](https://www.javascript.com/)
[![CSS3](https://img.shields.io/badge/CSS3-1572B6?style=for-the-badge&logo=css3)](https://www.w3.org/Style/CSS/)
[![License](https://img.shields.io/badge/License-MIT-green?style=for-the-badge)](LICENSE)

---

## 📋 Índice

- [Sobre](#sobre)
- [Características](#características)
- [Arquitetura](#arquitetura)
- [Requisitos](#requisitos)
- [Instalação](#instalação)
- [Como Usar](#como-usar)
- [Estrutura do Projeto](#estrutura-do-projeto)
- [Contribuindo](#contribuindo)
- [Licença](#licença)

---

## 🎯 Sobre

**LunaOS** é um projeto inovador de sistema operacional desenvolvido primariamente em **Python** com uma interface web moderna e intuitiva construída com **HTML5**, **CSS3** e **JavaScript**. O projeto combina eficiência de backend com uma experiência de usuário fluida no frontend.

Este sistema foi desenvolvido com foco em:
- ✨ Modularidade e escalabilidade
- 🔒 Segurança de dados
- 📱 Responsividade multiplataforma
- ⚡ Performance otimizada

---

## ✨ Características

### Backend (Python - 77.2%)
- **Gerenciamento de Processos**: Controle eficiente de aplicações em execução
- **Sistema de Arquivos**: Manipulação avançada de arquivos e diretórios
- **Gerenciamento de Memória**: Monitoramento e alocação inteligente de recursos
- **API RESTful**: Endpoints bem definidos para comunicação com frontend
- **Autenticação e Autorização**: Segurança em múltiplas camadas
- **Logging e Monitoramento**: Rastreamento detalhado de operações do sistema

### Frontend (HTML/CSS/JS - 22.3%)
- **Interface Responsiva**: Funciona perfeitamente em desktop, tablet e mobile
- **Dashboard Intuitivo**: Visualização clara dos recursos do sistema
- **Gerenciador de Tarefas**: Controle de aplicações em tempo real
- **Terminal Web**: Acesso via linha de comando integrado
- **Temas Customizáveis**: Suporte a múltiplos temas de cores
- **Notificações em Tempo Real**: Atualizações instantâneas do sistema

---

## 🏗️ Arquitetura

```
LunaOS
├── Backend (Python)
│   ├── Core System
│   │   ├── Kernel
│   │   ├── Process Manager
│   │   └── Memory Manager
│   ├── API Layer
│   │   ├── REST Endpoints
│   │   └── WebSocket Server
│   └── Utils
│       ├── Logger
│       ├── Validators
│       └── Helpers
├── Frontend (Web)
│   ├── HTML Templates
│   ├── CSS Styles
│   │   ├── Bootstrap/Components
│   │   └── Custom Themes
│   └── JavaScript
│       ├── API Client
│       ├── UI Components
│       └── Event Handlers
└── Configuration
    ├── Environment Variables
    ├── Settings
    └── Credentials
```

---

## 📦 Requisitos

### Sistema
- Python 3.8 ou superior
- Node.js 14+ (para ferramentas frontend opcionais)
- 4GB de RAM mínimo
- 2GB de espaço em disco

### Dependências Python
- Flask ou Django (para API web)
- SQLAlchemy (para ORM)
- psutil (para monitoramento de sistema)
- Requests (para requisições HTTP)
- Jinja2 (para templates)

### Dependências Frontend
- Bootstrap 5 (CSS framework)
- jQuery (manipulação DOM)
- Chart.js (gráficos)

---

## 🚀 Instalação

### 1. Clone o Repositório

```bash
git clone https://github.com/milogol2822/LunaOS.git
cd LunaOS
```

### 2. Crie um Ambiente Virtual

```bash
# No Linux/Mac
python3 -m venv venv
source venv/bin/activate

# No Windows
python -m venv venv
venv\Scripts\activate
```

### 3. Instale as Dependências

```bash
pip install -r requirements.txt
```

### 4. Configure o Ambiente

```bash
# Copie o arquivo de exemplo
cp .env.example .env

# Edite o arquivo .env com suas configurações
nano .env
```

### 5. Inicie o Servidor

```bash
python main.py
```

O sistema estará disponível em `http://localhost:5000`

---

## 💻 Como Usar

### Acesso Inicial

1. Abra seu navegador e acesse: `http://localhost:5000`
2. Faça login com suas credenciais padrão
3. Explore o dashboard principal

### Gerenciador de Tarefas

```bash
# Via API REST
curl -X GET http://localhost:5000/api/processes \
  -H "Authorization: Bearer YOUR_TOKEN"
```

### Terminal Web

1. Clique em "Terminal" no menu principal
2. Digite seus comandos normalmente
3. Os resultados aparecerão em tempo real

### Monitoramento de Recursos

- Visualize CPU, Memória e Disco em tempo real
- Configure alertas personalizados
- Exporte relatórios de uso

---

## 📁 Estrutura do Projeto

```
LunaOS/
├── app/
│   ├── __init__.py
│   ├── main.py                 # Ponto de entrada
│   ├── config.py               # Configurações
│   ├── models/                 # Modelos de dados
│   │   ├── user.py
│   │   ├── process.py
│   │   └── system.py
│   ├── routes/                 # Rotas/Endpoints
│   │   ├── api.py
│   │   ├── web.py
│   │   └── auth.py
│   ├── services/               # Lógica de negócio
│   │   ├── process_manager.py
│   │   ├── file_manager.py
│   │   └── auth_service.py
│   └── utils/                  # Utilitários
│       ├── logger.py
│       ├── validators.py
│       └── helpers.py
├── static/
│   ├── css/                    # Estilos
│   │   ├── bootstrap.min.css
│   │   ├── style.css
│   │   └── themes/
│   ├── js/                     # Scripts JavaScript
│   │   ├── app.js
│   │   ├── dashboard.js
│   │   └── terminal.js
│   └── images/                 # Imagens
├── templates/                  # Templates HTML
│   ├── base.html
│   ├── dashboard.html
│   ├── login.html
│   ├── terminal.html
│   └── settings.html
├── tests/                      # Testes
│   ├── test_api.py
│   ├── test_models.py
│   └── test_services.py
├── docs/                       # Documentação
│   ├── API.md
│   ├── INSTALLATION.md
│   └── ARCHITECTURE.md
├── requirements.txt            # Dependências Python
├── .env.example               # Variáveis de ambiente
├── .gitignore
├── LICENSE
└── README.md
```

---

## 🔌 API Reference

### Autenticação

```http
POST /api/auth/login
Content-Type: application/json

{
  "username": "user",
  "password": "password"
}

Response: 200 OK
{
  "token": "eyJ0eXAiOiJKV1QiLCJhbGc...",
  "user": { "id": 1, "username": "user" }
}
```

### Processos

```http
GET /api/processes
Authorization: Bearer <token>

Response: 200 OK
[
  {
    "pid": 1234,
    "name": "python",
    "cpu": 15.2,
    "memory": 124.5,
    "status": "running"
  }
]
```

### Sistema

```http
GET /api/system/info
Authorization: Bearer <token>

Response: 200 OK
{
  "hostname": "luna-device",
  "uptime": 2592000,
  "cpu_count": 4,
  "total_memory": 8589934592,
  "available_memory": 2147483648
}
```

Consulte a [Documentação da API](docs/API.md) para mais endpoints.

---

## 🧪 Testes

### Executar Testes

```bash
# Todos os testes
python -m pytest

# Com cobertura
python -m pytest --cov=app

# Teste específico
python -m pytest tests/test_api.py -v
```

---

## 🤝 Contribuindo

Contribuições são bem-vindas! Por favor, siga estes passos:

1. **Fork** o repositório
2. **Crie uma branch** para sua feature (`git checkout -b feature/AmazingFeature`)
3. **Commit** suas mudanças (`git commit -m 'Add some AmazingFeature'`)
4. **Push** para a branch (`git push origin feature/AmazingFeature`)
5. **Abra um Pull Request**

### Guia de Contribuição

- Siga o [PEP 8](https://www.python.org/dev/peps/pep-0008/) para código Python
- Mantenha a consistência com o estilo de código existente
- Escreva testes para novas funcionalidades
- Atualize a documentação conforme necessário

---

## 🐛 Reportar Bugs

Se encontrar um bug, por favor:

1. Verifique se o bug já foi reportado em [Issues](https://github.com/milogol2822/LunaOS/issues)
2. Se não, abra um novo issue com:
   - Descrição clara do problema
   - Passos para reproduzir
   - Comportamento esperado vs. atual
   - Screenshots (se aplicável)
   - Informações do ambiente (SO, versão Python, etc.)

---

## 📝 Roadmap

- [x] Sistema base e kernel
- [x] Interface web responsiva
- [x] API RESTful
- [ ] Suporte a plugins
- [ ] Dashboard customizável
- [ ] Sync em nuvem
- [ ] Aplicações nativas
- [ ] Sistema de permissões avançado

---

## 📞 Suporte

- 📧 Email: [seu-email@example.com]
- 💬 Discussões: [GitHub Discussions](https://github.com/milogol2822/LunaOS/discussions)
- 📚 Wiki: [Project Wiki](https://github.com/milogol2822/LunaOS/wiki)

---

## 📄 Licença

Este projeto está sob a licença **MIT**. Veja o arquivo [LICENSE](LICENSE) para mais detalhes.

```
MIT License

Copyright (c) 2026 milogol2822

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, and distribute the Software...
```

---

## 🙏 Agradecimentos

Agradecimentos especiais a:
- Comunidade Python
- Contribuidores do projeto
- Todos que reportam bugs e sugestões

---

<div align="center">

**Feito com ❤️ por [milogol2822](https://github.com/milogol2822)**

⭐ Se este projeto foi útil, considere deixar uma estrela! ⭐

</div>