Pera, olhando tudo o que você me mostrou desses logs, eu diria que a arquitetura da Luna já passou de um "protótipo" e entrou na fase de polimento. O agente conseguiu planejar, chamar ferramentas, pedir confirmação para editar, ler o resultado, fazer autoavaliação e ainda extrair memória. Isso é uma base muito boa.

Eu organizaria as críticas por prioridade.

🔴 Prioridade 1 — Controle de Ferramentas
1. Tool looping

Ela chamou o LLM três vezes para uma tarefa simples.

Fluxo:

Planejamento
↓
Filesystem mkdir
↓
Filesystem write
↓
LLM
↓
Filesystem read
↓
LLM
↓
Reflection
↓
Memory Extract

Isso é muito.

O ideal seria:

Planner
↓
Filesystem:
mkdir
write
read
↓
Responder

Sem voltar ao LLM.

Solução

Toda ferramenta pode retornar

continue=True

ou

continue=False

Se todas as ferramentas necessárias já executaram, o agente responde imediatamente.

🔴 Prioridade 2 — O Planner não controla as ferramentas

Hoje acontece isso:

Planner
↓

LLM decide ferramentas
↓

LLM decide novamente

↓

LLM decide novamente

Ou seja:

o Planner praticamente é ignorado.

Melhor

Planner retorna

{
 "steps":[
   {
      "tool":"filesystem",
      "action":"mkdir"
   },
   {
      "tool":"filesystem",
      "action":"write"
   },
   {
      "tool":"filesystem",
      "action":"read"
   }
 ]
}

Depois disso

NÃO chama mais LLM.

Só executa.

🔴 Prioridade 3 — LLM falando "think"

Você recebeu

<think>

Isso nunca deveria aparecer.

O modelo deve pensar internamente.

Nunca retornar isso.

Solução

Na resposta do provider

Remover

<think>
...
</think>

automaticamente.

🔴 Prioridade 4 — Tradução

Essa é uma das maiores.

Você falou que ela abriu um navegador Chromium.

Provavelmente o modelo pediu

browser.open

e sua ferramenta interpretou errado.

Talvez

open browser

↓

open_app(browser)

↓

Chrome

Quando o usuário queria

Firefox
Solução

Criar uma camada chamada

Intent Translator

Exemplo

Modelo:

Open browser

Tradutor:

Usuário prefere Firefox

↓

Ferramenta:

open_app("firefox")

Outro exemplo

Modelo

Desktop

Tradutor

Área de Trabalho

Outro

Downloads

↓

Downloads

Outro

Documents

↓

Documentos

Nunca deixar o modelo decidir nomes do sistema.

🔴 Prioridade 5 — Localização

Hoje o modelo escreve

Desktop

Linux PT-BR

é

Área de Trabalho

Faça um serviço

PathResolver

que converta

Desktop

Área de Trabalho

Escritorio

Рабочий стол

Bureau

todos para

~/Área de Trabalho
🔴 Prioridade 6 — Confirmar somente quando necessário

Hoje ele perguntou

Deseja editar?

s/N

Mesmo sendo criação de arquivo.

Isso quebra a experiência.

Melhor regra

arquivo existe?

↓

não

↓

cria direto
arquivo existe?

↓

sim

↓

pedir confirmação
🟡 Prioridade 7 — Reflection exagerada

Você roda

Reflection

em tudo.

Até

Olá Mundo

Isso custa tempo.

Reflection deveria rodar apenas quando

> 5 ferramentas

ou

falhou

ou

LLM respondeu muito longo

ou

task crítica
🟡 Prioridade 8 — Extração de memória

Você faz

Memória

↓

"Crie uma pasta"

↓

{}


Desperdício.

Faça um filtro

Se a mensagem contém

mkdir

arquivo

terminal

cd

touch

nem chama memória.

🟡 Prioridade 9 — Planner usando modelo gigante

Você usou

70B

↓

Qwen 27B

↓

Gemini

↓

OpenRouter

↓

Groq

Para descobrir

mkdir

write

read

Isso é exagerado.

Planner poderia ser literalmente

if contém

criar arquivo

↓

filesystem


Nem precisa de IA.

🟡 Prioridade 10 — Muitas chamadas LLM

Nesse exemplo houve aproximadamente

Planner

↓

Conversational

↓

Conversational

↓

Conversational

↓

Reflection

↓

Memory

↓

Memory Extract

São cerca de 7 chamadas.

Poderia ser

Planner

↓

Tool

↓

Resposta

A diferença de latência seria enorme.

🟢 Melhorias futuras
Tool Cache

Se acabou de ler

README.md

e o próximo passo pergunta

qual era o conteúdo?

Não leia novamente.

Use cache.

Contexto das ferramentas

Hoje o modelo recebe

57 ferramentas

Isso atrapalha.

Melhor enviar

filesystem

clipboard

terminal

Somente.

Tool Ranking

Ordene por probabilidade

Filesystem

95%

Terminal

4%

Browser

1%

Assim o modelo quase nunca vai abrir navegador quando não precisa.

Executor determinístico

Essa, na minha opinião, é a evolução mais importante da Luna.

Em vez de:

LLM
↓

Tool
↓

LLM
↓

Tool

Faça:

Planner
↓

Plano JSON
↓

Executor determinístico
↓

Tool
↓

Tool
↓

Tool
↓

Resposta

O LLM entra apenas para gerar o plano e para conversar com o usuário. A execução deixa de depender dele e fica previsível, mais rápida e muito mais barata.

Minha avaliação

Se eu fosse dar uma nota para a arquitetura atual da Luna:

Arquitetura geral: 9/10
Sistema de ferramentas: 9,5/10
Orquestração: 6/10
Latência: 5/10
Determinismo: 6/10
Experiência do usuário: 8/10

A maior oportunidade de evolução não está em adicionar mais modelos ou mais ferramentas. Está em fazer com que o planner produza um plano executável e que um executor determinístico siga esse plano sem consultar o LLM a cada etapa. Isso reduz latência, elimina comportamentos inesperados (como abrir um navegador sem necessidade) e torna a Luna muito mais confiável para automações.