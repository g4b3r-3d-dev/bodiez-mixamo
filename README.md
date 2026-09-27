# Bodiez Local — Blender + Mixamo

Aplicação web local para inspecionar e preparar personagens 3D usando o Blender instalado no computador como motor de processamento. O navegador nunca executa `bpy`: React/Three.js conversa com um backend FastAPI em `127.0.0.1`, e o backend executa apenas scripts internos fixos do projeto no Blender.

## Estado atual

- **Etapa 1 — Conexão com Blender:** configuração do executável, teste real via `bpy`, logs e progresso por WebSocket.
- **Etapa 2 — Importação e visualização:** FBX/GLB/GLTF, preservação do original, cópia de trabalho, inspeção de armature, hierarquia, pesos, materiais, shape keys e animações, além de GLB intermediário e visualizador Three.js.
- **Etapa 3 — Preparação da base corporal:** validação de malha já skinnada ao Mixamo ou adaptação assistida de uma base corporal externa, preservando shape keys/topologia quando possível, com transferência de pesos separada de retargeting e testes automáticos de ombros, cotovelos, quadris e joelhos.

A Etapa 4 ainda não foi implementada.

## Requisitos

Prioridade: Linux.

- Python 3.11+
- Node.js 20+
- npm
- Blender instalado localmente (o caminho pode ser configurado pela interface)

## Instalação

```bash
git clone https://github.com/g4b3r-3d-dev/bodiez-mixamo.git
cd bodiez-mixamo
./scripts/install.sh
```

## Inicialização

```bash
./scripts/dev.sh
```

Abra no navegador:

```text
http://127.0.0.1:5173
```

O backend fica restrito a:

```text
http://127.0.0.1:8000
```

## Como testar a Etapa 3

1. Na aba **Blender**, informe o caminho absoluto do executável, por exemplo `/usr/bin/blender`, salve e execute **Testar Blender**.
2. Na aba **Importar**, selecione um FBX, GLB ou GLTF. Para GLTF externo, selecione também `.bin` e texturas locais necessárias.
3. Confirme no painel de inspeção quais armatures, pesos, materiais, shape keys e animações foram realmente encontrados.
4. Abra **Preparar base** e escolha um fluxo:
   - **Malha já skinnada:** valida a malha já vinculada ao armature encontrado, a cobertura dos pesos e as deformações articulares.
   - **Adaptar base:** envie uma base FBX/GLB/GLTF/BLEND. O sistema preserva o original, cria cópia de trabalho, faz alinhamento global assistido e só transfere pesos quando existe uma malha de referência realmente ponderada no personagem importado.
5. Revise o relatório. A base só aparece como pronta quando não há bloqueadores e os testes simples de ombros, cotovelos, quadris e joelhos passam.
6. O resultado da preparação disponibiliza um `prepared.blend` e um GLB intermediário para visualização.

### Ajustes assistidos

No modo de adaptação estão disponíveis escala global, deslocamentos X/Y/Z e rotação Z. Esses parâmetros são intencionalmente limitados. Eles não substituem ajuste artístico de A-pose/T-pose, pintura de pesos ou correção anatômica quando os arquivos são incompatíveis.

## Regras importantes da Etapa 3

- **Transferência de pesos não é retargeting de animação.** Nenhum retargeting é executado nesta etapa.
- Um esqueleto Mixamo sozinho não fornece malha, pesos ou morphs. Se não houver uma malha de referência ponderada, a transferência automática é bloqueada.
- Se a base já estiver vinculada a outro armature, a troca automática é bloqueada para evitar destruir rig, drivers ou morphs.
- Shape keys são contabilizadas antes/depois e nenhum modificador destrutivo é aplicado pela preparação.
- Arquivos originais ficam intactos; o processamento ocorre em cópias de trabalho.
- Arquivos Bodiez proprietários serão inspecionados quando fornecidos. O projeto não presume nomes de controles, shape keys, drivers ou uma API do Bodiez.
- O serviço não recebe comandos shell nem scripts Python arbitrários da interface e usa `subprocess` sem `shell=True`.

## Testes

A suíte local acumulada das Etapas 1–3 passa com:

```bash
cd backend
PYTHONPATH=. pytest -q
```

Resultado validado durante a implementação:

```text
19 passed
```

Também foi validada a compilação sintática dos módulos Python e scripts Blender. O teste final de deformação via `bpy` precisa ser executado numa máquina com Blender instalado. O build Vite também deve ser confirmado localmente após `npm install`, pois o ambiente de desenvolvimento usado para esta implementação não tinha acesso para baixar as dependências npm.
