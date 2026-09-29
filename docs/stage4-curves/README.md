# Curvas femininas — Etapa 4

> O ajuste foi recalibrado para proporções mais naturais e validado no novo
> `models/femele.glb`. Veja a [validação em 360°](../femele-natural/README.md).
> As medições abaixo registram a versão inicial do controle.

Na etapa Corpo, clique em **Preparar controles** e ajuste **Curvas femininas**.
O slider varia de 0 a 100%; os atalhos Original, Suaves, Marcadas e Máximas
correspondem a 0, 35, 65 e 100%. O ajuste afina a cintura, amplia os quadris e
acentua a projeção dos glúteos. O volume dos seios continua independente.
O valor acompanha a aplicação automática, comparação antes/depois, presets JSON
e arquivo Blender personalizado. Original zera apenas este ajuste; Restaurar
zera todos os ajustes corporais. Preparações antigas precisam preparar os
controles novamente para gerar o novo morph.

O morph usa coordenadas anatômicas do rig e pesos do tronco/coxa, com influência
suave e localizada. Não move ossos nem altera a topologia. Cada revisão parte
da mesma base, evitando acúmulo. Se os pontos de referência do rig ou os pesos
necessários não forem encontrados, o controle fica indisponível. Roupas com
pesos compatíveis acompanham a deformação; o resultado depende da malha e dos
pesos da base e deve ser conferido nas poses que serão usadas.

## Validação em 28/09/2026

- Build TypeScript/Vite concluído; 68 testes Python passaram, incluindo Blender real.
- Teste de geometria cobre cintura, quadris, glúteos, simetria, mãos junto ao quadril,
  peito, joelhos, roupas, transforms do objeto, shape keys existentes e exportação GLB.
- API validada no modelo `femele-decimate-retextured-rename-parts.glb` em 35%, 100% e 0%,
  incluindo salvamento e leitura de preset. Intensidade de 35% correspondeu a 35%
  do deslocamento máximo de 100%.
- Restauração: nenhum vértice alterado acima de 1e-6; erro máximo de 2,84e-7 unidades.
- Renders dos GLBs inspecionados com a mesma câmera e escala: [frente](front.png) e
  [lado](side.png). [Medições completas](measurements.json).
- Não houve teste visual da interface: nenhum navegador estava disponível na sessão.

Para repetir a validação com o servidor local e o modelo preparado:

```bash
backend/.venv/bin/python scripts/validate_curves_api.py
```

Os GLBs e o relatório completo ficam em `.local-data/stage4-curves/`.
