# Etapa 4 — validação visual em 28/09/2026

> Relatório anterior ao controle de seios por ossos/marcadores. Consulte a [nova implementação e validação](../stage4-breast/README.md).

[Galeria de antes/depois](index.html)

Modelo real: `riged-decimate.fbx`, fornecido pelo usuário. SHA-256: `f0a5ba5d308883a65d8320a998d21673a87150c534e5ef84e7d530f4dba8b687`.

## Resultado

As imagens do preset anterior confirmaram uma diferença pouco perceptível. O controle de tronco usava apenas um osso da coluna, escolhido entre aliases, e o deslocamento dos morphs era fraco. A correção inclui todos os ossos Spine/Spine1/Spine2, combina os pesos regionais e aumenta a intensidade dos morphs assistidos. Baselines antigas são atualizadas ao aplicar morphs gerados; shapes artísticos existentes não são reescritos.

A interface agora aplica automaticamente após 750 ms sem ajustes, indica alterações pendentes, compara antes/depois com a câmera preservada, oferece vistas anatômicas e identifica o arquivo pelo nome. A aplicação manual continua disponível. A remoção explícita de uma fonte de morph passou a ser respeitada pelo backend. Os scripts de inicialização ficaram executáveis; encerrar o ambiente também encerra o processo Vite correto, liberando a porta.

## Evidências visuais inspecionadas

- [Preset anterior](01-preset-anterior.png): alteração quase imperceptível.
- [Encorpado corrigido](02-encorpado-corrigido.png): aumento visível de tronco, braços e pernas.
- [Altura e proporções](03-estrutura-corrigida.png): diferenças visíveis com a mesma escala de câmera.
- [Musculoso pela API](04-musculoso-api.png): GLB obtido pelo fluxo HTTP + WebSocket usado pela aplicação.

São renders de geometria real, com material neutro e câmera/luz/escala idênticas dentro de cada par. Não são imagens geradas por IA nem capturas da interface. Nenhuma sessão de navegador estava disponível para testar cliques ou inspecionar o layout final. A geometria do frontend foi validada separadamente com GLTFLoader, morph targets e skinning do Three.js instalado.

## Testes

- **49 testes Python passaram**, incluindo Blender real, animação/NLA, ossos conectados, morphs cobrindo toda a coluna, pesos misturados, restauração e remoção de binding.
- Build TypeScript/Vite aprovado; apenas aviso de bundle acima de 500 kB.
- Preparação e 13 aplicações pela API local: dois presets, restauração, estrutura combinada e nove controles individuais. Todas concluíram e retornaram GLB válido.
- Comparação das posições calculadas pelo Three.js em 62.027 vértices, considerando vértices duplicados na exportação. Alteração é contada acima de 1e-6 unidades da cena. Na restauração, o deslocamento máximo ficou abaixo de 1e-5, sem deformação acumulada.

| Aplicação | Vértices alterados | Deslocamento máximo (unidades da cena) |
|---|---:|---:|
| encorpado | 60325 | 0.02497776 |
| musculoso | 56299 | 0.01314619 |
| regular | 0 | 0.00000019 |
| estrutura | 62027 | 0.12492282 |
| control-height | 62027 | 0.05689787 |
| control-head_size | 2294 | 0.01706249 |
| control-shoulder_width | 9178 | 0.01262268 |
| control-hip_width | 46192 | 0.00568776 |
| control-arm_length | 9151 | 0.05278778 |
| control-leg_length | 46184 | 0.06689281 |
| control-arm_volume | 7172 | 0.01344127 |
| control-leg_volume | 42144 | 0.02007809 |
| control-torso_volume | 12167 | 0.02957893 |

[Dados das medições](api-measurements.json)

## Repetir

Com a aplicação rodando e uma preparação aprovada do modelo:

```bash
./scripts/dev.sh
# Em outro terminal:
backend/.venv/bin/python scripts/validate_stage4_api.py --all-controls
blender --background --factory-startup --disable-autoexec --python-exit-code 1 \
  --python scripts/render_body_comparison.py -- \
  --before .local-data/stage4-visual/api/before.glb \
  --after .local-data/stage4-visual/api/encorpado.glb \
  --output .local-data/stage4-visual/comparacao.png --label ENCORPADO --clay
PYTHONPATH=backend backend/.venv/bin/python -m pytest -q backend/tests
npm --prefix frontend run build
```

Os morphs assistidos mudam a silhueta; não esculpem definição muscular. O controle de seios continua indisponível neste FBX por não haver shape key correspondente. A inspeção visual cobre vista frontal dos casos acima; não equivale a uma avaliação artística de todas as poses, ângulos e animações. O FBX original foi preservado.
