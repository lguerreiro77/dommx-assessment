
# Manual de Preenchimento do Assessment DOMMx

## Objetivo
Este manual explica como preencher corretamente um assessment DOMMx utilizando a interface de avaliação implementada em `renderer_assessment.py`.

Ele apresenta:
- passo a passo do processo
- funcionamento da interface
- regras do assessment
- dicas práticas
- erros comuns a evitar

O objetivo é garantir que o assessment represente **a maturidade real de governança**.

---

# 1. Estrutura do Assessment

O assessment DOMMx é organizado na seguinte hierarquia:

**Domínio → Pergunta → Action → Procedimento**

Cada **domínio** representa uma capacidade de governança.

Exemplos:

- Data Governance
- Data Architecture
- Data Security
- Data Operations
- Data Quality

Cada domínio contém várias **perguntas**, que disparam **ações** baseadas nas notas de maturidade selecionadas.
Essas ações podem disparar vários **procedimentos**.

---

# 2. Iniciando um Assessment

Passo a passo:

1. Cadastrar-se no sistema
2. Dar consentimento eletrônico para utilização de dados pessoais e gravação da focus session
3. Fazer login no sistema
4. Selecionar o projeto
5. Ler atentamente a documentação de apoio
6. Abrir a tela de Assessment
7. Iniciar as respostas do assessment

O sistema carregará as perguntas definidas por domínio para o projeto selecionado.

---

# 3. Layout da Interface

A tela de assessment normalmente contém:

- título do domínio
- descrição do domínio
- texto da pergunta
- objetivo da pergunta
- seletor de resposta
- botões para selecionar o índice de maturidade
- dependendo da escolha, uma **ação é disparada**
- essa ação pode disparar vários **procedimentos**
- descrição dos procedimentos, notas e comentários
- fontes de pesquisa
- campo de comentários
- botões de navegação e salvamento
- painel de mensagens
- painel de navegação
- botão para submeter o assessment

A interface é interativa e salva respostas progressivamente.

---

# 4. Como Responder uma Pergunta

Para cada pergunta:

1. Ler cuidadosamente a pergunta e todas as informações apresentadas
2. Avaliar as práticas atuais da organização
3. Selecionar o nível de maturidade correspondente
4. Inserir comentários quando necessário
5. Consultar o material referencial disponível na tela de boas‑vindas

Comentários ajudam a explicar o contexto ou apresentar evidências.

---

# 5. Níveis de Maturidade

Interpretação típica:

Nível 0 – Prática inexistente  
Nível 1 – Prática inicial ou ad‑hoc  
Nível 2 – Prática definida  
Nível 3 – Prática gerenciada e controlada  
Nível 4 – Prática otimizada  

Sempre responder com base **na realidade atual**.

---

# 6. Evidências e Comentários

Sempre que possível incluir evidências no campo de comentário.

Exemplos:

- políticas
- comitês de governança
- papéis de stewardship
- controles de qualidade
- monitoramento de dados

Isso ajuda na interpretação dos resultados.

---

# 7. Navegação

É possível navegar entre perguntas usando:

Próxima pergunta  
Pergunta anterior

As respostas permanecem salvas durante a navegação, mas podem ser perdidas se o usuário sair da tela sem salvar.

---

# 8. Salvamento das Respostas

As respostas são salvas automaticamente após a seleção enquanto o usuário permanece na tela de assessment.

Se a tela for fechada sem salvar, as respostas podem ser perdidas.

Perguntas obrigatórias devem ser respondidas antes da submissão.

---

# 9. Conclusão do Domínio

Quando todas as perguntas forem respondidas o sistema calcula:

- score de maturidade do domínio
- recomendações de melhoria
- relatório com radar de maturidade e análise por domínio

---

# 10. Geração de Resultados

Após concluir o assessment o sistema permite gerar e fazer download do relatório.

Após submissão o assessment não poderá ser respondido novamente.

---

# 11. Dicas

✔ responder com evidências  
✔ manter consistência entre domínios  
✔ evitar respostas aspiracionais  
✔ documentar justificativas nos comentários  

---

# 12. Erros Comuns

❌ respostas inconsistentes  
❌ ausência de comentários  
❌ superestimar maturidade  

O objetivo é diagnóstico realista.

---

# 13. Filosofia

O assessment DOMMx foi criado para identificar lacunas de governança e priorizar melhorias.
