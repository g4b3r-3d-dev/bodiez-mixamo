# femele.glb — curvas naturais e revisão em 360°

Modelo: `models/femele.glb`. Validação em 28/09/2026.
SHA-256 original preservado: `7385af5a695eef0b9dcad97f0e692900b0d5823cca3e9a9f4da1231aed30fc4d`.

**[Abrir a galeria de 16 vistas](index.html)** — original, curvas revisadas em 65% e 100%.
As imagens também estão disponíveis diretamente: [frente](views/view-000-+00.png),
[perfil](views/view-090-+00.png), [costas](views/view-180-+00.png),
[outro perfil](views/view-270-+00.png).

## O que mudou

A versão anterior exagerava a projeção posterior em 100%, com transição curta
entre glúteos e coxas. A versão 2 reduz a compressão da cintura e a expansão dos
quadris/glúteos, prolongando a influência gradualmente até a parte superior das
coxas. O objetivo é preservar mais a silhueta da base em toda a faixa do slider.
O volume dos seios continua independente.

O morph é não destrutivo e mantém topologia, pesos e rig. Customizações antigas
com o morph assistido anterior são atualizadas quando aplicadas novamente; há
teste de regressão para essa atualização. Nenhuma escultura foi gravada no
arquivo original.

Para usar no aplicativo: **Corpo → Atualizar → femele.glb → Preparar controles**.
65% é a variante intermediária mostrada na galeria; 0% restaura o efeito deste
controle. Os GLBs e arquivos Blender testados estão em
`.local-data/femele-natural/final/` (`marcadas` = 65%; `maximas` = 100%).

## Cobertura

- Importação e preparação pelas APIs reais, incluindo testes de ombros,
  cotovelos, quadris e joelhos. A malha corporal possui 18.863 vértices skinnados;
  100% têm pesos. Rig Mixamo com 65 ossos.
- Aplicação/exportação via API em 35%, 65%, 100% e restauração; preset salvo e lido.
- GLBs avaliados no Three.js com o mesmo loader, morphs e skinning do visualizador.
- Inspeção visual de 16 imagens, cada uma com original/65%/100%: 12 direções
  horizontais de 30° em 30° e frente/costas com inclinação de ±20°.
- Auditoria em 0%, 25%, 35%, 50%, 65%, 75% e 100%, em repouso e em duas poses
  adicionais: flexão unilateral de quadril/joelho e rotação dos braços.
- **68 testes Python passaram**, incluindo Blender real e atualização dos morphs antigos.

## Resultados geométricos

Comparação do morph antigo e do revisado, ambos em 100%, na pose de repouso:

| Medição | Anterior | Revisado |
| --- | ---: | ---: |
| Maior deslocamento, unidades da cena | 0,034558 | 0,016232 |
| Razão mínima/máxima do comprimento das arestas | 0,764 / 1,422 | 0,896 / 1,196 |
| Razão mínima/máxima da área dos triângulos | 0,751 / 1,748 | 0,883 / 1,290 |
| Maior rotação da normal de um triângulo | 28,38° | 13,37° |
| Novos triângulos degenerados | 0 | 0 |

No revisado, todos os vértices ficaram finitos e nenhuma normal girou mais de
90° em qualquer intensidade/pose auditada. A restauração foi exata na malha
avaliada pelo Blender; no GLB reexportado, erro máximo de 3,63e-7 unidades,
sem vértices deslocados acima de 1e-6. A intensidade de 35% produziu 35% do
deslocamento máximo de 100%.

O teste de cruzamento de triângulos não adjacentes não encontrou **novos** pares
nas verificações em repouso em 0%, 35%, 65% e 100%. A própria base já contém
65 pares detectados: 46 em pernas/pés, 10 em braços/mãos e 9 em cabeça/pescoço.
Nenhum desses pares está na região tronco/quadril. A classificação das regiões
é espacial, aproximada, e o teste exclui contato e sobreposição coplanar.

[Auditoria detalhada](audit.json) · [Medições e origem](measurements.json).

## Limites da validação

“Natural” descreve a avaliação visual da silhueta, não uma medida anatômica
universal. A base conserva suas assimetrias e detalhes de superfície. As vistas
amostram uma volta completa; não representam todos os ângulos contínuos nem
todas as animações e combinações de sliders. As duas poses adicionais foram
auditadas geometricamente. Os renders documentam a pose de referência.
Esta rodada não valida visualmente os controles da interface em navegador.

## Repetir

Com o servidor local iniciado:

```bash
backend/.venv/bin/python scripts/validate_curves_api.py \
  --model models/femele.glb --output .local-data/femele-natural/retest
blender --background --factory-startup --disable-autoexec --python-exit-code 1 \
  --python scripts/audit_body_curves.py -- \
  --blend .local-data/femele-natural/retest/maximas.blend \
  --output .local-data/femele-natural/retest/audit.json
blender --background --factory-startup --disable-autoexec --python-exit-code 1 \
  --python scripts/render_body_orbit.py -- \
  --models .local-data/femele-natural/retest/before.glb \
    .local-data/femele-natural/retest/marcadas.glb \
    .local-data/femele-natural/retest/maximas.glb \
  --labels ORIGINAL 'CURVAS 65%' 'CURVAS 100%' \
  --output .local-data/femele-natural/retest/views --elevated
```
