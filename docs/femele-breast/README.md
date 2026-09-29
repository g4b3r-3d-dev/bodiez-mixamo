# femele.glb — validação dos seios em 360°

Data: 29/09/2026. Modelo: `models/femele.glb`.
SHA-256 preservado: `7385af5a695eef0b9dcad97f0e692900b0d5823cca3e9a9f4da1231aed30fc4d`.

**[Abrir a galeria de 16 vistas](index.html)**: original, redução −50%, aumento
+65% e aumento +100%. Os percentuais são valores do controle de deformação,
não medidas de variação do volume físico dos seios.

## Correção

O campo anterior empurrava também a superfície abaixo dos seios, formando um
ressalto e comprimindo excessivamente algumas arestas na transição para o tórax.
[Comparação anterior em vista oblíqua](previous-60.png).

O novo campo estima a região de ligação com o tórax atrás de cada marcador.
A influência diminui gradualmente até zero nessa região, e a projeção acompanha
a profundidade existente em vez de aplicar o mesmo avanço a toda a superfície.
A expansão lateral e vertical também foi moderada. Isso preserva melhor a base
do seio e evita comprimir o ápice em uma concavidade durante a redução.

O resultado mantém a assimetria e os detalhes da malha original. Nenhuma
topologia, peso ou osso foi alterado. O campo por marcadores é recalculado a cada
aplicação, portanto os presets existentes usam a correção ao serem reaplicados.
O controle por ossos explícitos não foi recalibrado nesta rodada: este modelo
não tem ossos de seios e usa marcadores de superfície.

## Cobertura

- Nove aplicações reais pela API: −50%, −25%, 0%, +35%, +65%, +75%, +100%;
  combinação com altura 105% e tronco +15%; combinação com curvas corporais 65%.
- Validação de marcadores inválidos, salvamento/leitura de preset, exportação
  de GLB e Blender, avaliação do skinning e morphs no Three.js.
- 16 vistas do tórax inspecionadas: 12 direções de 30° em 30° e frente/costas
  inclinadas em ±20°. Cada imagem compara quatro valores. Os cortes visíveis
  em braços, pescoço e abdômen são feitos apenas nas cópias de renderização.
- [Corpo completo com seios e curvas em 65%](combined-views/view-000-+00.png),
  também renderizado de lado, costas e em vista oblíqua.
- Auditoria de nove intensidades em três poses: repouso, flexão unilateral de
  quadril/joelho e rotação dos braços. Repetida com curvas corporais em 65%.
- **68 testes passaram**, incluindo Blender real. A regressão verifica
  restauração, simetria em uma base simétrica, preservação do ápice na redução,
  proteção do tórax atrás da região de ligação, roupas e exportação GLB.

## Resultados

Valores medidos em repouso, com aumento em +100%:

| Medição | Anterior | Revisado |
| --- | ---: | ---: |
| Maior deslocamento, unidades da cena | 0,036361 | 0,017002 |
| Razão mínima/máxima de comprimento das arestas | 0,148 / 2,189 | 0,546 / 1,411 |
| Razão mínima/máxima de área dos triângulos | 0,173 / 2,466 | 0,557 / 1,681 |
| Maior rotação da normal de um triângulo | 66,83° | 30,97° |

Na redução de −50%, a maior rotação de normal caiu de 37,19° para 11,94°.
Em todos os casos auditados, os vértices permaneceram finitos, sem novos
triângulos degenerados ou rotações de normal acima de 90° em relação ao mesmo
modelo/pose sem o ajuste de seios.

Nas sete aplicações isoladas verificadas no Three.js, nenhum vértice fora das
regiões marcadas moveu acima de 1e-5 unidades. Ambos os lados responderam na
direção esperada. Em +100%, a projeção máxima medida foi 0,01636 à esquerda e
0,01677 à direita; essa diferença acompanha a base e os pontos de superfície.
O teste sintético confirma simetria da deformação quando a base é simétrica.

Restaurar para 0% recuperou exatamente a malha avaliada no Blender. No GLB,
erro máximo de 3,63e-7 unidades, sem vértices deslocados acima de 1e-6.

Nenhum novo cruzamento de triângulos não adjacentes foi encontrado em repouso
em −50%, −25%, 0%, +35%, +65% e +100%, inclusive com curvas corporais em 65%.
Os 65 pares já presentes na base permanecem fora do tronco/quadril: 46 em
pernas/pés, 10 em braços/mãos e 9 em cabeça/pescoço. A classificação espacial é
aproximada e o teste exclui contatos e sobreposições coplanares.

[Relatório da API e localidade](report.json) · [Auditoria](audit.json) ·
[Auditoria com curvas](combined-audit.json) · [Marcadores utilizados](markers.json).

## Uso e limites

Em **Corpo**, escolha `femele.glb`, prepare os controles e use **Marcar posição
dos seios**. Posicione os dois marcadores na superfície, confirme e ajuste o
volume. 0% restaura o efeito deste controle. A área de influência utilizada
nesta validação corresponde a 7,5% da altura; coordenadas exatas estão no JSON.
O script de teste usa cliques reproduzíveis para este modelo, não detecção
anatômica automática de qualquer personagem.

O resultado depende dos marcadores, do raio e da malha. A validação visual
abrange as vistas registradas; não comprova todos os ângulos contínuos,
animações ou combinações de parâmetros. As poses adicionais foram auditadas
geometricamente. Não houve teste visual da interface em navegador nesta rodada.
O original conserva suas irregularidades e assimetrias; a correção suaviza o
ajuste, sem fazer uma reconstrução anatômica da superfície.

## Repetir

O modelo já está preparado no asset `b35a2a7b968443f8bc34812188380929` desta instalação.
Com o servidor local em execução:

```bash
backend/.venv/bin/python scripts/validate_breast_api.py \
  --asset-id b35a2a7b968443f8bc34812188380929 \
  --output .local-data/femele-breast/retest --full-range
blender --background --factory-startup --disable-autoexec --python-exit-code 1 \
  --python scripts/audit_body_curves.py -- \
  --blend .local-data/femele-breast/retest/maximo.blend \
  --output .local-data/femele-breast/retest/audit.json --control breast_size
blender --background --factory-startup --disable-autoexec --python-exit-code 1 \
  --python scripts/render_body_orbit.py -- \
  --models .local-data/femele-breast/retest/before.glb \
    .local-data/femele-breast/retest/reduzir.glb \
    .local-data/femele-breast/retest/aumento-moderado.glb \
    .local-data/femele-breast/retest/maximo.glb \
  --labels ORIGINAL 'REDUCAO -50%' 'AUMENTO +65%' 'AUMENTO +100%' \
  --output .local-data/femele-breast/retest/views \
  --focus-markers .local-data/femele-breast/retest/markers.json --elevated
```

Os GLBs completos e arquivos Blender desta execução estão em
`.local-data/femele-breast/final/`.
