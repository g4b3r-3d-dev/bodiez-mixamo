# Bodiez Local

Aplicação web **local** para preparar, personalizar, posar, animar, salvar e exportar personagens 3D usando o Blender instalado na máquina como motor de processamento. O navegador nunca executa `bpy`: o frontend React/TypeScript conversa com um backend FastAPI em `127.0.0.1`, e o backend executa somente scripts Python internos e fixos no Blender, sem `shell=True` e sem aceitar comandos/scripts arbitrários da interface.

## Estado do projeto

- **Etapa 1 — Conexão com Blender:** configuração do executável, teste real via `bpy`, logs/progresso por WebSocket.
- **Etapa 2 — Importação e visualização:** FBX/GLB/GLTF, original preservado, cópia de trabalho, inspeção de malhas/armatures/pesos/materiais/shape keys/animações e GLB intermediário para Three.js.
- **Etapa 3 — Preparação da base corporal:** validação de malha já vinculada ao Mixamo ou adaptação assistida de uma base FBX/GLB/GLTF/BLEND, preservação de topologia/shape keys, inspeção de drivers/rig, alinhamento global, transferência inicial de pesos quando existe uma malha Mixamo de referência e testes de deformação em ombros, cotovelos, quadris e joelhos.
- **Etapa 4 — Personalização corporal:** altura, cabeça, ombros, quadris e comprimentos por uma camada estrutural explícita do rig; volumes de braços/pernas/tronco por shape keys; morphs assistidos opcionais, presets, restauração e presets JSON locais.
- **Etapa 5 — Poses e animações:** seleção de ossos reais, rotações locais, restauração da referência corporal atual, salvar/carregar poses JSON, importação de animações FBX/GLB/GLTF, reprodução no Three.js e retargeting assistido com análise de nomes, hierarquia, rest pose, escala e root motion.
- **Etapa 6 — Atualização e experiência de uso:** morph targets equivalentes respondem diretamente no Three.js; mudanças estruturais são agrupadas com debounce antes de chamar o Blender; tarefas antigas são ignoradas por geração; desfazer/refazer, comparação antes/depois, progresso, erros e preservação de câmera/seleção durante atualizações.
- **Etapa 7 — Salvamento e exportação:** projeto local versionado com `source.blend`, parâmetros corporais/poses/animação quando disponíveis, exportação `.blend`, GLB, FBX e render PNG transparente, além de relatório de recursos que podem perder fidelidade fora do Blender.

> Transferência de pesos e retargeting de animação são operações diferentes. O `.blend` é o formato autoritativo/editável do projeto; GLB e FBX são formatos de intercâmbio e não preservam a semântica dos controles Bodiez.

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

O backend fica em `http://127.0.0.1:8000` e o `dev.sh` usa `app.stage7_main:app`, que incorpora as rotas das Etapas 1–6 e acrescenta a Etapa 7.

## Fluxo de teste das Etapas 3–7

1. Abra **Blender**, informe o executável e clique em **Testar Blender**.
2. Importe um FBX/GLB/GLTF e faça a inspeção real da Etapa 2.
3. Prepare a base corporal na Etapa 3 e confirme pesos/deformações.
4. Se necessário, personalize o corpo na Etapa 4 e aplique uma revisão definitiva.
5. Se necessário, crie uma pose ou retargeteie uma animação na Etapa 5.
6. Use a Etapa 6 para edição responsiva, comparação e uma revisão definitiva sem acumular prévias.
7. Abra **Exportação · Etapa 7**. A lista de fontes inclui bases preparadas, revisões corporais, revisões de pose e animações retargeteadas que realmente existem no armazenamento local.
8. Escolha a fonte final, dê um nome ao projeto e clique em **Salvar novo projeto**. O sistema cria `assets/projects/<project-id>/source.blend` e `project.bodiez.json`.
9. O manifesto usa `format: "bodiez-project"` e `format_version: 1`, guarda uma referência relativa a `source.blend` e inclui os valores/bindings corporais, biblioteca/pose e dados da animação quando esses recursos existem na linhagem selecionada.
10. Projetos salvos aparecem novamente na própria Etapa 7 e podem ser carregados sem depender de um caminho absoluto para o `.blend` de origem.
11. Escolha as saídas desejadas:
    - **BLEND editável:** formato autoritativo. O Blender tenta empacotar imagens externas no arquivo e mantém rig, modifiers, shape keys, actions e demais dados nativos sempre que possível.
    - **GLB:** saída de intercâmbio com skins/rig, materiais, animações e morph targets compatíveis. A semântica dos sliders/presets Bodiez não é transportada.
    - **FBX:** saída de intercâmbio com rig/animações e blend shapes em modo best-effort; a fidelidade depende do software de destino.
    - **PNG:** render RGBA com fundo transparente em 512, 1024 ou 2048 px.
12. Clique em **Exportar no Blender**. O relatório lista quantidade de malhas, armatures, shape keys, actions e avisos de portabilidade.
13. Se GLB tiver sido exportado, a própria tela abre o arquivo no visualizador Three.js para uma conferência rápida da saída.

### Projeto editável x saída assada/de intercâmbio

O arquivo `project.bodiez.json` preserva a intenção editável do projeto: versão do formato, linhagem da fonte, referências de arquivo e parâmetros/poses/animação disponíveis. O `source.blend` preserva a cena autoritativa usada naquele ponto.

GLB e FBX representam o **estado atual da cena** para interoperabilidade. Eles podem carregar recursos técnicos como skin, actions e morph targets, mas não carregam a API/semântica dos controles Bodiez, nomes de presets ou lógica de drivers como um sistema editável equivalente ao Blender. Por isso a interface não anuncia GLB/FBX como substitutos do projeto editável.

### Avisos de portabilidade

Antes de exportar, o script interno do Blender inspeciona a cena e avisa quando encontra, entre outros casos:

- imagens externas ausentes;
- drivers do Blender;
- constraints;
- modificadores diferentes de Armature;
- materiais com árvores de nós mais complexas que um conjunto PBR básico;
- shape keys ao exportar FBX, cuja interpretação varia entre aplicações.

O sistema não remove silenciosamente esses recursos do projeto `.blend`. Os avisos se referem à portabilidade para GLB/FBX.

### Regras de confiabilidade implementadas

- Um esqueleto Mixamo sozinho **não** é tratado como fonte de pesos.
- Bases com outro armature conflitante não têm seu rig substituído automaticamente na Etapa 3.
- Shape keys não são aplicadas destrutivamente durante a preparação/personalização.
- Prefixos/namespaces como `mixamorig:` são normalizados para descoberta, mas nomes reais dos ossos continuam sendo usados na cena.
- Proporções estruturais da Etapa 4 permanecem como baseline durante animação.
- A Etapa 6 mantém Blender como fonte autoritativa para alterações de rig e descarta resultados ultrapassados por geração.
- A Etapa 7 só aceita identificadores hexadecimais internos e formatos de exportação permitidos; o frontend não escolhe caminhos arbitrários no sistema de arquivos.
- O projeto salvo recebe uma cópia própria de `source.blend`; o arquivo de origem selecionado não é sobrescrito.
- Exportações ficam em diretórios identificados por UUID sob o projeto. Downloads só resolvem nomes pré-definidos para BLEND, GLB, FBX, PNG e relatório.
- O script de exportação é interno e fixo. Nenhum código Python ou comando shell é aceito da interface.
- Arquivos Bodiez proprietários continuam sendo tratados por inspeção; nomes de controles, shape keys, drivers ou APIs não são presumidos.

## Testes

Suíte completa no clone local:

```bash
PYTHONPATH=backend pytest -q backend/tests
```

Durante a implementação da Etapa 7 foram executados **5 testes específicos**, cobrindo descoberta de fontes das Etapas 3–5, preservação/cópia do `.blend`, gravação de parâmetros corporais no manifesto, captura de pose/animação da Etapa 5, validação de formatos/resoluções e confinamento de IDs/caminhos. Resultado local da Etapa 7:

```text
5 passed
```

Também foram validados com `py_compile` os novos módulos Python e o script `bpy`, e os novos TSX passaram na transpilação sintática do TypeScript.

O ambiente usado para desenvolver esta etapa continua sem resolução DNS para `github.com` no container e não contém Blender. Por isso não foi possível executar novamente a suíte acumulada inteira a partir de um clone limpo nem realizar uma exportação real com `bpy` aqui. O teste final deve ser executado no computador local com Blender e dependências npm instaladas por `./scripts/install.sh`.

## Dados locais

Por padrão:

- configurações: `~/.config/bodiez-local/settings.json`
- assets: `~/.local/share/bodiez-local/assets/`
- projetos: `~/.local/share/bodiez-local/assets/projects/<project-id>/`

Cada projeto da Etapa 7 contém pelo menos:

```text
project.bodiez.json
source.blend
exports/<export-id>/
```

Preparações continuam em `assets/<asset-id>/preparations/<preparation-id>/`; personalizações em `customizations/<customization-id>/`; sessões da Etapa 5 em `assets/stage5/<session-id>/`; e prévias temporárias da Etapa 6 em `customizations/<customization-id>/live/<client-token>/<generation>/`.
