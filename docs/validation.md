# Validação — 2026-09-27

## Resultados

- `PYTHONPATH=backend backend/.venv/bin/python -m pytest -q backend/tests`: **38 passed**, um aviso de depreciação em Starlette/AnyIO.
- `cd frontend && npm run build`: TypeScript e build Vite concluídos. Aviso de bundle JavaScript acima de 500 kB (964,18 kB; gzip 255,44 kB).
- `bash -n scripts/dev.sh scripts/install.sh`: aprovado.
- Compilação sintática de `backend/app` e `backend/blender_scripts`: aprovada.
- Aplicação `app.stage7_main:app` via FastAPI TestClient: `/api/health`, `/api/settings` e `/openapi.json` retornaram HTTP 200.
- Blender 4.0.2 real: script de detecção executado com sucesso.
- Cena sintética padrão do Blender: exportação pelos scripts do projeto para BLEND, GLB e FBX; arquivos produzidos e não vazios. GLB reimportado pelo script de inspeção, com relatório JSON e GLB de prévia produzidos. Dados temporários removidos após o teste.

## Correções

- Consulta de influência por associação aos grupos existentes, evitando `Vertex not in group`.
- Teste de regressão em Blender real para grupos esparsos, grupo ausente, peso abaixo do limite e limite de 600 amostras. Esse teste é ignorado explicitamente quando Blender não está instalado.
- Dois testes assíncronos passaram a usar `asyncio.run`, como os demais testes do projeto, sem exigir plugin adicional.
- Tipos Vite para importações CSS; cleanup React retornando void; descarte de materiais do SkeletonHelper aceitando material único ou lista.

## Limites

A maior parte da suíte testa serviços e APIs com dados sintéticos ou Blender simulado. A exportação real acima usa uma cena simples e não comprova preservação de rig, morphs e animações de personagens complexos. Não foram validados visualmente o navegador, o render PNG, nem o fluxo completo de preparação, personalização e retargeting com personagem real. Os avisos de addons locais emitidos pelo Blender não impediram os testes.


## Correção da Etapa 4 com o FBX real

Modelo: `riged-decimate.fbx`, em `modelos-3d/tripo art 3d/createds/game/men-base-limpo/`.
SHA-256: `f0a5ba5d308883a65d8320a998d21673a87150c534e5ef84e7d530f4dba8b687`.

A reprodução mostrou que a action importada sobrescrevia os valores dos ossos durante a avaliação do Blender. Por exemplo, cabeça solicitada em 115% voltava a 100% ao reabrir o resultado. A exportação GLB também usava a pose de repouso, e os braços conectados ignoravam a translação aplicada pelo controle de largura. O visualizador reenquadrava a câmera a cada atualização, ocultando mudanças de altura.

Correções:

- A cópia corporal suspende a action/NLA; as actions ficam preservadas nos datablocks e o arquivo original não é alterado.
- A prévia corporal exporta o estado atual, sem reprodução de animações, usando `export_current_frame=True` e `export_rest_position_armature=False`. Parâmetros documentados na [API oficial do Blender](https://docs.blender.org/api/main/bpy.ops.export_scene.html#bpy.ops.export_scene.gltf).
- Larguras usam a direção entre os ossos esquerdo/direito, convertida para o espaço local de cada osso. Quando necessário, a revisão desmarca a conexão dos ossos, mantendo pais e matrizes de repouso; os nomes ficam registrados em `bodiez_width_offset_bones`. A baseline e o FBX de origem permanecem intactos.
- A Etapa 4 conserva a câmera entre aplicações e mostra erros de carregamento da prévia.

Validação posterior: **47 testes passaram**; build TypeScript/Vite aprovado. A nova regressão inclui action e NLA, ossos conectados, preservação da personalização após trocar de frame/reabrir o BLEND, reimportação do GLB e restauração sem deformação acumulada.

No FBX real, os nove controles habilitados foram aplicados individualmente a uma baseline limpa. Cada controle deslocou vértices; as respectivas prévias GLB foram reimportadas e comparadas à geometria avaliada no Blender. Valores abaixo em unidades da cena:

| Controle | Deslocamento máximo | Erro máximo da prévia¹ |
|---|---:|---:|
| height | 0.0568978 | 0.0000004 |
| head_size | 0.0170625 | 0.0000012 |
| shoulder_width | 0.0126227 | 0.0001051 |
| hip_width | 0.0056878 | 0.0000012 |
| arm_length | 0.0527877 | 0.0000043 |
| leg_length | 0.0668927 | 0.0000017 |
| arm_volume | 0.0028950 | 0.0000005 |
| leg_volume | 0.0043245 | 0.0000005 |
| torso_volume | 0.0061768 | 0.0000005 |

¹ Distância ao vértice mais próximo da geometria avaliada, pois a exportação pode duplicar vértices nas costuras. Não é uma avaliação artística da deformação. Os controles de volume são morphs assistidos sutis, sem definição muscular esculpida; seios permanecem indisponíveis porque o modelo não tem shape key correspondente.

Também foi exercitado o servidor local em execução: POST de preparação dos controles, acompanhamento pelo WebSocket, POST de aplicação e GET da prévia. Todas as tarefas terminaram com sucesso; a prévia GLB retornou 5.894.468 bytes. A cópia utilizada pela API tem o mesmo SHA-256 do arquivo indicado pelo usuário. Nenhuma sessão de navegador estava disponível para inspeção visual da interface.


## Nova validação visual — 28/09/2026

A verificação posterior identificou morphs pouco perceptíveis e cobertura incompleta do tronco. Veja [comparações, correções e 49 testes](stage4-visual/README.md). Esta validação inclui renders de antes/depois e medições da geometria com Three.js.


## Modelo feminino — 28/09/2026

[Relatório feminino e imagens](stage4-female/README.md): importação, correção de falso bloqueio na preparação, 13 aplicações via API e verificação da geometria no Three.js. Suíte atual: **50 testes passaram**.
