# Etapa 8 — Validação final

A Etapa 8 fecha o fluxo funcional sem criar uma nova forma de editar o personagem. Ela reabre um projeto salvo pela Etapa 7 no Blender, mede a cena real e, quando uma exportação é selecionada, reimporta os arquivos de intercâmbio para comparar o que sobreviveu.

## Fluxo coberto

1. **Importar/preparar:** a linhagem registrada no projeto comprova que a cena veio das etapas anteriores.
2. **Personalizar:** quando a fonte passou pela Etapa 4, `values` e `bindings` corporais precisam estar coerentes com as flags de editabilidade do manifesto.
3. **Posar:** quando existe pose na linhagem, os dados salvos precisam estar coerentes com o manifesto.
4. **Animar:** quando existe animação retargeteada, o projeto registra a animação e o relatório correspondente.
5. **Salvar:** `project.bodiez.json` e `source.blend` precisam existir no diretório próprio do projeto.
6. **Reabrir:** o Blender abre `source.blend` em background, sem executar scripts arbitrários vindos do projeto.
7. **Exportar:** uma exportação selecionada precisa pertencer ao mesmo projeto e os formatos solicitados são conferidos; GLB e FBX são reimportados quando existem.

## Critérios medidos

### Projeto e reabertura

- formato `bodiez-project`, versão 1;
- `source.blend` presente;
- `file_ref` relativo (`source.blend`), sem depender de caminho absoluto;
- coerência entre parâmetros corporais/poses/animação e as flags de editabilidade;
- exportação selecionada pertencente ao projeto correto.

### Escala e orientação

O Blender mede os limites mundiais XYZ e exige valores finitos e não nulos. A orientação recebe aviso quando a extensão vertical Z fica muito pequena em relação à maior extensão horizontal. Isso é um diagnóstico, não uma conversão automática de eixos.

### Deformação

O armature principal é descoberto pelos ossos realmente presentes, tolerando prefixos/namespaces como `mixamorig:`. Ombros, cotovelos, quadris e joelhos encontrados recebem uma pequena rotação diagnóstica de 12°. Vértices com peso relevante são amostrados no mesh avaliado e a validação exige movimento finito e mensurável.

A cena não é salva depois desses testes; as rotações diagnósticas são temporárias.

### GLB / FBX

Quando presentes, os arquivos são reimportados em uma cena limpa e comparados com `source.blend` quanto a:

- presença de malha;
- presença de rig quando a fonte possui armature;
- actions/animações quando a fonte as possui;
- morph/shape keys quando a fonte as possui;
- razão de altura entre a cena fonte e o arquivo reimportado.

A comparação de escala usa tolerância porque os formatos e importadores podem representar unidades de maneira diferente.

### PNG

O PNG gerado pela Etapa 7 é carregado no Blender e precisa possuir dimensões válidas e canal alpha.

## Veredito

- **Aprovado:** nenhuma falha nem aviso.
- **Aprovado com avisos:** não há bloqueadores, mas há itens que exigem revisão humana ou formatos opcionais não selecionados.
- **Bloqueado:** pelo menos uma verificação crítica falhou.

O relatório pode ser baixado como `bodiez-final-validation.json`.

## Limitações reais

- O teste de orientação assume que o personagem está normalmente em pé no eixo Z do Blender. Personagens deliberadamente deitados podem produzir aviso legítimo.
- A perturbação de 12° comprova que o skin responde de forma finita; ela não substitui inspeção artística de volume, interpenetração, candy-wrapper, colapso de ombros ou qualidade de pesos em poses extremas.
- Reimportar GLB/FBX confirma estrutura, escala aproximada e presença de recursos no importador do Blender. Isso não garante resultado idêntico em Unity, Unreal, Maya, 3ds Max ou outros consumidores.
- Drivers, constraints e modificadores proprietários do Blender não possuem equivalência editável garantida em GLB/FBX. O `.blend` continua sendo o formato autoritativo.
- Materiais complexos podem ser simplificados no intercâmbio mesmo quando a malha/rig passam na validação.
- A validação não presume nomes, drivers, shape keys ou APIs proprietárias do Bodiez. Recursos proprietários só podem ser garantidos depois de inspecionar arquivos originais reais.
- Um esqueleto Mixamo por si só não comprova pesos nem morphs. O teste final mede somente a cena que efetivamente foi preparada.
- A Etapa 8 não retargeteia novamente e não corrige automaticamente problemas encontrados; ela os registra para revisão.

## Execução local

```bash
git pull origin main
./scripts/install.sh
./scripts/dev.sh
```

Abra `http://127.0.0.1:5173`, entre em **Validação final · Etapa 8**, escolha um projeto e, preferencialmente, uma exportação que contenha BLEND + GLB + FBX + PNG.

Para executar somente os testes automatizados da Etapa 8:

```bash
PYTHONPATH=backend pytest -q backend/tests/test_stage8.py
```

A validação real de deformação e reimportação exige o Blender local configurado na Etapa 1.
