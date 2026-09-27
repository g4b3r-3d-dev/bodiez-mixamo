# Bodiez Local

Aplicação web **local** para preparar, personalizar, posar e animar personagens 3D usando o Blender instalado na máquina como motor de processamento. O navegador nunca executa `bpy`: o frontend React/TypeScript conversa com um backend FastAPI em `127.0.0.1`, e o backend executa somente scripts Python internos e fixos no Blender, sem `shell=True` e sem aceitar comandos/scripts arbitrários da interface.

## Estado do projeto

- **Etapa 1 — Conexão com Blender:** configuração do executável, teste real via `bpy`, logs/progresso por WebSocket.
- **Etapa 2 — Importação e visualização:** FBX/GLB/GLTF, original preservado, cópia de trabalho, inspeção de malhas/armatures/pesos/materiais/shape keys/animações e GLB intermediário para Three.js.
- **Etapa 3 — Preparação da base corporal:** validação de malha já vinculada ao Mixamo ou adaptação assistida de uma base FBX/GLB/GLTF/BLEND, preservação de topologia/shape keys, inspeção de drivers/rig, alinhamento global, transferência inicial de pesos quando existe uma malha Mixamo de referência e testes de deformação em ombros, cotovelos, quadris e joelhos.
- **Etapa 4 — Personalização corporal:** altura, cabeça, ombros, quadris e comprimentos por uma camada estrutural explícita do rig; volumes de braços/pernas/tronco por shape keys; morphs assistidos opcionais gerados a partir dos pesos quando faltam morphs artísticos; presets Magro/Regular/Musculoso/Encorpado, restauração e presets JSON locais.
- **Etapa 5 — Poses e animações:** seleção de ossos reais, rotações locais, restauração da referência corporal atual, salvar/carregar poses JSON, importação de animações FBX/GLB/GLTF, reprodução no Three.js e retargeting assistido com análise de nomes, hierarquia, rest pose, escala e root motion.

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

O backend fica em `http://127.0.0.1:8000`.

## Fluxo de teste das Etapas 3–5

1. Abra **Blender**, informe o executável e clique em **Testar Blender**.
2. Abra **Importar**, selecione um FBX/GLB/GLTF com personagem e aguarde a inspeção real.
3. Abra **Preparar base** e use **Malha já skinnada** ou **Adaptar base**.
4. Confirme o relatório de pesos e os testes de ombros, cotovelos, quadris e joelhos.
5. Se desejar alterar proporções, abra **Corpo · Etapa 4**, prepare os controles e aplique uma revisão corporal.
6. Abra **Poses/Animações · Etapa 5**.
7. Escolha uma base preparada da Etapa 3 ou uma revisão personalizada da Etapa 4 e clique em **Preparar Etapa 5**.
8. Em **Esqueleto**, selecione um osso real descoberto pelo Blender e ajuste rotações X/Y/Z. **Aplicar pose** gera uma revisão nova partindo da baseline; **Referência** volta à referência corporal atual sem apagar as proporções da Etapa 4.
9. Em **Poses**, salve/carregue poses locais ou baixe um JSON contendo a assinatura do esqueleto e as rotações.
10. Em **Animações Mixamo**, selecione exatamente um FBX/GLB/GLTF e suas dependências locais, se houver.
11. Escolha root motion **Preservar** ou **In-place**. No modo in-place o retarget remove X/Y do quadril e preserva o movimento vertical.
12. O Blender mede cobertura de mapeamento, coerência da hierarquia e diferença da rest pose. Quando os critérios são suficientes, a animação é amostrada e retargeteada sobre o corpo atual; quando não são, o sistema retorna os bloqueadores em vez de afirmar compatibilidade.
13. Para uma animação aprovada, use reprodução/pausa, repetição e velocidade no visualizador e baixe o `.blend` retargeteado para inspeção.

### Regras de confiabilidade implementadas

- Um esqueleto Mixamo sozinho **não** é tratado como fonte de pesos.
- Bases com outro armature conflitante não têm seu rig substituído automaticamente na Etapa 3.
- Shape keys não são aplicadas destrutivamente durante a preparação/personalização.
- A Etapa 5 preserva o arquivo de animação enviado em `original/` e trabalha numa cópia separada.
- Prefixos/namespaces como `mixamorig:` são normalizados para descoberta, mas nomes reais dos ossos continuam sendo usados na cena.
- O retargeting usa nomes normalizados + correspondência semântica, verifica a hierarquia e calcula a diferença de orientação local entre os ossos de referência.
- Rotações animadas são transferidas como deltas locais com correção de orientação da rest pose; translações de membros não são copiadas indiscriminadamente.
- A escala do root motion usa a relação corporal entre quadril e cabeça (com fallback pela extensão do armature).
- Proporções estruturais da Etapa 4 permanecem como baseline: o bake de animação preserva location/scale estruturais e acrescenta a rotação animada, em vez de sobrescrever a personalização.
- Se o mapeamento essencial, a cobertura do esqueleto, a hierarquia ou a orientação média forem insuficientes, o retargeting automático é bloqueado e marcado como intervenção necessária.
- Depois do bake, o Blender amostra a animação no corpo atual, verifica matrizes não finitas, extensão geométrica anormal e presença de canais nas principais articulações.
- Arquivos Bodiez proprietários continuam sendo tratados por inspeção; nomes de controles, shape keys, drivers ou APIs não são presumidos.

## Testes

Suíte completa local:

```bash
PYTHONPATH=backend pytest -q backend/tests
```

Na implementação da Etapa 5, **5 novos testes específicos passaram** para descoberta de fontes, preservação do `.blend` de origem, bloqueio de preparação não aprovada, validação/salvamento de poses e garantia de que revisões de pose partem sempre da mesma baseline limpa. A última validação acumulada anterior à Etapa 5 estava em 32 testes passando.

Também foi validada a sintaxe dos novos módulos Python e a transpilação sintática dos novos arquivos TSX. A validação final do retargeting/deformação depende do Blender real e deve ser feita na máquina local com personagens/animações reais; o build Vite completo depende das dependências npm instaladas pelo `./scripts/install.sh`.

## Dados locais

Por padrão:

- configurações: `~/.config/bodiez-local/settings.json`
- assets: `~/.local/share/bodiez-local/assets/`

Cada importação preserva o original e mantém cópias/saídas derivadas separadas. Preparações ficam em `assets/<asset-id>/preparations/<preparation-id>/`; personalizações ficam em `customizations/<customization-id>/`; sessões da Etapa 5 ficam em `assets/stage5/<session-id>/`, com baseline, poses e animações isoladas.
