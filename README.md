# Bodiez Local

Aplicação web **local** para preparar, personalizar, posar e animar personagens 3D usando o Blender instalado na máquina como motor de processamento. O navegador nunca executa `bpy`: o frontend React/TypeScript conversa com um backend FastAPI em `127.0.0.1`, e o backend executa somente scripts Python internos e fixos no Blender, sem `shell=True` e sem aceitar comandos/scripts arbitrários da interface.

## Estado do projeto

- **Etapa 1 — Conexão com Blender:** configuração do executável, teste real via `bpy`, logs/progresso por WebSocket.
- **Etapa 2 — Importação e visualização:** FBX/GLB/GLTF, original preservado, cópia de trabalho, inspeção de malhas/armatures/pesos/materiais/shape keys/animações e GLB intermediário para Three.js.
- **Etapa 3 — Preparação da base corporal:** validação de malha já vinculada ao Mixamo ou adaptação assistida de uma base FBX/GLB/GLTF/BLEND, preservação de topologia/shape keys, inspeção de drivers/rig, alinhamento global, transferência inicial de pesos quando existe uma malha Mixamo de referência e testes de deformação em ombros, cotovelos, quadris e joelhos.
- **Etapa 4 — Personalização corporal:** altura, cabeça, ombros, quadris e comprimentos por uma camada estrutural explícita do rig; volumes de braços/pernas/tronco por shape keys; morphs assistidos opcionais gerados a partir dos pesos quando faltam morphs artísticos; presets Magro/Regular/Musculoso/Encorpado, restauração e presets JSON locais.
- **Etapa 5 — Poses e animações:** seleção de ossos reais, rotações locais, restauração da referência corporal atual, salvar/carregar poses JSON, importação de animações FBX/GLB/GLTF, reprodução no Three.js e retargeting assistido com análise de nomes, hierarquia, rest pose, escala e root motion.
- **Etapa 6 — Atualização e experiência de uso:** morph targets equivalentes respondem diretamente no Three.js; mudanças estruturais são agrupadas com debounce antes de chamar o Blender; tarefas antigas são ignoradas por geração; desfazer/refazer, comparação antes/depois, progresso, erros e preservação de câmera/seleção durante atualizações.

> Transferência de pesos e retargeting de animação são operações diferentes. A Etapa 3 prepara skinning/deformação; a Etapa 5 trata animação sem transferir pesos.

## Requisitos

- Linux (prioridade do projeto; outros sistemas poderão ser ajustados depois)
- Python 3.11+
- Node.js 20+
- Blender instalado localmente

O caminho do Blender é configurável pela interface. Exemplos comuns:

```text
/usr/bin/blender
/opt/blender/blender
```

## Instalação

```bash
./scripts/install.sh
```

Ou manualmente:

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -r backend/requirements.txt
cd frontend
npm install
cd ..
```

## Inicialização

```bash
./scripts/dev.sh
```

Abra:

```text
http://127.0.0.1:5173
```

O backend fica em `http://127.0.0.1:8000` e o `dev.sh` usa `app.stage6_main:app`, que incorpora as rotas das Etapas 1–5 e acrescenta a Etapa 6.

## Fluxo de teste das Etapas 3–6

1. Abra **Blender**, informe o executável e clique em **Testar Blender**.
2. Abra **Importar**, selecione um FBX/GLB/GLTF com personagem e aguarde a inspeção real.
3. Abra **Preparar base** e use **Malha já skinnada** ou **Adaptar base**.
4. Confirme o relatório de pesos e os testes de ombros, cotovelos, quadris e joelhos.
5. Se desejar alterar proporções, abra **Corpo · Etapa 4**, prepare os controles e aplique uma revisão corporal.
6. Para poses/animações, abra **Poses/Animações · Etapa 5**, selecione uma fonte, prepare a sessão e teste poses ou retargeting Mixamo.
7. Para a experiência responsiva, abra **Experiência · Etapa 6** e escolha uma preparação aprovada.
8. Clique em **Preparar experiência**. O Blender prepara uma baseline e informa quais controles realmente existem.
9. Mova um slider de volume/silhueta que esteja ligado a um shape key: quando o GLB expõe o morph target equivalente, a alteração aparece imediatamente no Three.js sem iniciar outro processo do Blender.
10. Mova sliders estruturais como altura/ombros/comprimentos rapidamente: as mudanças são agrupadas e somente após 900 ms sem novas alterações uma sincronização Blender é criada.
11. Faça outra alteração estrutural enquanto uma sincronização anterior ainda está terminando. Cada solicitação recebe uma geração; a interface e o backend ignoram o resultado antigo quando existe uma geração mais nova.
12. Teste **Desfazer/Refazer** pelos botões ou `Ctrl/Cmd+Z` e `Ctrl/Cmd+Y` (`Ctrl/Cmd+Shift+Z` também refaz). Um arraste de slider entra no histórico como uma edição agrupada.
13. Use **Comparar antes/depois**. A câmera não é reenquadrada ao trocar a prévia e o controle selecionado continua selecionado.
14. Use **Aplicar definitivo** quando quiser uma revisão persistente. Essa revisão continua partindo da baseline limpa da Etapa 4, não de uma cadeia acumulada de prévias.

### Regras de confiabilidade implementadas

- Um esqueleto Mixamo sozinho **não** é tratado como fonte de pesos.
- Bases com outro armature conflitante não têm seu rig substituído automaticamente na Etapa 3.
- Shape keys não são aplicadas destrutivamente durante a preparação/personalização.
- Prefixos/namespaces como `mixamorig:` são normalizados para descoberta, mas nomes reais dos ossos continuam sendo usados na cena.
- O retargeting usa nomes normalizados + correspondência semântica, verifica a hierarquia e calcula a diferença de orientação local entre os ossos de referência.
- Proporções estruturais da Etapa 4 permanecem como baseline durante animação.
- A Etapa 6 não envia `bpy` ao navegador e não aceita scripts/comandos do frontend; continua reutilizando o script interno fixo `body_customize.py`.
- Morphs locais só são aplicados quando a fonte mapeada corresponde a um morph target realmente exposto no GLB; a interface mostra quantos alvos locais foram encontrados.
- Operações que dependem de rig/estrutura continuam usando o Blender como referência. O frontend apenas faz debounce de 900 ms e nunca tenta reproduzir essas operações estruturalmente no Three.js.
- Cada cliente da Etapa 6 recebe um token aleatório de 32 caracteres hexadecimais e cada atualização estrutural recebe uma geração crescente. O backend mantém a geração mais nova e não inicia Blender para uma geração que já chegou ultrapassada.
- Se uma tarefa que já estava rodando termina depois de uma geração nova, o resultado é marcado como antigo e não substitui a visualização atual.
- Prévia ao vivo e revisão definitiva são separadas. **Aplicar definitivo** reutiliza a baseline limpa e os valores atuais da personalização.
- Arquivos Bodiez proprietários continuam sendo tratados por inspeção; nomes de controles, shape keys, drivers ou APIs não são presumidos.

## Testes

Suíte completa no clone local:

```bash
PYTHONPATH=backend pytest -q backend/tests
```

Durante a implementação da Etapa 6 foram validados sintaticamente os novos módulos Python e arquivos TSX. Também foram executados **4 testes específicos da Etapa 6** em um harness local do serviço, cobrindo resolução de morphs no pedido, controle de geração, rejeição de token inválido e garantia de que uma geração já ultrapassada não inicia processo Blender.

O ambiente usado para desenvolver esta etapa não consegue clonar o GitHub por DNS nem contém o Blender, portanto a suíte acumulada completa e o processamento real `bpy` precisam ser executados no computador local. O build Vite completo depende das dependências instaladas por `./scripts/install.sh`.

## Dados locais

Por padrão:

- configurações: `~/.config/bodiez-local/settings.json`
- assets: `~/.local/share/bodiez-local/assets/`

Cada importação preserva o original e mantém cópias/saídas derivadas separadas. Preparações ficam em `assets/<asset-id>/preparations/<preparation-id>/`; personalizações ficam em `customizations/<customization-id>/`; sessões da Etapa 5 ficam em `assets/stage5/<session-id>/`. As prévias temporárias da Etapa 6 ficam em `customizations/<customization-id>/live/<client-token>/<generation>/` e as gerações antigas são limpas progressivamente.
