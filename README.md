# Bodiez Local

Aplicação web **local** para preparar e personalizar personagens 3D usando o Blender instalado na máquina como motor de processamento. O navegador nunca executa `bpy`: o frontend React/TypeScript conversa com um backend FastAPI em `127.0.0.1`, e o backend executa somente scripts Python internos e fixos no Blender, sem `shell=True` e sem aceitar comandos/scripts arbitrários da interface.

## Estado do projeto

- **Etapa 1 — Conexão com Blender:** configuração do executável, teste real via `bpy`, logs/progresso por WebSocket.
- **Etapa 2 — Importação e visualização:** FBX/GLB/GLTF, original preservado, cópia de trabalho, inspeção de malhas/armatures/pesos/materiais/shape keys/animações e GLB intermediário para Three.js.
- **Etapa 3 — Preparação da base corporal:** validação de malha já vinculada ao Mixamo ou adaptação assistida de uma base FBX/GLB/GLTF/BLEND, preservação de topologia/shape keys, inspeção de drivers/rig, alinhamento global, transferência inicial de pesos quando existe uma malha Mixamo de referência e testes de deformação em ombros, cotovelos, quadris e joelhos.

> Transferência de pesos e retargeting de animação são operações diferentes. A Etapa 3 só prepara skinning/deformação; retargeting será tratado na Etapa 5.

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

## Teste da Etapa 3

1. Abra **Blender**, informe o executável e clique em **Testar Blender**.
2. Abra **Importar**, selecione um FBX/GLB/GLTF com personagem e aguarde a inspeção real.
3. Abra **Preparar base**.
4. Escolha um dos fluxos:
   - **Usar malha vinculada:** valida o skinning já presente sem transferir pesos.
   - **Adaptar outra base:** selecione uma base FBX/GLB/GLTF/BLEND; o Blender inspeciona objetos, shape keys, drivers e rig antes de qualquer vinculação.
5. No fluxo de adaptação, ajuste escala/offset/rotação global somente se necessário.
6. Execute a preparação. O painel informa bloqueadores, avisos, cobertura de pesos e os testes reais de deformação de ombros/cotovelos/quadris/joelhos.
7. O `.blend` preparado pode ser baixado para revisão manual.

### Regras de confiabilidade implementadas

- Um esqueleto Mixamo sozinho **não** é tratado como fonte de pesos. A transferência automática só é tentada quando há malha de referência realmente vinculada ao armature e com pesos suficientes.
- Se a base já possui outro armature/modificador conflitante, a troca automática de rig é bloqueada para evitar quebrar morphs, drivers ou deformações existentes.
- Shape keys não são aplicadas nem destruídas; a transferência de pesos altera grupos de vértices e adiciona o modificador Armature sem aplicar modificadores destrutivos.
- Bases `.blend` são carregadas por append de datablocks no script interno; os drivers encontrados são inspecionados e preservados quando possível, mas não são reinterpretados como uma API do Bodiez.
- O alinhamento automático atual é global por altura/centro. Diferenças locais entre A-pose/T-pose, anatomia e proporções são explicitamente marcadas como revisão assistida.
- A transferência automática usa pesos da malha Mixamo de referência pelo vértice espacial mais próximo. É uma preparação inicial e exige revisão visual; não é anunciada como skinning universal.

## Testes

```bash
PYTHONPATH=backend pytest -q backend/tests
```

Estado atual: **19 testes automatizados** para API, segurança, preservação de arquivos, orquestração Blender simulada e preparação corporal.

O teste final de deformação com `bpy` precisa ser executado com o Blender real instalado na máquina, porque o ambiente de desenvolvimento automatizado deste repositório não contém o Blender.

## Dados locais

Por padrão:

- configurações: `~/.config/bodiez-local/settings.json`
- assets: `~/.local/share/bodiez-local/assets/`

Cada importação preserva o original e mantém cópias/saídas derivadas separadas. Preparações ficam em `assets/<asset-id>/preparations/<preparation-id>/`.
