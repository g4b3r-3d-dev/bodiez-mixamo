# Modelo feminino — validação da Etapa 4

> Relatório anterior ao controle de seios por ossos/marcadores. Consulte a [nova implementação e validação](../stage4-breast/README.md).

Data: 28/09/2026. Modelo: `femele-decimate-retextured-rename-parts.glb`.
SHA-256 do original preservado: `fbb446f2b1b30275607e1b108acabcbb0a78f51b8b4ac4a77f294e1f0a38f2dd`.

## Resultado

Importação pela API local, preparação e **13 aplicações** concluídas: presets encorpado/musculoso, restauração, estrutura combinada e nove controles individuais. A geometria de cada GLB foi avaliada pelo GLTFLoader e pelo skinning/morphs do Three.js utilizado na interface.

O arquivo original contém nove malhas, um skin e 34 animações. Não contém morph targets originais. Os nove controles gerais estão habilitados; o controle específico de seios permanece indisponível por não existir shape key correspondente. O volume do tronco é uma deformação regional assistida, não um controle independente de seios.

## Defeito encontrado e corrigido

A primeira preparação foi bloqueada no cotovelo direito. O diagnóstico selecionava os primeiros 600 vértices do grupo; naquele trecho, a influência média era apenas 0,003908. Os vértices realmente influenciados apareciam depois na ordem da malha.

A amostragem passou a cobrir todo o grupo, ainda limitada a 600 vértices por malha. A influência média da amostra representativa foi 0,455797. O deslocamento médio medido passou de 0,0000698 para 0,0204781 unidades da cena. O limite de aprovação e os pesos originais não foram alterados. O teste de rotação também preserva o modo de rotação e restaura a matriz da pose mesmo em caso de erro.

A nova regressão reproduz o caso de pesos fracos no início da malha e fortes no final. Ela também confirma que desabilitar o modificador do armature continua causando reprovação. **50 testes Python passaram**, incluindo quatro testes com Blender real.

## Antes/depois

Renderizações dos GLBs produzidos pela API, inspecionadas com a mesma câmera, luz e escala dentro de cada comparação:

- [Encorpado, material neutro](01-encorpado.png)
- [Musculoso, materiais e texturas do arquivo](02-musculoso-textura.png)
- [Altura e proporções, material neutro](03-estrutura.png)

São renders de validação, não capturas da interface. A inspeção visual cobre estas vistas frontais; não comprova todas as poses e animações.

## Medições no Three.js

Vértices alterados: deslocamento maior que 1e-6 unidades da cena. O GLB pode duplicar vértices em costuras. A restauração admite erro numérico de até 1e-5.

| Aplicação | Vértices alterados | Deslocamento máximo |
|---|---:|---:|
| encorpado | 144244 | 0.02917909 |
| musculoso | 142505 | 0.01535741 |
| regular | 0 | 0.00000028 |
| estrutura | 161386 | 0.13691649 |
| control-height | 161386 | 0.10000823 |
| control-head_size | 21034 | 0.01792728 |
| control-shoulder_width | 75785 | 0.01155684 |
| control-hip_width | 50724 | 0.00689761 |
| control-arm_length | 75758 | 0.05025927 |
| control-leg_length | 50691 | 0.06876175 |
| control-arm_volume | 56457 | 0.01180902 |
| control-leg_volume | 48978 | 0.01952123 |
| control-torso_volume | 56056 | 0.03455419 |

[Dados completos das medições](measurements.json).

Para repetir, com a aplicação iniciada e o modelo já preparado:

```bash
backend/.venv/bin/python scripts/validate_stage4_api.py \
  --name femele-decimate-retextured-rename-parts.glb --all-controls \
  --output .local-data/stage4-female/api
blender --background --factory-startup --disable-autoexec --python-exit-code 1 \
  --python scripts/render_body_comparison.py -- \
  --before .local-data/stage4-female/api/before.glb \
  --after .local-data/stage4-female/api/encorpado.glb \
  --output .local-data/stage4-female/comparacao.png --label ENCORPADO --clay
```
