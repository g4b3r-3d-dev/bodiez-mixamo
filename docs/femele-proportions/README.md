# Proporções naturais sempre ativas

Modelo de referência: `models/femele.glb`. Data: 29/09/2026.
SHA-256 original preservado: `7385af5a695eef0b9dcad97f0e692900b0d5823cca3e9a9f4da1231aed30fc4d`.

[Abrir comparações de corpo e seios em 360°](index.html).

## Comportamento

A personalização agora usa limites conservadores relativos à base original.
Eles preservam as características do personagem; não representam limites
anatômicos da população ou um tipo corporal ideal. As curvas continuam ajustáveis
até 100%, e os seios de −50% a +100% de intensidade de deformação.

| Controle | Intervalo relativo à base |
| --- | --- |
| Altura uniforme | 90–110% |
| Cabeça, largura dos ombros e quadris | 94–106% |
| Comprimento dos braços e pernas | 96–104% |
| Volume dos braços e pernas | −22% a +28% de intensidade |
| Volume do tronco | −20% a +25% de intensidade |

Cada aplicação parte da base limpa. O Blender avalia o resultado combinado,
inclusive morphs existentes selecionados pelo usuário. Mede compressão/expansão
de arestas, rotação das normais, deslocamento e triângulos degenerados em três
poses: referência, flexão de quadril/joelho e braços abaixados. Também verifica
novos cruzamentos dentro de cada malha na pose de referência.

Quando necessário, reduz os ajustes em conjunto e verifica novamente.
A altura uniforme é preservada. Depois tenta recuperar a intensidade solicitada
de curvas e seios, sem ultrapassar os mesmos critérios. Isso evita que uma
restrição nos ombros reduza desnecessariamente a silhueta e os seios.

Os valores efetivos voltam pela API, atualizam os controles e são exibidos na
prévia e nos arquivos exportados. A interface informa quais controles foram
moderados. Presets antigos dentro dos limites anteriormente aceitos são
adaptados ao perfil atual; valores fora dos limites absolutos e fora do
intervalo de uma fonte de morph continuam sendo rejeitados.

## Validação

- **71 testes passaram**, incluindo regressões com Blender real, limites de
  presets antigos, preservação de fontes, inversão de triângulos, cruzamento
  novo, contatos preexistentes, restauração e reaplicação estável.
- Build TypeScript/Vite concluído. Permanece o aviso de tamanho do bundle.
- 11 combinações reais pela API, mais reaplicação dos valores efetivos e
  salvamento/leitura de preset. Geometria GLB também avaliada no Three.js.
- Auditoria independente dos 11 arquivos Blender em três poses: 33 casos.
- 16 vistas do corpo e 16 do tórax: órbita de 30° em 30° e frente/costas
  inclinadas em ±20°. As imagens usam os arquivos GLB exportados; o recorte
  do tórax só existe nas cópias de renderização.
- Original preservado e restauração conferida na exportação.

Fatores de moderação sobre os valores solicitados (1 significa preservar a
intensidade solicitada). Consulte o JSON para cada valor efetivamente aplicado:

| Combinação | Ajustes gerais | Curvas/seios após recuperação |
| --- | ---: | ---: |
| maximos | 0.5 | 1 |
| minimos | 0.25 | 1 |
| curvas-com-seios | 1 | 1 |
| cintura-marcada | 0.125 | 1 |
| contrastes | 0.125 | 1 |
| regular | 1 | 1 |
| magro | 0.125 | 0.125 |
| musculoso | 0.25 | 0.25 |
| encorpado | 0.25 | 0.25 |
| preset-antigo | 0.5 | 1 |
| restaurado | 1 | 1 |

Nos 33 casos finais, as arestas ficaram entre **0,504× e 1,485×** o
comprimento original e a maior rotação de normal foi **37,02°**. Nenhum
triângulo novo ficou degenerado. A restauração no GLB teve erro máximo
de **3,63e-7** unidades da cena.

[Relatório API e valores](report.json) · [Auditoria das poses](pose-audit.json) ·
[Testes](tests.txt) · [Build](build.txt) · [Marcadores](markers.json).

## Alcance da proteção

Os critérios são geométricos: arestas entre 0,5× e 1,5× o comprimento original,
rotação de normal até 60° e deslocamento até 6% da maior dimensão da malha
(descontada a altura uniforme). Cruzamentos usam tolerância de 0,02% dessa
dimensão e desconsideram contatos, sobreposições e cruzamentos já presentes na
base. Colisões entre malhas distintas não são verificadas. As duas poses
adicionais verificam distorção; cruzamentos são verificados na pose de referência.

A auditoria inicial revelou dobras na região dos ombros em combinações que
pareciam estáveis em repouso; a proteção passou a incluir essas poses antes
de exportar. O teste sintético também exige rejeitar um cruzamento realmente
novo, sem confundi-lo com contatos já existentes.

A proteção prioriza uma aparência natural, mas não reconstrói a anatomia de uma
base estilizada nem corrige seus defeitos originais. Os ângulos são amostras
registradas, e as poses testadas não cobrem todas as animações possíveis.
A camada estrutural ainda precisa ser conciliada com as animações da Etapa 5.
A interface foi compilada; esta rodada não inclui inspeção visual em navegador.

## Reproduzir

```bash
backend/.venv/bin/python scripts/validate_natural_body_api.py \
  --prepared .local-data/femele-breast/final/prepared.json \
  --markers .local-data/femele-breast/final/markers.json \
  --output .local-data/femele-proportions
```

O script reutiliza a personalização do teste anterior disponível nesta
instalação. `scripts/audit_natural_body.py` recebe `--baseline`, `--variants`
e `--output` pelo Blender. `scripts/render_body_orbit.py` gera as vistas a
partir dos GLBs, com `--elevated` e, no tórax, `--focus-markers`.

Os arquivos completos `.blend` e `.glb` estão em `.local-data/femele-proportions/`.
